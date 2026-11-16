from slr_snowball.models import Seed, Work
from slr_snowball.sources import CrossrefSource, OpenAlexSource, SemanticScholarSource
from slr_snowball.sources.openalex import parse_openalex
from slr_snowball.sources.semantic_scholar import parse_s2


class FakeHttp:
    """Returns canned JSON by URL path; records every call."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, dict(params or {}), headers))
        return self.handler(url, params or {})


OA_RAW = {
    "id": "https://openalex.org/W9",
    "doi": "https://doi.org/10.1/X",
    "title": "A paper",
    "publication_year": 2021,
    "publication_date": "2021-03-01",
    "type": "article",
    "primary_location": {"source": {"display_name": "NSDI"}},
    "referenced_works": ["https://openalex.org/W1"],
    "cited_by_count": 4,
    "abstract_inverted_index": {"Hello": [0], "world": [1]},
}


def test_parse_openalex():
    work = parse_openalex(OA_RAW)
    assert (work.doi, work.venue, work.abstract) == ("10.1/x", "NSDI", "Hello world")
    assert work.ids == {"openalex": "W9"} and work.reference_ids == ["W1"]


def test_openalex_follows_cursor_and_sends_key():
    pages = {
        "*": {"results": [OA_RAW], "meta": {"next_cursor": "c2"}},
        "c2": {"results": [OA_RAW], "meta": {"next_cursor": None}},
    }
    http = FakeHttp(lambda url, p: pages[p["cursor"]])
    works = OpenAlexSource(http, "KEY").citations(Work(ids={"openalex": "W9"}))
    assert len(works) == 2 and len(http.calls) == 2
    assert all(call[1]["api_key"] == "KEY" for call in http.calls)


def test_openalex_falls_back_to_title_search():
    def handler(url, p):
        return None if "/works/doi:" in url else {"results": [OA_RAW]}

    match = OpenAlexSource(FakeHttp(handler), "KEY").find(Seed("1", "A paper", doi="10.1/missing"))
    assert match.method == "title-match" and match.score == 1.0


def test_crossref_counts_references_without_doi():
    data = {
        "message": {
            "reference": [
                {"DOI": "10.1/A", "article-title": "Ref A", "year": "2019"},
                {"unstructured": "Some book, 2001"},
            ]
        }
    }
    source = CrossrefSource(FakeHttp(lambda url, p: data))
    refs = source.references(Work(doi="10.1/seed"))
    assert [(r.doi, r.year) for r in refs] == [("10.1/a", 2019)]
    assert source.unresolved == 1
    assert source.citations(Work(doi="10.1/seed")) == []


def test_parse_s2():
    work = parse_s2(
        {
            "paperId": "p1",
            "externalIds": {"DOI": "10.1/Y"},
            "title": "T",
            "year": 2022,
            "publicationTypes": ["Conference"],
            "citationCount": 7,
        }
    )
    assert work.ids == {"s2": "p1"} and work.doi == "10.1/y" and work.type == "conference"


def test_semantic_scholar_pages_and_skips_withheld_entries():
    pages = {
        0: {
            "data": [
                {"citingPaper": {"paperId": "a", "title": "A"}},
                {"citingPaper": {"paperId": None}},
            ],
            "next": 1000,
        },
        1000: {"data": [{"citingPaper": {"paperId": "b", "title": "B"}}]},
    }
    http = FakeHttp(lambda url, p: pages[p["offset"]])
    works = SemanticScholarSource(http, api_key="K").citations(Work(ids={"s2": "seed"}))
    assert [w.ids["s2"] for w in works] == ["a", "b"]
    assert http.calls[0][2] == {"x-api-key": "K"}


def test_semantic_scholar_withheld_reference_list_comes_back_as_null():
    http = FakeHttp(lambda url, p: {"data": None})
    assert SemanticScholarSource(http).references(Work(ids={"s2": "seed"})) == []


def test_semantic_scholar_uses_known_paper_id_first():
    raw = {"paperId": "abc", "title": "Breakwater", "year": 2020}
    http = FakeHttp(lambda url, p: raw if url.endswith("/paper/abc") else None)
    match = SemanticScholarSource(http).find(Seed("57", "Breakwater", s2_id="abc"))
    assert match.method == "s2_id" and match.work.ids == {"s2": "abc"}
    assert len(http.calls) == 1
