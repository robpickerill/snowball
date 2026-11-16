#!/usr/bin/env python3
"""
Citation snowballing for the SLR using OpenAlex (backward + forward) and Crossref (backward cross-check).

Inputs
  seeds.csv          id,title,year,doi        (included studies; doi may be blank, e.g. USENIX papers)
  known_records.csv  source,ref,title,doi     (records already screened: Rayyan pool, earlier snowball pass)

Outputs (in --out folder)
  candidates.csv     one row per unique candidate, with direction, linked seeds, flags, abstract
  seed_resolution.csv  how each seed was matched in OpenAlex (check any 'title-match' or 'NOT FOUND')
  prisma_counts.json counts for the PRISMA 2020 "citation searching" box, with the run date
  run_log.txt        every API call made, for the methods section

Usage
  export OPENALEX_API_KEY=...        (free key from openalex.org)
  python snowball.py --seeds seeds.csv --known known_records.csv --out round1 \
         --year-min 2018 --date-max 2026-08-31

For a second round, pass the newly included papers as --seeds and add round-1 records to --known.
"""
import argparse, csv, datetime as dt, json, os, re, sys, time, unicodedata
from difflib import SequenceMatcher
import requests

OA = "https://api.openalex.org"
CR = "https://api.crossref.org"
SELECT = ("id,doi,title,publication_year,publication_date,type,primary_location,"
          "referenced_works,abstract_inverted_index,cited_by_count")
LOG = []


def norm_title(t):
    t = unicodedata.normalize("NFKC", t or "").lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def norm_doi(d):
    d = (d or "").strip().lower()
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", d)


def get(url, params, tries=5):
    for i in range(tries):
        try:
            r = requests.get(url, params=params, timeout=60)
        except requests.RequestException as e:
            LOG.append(f"ERR {url} {e}")
            time.sleep(2 ** i)
            continue
        LOG.append(f"{r.status_code} {r.url.split('api_key=')[0]}")
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            return None
        time.sleep(2 ** i)  # 429 / 5xx: back off
    return None


class OpenAlex:
    def __init__(self, key):
        self.key = key

    def p(self, **kw):
        kw["api_key"] = self.key
        return kw

    def work_by_doi(self, doi):
        return get(f"{OA}/works/doi:{doi}", self.p(select=SELECT))

    def search_title(self, title):
        j = get(f"{OA}/works", self.p(search=title, **{"per-page": 5}, select=SELECT))
        best, score = None, 0.0
        for w in (j or {}).get("results", []):
            s = SequenceMatcher(None, norm_title(title), norm_title(w.get("title"))).ratio()
            if s > score:
                best, score = w, s
        return best, score

    def works_by_ids(self, ids):
        out = []
        ids = [i.rsplit("/", 1)[-1] for i in ids]
        for k in range(0, len(ids), 50):
            chunk = "|".join(ids[k:k + 50])
            j = get(f"{OA}/works", self.p(filter=f"openalex:{chunk}", **{"per-page": 50}, select=SELECT))
            out += (j or {}).get("results", [])
        return out

    def works_by_dois(self, dois):
        out = []
        for k in range(0, len(dois), 50):
            chunk = "|".join(dois[k:k + 50])
            j = get(f"{OA}/works", self.p(filter=f"doi:{chunk}", **{"per-page": 50}, select=SELECT))
            out += (j or {}).get("results", [])
        return out

    def citing(self, wid):
        wid = wid.rsplit("/", 1)[-1]
        out, cursor = [], "*"
        while cursor:
            j = get(f"{OA}/works", self.p(filter=f"cites:{wid}", **{"per-page": 200}, cursor=cursor, select=SELECT))
            if not j:
                break
            out += j.get("results", [])
            cursor = j.get("meta", {}).get("next_cursor")
            if not j.get("results"):
                break
        return out


def crossref_refs(doi):
    j = get(f"{CR}/works/{doi}", {})
    refs = ((j or {}).get("message") or {}).get("reference") or []
    dois = [norm_doi(r.get("DOI")) for r in refs if r.get("DOI")]
    unstructured = [r.get("unstructured") or r.get("article-title") or "" for r in refs if not r.get("DOI")]
    return dois, unstructured, len(refs)


def abstract(w):
    inv = w.get("abstract_inverted_index") or {}
    pos = {}
    for word, idx in inv.items():
        for i in idx:
            pos[i] = word
    return " ".join(pos[i] for i in sorted(pos))


