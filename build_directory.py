"""
Build the Campus Recruiting Directory page from the Ashby candidate CSV.

- Counts DISTINCT hired people per school.
- Normalizes school names (casing/aliases/sub-colleges/multi-school cells).
- School list = dedup UNION of three inclusion criteria:
    1. Top ~100 U.S. national universities (names only; see RANKING_SOURCE)
    2. Any 4-year degree-granting college/university in New York State
    3. Any school that appears as an alma mater in the CSV
- 0-hire schools from criteria 1 & 2 are INCLUDED (shown with an empty state).
- For each hire: name + whatever contact info exists (email, phone, LinkedIn, ...).

Run:  python3 build_directory.py
Out:  campus-recruiting-directory.html   (self-contained, data inlined)

NOTE: the output contains real candidate PII - keep it out of git.
"""

import pandas as pd
import ast, json, re, html
from collections import defaultdict

CSV = "ashby_candidate_list.csv"
OUT = "campus-recruiting-directory.html"

# Source used for the Top-100 inclusion set. We use only the *set of institution
# names* for membership testing - not the ranked order.
RANKING_SOURCE = ("U.S. News & World Report — 2025 Best National Universities "
                  "(used as an unordered set of institution names for inclusion, "
                  "not the ranking order)")

# --- Criterion 1: ~Top 100 U.S. national universities (names only) ------------
TOP_NATIONAL = [
    "Princeton University", "Massachusetts Institute of Technology",
    "Harvard University", "Stanford University", "Yale University",
    "California Institute of Technology", "Duke University",
    "Johns Hopkins University", "Northwestern University",
    "University of Pennsylvania", "Cornell University", "University of Chicago",
    "Brown University", "Columbia University", "Dartmouth College",
    "University of California, Los Angeles", "University of California, Berkeley",
    "Rice University", "University of Notre Dame", "Vanderbilt University",
    "Carnegie Mellon University", "University of Michigan",
    "Washington University in St. Louis", "Emory University",
    "Georgetown University", "University of Virginia",
    "University of North Carolina at Chapel Hill",
    "University of Southern California", "University of California, San Diego",
    "New York University", "University of Florida",
    "University of Texas at Austin", "University of California, Davis",
    "University of California, Irvine", "Georgia Institute of Technology",
    "University of California, Santa Barbara",
    "University of Illinois Urbana-Champaign",
    "University of Wisconsin-Madison", "Boston College",
    "Rutgers University", "Tufts University", "University of Washington",
    "Boston University", "The Ohio State University", "Purdue University",
    "University of Georgia", "University of Maryland, College Park",
    "Lehigh University", "Wake Forest University", "Texas A&M University",
    "University of California, Santa Cruz", "Case Western Reserve University",
    "Northeastern University", "Virginia Tech", "Michigan State University",
    "Florida State University", "William & Mary", "University of Rochester",
    "University of Minnesota, Twin Cities", "Pennsylvania State University",
    "George Washington University", "University of Pittsburgh",
    "Brandeis University", "University of California, Riverside",
    "University of Connecticut", "University of Miami",
    "Indiana University Bloomington", "Tulane University",
    "University of Colorado Boulder", "Syracuse University",
    "Pepperdine University", "Southern Methodist University",
    "Stony Brook University", "Rensselaer Polytechnic Institute",
    "University of Massachusetts Amherst", "Clemson University",
    "Fordham University", "Baylor University", "Brigham Young University",
    "American University", "Arizona State University", "University of Delaware",
    "Marquette University", "Stevens Institute of Technology",
    "North Carolina State University", "Binghamton University",
    "University of Iowa", "University of Arizona", "Auburn University",
    "Loyola Marymount University", "University of Tennessee, Knoxville",
    "University of Kentucky", "University of Nebraska-Lincoln",
    "University of San Diego", "Yeshiva University", "Worcester Polytechnic Institute",
    "University at Buffalo", "University of Vermont", "Texas Christian University",
    "University of Denver",
]

