# snowball

Citation snowballing for my systematic literature review on overload and metastable
failures in distributed systems.

Takes the included papers (seeds), fetches what they cite (backward) and what cites them
(forward), merges results across databases, and drops anything already screened or outside
the date window. Outputs the list to screen and the counts for the PRISMA "citation
searching" box. Every API call is logged so the search can be rerun.

## Run

```bash
uv sync
export OPENALEX_API_KEY=...   # required, free at https://openalex.org/settings/api
export S2_API_KEY=...         # optional, Semantic Scholar is heavily rate limited without it
uv run slr-snowball --seeds data/round1/seeds.csv --known data/round1/known_records.csv --out round1
```

`nix develop` gives Python, uv and ruff. `uv run slr-snowball -h` lists every option.

## Input

`seeds.csv`: papers to snowball from. Columns `id`, `title`, `doi` (may be blank) are
required. `s2_id` is optional, for seeds OpenAlex lacks: the id at the end of the paper's
semanticscholar.org URL.

```csv
id,title,year,doi,s2_id
2,Vicious Cycles in Distributed Software Systems,2023,10.1109/ASE56229.2023.00032,
57,Overload Control for us-scale RPCs with Breakwater,2020,,2b74469f0bedfe0e9fbb241af8fbfdbeacfa8bce
```

`known_records.csv`: records already screened. Matched on `doi`, then on `title` after
lower-casing and stripping punctuation. `source` is copied into the output.

```csv
source,ref,title,doi
rayyan_pool,14,Metastable failures in distributed systems,10.1145/3458336.3465286
```

Each round: append the last round's screened records to `known_records.csv` and use the
newly included papers as seeds.

`data/round1` holds 37 seeds (7 without a DOI, 10 with an `s2_id`), 175 known records
(62 from Rayyan full-text screening, 113 from a manual first snowball pass), the 37 Rayyan
full-text includes for `--check` (`included.csv`) and the keyword terms (`keywords.toml`).

## Output

- `candidates.csv`: one row per paper with linked seeds, direction, source, `to_screen`,
  `possible_duplicate_of` and abstract. To-screen rows first, most-linked first.
- `seed_resolution.csv`: how each seed was found. Check NOT FOUND, FAILED and title-match.
- `prisma_counts.json`: run date and PRISMA counts.
- `run_log.txt`: every request and status code, keys redacted.

## Keyword screening

Cuts the `to_screen` rows of `candidates.csv` down to the ones worth reading.

```bash
uv run slr-screen --candidates round1/candidates.csv --terms data/round1/keywords.toml \
  --out round1 --sample 35 --seed 1
```

- A record is a hit if its title or abstract has a `[topic]` term and a `[context]` term.
- `metastab*` matches word starts, terms without `*` match whole words. Case and hyphens
  don't matter.
- Records without an abstract are `no abstract`. Screen these on title.
- `--sample 35 --seed 1` marks 35 excluded records in `sampled`, a spot check of what the
  filter lost.
- `--check data/round1/included.csv` (`title`, `abstract`) lists known includes that
  aren't hits.
- `--ris` also writes `keyword_screen.ris`: hits and `no abstract` records, for import into
  Rayyan as a new source. `KW` holds the status, `N1` the matched terms, `AN` the
  `record_id`. Decisions are made in Rayyan, not in `decision`.

Outputs `keyword_screen.csv` (`hit`, then `no abstract`, then `excluded`, with
`matched_terms` and an empty `decision`) and `keyword_counts.json` for the PRISMA
"excluded by automation tools" box. The terms file is frozen before screening and cited in
the methods.

## Sources and merging

- OpenAlex: main source, backward and forward.
- Crossref: publisher reference lists, backward only.
- Semantic Scholar: by default only for seeds where OpenAlex finds nothing, or no
  references or citations. `--s2 all` or `--s2 off` to change.

Records sharing a DOI, OpenAlex id, Semantic Scholar id, or normalised title (years at most
one apart) merge into one row. Titles 95%+ similar are flagged in `possible_duplicate_of`,
not merged.

## Limitations

- Databases change, so reruns can find more. Report the run date.
- Crossref references without a DOI are counted, not followed.
- Some publishers withhold reference lists. If no source has one, read the PDF.
- Semantic Scholar lookups that exhaust retries are marked FAILED. Get a key and rerun.
- No Google Scholar: no API.

## Development

```bash
uv run pytest
uv run ruff check
uv run ruff format
```

Tests need no network. To add a database, subclass `CitationSource` and implement `find`,
`references` and `citations`.
