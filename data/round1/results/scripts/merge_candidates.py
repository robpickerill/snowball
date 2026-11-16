#!/usr/bin/env python3
"""Merge round-1 snowballing sources into one de-duplicated screening list.
Sources: round1/candidates.csv (OpenAlex backward+forward, Crossref backward),
         pdf_backward.json (reference lists parsed from seed PDFs, resolved in OpenAlex),
         s2_gapfill.json (Semantic Scholar citations/references for seeds OpenAlex lacks).
Writes round1/screening_list.csv and round1/prisma_counts_merged.json."""
import csv, json, re, unicodedata, datetime as dt

YEAR_MIN, DATE_MAX = 2018, "2026-08-31"


def nt(t):
    t = unicodedata.normalize("NFKC", t or "").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", t)).strip()


def nd(d):
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", (d or "").strip().lower())


def oa_abstract(w):
    inv = w.get("abstract_inverted_index") or {}
    pos = {i: k for k, v in inv.items() for i in v}
    return " ".join(pos[i] for i in sorted(pos))


seeds = list(csv.DictReader(open("seeds.csv", encoding="utf-8-sig")))
seed_titles = {nt(s["title"]) for s in seeds}
seed_dois = {nd(s["doi"]) for s in seeds if s["doi"]}
known = list(csv.DictReader(open("known_records.csv", encoding="utf-8-sig")))
k_doi = {nd(k["doi"]): k["source"] for k in known if k["doi"]}
k_title = {nt(k["title"]): k["source"] for k in known if k["title"]}

recs = {}  # key -> record


def key_of(doi, title):
    return ("doi", doi) if doi else ("t", nt(title))


def add(doi, title, year, date, venue, abstract, seed, direction, source):
    doi, t = nd(doi), (title or "").strip()
    if not t or nt(t) in seed_titles or (doi and doi in seed_dois):
        return
    k = key_of(doi, t)
    # merge title-keyed and doi-keyed duplicates
    if k[0] == "doi" and ("t", nt(t)) in recs:
        recs[k] = recs.pop(("t", nt(t)))
    elif k[0] == "t":
        for kk, r in recs.items():
            if nt(r["title"]) == nt(t):
                k = kk
                break
    r = recs.setdefault(k, {"doi": doi, "title": t, "year": year or 0, "date": date or "", "venue": venue or "",
                            "abstract": abstract or "", "seeds": set(), "dirs": set(), "sources": set()})
    if not r["abstract"] and abstract:
        r["abstract"] = abstract
    if not r["doi"] and doi:
        r["doi"] = doi
    r["seeds"].add(seed); r["dirs"].add(direction); r["sources"].add(source)


# 1. OpenAlex/Crossref run
for c in csv.DictReader(open("round1/candidates.csv", encoding="utf-8-sig")):
    for s in c["seeds"].split(";"):
        for d in c["direction"].split(";"):
            for src in c["found_by"].split(";"):
                add(c["doi"], c["title"], int(c["year"] or 0), c["date"], c["venue"], c["abstract"], s, d, src)
# 2. PDF reference lists
for s, works in json.load(open("pdf_backward.json")).items():
    for w in works:
        v = ((w.get("primary_location") or {}).get("source") or {}).get("display_name")
        add(w.get("doi"), w.get("title"), w.get("publication_year"), w.get("publication_date"), v,
            oa_abstract(w), s, "backward", "pdf-references")
# 3. Semantic Scholar gap-fill
for s, g in json.load(open("s2_gapfill.json")).items():
    for kind, direction in (("citations", "forward"), ("references", "backward")):
        for p in g.get(kind, []):
            add((p.get("externalIds") or {}).get("DOI"), p.get("title"), p.get("year"), p.get("publicationDate"),
                p.get("venue"), p.get("abstract"), s, direction, "semanticscholar")

rows = []
for r in recs.values():
    prior = k_doi.get(r["doi"]) if r["doi"] else None
    prior = prior or k_title.get(nt(r["title"]))
    y = int(r["year"] or 0)
    in_win = y >= YEAR_MIN and (not r["date"] or r["date"] <= DATE_MAX)
    rows.append({"title": r["title"], "year": y, "date": r["date"], "venue": r["venue"], "doi": r["doi"],
                 "direction": ";".join(sorted(r["dirs"])), "found_by": ";".join(sorted(r["sources"])),
                 "n_seeds": len(r["seeds"]), "seeds": ";".join(sorted(r["seeds"], key=int)),
                 "already_screened": prior or "", "in_date_window": in_win, "to_screen": in_win and not prior,
                 "has_abstract": bool(r["abstract"]), "abstract": r["abstract"][:3000]})
rows.sort(key=lambda x: (not x["to_screen"], -x["n_seeds"], -x["year"]))
with open("round1/screening_list.csv", "w", newline="", encoding="utf-8-sig") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
oa = json.load(open("round1/prisma_counts.json"))
counts = {
    "run_date_openalex_crossref": oa["run_date"],
    "merged_on": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    "sources": ["OpenAlex (backward, forward)", "Crossref (backward)",
                "Seed PDF reference lists resolved in OpenAlex (rows 43, 44, 55, 57)",
                "Semantic Scholar (forward for 43, 44, 47, 54, 55, 57, 35, 56; backward for 47, 54, 35, 56)"],
    "seeds": len(seeds),
    "records_identified": len(rows),
    "already_screened": sum(1 for x in rows if x["already_screened"]),
    "outside_date_window": sum(1 for x in rows if not x["in_date_window"] and not x["already_screened"]),
    "to_screen": sum(1 for x in rows if x["to_screen"]),
    "to_screen_without_abstract": sum(1 for x in rows if x["to_screen"] and not x["has_abstract"]),
}
json.dump(counts, open("round1/prisma_counts_merged.json", "w"), indent=2)
print(json.dumps(counts, indent=2))
