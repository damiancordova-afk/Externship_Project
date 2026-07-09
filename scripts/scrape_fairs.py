#!/usr/bin/env python3
"""
Scheduled career-fair scraper — live per-college updates.

For every college already in career_fairs.json, fetches that college's public
career-center page(s), extracts upcoming fair dates, and merges anything new
back into career_fairs.json. career_fairs.json is the single source of truth;
the directory (campus-recruiting-directory.html) is regenerated from it by
build_directory.py, so this script only touches the JSON.

Design notes / honest limits
----------------------------
* Merge is ADDITIVE and SAFE: existing rows are never deleted. New rows are
  appended only when (college, date) is not already present, so a bad scrape can
  add noise but can't wipe curated data — review the diff the Action commits.
* Only UPCOMING fairs (date >= today) are added; the feed is forward-looking.
* The default extractor is GENERIC: it looks for date strings that appear near
  career-fair keywords, and skips obviously niche fairs (nursing, accounting,
  MBA-only, etc.) to match the directory's general + tech/STEM scope. It will
  still miss JavaScript-rendered pages (many Handshake / Symplicity calendars)
  and won't always produce clean fair *names*. For good results, add a
  site-specific function to EXTRACTORS below.
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

TODAY = dt.date.today()
# Only accept plausible dates: last year through two years out. Anything else is
# almost certainly a stray date on the page (footer copyright, unrelated event).
MIN_DATE = TODAY - dt.timedelta(days=365)
MAX_DATE = TODAY + dt.timedelta(days=730)

KEYWORDS = re.compile(
    r"career fair|career expo|job fair|internship fair|job & internship|"
    r"recruit|talent connect|industrial roundtable|career night|career day|"
    r"hiring expo|engineering expo|tech fair|stem",
    re.I,
)

# Skip obviously niche fairs so the feed stays scoped to general + tech/STEM,
# matching the curated directory. A block matching any of these is dropped.
NEGATIVE = re.compile(
    r"\b(nursing|accounting|cpa|mba|business school|law school|pre-?law|"
    r"education|teacher|educator|hospitality|supply chain|doctoral|postdoc|"
    r"graduate school fair|health(care)? professions|pharmacy|dental|nurse)\b",
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
        if NEGATIVE.search(block):     # niche fair — out of scope
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
# (Sources that merely serve a login-gated Symplicity/Handshake calendar don't
# need to be listed — the generic extractor just finds no dates and moves on.)
MANUAL_COLLEGES = {
    "University of Michigan",   # career-center site behind a WAF (403 to bots)
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
    today_iso = TODAY.isoformat()
    for row in scraped:
        if row["date"] < today_iso:      # only ever add upcoming fairs
            continue
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


def prune_past(fairs: list[dict]) -> tuple[list[dict], int]:
    """Drop fairs that have already happened; the feed is forward-looking."""
    today_iso = TODAY.isoformat()
    kept = [f for f in fairs if f.get("date", "") >= today_iso]
    return kept, len(fairs) - len(kept)


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
    merged, pruned = prune_past(merged)

    print(f"\n{len(added)} new fair(s) discovered:")
    for f in added:
        print(f"  + {f['college']} {f['date']} — {f['name']}")
    if pruned:
        print(f"{pruned} past fair(s) pruned from the feed.")

    if args.dry_run:
        print("\n(--dry-run) no files written.")
        return 0

    if not added and not pruned:
        print("\nNothing new; file unchanged.")
        return 0

    data["last_scraped"] = TODAY.isoformat()
    write_json(data, merged)
    print(f"\nWrote {JSON_PATH.name} "
          f"({len(added)} added, {pruned} pruned, {len(merged)} total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
