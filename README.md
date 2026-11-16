# snowball

Citation snowballing for my systematic literature review (overload and metastable
failures in cloud, microservice and distributed systems).

You give it the papers you've included (the seeds). It pulls the references of each one
(backward) and the papers that cite it (forward), merges the results from a few
databases, drops anything already screened or outside the date window, and writes out a
list to screen plus the numbers for the PRISMA "citation searching" box.

Every API call goes in a log, so the search can be written up and rerun.

## Sources

- **OpenAlex**: main source. Finds the seeds, then backward and forward. Needs a free API key.
- **Crossref**: backward only. Publisher reference lists, picks up refs OpenAlex misses.
- **Semantic Scholar**: backward and forward. Mostly for USENIX/OpenReview papers that
  aren't in OpenAlex (Breakwater, Metastable Failures in the Wild etc). Key is optional
  but it's slow without one.

By default Semantic Scholar is only used for a seed when OpenAlex can't find it, or finds
it with no references or no citations (`--s2 fallback`). `--s2 all` uses it for every
seed, `--s2 off` turns it off.

## Duplicates

- Records with the same DOI, OpenAlex id, Semantic Scholar id, or the same title within a
  year of each other are merged into one row. The row keeps every seed/direction/source
  that found it.
- Anything matching `known_records.csv` (by DOI or title) is marked `already_screened`.
- Titles that are nearly the same (95%+, within a year) are flagged in
  `possible_duplicate_of` but left for me to check. Usually a preprint and the published
  version.

## Running it

```bash
uv sync
export OPENALEX_API_KEY=...   # https://openalex.org/settings/api
export S2_API_KEY=...         # optional
uv run slr-snowball --seeds data/round1/seeds.csv --known data/round1/known_records.csv --out round1
```

There's also a Nix flake: `nix develop` (or `direnv allow`) gives you Python, uv, ruff
and git, then use the uv commands above.

Inputs:

- `--seeds`: csv with `id,title,doi` (year optional, doi can be blank). You can also add
  an `s2_id` column with the Semantic Scholar paper id for seeds OpenAlex doesn't have,
  which saves a search.
- `--known`: csv with `source,title,doi` for everything already screened

Other options: `--year-min` and `--date-max` (default 2018 to 2026-08-31),
`--title-threshold` (0.90, only used when a seed has no DOI), `--no-crossref`,
`--crossref-mailto`, `--pause`, `--s2-pause`. `uv run slr-snowball -h` lists them all.

## Output

- `candidates.csv`: one row per paper. Linked seeds, direction, which source found it,
  already_screened, in_date_window, to_screen, possible_duplicate_of, abstract. The
  to-screen ones are at the top, sorted by how many seeds link to them.
- `seed_resolution.csv`: how each seed was matched and how many links each source gave.
  Check anything that says NOT FOUND or title-match.
- `prisma_counts.json`: run date and the counts for PRISMA.
- `run_log.txt`: every request and its status code (keys are redacted).

## Layout

```
data/round1/          seeds and known records for round 1
examples/             small example inputs
src/slr_snowball/
  cli.py              command line
  pipeline.py         Snowballer, the actual snowballing
  models.py           Seed, Work, Candidate, CandidatePool etc
  duplicates.py       near-duplicate flags
  sources/            OpenAlex, Crossref and Semantic Scholar clients
  http.py             requests with retries and the call log
  files.py            reading/writing csv and json
tests/                tests, no network needed
```

To add another database, subclass `CitationSource` and implement `find`, `references`
and `citations`.

## Dev

```bash
uv run pytest
uv run ruff check
uv run ruff format
```

CI runs ruff, the tests on Python 3.10 to 3.13, and the tests inside the Nix shell.

## Limitations

- OpenAlex and Semantic Scholar keep changing, so a rerun can find more. Use the run
  date in `prisma_counts.json` when reporting.
- Crossref refs without a DOI are counted but not followed up.
- Some publishers hide reference lists from Semantic Scholar. If a seed has no reference
  list anywhere, go through the PDF by hand.
- No Google Scholar, there's no API for it.
- Without a key Semantic Scholar rate limits a lot. If a lookup still fails after the
  retries it's marked FAILED in `seed_resolution.csv` (not NOT FOUND) and listed under
  `seeds_with_failed_lookups`, so get a key and rerun.