def venue(w):
    src = ((w.get("primary_location") or {}).get("source") or {})
    return src.get("display_name") or ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", required=True)
    ap.add_argument("--known", required=True)
    ap.add_argument("--out", default="snowball_out")
    ap.add_argument("--year-min", type=int, default=2018)
    ap.add_argument("--date-max", default="2026-08-31")
    ap.add_argument("--title-threshold", type=float, default=0.90)
    a = ap.parse_args()

    key = os.environ.get("OPENALEX_API_KEY")
    if not key:
        sys.exit("Set OPENALEX_API_KEY (free key from openalex.org).")
    oa = OpenAlex(key)
    os.makedirs(a.out, exist_ok=True)
    run_date = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    seeds = list(csv.DictReader(open(a.seeds, encoding="utf-8-sig")))
    known = list(csv.DictReader(open(a.known, encoding="utf-8-sig")))
    known_doi = {norm_doi(k["doi"]): k["source"] for k in known if k.get("doi")}
    known_title = {norm_title(k["title"]): k["source"] for k in known if k.get("title")}

    # 1. resolve seeds
    seed_rows, seed_ids = [], {}
    for s in seeds:
        w, how, score = None, "", ""
        if s.get("doi"):
            w = oa.work_by_doi(norm_doi(s["doi"]))
            how = "doi" if w else ""
        if not w:
            w, sc = oa.search_title(s["title"])
            if w and sc >= a.title_threshold:
                how, score = "title-match", f"{sc:.2f}"
            else:
                w, how, score = None, "NOT FOUND", f"{sc:.2f}" if sc else ""
        seed_rows.append({"id": s["id"], "title": s["title"], "match": how, "score": score,
                          "openalex": (w or {}).get("id", ""), "openalex_title": (w or {}).get("title", ""),
                          "n_references": len((w or {}).get("referenced_works") or [])})
        if w:
            seed_ids[w["id"]] = (s["id"], w)
    seed_doi = {norm_doi(w.get("doi")) for _, w in seed_ids.values() if w.get("doi")}

    # 2. collect links
    cand = {}  # openalex id -> record

    def add(w, seed, direction, source):
        wid = w["id"]
        if wid in seed_ids:
            return
        r = cand.setdefault(wid, {"w": w, "seeds": set(), "dirs": set(), "sources": set()})
        r["seeds"].add(seed); r["dirs"].add(direction); r["sources"].add(source)

    raw = {"openalex_backward": 0, "openalex_forward": 0, "crossref_backward": 0,
           "crossref_unresolved_refs": 0}
    for wid, (sid, w) in seed_ids.items():
        refs = w.get("referenced_works") or []
        raw["openalex_backward"] += len(refs)
        for rw in oa.works_by_ids(refs):
            add(rw, sid, "backward", "openalex")
        cits = oa.citing(wid)
        raw["openalex_forward"] += len(cits)
        for cw in cits:
            add(cw, sid, "forward", "openalex")
        if w.get("doi"):
            dois, unstr, n = crossref_refs(norm_doi(w["doi"]))
            raw["crossref_backward"] += n
            raw["crossref_unresolved_refs"] += len(unstr)
            for rw in oa.works_by_dois(dois):
                add(rw, sid, "backward", "crossref")

    # 3. flag and write
    rows = []
    for wid, r in cand.items():
        w = r["w"]
        d, t = norm_doi(w.get("doi")), norm_title(w.get("title"))
        prior = known_doi.get(d) if d else None
        prior = prior or known_title.get(t)
        date = w.get("publication_date") or ""
        year = w.get("publication_year") or 0
        in_window = year >= a.year_min and (not date or date <= a.date_max)
        rows.append({
            "openalex": wid, "doi": d, "title": w.get("title") or "", "year": year, "date": date,
            "venue": venue(w), "type": w.get("type") or "", "cited_by": w.get("cited_by_count") or 0,
            "direction": ";".join(sorted(r["dirs"])), "found_by": ";".join(sorted(r["sources"])),
            "n_seeds": len(r["seeds"]), "seeds": ";".join(sorted(r["seeds"], key=int)),
            "already_screened": prior or "", "in_date_window": in_window,
            "to_screen": in_window and not prior, "abstract": abstract(w)[:3000],
        })
    rows.sort(key=lambda x: (-x["to_screen"], -x["n_seeds"], -x["year"]))

    with open(os.path.join(a.out, "candidates.csv"), "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["openalex"])
        wr.writeheader(); wr.writerows(rows)
    with open(os.path.join(a.out, "seed_resolution.csv"), "w", newline="", encoding="utf-8-sig") as f:
        wr = csv.DictWriter(f, fieldnames=list(seed_rows[0].keys()))
        wr.writeheader(); wr.writerows(seed_rows)
    counts = {
        "run_date": run_date, "sources": ["OpenAlex (backward, forward)", "Crossref (backward)"],
        "seeds": len(seeds), "seeds_resolved": len(seed_ids),
        "raw_links": raw,
        "unique_candidates": len(rows),
        "already_screened": sum(1 for x in rows if x["already_screened"]),
        "outside_date_window": sum(1 for x in rows if not x["in_date_window"] and not x["already_screened"]),
        "to_screen": sum(1 for x in rows if x["to_screen"]),
    }
    json.dump(counts, open(os.path.join(a.out, "prisma_counts.json"), "w"), indent=2)
    open(os.path.join(a.out, "run_log.txt"), "w").write(f"Run {run_date}\n" + "\n".join(LOG))
    print(json.dumps(counts, indent=2))


if __name__ == "__main__":
    main()
