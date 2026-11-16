#!/usr/bin/env python3
"""Gap-fill for seeds that OpenAlex does not index (or indexes without references/citations).
Pulls forward citations and, where available, references from Semantic Scholar, slowly (shared rate limit).
Writes s2_gapfill.json: {seed_id: {"paperId":..., "citations":[...], "references":[...]}}"""
import json, sys, time, requests

S2 = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,year,venue,externalIds,abstract,publicationDate,publicationTypes"
SEEDS = {  # seed id -> Semantic Scholar paperId (None = look up by search)
    "43": "0057e9bc7762bf8b8ed6a70e090ab3b7abd81833",
    "44": "465cc2ebbbe9747eb43e2455fb3c8cd11367bffb",
    "47": "a6e6b5dfa8292be96a1bb8f8f602748eb04711b9",
    "54": "f10c751b3ccffd4f6e0ce2fdba6b551b12a56680",
    "55": "1cb0c82b180c895b052502debabc61db581a5cd9",
    "57": None,
    "35": "bd033a07a7efe01801351c9f983856da73bb25d6",
    "56": "0daa3947f34be9f958459228469db4ba7a957455",
}
WANT_REFS = {"47", "54", "35", "56"}


def get(path, params, tries=12):
    for i in range(tries):
        try:
            r = requests.get(S2 + path, params=params, timeout=60)
            if r.status_code == 200:
                time.sleep(4)
                return r.json()
            if r.status_code == 404:
                return None
        except requests.RequestException:
            pass
        time.sleep(min(20 * (i + 1), 120))
    print("FAILED", path, flush=True)
    return None


def paged(pid, kind):
    out, off = [], 0
    while True:
        j = get(f"/paper/{pid}/{kind}", {"fields": FIELDS, "limit": 500, "offset": off})
        if not j:
            break
        key = "citingPaper" if kind == "citations" else "citedPaper"
        out += [d[key] for d in (j.get("data") or []) if d.get(key)]
        if "next" not in j:
            break
        off = j["next"]
    return out


import os
res = json.load(open("s2_gapfill.json")) if os.path.exists("s2_gapfill.json") else {}
for sid, pid in SEEDS.items():
    if sid in res:
        continue
    if pid is None:
        j = get("/paper/search", {"query": "Breakwater overload control RPCs", "fields": "title,year,venue", "limit": 5})
        cands = [d for d in (j or {}).get("data", []) if "breakwater" in (d.get("title") or "").lower()]
        pid = cands[0]["paperId"] if cands else None
        print("57 ->", pid, cands[0]["title"] if cands else "", flush=True)
    if not pid:
        res[sid] = {"paperId": None, "citations": [], "references": []}
        continue
    cit = paged(pid, "citations")
    refs = paged(pid, "references") if sid in WANT_REFS else []
    res[sid] = {"paperId": pid, "citations": cit, "references": refs}
    print(sid, "citations", len(cit), "references", len(refs), flush=True)
    json.dump(res, open("s2_gapfill.json", "w"))
print("DONE", flush=True)
