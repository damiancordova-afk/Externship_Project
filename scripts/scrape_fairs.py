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
SOURCES_PATH = ROOT / "fair_sources.json"          # curated, reviewed source URLs
PENDING_PATH = ROOT / "fair_sources_pending.json"  # discovery output awaiting review

# Discovery is self-throttled to ~monthly (the Action itself runs weekly). Free
# search-API tiers are small, so each run caps its queries and rotates through
# target schools across months.
DISCOVERY_INTERVAL_DAYS = 30
DISCOVERY_QUERY_BUDGET = 40

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


def scrape(fairs: list[dict], curated_sources: dict, use_net: bool) -> list[dict]:
    """Existing behavior, UNCHANGED: fetch each known career-center URL and
    extract fair dates. Now also scrapes any curated/approved URLs from
    fair_sources.json, so discovered-and-approved sites feed the same pipeline."""
    if not use_net:
        print("(--no-net) skipping fetch; nothing new scraped")
        return []
    # Targets = URLs already in the feed  +  curated/approved URLs.
    targets: dict[str, list[str]] = sources_from(fairs)
    for college, urls in (curated_sources or {}).items():
        targets.setdefault(college, [])
        for u in urls:
            if u and u not in targets[college]:
                targets[college].append(u)
    found: list[dict] = []
    for college, urls in targets.items():
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


def prune_stale(fairs: list[dict]) -> tuple[list[dict], int]:
    """Keep every UPCOMING fair, plus at most the single most-recently-passed fair
    per college (so a 'recently passed' one survives but old ones don't pile up).
    The directory renders that one passed fair in a separate section."""
    today_iso = TODAY.isoformat()
    by_college: dict[str, list[dict]] = {}
    for f in fairs:
        by_college.setdefault(f["college"], []).append(f)
    kept: list[dict] = []
    dropped = 0
    for _college, fs in by_college.items():
        upcoming = [f for f in fs if f.get("date", "") >= today_iso]
        past = sorted((f for f in fs if f.get("date", "") < today_iso),
                      key=lambda x: x["date"])
        kept.extend(upcoming)
        if past:
            kept.append(past[-1])       # most-recently-passed only
            dropped += len(past) - 1    # older past fairs pruned
    kept.sort(key=lambda f: (f["college"], f["date"]))
    return kept, dropped


# ----------------------------------------------------------------------------
# Discovery: web-search for NEW career-fair / job-board sites not on our list.
# Runs alongside (not instead of) the scraper. Self-throttled to ~monthly.
# Candidates are written to PENDING_PATH for human review; NEVER auto-added.
# ----------------------------------------------------------------------------
def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception as e:  # noqa: BLE001
        print(f"  ! could not read {path.name}: {e}", file=sys.stderr)
        return default


def discovery_targets() -> list[str]:
    """The curated target schools (Top-100 / NY / SF / extra) to search for.
    Loaded from build_directory so the two never drift. No candidate PII."""
    try:
        sys.path.insert(0, str(ROOT))
        from build_directory import (  # type: ignore
            TOP_NATIONAL, NY_FOUR_YEAR, SF_FOUR_YEAR, EXTRA_TRACKED)
    except Exception as e:  # noqa: BLE001
        print(f"  ! discovery: cannot load school lists ({e})", file=sys.stderr)
        return []
    seen, out = set(), []
    for n in TOP_NATIONAL + NY_FOUR_YEAR + SF_FOUR_YEAR + EXTRA_TRACKED:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


_NEG_DOMAIN = re.compile(
    r"(facebook|twitter|reddit|wikipedia|youtube|instagram|indeed|glassdoor|"
    r"ziprecruiter|linkedin)\.com", re.I)
_POS_SOURCE = re.compile(
    r"career.?fair|/career|/careers|career-?center|career-?services|/events|"
    r"joinhandshake\.com|symplicity|12twenty", re.I)