# --- Criterion 2: 4-year degree-granting institutions in New York State -------
NY_FOUR_YEAR = [
    # Private
    "Columbia University", "Cornell University", "New York University",
    "Fordham University", "Syracuse University", "University of Rochester",
    "Rensselaer Polytechnic Institute", "Rochester Institute of Technology",
    "Colgate University", "Hamilton College", "Vassar College",
    "Barnard College", "Skidmore College", "Union College",
    "Hobart and William Smith Colleges", "St. Lawrence University",
    "Ithaca College", "Pace University", "Yeshiva University",
    "The New School", "Pratt Institute", "Manhattan College",
    "Marist College", "Siena College", "Le Moyne College",
    "Canisius University", "St. John's University", "Adelphi University",
    "Hofstra University", "Clarkson University", "Wagner College",
    "Iona University", "Nazareth University", "Sarah Lawrence College",
    "Bard College", "Cooper Union", "The Juilliard School",
    "Rockefeller University", "Colgate University", "Elmira College",
    "Wells College", "Utica University", "Daemen University",
    "St. Bonaventure University", "Niagara University", "Dominican University New York",
    "Molloy University", "Mercy University", "Long Island University",
    "New York Institute of Technology", "School of Visual Arts",
    "Fashion Institute of Technology",
    # SUNY (4-year)
    "University at Albany", "Binghamton University", "University at Buffalo",
    "Stony Brook University", "SUNY College at Brockport",
    "Buffalo State University", "SUNY Cortland", "SUNY Fredonia",
    "SUNY Geneseo", "SUNY New Paltz", "SUNY Old Westbury", "SUNY Oneonta",
    "SUNY Oswego", "SUNY Plattsburgh", "SUNY Potsdam", "Purchase College",
    "SUNY Empire State University", "SUNY Polytechnic Institute",
    "SUNY Maritime College",
    "SUNY College of Environmental Science and Forestry",
    "Farmingdale State College", "SUNY Cobleskill", "SUNY Morrisville",
    "Alfred State College", "SUNY Delhi",
    # CUNY (4-year)
    "Baruch College", "Brooklyn College", "The City College of New York",
    "Hunter College", "John Jay College of Criminal Justice", "Lehman College",
    "Medgar Evers College", "New York City College of Technology",
    "Queens College", "College of Staten Island", "York College, CUNY",
    "Macaulay Honors College",
]

# --- Criterion 2b: 4-year degree-granting institutions in San Francisco -------
SF_FOUR_YEAR = [
    "University of San Francisco",
    "San Francisco State University",
    "California College of the Arts",
    "Academy of Art University",
    "Golden Gate University",
    "San Francisco Conservatory of Music",
]

# --- Alias map: normalized-key -> official display name -----------------------
_ALIAS_RAW = {
    "nyu": "New York University",
    "mit": "Massachusetts Institute of Technology",
    "ucla": "University of California, Los Angeles",
    "usc": "University of Southern California",
    "cal": "University of California, Berkeley",
    "uc berkeley": "University of California, Berkeley",
    "berkeley": "University of California, Berkeley",
    "ucsd": "University of California, San Diego",
    "uc san diego": "University of California, San Diego",
    "uc davis": "University of California, Davis",
    "uc irvine": "University of California, Irvine",
    "uc santa barbara": "University of California, Santa Barbara",
    "ucsb": "University of California, Santa Barbara",
    "cmu": "Carnegie Mellon University",
    "penn": "University of Pennsylvania",
    "upenn": "University of Pennsylvania",
    "uiuc": "University of Illinois Urbana-Champaign",
    "university of illinois": "University of Illinois Urbana-Champaign",
    "georgia tech": "Georgia Institute of Technology",
    "gatech": "Georgia Institute of Technology",
    "ut austin": "University of Texas at Austin",
    "umich": "University of Michigan",
    "u of m": "University of Michigan",
    "osu": "The Ohio State University",
    "ohio state": "The Ohio State University",
    "asu": "Arizona State University",
    "psu": "Pennsylvania State University",
    "penn state": "Pennsylvania State University",
    "rpi": "Rensselaer Polytechnic Institute",
    "rit": "Rochester Institute of Technology",
    "suny buffalo": "University at Buffalo",
    "suny binghamton": "Binghamton University",
    "suny albany": "University at Albany",
    "suny stony brook": "Stony Brook University",
    "cuny baruch": "Baruch College",
    "wash u": "Washington University in St. Louis",
    "washu": "Washington University in St. Louis",
    "unc": "University of North Carolina at Chapel Hill",
    "uw": "University of Washington",
    "uw madison": "University of Wisconsin-Madison",
    "uf": "University of Florida",
    "gwu": "George Washington University",
    "bu": "Boston University",
    "bc": "Boston College",
    "wpi": "Worcester Polytechnic Institute",
    "sfsu": "San Francisco State University",
    "sf state": "San Francisco State University",
    "cca": "California College of the Arts",
}


