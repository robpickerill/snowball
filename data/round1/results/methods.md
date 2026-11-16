# Citation searching (snowballing), round 1

**Seeds:** all 37 included studies (rows 2 to 61 that passed full-text screening, including rows 56 and 59).
**Window:** publication year 2018 to 31 August 2026, matching the database searches.
**Run dates:** OpenAlex and Crossref queries 15/11/2026 14:27 UTC; gap-fill and merge 15/11/2026, completed 18:43 UTC.

## Sources and directions

| Source | Direction | Seeds covered |
|---|---|---|
| OpenAlex API | backward (referenced works) and forward (works citing the seed) | 31 seeds found in OpenAlex (30 by DOI, 1 by exact title) |
| Crossref REST API | backward (publisher-deposited reference lists, resolved to OpenAlex by DOI) | seeds with DOIs |
| Seed PDF reference lists, titles matched in OpenAlex (similarity ≥ 0.90) | backward | rows 35, 43, 44, 47, 54, 55, 56, 57 (no reference lists in OpenAlex, Crossref or Semantic Scholar) |
| Semantic Scholar Graph API | forward | rows 35, 43, 44, 47, 54, 55, 56, 57 |

**Why a gap-fill was needed.** Six core seeds published by USENIX or OpenReview have no DOI and are missing from OpenAlex: Rajomon (43), Defcon (44), PolicyShedder (47), Protego (54) and *Metastable Failures in the Wild* (55). Breakwater (57) is indexed, but with no references and 6 citing works, against 81 in Semantic Scholar. Rows 35 and 56 are indexed without reference lists. Without the gap-fill, the forward citations of the most-cited seeds would be missed.

## Counts (PRISMA 2020, "identification of studies via other methods: citation searching")

| | n |
|---|---|
| Records identified (unique, after de-duplication by DOI and normalised title) | 1192 |
| Already in the review pool or the earlier citation pass | 99 |
| Outside the date window | 483 |
| **Records to screen (title and abstract)** | **610** |
| of which have no abstract in any source | 83 |

## Limitations to report
- Reference lists are incomplete for some publishers. 585 Crossref references had no DOI and could not be resolved automatically.
- PDF-parsed references were matched by title only. References to web pages, incident reports and software were not matched.
- Citation counts grow over time. The run date above fixes what was found.
- Semantic Scholar was used only to fill gaps where OpenAlex lacks the seed.

## Next steps
Screen the 610 records on title and abstract against IC1 to IC7 and EC1 to EC4. Add includes to Rayyan as a separate source ("citation searching"), then do full-text screening and extraction. Repeat the search with any new includes as seeds until a round adds no new studies.
