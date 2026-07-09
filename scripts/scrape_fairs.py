#!/usr/bin/env python3
"""
Scheduled career-fair scraper.

Fetches each college's public career-center page(s), extracts fair dates, and
merges anything new into career_fairs.json. Also regenerates the FAIRS_FALLBACK
block embedded in campus-recruiting-directory.html so the file:// fallback stays
in sync.

Design notes / honest limits
----------------------------
* Merge is ADDITIVE and SAFE: existing rows are never deleted (past fairs are
  kept as history). New rows are appended only when (college, date) is not
  already present. This means a bad scrape can add noise but can't wipe curated
  data — review the diff the GitHub Action commits.
* The default extractor is GENERIC: it looks for date strings that appear near
  career-fair keywords. It is deliberately conservative but will still miss
  JavaScript-rendered pages (many Handshake-backed calendars) and won't produce
  great fair *names*. For good results, add a site-specific function to
  EXTRACTORS below.
* Auto-added rows are tagged {"auto": true, "scraped_at": "<date>"} so you can
  tell them apart from curated rows and prune them if needed.

Usage
-----
    python scripts/scrape_fairs.py            # scrape + write
    python scripts/scrape_fairs.py --dry-run  # scrape, print what WOULD change
    python scripts/scrape_fairs.py --no-net   # skip network (merge/write path only)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JSON_PATH = ROOT / "career_fairs.json"
HTML_PATH = ROOT / "campus-recruiting-directory.html"

TODAY = dt.date.today()
# Only accept plausible dates: last year through two years out. Anything else is
# almost certainly a stray date on the page (footer copyright, unrelated event).
MIN_DATE = TODAY - dt.timedelta(days=365)
MAX_DATE = TODAY + dt.timedelta(days=730)

KEYWORDS = re.compile(
    r"career fair|career expo|job fair|internship fair|job & internship|"
    r"recruit|talent connect|industrial roundtable|career night|career day",
    re.I,
)

USER_AGENT = "ValonCampusRecruitingBot/1.0 (+career-fair schedule sync)"

MONTHS = {
    m.lower(): i
    for i, m in enumerate(
        ["January", "February", "March", "April", "May", "June", "July",
         "August", "September", "October", "November", "December"], start=1)
}
MONTHS.update({m[:3].lower(): i for m, i in list(MONTHS.items())})


# ----------------------------------------------------------------------------
# Date parsing
# ----------------------------------------------------------------------------
def _mk(y: int, m: int, d: int) -> str | None:
    try:
        date = dt.date(y, m, d)
    except ValueError:
        return None
    if MIN_DATE <= date <= MAX_DATE:
        return date.isoformat()
    return None


def find_dates(text: str) -> list[str]:
    """Return ISO date strings found in free text, filtered to a sane window."""
    out: list[str] = []

    # "September 25, 2026" / "Sep 25 2026"
    for m in re.finditer(
        r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", text):
        mon = MONTHS.get(m.group(1).lower())
        if mon:
            iso = _mk(int(m.group(3)), mon, int(m.group(2)))
            if iso:
                out.append(iso)

    # ISO "2026-09-25"
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
        iso = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if iso:
            out.append(iso)

    # "9/25/2026" or "09/25/26"
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b", text):
        y = int(m.group(3))
        y += 2000 if y < 100 else 0
        iso = _mk(y, int(m.group(1)), int(m.group(2)))
        if iso:
            out.append(iso)

    return out


# ----------------------------------------------------------------------------
# Extractors
# ----------------------------------------------------------------------------
def generic_extractor(html: str, college: str, url: str) -> list[dict]:
    """
    Conservative default: split the page into blocks, and for any block that
    mentions a career-fair keyword AND contains a date, emit a row. Fair name is
    a best-effort trim of the block text.
    """
    try:
        from bs4 import BeautifulSoup  # type: ignore
    except ImportError:
        print("  ! beautifulsoup4 not installed; skipping generic parse", file=sys.stderr)
        return []

    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()

    rows: list[dict] = []
    seen: set[str] = set()
    # Candidate blocks: list items, table rows, headings, paragraphs, cards.
    for el in soup.find_all(["li", "tr", "article", "section", "h2", "h3", "p", "div"]):
        block = " ".join(el.get_text(" ", strip=True).split())
        if not block or len(block) > 400:
            continue
        if not KEYWORDS.search(block):
            continue
        dates = find_dates(block)
        if not dates:
            continue
        # Name: text up to the first date-ish token, trimmed.
        name = re.split(r"\b[A-Za-z]{3,9}\.?\s+\d{1,2}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}",
                        block)[0].strip(" -–—:·|")
        name = (name[:80] or "Career fair").strip()
        for iso in dates:
            if iso in seen:
                continue
            seen.add(iso)
            rows.append({
                "college": college,
                "name": name or "Career fair",
                "date": iso,
                "location": "",
                "source": url,
            })
    return rows


# Site-specific extractors go here, keyed by college. Signature matches
# generic_extractor(html, college, url) -> list[dict]. Fill these in as pages
# prove too dynamic/irregular for the generic pass.
EXTRACTORS: dict[str, callable] = {
    # "MIT": mit_extractor,
}

# Schools the scraper cannot reach — their fair dates live behind a login
# (Handshake / 12twenty) or a bot wall, and Valon has no API access. These are
# maintained by hand: add/update curated rows for them in career_fairs.json.
# The scraper skips them so it never wastes requests or writes junk here.
MANUAL_COLLEGES = {
    "UC Berkeley",    # dates in Handshake (school login)
    "Arizona State",  # dates in 12twenty (school login)
    "Northeastern",   # dates in Handshake (school login)
    "Michigan",       # career-center site behind a WAF (returns 403 to bots)
}


# ----------------------------------------------------------------------------
# Fetch + orchestrate
# ----------------------------------------------------------------------------
def fetch(url: str, timeout: int = 20) -> str | None:
    try:
        import requests  # type: ignore
    except ImportError:
        print("  ! requests not installed; cannot fetch", file=sys.stderr)
        return None
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout)
        r.raise_for_status()
        return r.text
    except Exception as e:  # noqa: BLE001 — one bad site shouldn't kill the run
        print(f"  ! fetch failed for {url}: {e}", file=sys.stderr)
        return None


def sources_from(fairs: list[dict]) -> dict[str, list[str]]:
    """Group the distinct source URLs we already know about, per college."""
    by: dict[str, list[str]] = {}
    for f in fairs:
        by.setdefault(f["college"], [])
        if f.get("source") and f["source"] not in by[f["college"]]:
            by[f["college"]].append(f["source"])
    return by


def scrape(fairs: list[dict], use_net: bool) -> list[dict]:
    if not use_net:
        print("(--no-net) skipping fetch; nothing new scraped")
        return []
    found: list[dict] = []
    for college, urls in sources_from(fairs).items():
        if college in MANUAL_COLLEGES:
            print(f"· {college}: manual-entry school — skipping")
            continue
        extractor = EXTRACTORS.get(college, generic_extractor)
        for url in urls:
            print(f"· {college}: {url}")
            html = fetch(url)
            rows = extractor(html, college, url) if html else []
            print(f"    {len(rows)} candidate row(s)")
            found.extend(rows)
    return found


def merge(existing: list[dict], scraped: list[dict]) -> tuple[list[dict], list[dict]]:
    """Add scraped rows whose (college, date) isn't already present. Returns
    (merged_list, newly_added)."""
    have = {(f["college"], f["date"]) for f in existing}
    added: list[dict] = []
    stamp = TODAY.isoformat()
    for row in scraped:
        key = (row["college"], row["date"])
        if key in have:
            continue
        have.add(key)
        row = {**row, "auto": True, "scraped_at": stamp}
        added.append(row)
    merged = existing + added
    merged.sort(key=lambda f: (f["college"], f["date"]))
    return merged, added


# ----------------------------------------------------------------------------
# Writers
# ----------------------------------------------------------------------------
def write_json(data: dict, fairs: list[dict]) -> None:
    data["fairs"] = fairs
    JSON_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                         encoding="utf-8")


def write_fallback(fairs: list[dict]) -> bool:
    """Regenerate the FAIRS_FALLBACK array between markers in the HTML.
    Returns True if the file changed."""
    html = HTML_PATH.read_text(encoding="utf-8")
    start = "/* FAIRS_FALLBACK_START */"
    end = "/* FAIRS_FALLBACK_END */"
    if start not in html or end not in html:
        print("  ! FAIRS_FALLBACK markers not found; skipping HTML sync", file=sys.stderr)
        return False

    lines = ["    const FAIRS_FALLBACK = ["]
    for f in fairs:
        parts = [
            f'college: {json.dumps(f["college"], ensure_ascii=False)}',
            f'name: {json.dumps(f["name"], ensure_ascii=False)}',
            f'date: {json.dumps(f["date"])}',
            f'location: {json.dumps(f.get("location", ""), ensure_ascii=False)}',
            f'source: {json.dumps(f.get("source", ""), ensure_ascii=False)}',
        ]
        lines.append("      { " + ", ".join(parts) + " },")
    lines.append("    ];")
    block = f"{start}\n" + "\n".join(lines) + f"\n    {end}"

    new_html = re.sub(re.escape(start) + r".*?" + re.escape(end), block, html,
                      flags=re.S)
    if new_html != html:
        HTML_PATH.write_text(new_html, encoding="utf-8")
        return True
    return False


# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="scrape + report, but don't write files")
    ap.add_argument("--no-net", action="store_true",
                    help="skip network fetches (exercise merge/write path only)")
    args = ap.parse_args()

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    existing = data.get("fairs", [])
    print(f"Loaded {len(existing)} existing fairs from {JSON_PATH.name}")

    scraped = scrape(existing, use_net=not args.no_net)
    merged, added = merge(existing, scraped)

    print(f"\n{len(added)} new fair(s) discovered:")
    for f in added:
        print(f"  + {f['college']} {f['date']} — {f['name']}")

    if args.dry_run:
        print("\n(--dry-run) no files written.")
        return 0

    if not added:
        print("\nNothing new; files unchanged.")
        return 0

    data["last_scraped"] = TODAY.isoformat()
    write_json(data, merged)
    changed = write_fallback(merged)
    print(f"\nWrote {JSON_PATH.name}"
          + (f" and updated fallback in {HTML_PATH.name}" if changed else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
