from slr_snowball.http import RetriesExhausted
from slr_snowball.models import DateWindow, KnownRecords, Seed, Work
from slr_snowball.pipeline import Snowballer

from conftest import SEEDS, FakeSource, paper


def by_title(result):
    return {r["title"]: r for r in result.rows}


def test_openalex_only(openalex):
    result = Snowballer(openalex, s2_mode="off").run(SEEDS[:2])
    rows = by_title(result)
    assert "Metastable failures in the cloud" not in rows  # seeds are never candidates
    assert rows["Admission control at scale"]["seeds"] == "1;2"  # one row, both seeds
    assert rows["Detecting metastable states early"]["n_seeds"] == 2
    assert result.seeds_dropped_from_candidates == 2


def test_semantic_scholar_only_fills_gaps(openalex, s2):
    result = Snowballer(openalex, semantic_scholar=s2).run(SEEDS)
    assert s2.find_calls == ["3"]  # seeds 1 and 2 had OpenAlex links, so S2 was not asked
    rows = by_title(result)
    c1 = rows["Detecting metastable states early"]
    assert c1["found_by"] == "openalex;s2" and c1["seeds"] == "1;2;3"  # merged across sources
    assert rows["A citing paper only Semantic Scholar knows"]["found_by"] == "s2"


def test_semantic_scholar_all_mode(openalex, s2):
    Snowballer(openalex, semantic_scholar=s2, s2_mode="all").run(SEEDS)
    assert s2.find_calls == ["1", "2", "3"]


def test_crossref_adds_missed_references_and_openalex_fills_details(openalex):
    crossref = FakeSource(
        "crossref",
        [Work(title="Found only through Crossref references", doi="10.1/x1", year=2021)],
        references={"Metastable failures in the cloud": ["Found only through Crossref references"]},
    )
    crossref.unresolved = 0
    result = Snowballer(openalex, crossref=crossref, s2_mode="off").run(SEEDS[:1])
    row = by_title(result)["Found only through Crossref references"]
    assert row["found_by"] == "crossref"
    assert row["openalex"] == "X1" and row["abstract"] == "An abstract"  # filled from OpenAlex


def test_window_known_records_and_counts(openalex):
    known = KnownRecords([{"source": "rayyan", "title": "Queueing models of retry storms"}])
    result = Snowballer(
        openalex, s2_mode="off", known=known, window=DateWindow(2018, "2026-08-31")
    ).run(SEEDS[:2])
    rows = by_title(result)
    assert rows["Queueing models of retry storms"]["already_screened"] == "rayyan"
    assert not rows["A classic queueing paper from the seventies"]["in_date_window"]
    assert not rows["A paper published after the window"]["in_date_window"]
    counts = result.counts()
    assert counts["unique_candidates"] == 5
    assert counts["seeds_dropped_from_candidates"] == 2
    assert (counts["already_screened"], counts["outside_date_window"], counts["to_screen"]) == (
        1,
        2,
        2,
    )
    assert [r["to_screen"] for r in result.rows] == sorted(
        (r["to_screen"] for r in result.rows), reverse=True
    )


def test_possible_duplicates_are_flagged_not_merged():
    oa = FakeSource(
        "openalex",
        [
            paper("S", "Seed paper about overload"),
            paper("A", "Metastable failures in distributed systems", 2022),
            paper("B", "Metastable failures in distributed system", 2023),
        ],
        citations={
            "Seed paper about overload": [
                "Metastable failures in distributed systems",
                "Metastable failures in distributed system",
            ]
        },
    )
    oa.works_by_dois = lambda dois: []

    result = Snowballer(oa, s2_mode="off").run([Seed("1", "Seed paper about overload")])
    flags = {r["openalex"]: r["possible_duplicate_of"] for r in result.rows}
    assert flags == {"A": "B", "B": "A"}


def test_rate_limited_semantic_scholar_is_reported_not_hidden(openalex, s2):
    def refuse(seed):
        raise RetriesExhausted("429")

    s2.find = refuse
    result = Snowballer(openalex, semantic_scholar=s2).run(SEEDS)
    report = result.reports[2]
    assert report.s2.method == "FAILED" and "rate limited" in report.notes[0]
    assert result.counts()["seeds_with_failed_lookups"] == ["3"]
