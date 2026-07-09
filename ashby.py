"""
Ashby FAST Local Extractor
Run this directly in VS Code's terminal (not Colab) for speed:
    python3 ashby_fast_extract.py

Requires: pip install requests pandas
"""

import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
from getpass import getpass
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

API_KEY = getpass("Paste your Ashby API key: ")
BASE_URL = "https://api.ashbyhq.com"

# Ashby's `createdAfter` expects a Unix timestamp in MILLISECONDS (a number),
# not an ISO-8601 string. Passing a string silently returns 0 records.
_cutoff_dt = datetime.now(timezone.utc) - timedelta(days=3*365)
CUTOFF_MS = int(_cutoff_dt.timestamp() * 1000)
print(f"Pulling records created after: {_cutoff_dt.isoformat()} ({CUTOFF_MS} ms)\n")

# Reuse one connection instead of opening a new one every request - faster.
session = requests.Session()
session.auth = (API_KEY, "")

REQUEST_TIMEOUT = 30      # seconds per request - fail fast instead of hanging forever
MAX_RETRIES = 3           # retry transient failures (timeouts, 429, 5xx)

def ashby_post(endpoint, payload=None):
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = session.post(
                f"{BASE_URL}/{endpoint}",
                json=payload or {},
                timeout=REQUEST_TIMEOUT,
            )
            # Retry on rate-limit / server errors; don't retry 4xx like 403.
            if resp.status_code == 429 or resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} transient", response=resp)
            resp.raise_for_status()
            return resp.json()
        except (requests.Timeout, requests.ConnectionError, requests.HTTPError) as e:
            # Non-retryable client errors (e.g. 403 Forbidden) - surface immediately.
            status = getattr(getattr(e, "response", None), "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                raise
            last_err = e
            if attempt < MAX_RETRIES:
                wait = 2 ** (attempt - 1)   # 1s, 2s, 4s backoff
                print(f"  .. [{endpoint}] {e} - retry {attempt}/{MAX_RETRIES - 1} in {wait}s")
                time.sleep(wait)
    raise last_err

def fetch_all(endpoint, extra_params=None, page_limit=100, max_pages=2000, verbose=True):
    all_results = []
    cursor = None
    page = 1
    seen_cursors = set()

    while True:
        if page > max_pages:
            if verbose:
                print(f"  !! [{endpoint}] hit max_pages cap - stopping.")
            break

        payload = {"limit": page_limit}
        if extra_params:
            payload.update(extra_params)
        if cursor:
            payload["cursor"] = cursor

        prev_count = len(all_results)
        data = ashby_post(endpoint, payload)
        results = data.get("results", [])
        all_results.extend(results)

        if len(results) == 0 and data.get("moreDataAvailable"):
            if verbose:
                print(f"  !! [{endpoint}] 0 results but claims more data - stopping.")
            break
        if not data.get("moreDataAvailable"):
            break

        next_cursor = data.get("nextCursor")
        if not next_cursor or next_cursor in seen_cursors:
            break
        seen_cursors.add(next_cursor)

        if len(all_results) == prev_count:
            break

        cursor = next_cursor
        page += 1
        # No sleep here - local + threaded, and Ashby's rate limit is generous
        # enough for sequential pagination within a single endpoint. If you
        # hit HTTP 429 errors, add: time.sleep(0.2) here.

    if verbose:
        print(f"  [{endpoint}] done - {len(all_results)} records")
    return endpoint, all_results

CONCURRENCY = 8   # parallel workers for per-hire fetches (keep modest to avoid 429s)

def save_csv(records, name):
    if not records:
        print(f"  (skip {name}: 0 records)")
        return
    df = pd.json_normalize(records)
    filename = f"ashby_{name.replace('.', '_')}.csv"
    df.to_csv(filename, index=False)
    print(f"Saved {filename} - {len(df)} rows, {len(df.columns)} columns")

start = time.time()

# ---------------------------------------------------------------
# Phase 1: HIRED applications + reference data (small, parallel)
#   - offer.list is intentionally dropped (403 / not needed; hire signal
#     comes from application.list status=Hired).
#   - candidate.list / applicationFeedback.list are NOT pulled in bulk;
#     we fetch only the candidates/feedback tied to actual hires below.
# ---------------------------------------------------------------
phase1 = [
    ("application.list", {"createdAfter": CUTOFF_MS, "status": "Hired"}),
    ("job.list", None),
    ("department.list", None),
    ("location.list", None),
]
print("Phase 1: pulling hired applications + reference data...\n")
results = {}
with ThreadPoolExecutor(max_workers=len(phase1)) as executor:
    futures = {executor.submit(fetch_all, ep, params): ep for ep, params in phase1}
    for future in as_completed(futures):
        ep = futures[future]
        try:
            name, data = future.result()
            results[name] = data
        except Exception as e:
            print(f"  !! [{ep}] failed: {e}")
            results[ep] = []

hired_apps = results.get("application.list", [])
for name in ("application.list", "job.list", "department.list", "location.list"):
    save_csv(results.get(name, []), name)

# ---------------------------------------------------------------
# Phase 2: only the HIRED candidates (for school data).
#   Ranking is PURE VOLUME - interview feedback is intentionally NOT
#   pulled (hires already cleared the bar, so their scores add little
#   signal and would just be noise / extra PII).
# ---------------------------------------------------------------
def get_candidate_id(app):
    # Handle both a top-level candidateId and a nested candidate object.
    return app.get("candidateId") or (app.get("candidate") or {}).get("id")

cand_ids = sorted({cid for a in hired_apps if (cid := get_candidate_id(a))})

print(f"\nPhase 2: {len(cand_ids)} unique hired candidates")
if hired_apps and not cand_ids:
    print("  !! Could not locate candidate ids on applications.")
    print("     application keys seen:", list(hired_apps[0].keys()))

def fetch_candidate(cid):
    r = ashby_post("candidate.info", {"id": cid}).get("results")
    return r

def run_pool(label, fn, items):
    out = []
    total = len(items)
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {ex.submit(fn, it): it for it in items}
        for i, fut in enumerate(as_completed(futs), 1):
            it = futs[fut]
            try:
                res = fut.result()
                if isinstance(res, list):
                    out.extend(res)
                elif res:
                    out.append(res)
            except Exception as e:
                print(f"  !! {label} {it} failed: {e}")
            if i % 100 == 0 or i == total:
                print(f"  {label}: {i}/{total}")
    return out

print("\nFetching hired candidates (school data)...")
candidates = run_pool("candidate.info", fetch_candidate, cand_ids)
save_csv(candidates, "candidate.list")

elapsed = time.time() - start
print(f"\nAll done in {elapsed:.1f} seconds.")
print("Done. CSVs are in the same folder you ran this script from.")