def parse(v):
    if pd.isna(v):
        return None
    try:
        return ast.literal_eval(v)
    except Exception:
        return v


def norm_key(s):
    """Normalized key for matching: lowercase, drop punctuation/parentheticals/stopwords."""
    s = str(s).lower()
    s = re.sub(r"\(.*?\)", " ", s)      # drop parentheticals e.g. "(MIT)"
    s = s.replace("&", " and ")
    s = re.sub(r"[^a-z0-9 ]", " ", s)   # punctuation -> space
    s = re.sub(r"\b(the|at|of|for)\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_ALIAS_KEYS = {norm_key(k): v for k, v in _ALIAS_RAW.items()}
_SUBCOLLEGE = re.compile(r",\s*(college|school|graduate school|faculty|division)\s+of\s+.*$", re.I)


def split_multi(raw):
    """Split cells that list more than one school ('A / B', 'A - B')."""
    parts = re.split(r"\s*/\s*|\s+-\s+|\s*;\s*", str(raw))
    return [p.strip() for p in parts if p.strip()]


def pretty(name):
    """Best-effort display casing for schools with no official match."""
    if name.isupper() or name.islower():
        small = {"of", "the", "at", "and", "for", "in"}
        words = []
        for i, w in enumerate(name.split()):
            lw = w.lower()
            words.append(lw if (lw in small and i > 0) else lw.capitalize())
        return " ".join(words)
    return name.strip()


def canonicalize(raw):
    """Return list of (display_name, key) for one raw school cell (may be multiple)."""
    out = []
    for part in split_multi(raw):
        part = _SUBCOLLEGE.sub("", part).strip()
        if not part:
            continue
        k = norm_key(part)
        if not k:
            continue
        if k in _ALIAS_KEYS:                     # alias -> official
            disp = _ALIAS_KEYS[k]
            k = norm_key(disp)
        elif k in OFFICIAL:                       # matches an inclusion-list name
            disp = OFFICIAL[k]
        else:
            disp = pretty(part)
        out.append((disp, k))
    return out


def extract_contacts(row):
    """Ordered list of available contacts for a hire; omits anything missing."""
    contacts = []
    email = row.get("primaryEmailAddress.value")
    if pd.notna(email):
        contacts.append({"kind": "email", "label": "Email",
                         "value": str(email), "href": f"mailto:{email}"})
    social = parse(row.get("socialLinks"))
    if isinstance(social, list):
        want = {"linkedin": "LinkedIn", "github": "GitHub",
                "website": "Website", "twitter": "Twitter"}
        for item in social:
            if not isinstance(item, dict):
                continue
            t = str(item.get("type", "")).lower()
            url = item.get("url")
            if url and t in want:
                contacts.append({"kind": t, "label": want[t],
                                 "value": url, "href": url})
    phone = row.get("primaryPhoneNumber.value")
    if pd.notna(phone):
        contacts.append({"kind": "phone", "label": "Phone",
                         "value": str(phone), "href": f"tel:{phone}"})
    pu = row.get("profileUrl")
    if pd.notna(pu):
        contacts.append({"kind": "ashby", "label": "Ashby profile",
                         "value": str(pu), "href": str(pu)})
    return contacts


# Build official-name lookup (norm_key -> display) from all inclusion lists.
OFFICIAL = {}
for nm in TOP_NATIONAL + NY_FOUR_YEAR + SF_FOUR_YEAR:
    OFFICIAL.setdefault(norm_key(nm), nm)

TOP_KEYS = {norm_key(n) for n in TOP_NATIONAL}
NY_KEYS = {norm_key(n) for n in NY_FOUR_YEAR}
SF_KEYS = {norm_key(n) for n in SF_FOUR_YEAR}


def main():
    df = pd.read_csv(CSV, low_memory=False)

    # key -> record
    schools = defaultdict(lambda: {"display": None, "keys_seen": defaultdict(int),
                                   "person_ids": set(), "hires": []})

    missing_school = 0
    for _, row in df.iterrows():
        raw = row.get("school")
        if pd.isna(raw) or not str(raw).strip():
            missing_school += 1
            continue
        pid = row.get("id")
        contacts = extract_contacts(row)
        name = row.get("name")
        hire = {"name": (None if pd.isna(name) else str(name)),
                "contacts": contacts}
        for disp, k in canonicalize(raw):
            rec = schools[k]
            rec["keys_seen"][disp] += 1
            if pid not in rec["person_ids"]:
                rec["person_ids"].add(pid)
                rec["hires"].append(hire)

    # Seed 0-hire schools from the target-list criteria.
    for k in TOP_KEYS | NY_KEYS | SF_KEYS:
        schools[k]  # touch to create empty record

    # Finalize records.
    out = []
    for k, rec in schools.items():
        if OFFICIAL.get(k):
            display = OFFICIAL[k]
        elif rec["keys_seen"]:
            display = max(rec["keys_seen"].items(), key=lambda kv: (kv[1], len(kv[0])))[0]
        else:
            display = k.title()
        criteria = []
        if k in TOP_KEYS:
            criteria.append("ranked")
        if k in NY_KEYS:
            criteria.append("ny")
        if k in SF_KEYS:
            criteria.append("sf")
        if rec["hires"]:
            criteria.append("hired")
        out.append({
            "name": display,
            "count": len(rec["person_ids"]),
            "criteria": criteria,
            "hires": sorted(rec["hires"], key=lambda h: (h["name"] or "").lower()),
        })

    out.sort(key=lambda s: (-s["count"], s["name"].lower()))

    # --- stats (aggregate only; no PII) ---
    total_schools = len(out)
    with_hires = sum(1 for s in out if s["count"] > 0)
    print(f"Candidates in CSV:        {len(df)}")
    print(f"  missing school:         {missing_school}")
    print(f"Schools in directory:     {total_schools}")
    print(f"  with >=1 hire:          {with_hires}")
    print(f"  0-hire (target only):   {total_schools - with_hires}")
    print(f"  ranked (Top-100):       {sum(1 for s in out if 'ranked' in s['criteria'])}")
    print(f"  NY 4-year:              {sum(1 for s in out if 'ny' in s['criteria'])}")
    print(f"  SF 4-year:              {sum(1 for s in out if 'sf' in s['criteria'])}")
    print(f"Top 5 by hires:           " +
          ", ".join(f"{s['name']} ({s['count']})" for s in out[:5]))

    payload = {"generatedFrom": CSV, "rankingSource": RANKING_SOURCE,
               "totalSchools": total_schools, "schoolsWithHires": with_hires,
               "candidateCount": int(len(df)), "missingSchool": int(missing_school),
               "schools": out}

    tpl = TEMPLATE.replace("__DATA__", json.dumps(payload))
    tpl = tpl.replace("__RANKING_SOURCE__", html.escape(RANKING_SOURCE))
    with open(OUT, "w") as f:
        f.write(tpl)
    print(f"\nWrote {OUT}")


# HTML template is imported from a sibling module to keep this file focused.
from directory_template import TEMPLATE

if __name__ == "__main__":
    main()
