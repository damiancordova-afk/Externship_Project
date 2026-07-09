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

## 2. New fairs being posted — needs a refresh job

The app reads its data from **`career_fairs.json`** (with an identical copy
embedded in the HTML as a `file://` fallback). To pick up newly-posted fairs, a
scheduled job must rewrite `career_fairs.json`. The browser cannot scrape the
college career-center pages itself — cross-origin requests to those sites are
blocked, and they serve HTML, not an API.

### Options for the refresh job (pick one)

- **Scrape the source pages.** Each fair row carries a `source` URL (the public
  career-center page it came from). A scheduled scraper (GitHub Action / cron)
  fetches those pages, parses the dates, and writes `career_fairs.json`. Most
  robust but per-site parsing is brittle — the schools redesign pages.
- **Handshake / ATS API.** If Valon has Handshake employer API access (or pulls
  fair schedules from another system), query it on a schedule and emit the same
  JSON shape. Cleaner than scraping.
- **Manual/CSV.** A recruiter edits a sheet; an export step writes the JSON.
  Lowest engineering cost, human-in-the-loop.

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