def plausible_source(url: str) -> bool:
    u = (url or "").lower()
    if not u.startswith("http") or _NEG_DOMAIN.search(u):
        return False
    if _POS_SOURCE.search(u):
        return True
    return ".edu" in u and ("career" in u or "event" in u)


def source_score(url: str) -> int:
    """Rough relevance rank so real official career pages sort to the top of the
    review file and noise sinks to the bottom. Higher = more likely legit."""
    u = (url or "").lower()
    score = 0
    if ".edu" in u:
        score += 3
    if re.search(r"career.?fair|career-?center|career-?services|/careers?\b", u):
        score += 2
    if "/events" in u:
        score += 1
    if re.search(r"symplicity|joinhandshake|12twenty|careereco", u):
        score += 1                      # real recruiting platforms
    if re.search(r"blog|press-?room|press-?release|/news|forum|/event/", u):
        score -= 2                      # articles / one-off event pages, not schedules
    return score


def web_search(query: str, num: int = 6):
    """Return [(title, url)] via whichever Search API key is set, [] on error,
    or None if NO backend is configured (so discovery can no-op cleanly)."""
    import os
    try:
        import requests  # type: ignore
    except ImportError:
        return None
    tav = os.environ.get("TAVILY_API_KEY")
    serp = os.environ.get("SERPAPI_KEY")
    bing = os.environ.get("BING_SEARCH_KEY")
    gkey, gcx = os.environ.get("GOOGLE_API_KEY"), os.environ.get("GOOGLE_CSE_ID")
    try:
        if tav:
            r = requests.post("https://api.tavily.com/search",
                              json={"api_key": tav, "query": query,
                                    "max_results": num, "search_depth": "basic"},
                              timeout=25)
            r.raise_for_status()
            return [(i.get("title", ""), i.get("url", ""))
                    for i in r.json().get("results", [])[:num]]
        if serp:
            r = requests.get("https://serpapi.com/search.json",
                             params={"q": query, "api_key": serp, "num": num,
                                     "engine": "google"}, timeout=25)
            r.raise_for_status()
            return [(i.get("title", ""), i.get("link", ""))
                    for i in r.json().get("organic_results", [])[:num]]
        if bing:
            r = requests.get("https://api.bing.microsoft.com/v7.0/search",
                             headers={"Ocp-Apim-Subscription-Key": bing},
                             params={"q": query, "count": num}, timeout=25)
            r.raise_for_status()
            return [(i.get("name", ""), i.get("url", ""))
                    for i in r.json().get("webPages", {}).get("value", [])[:num]]
        if gkey and gcx:
            r = requests.get("https://www.googleapis.com/customsearch/v1",
                             params={"key": gkey, "cx": gcx, "q": query,
                                     "num": min(num, 10)}, timeout=25)
            r.raise_for_status()
            return [(i.get("title", ""), i.get("link", ""))
                    for i in r.json().get("items", [])[:num]]
    except Exception as e:  # noqa: BLE001
        print(f"  ! search failed for {query!r}: {e}", file=sys.stderr)
        return []
    return None  # no backend configured


