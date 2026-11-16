# snowball

Citation snowballing for my systematic literature review on overload and metastable
failures in cloud, microservice and distributed systems.

It takes the papers I've included (the seeds), gets everything they cite (backward) and
everything that cites them (forward), merges the results from a few databases, and
drops anything I've already screened or that's outside the date window. What's left is
the list to screen, plus the numbers for the PRISMA "citation searching" box.

Every API call is logged, so the search can be written up and rerun.

## Quick start

```bash
uv sync
export OPENALEX_API_KEY=...   # free, https://openalex.org/settings/api
export S2_API_KEY=...         # optional, but Semantic Scholar is slow without it
uv run slr-snowball --seeds data/round1/seeds.csv --known data/round1/known_records.csv --out round1
```

If you use Nix, `nix develop` (or `direnv allow`) gives you Python, uv, ruff and git.

## Input files

### seeds.csv

The papers to snowball from. For me that's the included studies after full-text
screening, one row per paper.

| column | needed? | what it is |
|---|---|---|
| `id` | yes | my row number for the paper in the extraction sheet, so results can be traced back |
| `title` | yes | full title, used when there's no DOI |
| `doi` | yes, can be blank | blank for papers without one (USENIX, OpenReview) |
| `year` | no | just for reference |
| `s2_id` | no | Semantic Scholar paper id, for seeds OpenAlex doesn't have. Saves a search |

```csv
id,title,year,doi,s2_id
2,Vicious Cycles in Distributed Software Systems,2023,10.1109/ASE56229.2023.00032,
57,Overload Control for us-scale RPCs with Breakwater,2020,,2b74469f0bedfe0e9fbb241af8fbfdbeacfa8bce
```

To find an `s2_id`, search for the paper on semanticscholar.org. The id is the long
string at the end of the paper's URL.

### known_records.csv

Everything I've already screened, so it doesn't come back as new. A paper here is
marked `already_screened` in the output and not counted as to screen.

| column | needed? | what it is |
|---|---|---|
| `source` | yes | where the record came from, copied into the output so you can see why it was dropped |
| `ref` | no | my own reference (row number etc), ignored by the tool |
| `title` | yes | matched after lower-casing and stripping punctuation |
| `doi` | yes, can be blank | matched first if there is one |

```csv
source,ref,title,doi
rayyan_pool,14,Metastable failures in distributed systems,10.1145/3458336.3465286
snowball_pass1_exclude,,Towards Hybrid Cooperative-Preemptive Scheduling,10.1145/3764860.3768329
```

For each new round, add the records screened in the last round to this file and use the
newly included papers as the seeds.

### What's in data/round1

- `seeds.csv`: the 37 included studies. 7 have no DOI and 8 have an `s2_id`.
- `known_records.csv`: 175 records. The 62 papers that went to full-text screening in
  Rayyan (`rayyan_pool`), and 113 from a first snowball pass I did before writing this
  tool (`snowball_pass1_include`, `_maybe`, `_exclude` and `_pre-2018 background`).

## Output

Written to the `--out` folder:

- `candidates.csv`: one row per paper, with the seeds it's linked to, direction, which
  source found it, `already_screened`, `in_date_window`, `to_screen`,
  `possible_duplicate_of` and the abstract. Papers to screen are at the top, the ones
  linked to the most seeds first.
- `seed_resolution.csv`: how each seed was found and how many links each source gave.
  Check anything marked NOT FOUND, FAILED or title-match.
- `prisma_counts.json`: run date and the counts for PRISMA.
- `run_log.txt`: every request and its status code (keys are hidden).

## How it works

Sources:

- **OpenAlex** is the main one. It finds the seeds, then gets references and citations.
- **Crossref** gives the reference lists publishers deposit, which catches some OpenAlex
  misses. Backward only.
- **Semantic Scholar** covers papers OpenAlex doesn't have (Breakwater, Metastable
  Failures in the Wild etc). By default it's only used when OpenAlex can't find a seed or
  has no references or citations for it. `--s2 all` uses it for every seed, `--s2 off`
  turns it off.

Duplicates:

- Records with the same DOI, OpenAlex id, Semantic Scholar id, or the same title within a
  year are merged into one row, keeping every seed and source that found it.
- Titles that are nearly the same (95%+, within a year) are flagged in
  `possible_duplicate_of` but not merged. Usually a preprint and the published version, or
  OpenAlex having two records for one paper.

Other options: `--year-min` and `--date-max` (default 2018 to 2026-08-31),
`--title-threshold` (0.90), `--no-crossref`, `--crossref-mailto`, `--pause` and
`--s2-pause`. Run `uv run slr-snowball -h` for the full list.

## Limitations

- OpenAlex and Semantic Scholar keep changing, so a rerun can find more. Report the run
  date from `prisma_counts.json`.
- Crossref references without a DOI are counted but not followed up.
- Some publishers hide reference lists from Semantic Scholar. If a seed has no reference
  list anywhere, go through the PDF by hand.
- Without a key, Semantic Scholar rate limits a lot. Lookups that still fail are marked
  FAILED and listed under `seeds_with_failed_lookups`. Get a key and rerun.
- No Google Scholar, as it has no API.

## Development

```bash
uv run pytest
uv run ruff check
uv run ruff format
```

CI runs ruff, the tests on Python 3.10 to 3.13, and the tests inside the Nix shell.

```
data/round1/          inputs for round 1
examples/             small example inputs
src/slr_snowball/
  cli.py              command line
  pipeline.py         the snowballing itself
  models.py           Seed, Work, Candidate etc
  duplicates.py       near-duplicate flags
  sources/            OpenAlex, Crossref and Semantic Scholar
  http.py             requests, retries and the call log
  files.py            reading and writing files
tests/                tests (no network needed)
```

To add another database, subclass `CitationSource` and write `find`, `references` and
`citations`.
