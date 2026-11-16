from slr_snowball.models import CandidatePool, DateWindow, KnownRecords, Work


def test_work_normalises_doi_and_merges_blanks():
    a = Work(title="Breakwater", doi="https://doi.org/10.1/ABC", ids={"openalex": "W1"})
    b = Work(title="Breakwater", year=2020, abstract="text", ids={"s2": "p1"})
    a.merge(b)
    assert a.doi == "10.1/abc"
    assert a.year == 2020 and a.abstract == "text"
    assert a.ids == {"openalex": "W1", "s2": "p1"}
    assert a.record_id == "W1"


def test_date_window_is_inclusive():
    window = DateWindow(2018, "2026-08-31")
    assert window.contains(Work(year=2018, date="2018-01-01"))
    assert window.contains(Work(year=2026, date="2026-08-31"))
    assert not window.contains(Work(year=2026, date="2026-09-01"))
    assert not window.contains(Work(year=2017))
    assert window.contains(Work(year=2026))  # year only: kept if the year is inside


def test_known_records_match_by_doi_or_title():
    known = KnownRecords(
        [
            {"source": "rayyan", "doi": "https://doi.org/10.1/A", "title": ""},
            {"source": "round1", "doi": "", "title": "Some Paper: A Study"},
        ]
    )
    assert known.match(Work(doi="10.1/a")) == "rayyan"
    assert known.match(Work(title="some paper a study")) == "round1"
    assert known.match(Work(doi="10.9/z", title="unrelated")) is None


def test_pool_merges_same_paper_from_different_sources():
    pool = CandidatePool()
    pool.add(
        Work(title="Overload control for us-scale RPCs", doi="10.1/b", ids={"openalex": "W1"}),
        "1",
        "backward",
        "openalex",
    )
    pool.add(
        Work(title="Overload control for us-scale RPCs", doi="10.1/b", ids={"s2": "p1"}),
        "2",
        "forward",
        "s2",
    )
    pool.add(
        Work(title="Overload Control for us-Scale RPCs!", year=0, ids={"s2": "p2"}),
        "3",
        "forward",
        "s2",
    )
    assert len(pool) == 1
    only = next(iter(pool))
    assert only.seeds == {"1", "2", "3"} and only.sources == {"openalex", "s2"}


def test_pool_keeps_same_title_years_apart_separate():
    pool = CandidatePool()
    pool.add(
        Work(title="A survey of overload control methods", year=2015), "1", "backward", "openalex"
    )
    pool.add(
        Work(title="A survey of overload control methods", year=2024), "1", "forward", "openalex"
    )
    assert len(pool) == 2


def test_pool_discards_seeds():
    pool = CandidatePool()
    pool.add(
        Work(title="Seed paper title that is long enough", doi="10.1/s"), "2", "forward", "openalex"
    )
    pool.add(Work(title="Another candidate paper title", doi="10.1/c"), "2", "forward", "openalex")
    assert pool.discard_matching([Work(doi="10.1/s")]) == 1
    assert [c.work.doi for c in pool] == ["10.1/c"]


def test_date_window_keeps_unknown_dates():
    assert DateWindow(2018, "2026-08-31").contains(Work())
