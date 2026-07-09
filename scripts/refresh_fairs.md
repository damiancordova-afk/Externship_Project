# Keeping career-fair dates fresh

The directory (`campus-recruiting-directory.html`) never hard-codes a "next fair"
date. It reads a feed and computes each school's **next** and **most-recent**
fair against *today's* date, every time the page loads.

That gives you two layers of "automatic":

## 1. Fairs passing — already fully automatic

No job required. Because `nextFairObj` / `lastFairObj` are recomputed on every
load from `TODAY_ISO`, a fair that happened yesterday stops being "Next" and the
following upcoming fair takes its place the next time anyone opens the page. When
a school has no future fair left in the data, the row shows
"No upcoming fair listed" and sinks to the bottom of the "Upcoming career fair"
sort.

## 2. New fairs being posted — the scheduled scraper (BUILT)

The app reads its data from **`career_fairs.json`** (with an identical copy
embedded in the HTML as a `file://` fallback). To pick up newly-posted fairs, a
scheduled job rewrites `career_fairs.json`. The browser cannot scrape the college
career-center pages itself — cross-origin requests to those sites are blocked, and
they serve HTML, not an API — so this runs server-side.

### What's implemented

- **`scripts/scrape_fairs.py`** — fetches each college's known `source` pages,
  extracts fair dates, and MERGES new ones into `career_fairs.json` (additive —
  never deletes curated history; dedupes by college+date; tags auto rows with
  `"auto": true`). It also regenerates the `FAIRS_FALLBACK` block in the HTML
  between the `FAIRS_FALLBACK_START/END` markers. Run it with `--dry-run` to
  preview, `--no-net` to exercise only the merge/write path.
- **`.github/workflows/refresh-fairs.yml`** — runs the scraper weekly (Mon 13:00
  UTC) and on manual dispatch, then commits any changes.

### Honest limits (read before trusting it)

- **Works on static-HTML pages only.** A live test captured
  Purdue/UIUC/Georgia Tech/Rutgers/SJSU/Cornell well.
- **Five schools can't be scraped** and must be entered manually (see below).
- **Name quality varies.** The generic extractor grabs imperfect fair names.
  Add a site-specific function to the `EXTRACTORS` registry to fix a given site.
- **Parsers break on redesigns.** Review the automated commits the Action pushes;
  auto rows are tagged `"auto": true` so they're easy to spot and prune.

### The five holdouts — why, and what to do

Investigated live. A headless browser (Playwright) was tried and **removed**: it
rendered the pages but the specific dates still weren't present, because they
live in login-gated platforms. Valon does **not** have API access to those, so
these are **manual-entry** schools. The scraper lists them in `MANUAL_COLLEGES`
and skips them entirely, so it never overwrites or duplicates your hand-entered
rows. To maintain them, add/update curated (non-`auto`) rows in
`career_fairs.json` once per recruiting season:

- **UC Berkeley, Arizona State, Northeastern** — dates live inside
  Handshake / 12twenty (behind school login); the public pages only show fair
  names, not dates.
- **Michigan** — the career-center site is behind a WAF that returns 403 to
  automated requests (including headless Chromium).
- (**Cornell** is now scraped — its `source` was updated to a working event URL.)

### JSON shape the app expects

```json
{
  "fairs": [
    {
      "college": "MIT",
      "name": "Fall Career Fair (FCF)",
      "date": "2026-09-25",
      "location": "Johnson Athletic Center",
      "source": "https://capd.mit.edu/channels/fall-career-fair/"
    }
  ]
}
```

- `college` must match a school's `fairKey` in the HTML (e.g. `"MIT"`,
  `"UC Berkeley"`, `"Georgia Tech"`).
- `date` must be ISO `YYYY-MM-DD`.
- A school may have any number of fairs; the app derives next/most-recent.

### Deploy note

`fetch("career_fairs.json")` only works when the page is served over http(s)
(local dev server, or a host like Vercel/GitHub Pages). Opened straight from disk
(`file://`), the browser blocks the fetch and the app transparently falls back to
the embedded copy. So for live auto-refresh, serve the folder — don't double-click
the HTML.

If you keep the embedded fallback in sync, regenerate it from `career_fairs.json`
whenever the refresh job runs (it's the block labeled `FAIRS_FALLBACK`).