def discover(data: dict, existing_fairs: list[dict], curated_sources: dict,
             force: bool, write: bool):
    """Monthly-throttled discovery. Returns (state_or_None, new_candidates).
    state_or_None is None when discovery did NOT run (throttled / no backend)."""
    state = dict(data.get("discovery", {}) or {})
    last = state.get("last_run")
    if not force and last:
        try:
            gap = (TODAY - dt.date.fromisoformat(last)).days
        except ValueError:
            gap = DISCOVERY_INTERVAL_DAYS
        if gap < DISCOVERY_INTERVAL_DAYS:
            print(f"· discovery: last ran {last} ({gap}d ago) < "
                  f"{DISCOVERY_INTERVAL_DAYS}d — skipping (monthly cadence)")
            return None, []

    targets = discovery_targets()
    if not targets:
        return None, []

    known = {f["college"] for f in existing_fairs} | set(curated_sources)
    searched = set(state.get("searched_colleges", []))
    todo = [s for s in targets if s not in known and s not in searched]
    if not todo:                       # full rotation done -> start over
        searched = set()
        todo = [s for s in targets if s not in known]

    pending = _read_json(PENDING_PATH, [])
    seen = {(p["college"], p["url"]) for p in pending}
    new: list[dict] = []
    budget = DISCOVERY_QUERY_BUDGET
    for school in todo:
        if budget <= 0:
            break
        query = f"{school} career fair 2026"
        results = web_search(query)
        if results is None:            # no backend -> don't mark state, retry later
            print("  ! discovery: no search backend configured "
                  "(set TAVILY_API_KEY / SERPAPI_KEY / BING_SEARCH_KEY / "
                  "GOOGLE_API_KEY+GOOGLE_CSE_ID)")
            return None, []
        budget -= 1
        searched.add(school)
        for title, url in results:
            if plausible_source(url) and (school, url) not in seen:
                seen.add((school, url))
                new.append({"college": school, "url": url, "title": title,
                            "score": source_score(url),
                            "query": query, "found": TODAY.isoformat(),
                            "status": "pending_review"})

    if write:
        pending.extend(new)
        # Best (most-likely-official) sources first within each school.
        pending.sort(key=lambda p: (p["college"], -p.get("score", 0), p["url"]))
        PENDING_PATH.write_text(
            json.dumps(pending, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    state = {"last_run": TODAY.isoformat(), "searched_colleges": sorted(searched)}
    return state, new


# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="scrape + report, but don't write files")
    ap.add_argument("--no-net", action="store_true",
                    help="skip network fetches (exercise merge/write path only)")
    ap.add_argument("--no-discover", action="store_true",
                    help="skip the web-search discovery step")
    ap.add_argument("--force-discover", action="store_true",
                    help="run discovery now even if <30 days since last run")
    args = ap.parse_args()

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    existing = data.get("fairs", [])
    curated = _read_json(SOURCES_PATH, {})     # {college: [approved urls]}
    n_curated = sum(len(v) for v in curated.values())
    print(f"Loaded {len(existing)} existing fairs; {n_curated} curated source URL(s)")

    # 1) SCRAPE (unchanged behavior) — known feed URLs + curated/approved URLs.
    scraped = scrape(existing, curated, use_net=not args.no_net)
    merged, added = merge(existing, scraped)
    merged, pruned = prune_stale(merged)

    # 2) DISCOVERY (search API) — additive, monthly-throttled, review-only.
    disc_state, disc_new = (None, [])
    if not args.no_discover and not args.no_net:
        disc_state, disc_new = discover(data, existing, curated,
                                        force=args.force_discover,
                                        write=not args.dry_run)

    print(f"\n{len(added)} new fair(s) scraped:")
    for f in added:
        print(f"  + {f['college']} {f['date']} — {f['name']}")
    if pruned:
        print(f"{pruned} stale past fair(s) pruned (kept 1 most-recent per school).")
    if disc_new:
        print(f"{len(disc_new)} candidate source(s) flagged for review in "
              f"{PENDING_PATH.name} (NOT auto-added).")
    if disc_state:
        print(f"discovery ran; {len(disc_state['searched_colleges'])} school(s) "
              f"searched cumulatively.")

    if args.dry_run:
        print("\n(--dry-run) no files written.")
        return 0

    # career_fairs.json changes if fairs changed OR discovery state advanced.
    file_changed = bool(added or pruned) or disc_state is not None
    if disc_state is not None:
        data["discovery"] = disc_state
    if not file_changed:
        print("\nNothing new; career_fairs.json unchanged.")
        return 0

    data["last_scraped"] = TODAY.isoformat()
    write_json(data, merged)
    print(f"\nWrote {JSON_PATH.name} "
          f"({len(added)} added, {pruned} pruned, {len(merged)} total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
