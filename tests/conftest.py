"""Shared fakes: an in-memory library of papers and sources that read from it."""

from __future__ import annotations

import pytest

from slr_snowball.models import Match, Seed, Work
from slr_snowball.sources import CitationSource


def paper(key, title, year=2022, doi="", date="", s2=None, refs=(), abstract="An abstract"):
    """A Work as OpenAlex would return it (s2 id optional)."""
    ids = {"openalex": key}
    if s2:
        ids["s2"] = s2
    return Work(
        title=title,
        doi=doi,
        year=year,
        date=date or f"{year}-06-01",
        abstract=abstract,
        venue="Test Venue",
        ids=ids,
        reference_ids=list(refs),
    )


class FakeSource(CitationSource):
    """A source over a dict of works, with its own reference and citation maps."""

    def __init__(self, name, works, references=None, citations=None):
        super().__init__()
        self.name = name
        self.works = {w.title: w for w in works}
        self.refs = references or {}
        self.cits = citations or {}
        self.find_calls = []

    def find(self, seed: Seed) -> Match:
        self.find_calls.append(seed.id)
        work = self.works.get(seed.title)
        return Match(work, "doi" if seed.doi else "title-match") if work else Match.not_found()

    def references(self, work):
        return [self.works[t] for t in self.refs.get(work.title, [])]

    def citations(self, work):
        return [self.works[t] for t in self.cits.get(work.title, [])]


class FakeOpenAlex(FakeSource):
    def __init__(self, works, references=None, citations=None):
        super().__init__("openalex", works, references, citations)

    def works_by_dois(self, dois):
        return [w for w in self.works.values() if w.doi in set(dois)]


SEEDS = [
    Seed("1", "Metastable failures in the cloud", doi="10.1/s1"),
    Seed("2", "Overload control for microservices"),
    Seed("3", "A USENIX paper missing from OpenAlex"),
]


@pytest.fixture
def openalex():
    works = [
        paper("S1", "Metastable failures in the cloud", doi="10.1/s1"),
        paper("S2", "Overload control for microservices"),
        paper("R1", "Queueing models of retry storms", 2019),
        paper("R2", "Admission control at scale", 2020, doi="10.1/r2"),
        paper("OLD", "A classic queueing paper from the seventies", 1978),
        paper("C1", "Detecting metastable states early", 2025),
        paper("LATE", "A paper published after the window", 2026, date="2026-10-01"),
        paper("X1", "Found only through Crossref references", 2021, doi="10.1/x1"),
    ]
    return FakeOpenAlex(
        works,
        references={
            "Metastable failures in the cloud": [
                "Queueing models of retry storms",
                "Admission control at scale",
                "A classic queueing paper from the seventies",
            ],
            "Overload control for microservices": [
                "Admission control at scale",
                "Metastable failures in the cloud",
            ],
        },
        citations={
            "Metastable failures in the cloud": [
                "Detecting metastable states early",
                "A paper published after the window",
                "Overload control for microservices",
            ],
            "Overload control for microservices": ["Detecting metastable states early"],
        },
    )


@pytest.fixture
def s2():
    def s2paper(sid, title, year=2023, doi=""):
        return Work(title=title, year=year, doi=doi, ids={"s2": sid})

    works = [
        s2paper("p3", "A USENIX paper missing from OpenAlex", 2022),
        s2paper("p9", "Detecting metastable states early", 2025),  # same paper as C1
        s2paper("p10", "A citing paper only Semantic Scholar knows", 2024),
        s2paper("p11", "Admission control at scale", 2020, doi="10.1/r2"),  # same as R2
    ]
    return FakeSource(
        "s2",
        works,
        references={"A USENIX paper missing from OpenAlex": ["Admission control at scale"]},
        citations={
            "A USENIX paper missing from OpenAlex": [
                "Detecting metastable states early",
                "A citing paper only Semantic Scholar knows",
            ]
        },
    )
