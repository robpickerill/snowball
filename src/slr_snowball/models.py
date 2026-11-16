"""Data objects shared by every source and by the pipeline."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from .text import normalise_doi, normalise_title

BACKWARD, FORWARD = "backward", "forward"


@dataclass(frozen=True)
class Seed:
    """An included study whose references and citations are followed."""

    id: str
    title: str
    doi: str = ""
    year: str = ""
    s2_id: str = ""  # optional Semantic Scholar paperId, skips the title search


@dataclass
class Work:
    """One paper, in the same shape whichever database it came from."""

    title: str = ""
    doi: str = ""
    year: int = 0
    date: str = ""
    venue: str = ""
    type: str = ""
    cited_by: int = 0
    abstract: str = ""
    ids: dict[str, str] = field(default_factory=dict)  # e.g. {"openalex": "W1", "s2": "ab12"}
    reference_ids: list[str] = field(default_factory=list)  # OpenAlex ids of its references

    def __post_init__(self) -> None:
        self.doi = normalise_doi(self.doi)

    @property
    def record_id(self) -> str:
        """A stable label for output files: OpenAlex id, else DOI, else Semantic Scholar id."""
        if "openalex" in self.ids:
            return self.ids["openalex"]
        if self.doi:
            return f"doi:{self.doi}"
        return (
            f"s2:{self.ids['s2']}"
            if "s2" in self.ids
            else f"title:{normalise_title(self.title)[:60]}"
        )

    def merge(self, other: Work) -> None:
        """Fill blanks from another record of the same paper."""
        for name in ("title", "doi", "year", "date", "venue", "type", "abstract"):
            if not getattr(self, name) and getattr(other, name):
                setattr(self, name, getattr(other, name))
        self.cited_by = max(self.cited_by, other.cited_by)
        for source, value in other.ids.items():
            self.ids.setdefault(source, value)
        if not self.reference_ids:
            self.reference_ids = list(other.reference_ids)


@dataclass
class Match:
    """The result of looking a seed up in one source."""

    work: Work | None
    method: str  # "doi", "title-match" or "NOT FOUND"
    score: float | None = None

    @property
    def found(self) -> bool:
        return self.work is not None

    @classmethod
    def not_found(cls, score: float | None = None) -> Match:
        return cls(None, "NOT FOUND", score)


@dataclass
class SeedReport:
    """How one seed was handled, for seed_resolution.csv."""

    seed: Seed
    openalex: Match = field(default_factory=Match.not_found)
    s2: Match | None = None  # None = Semantic Scholar not used for this seed
    links: dict[str, int] = field(default_factory=dict)  # "openalex_backward" -> count
    notes: list[str] = field(default_factory=list)  # anything that went wrong

    def to_row(self) -> dict:
        oa = self.openalex.work or Work()
        s2 = (self.s2.work if self.s2 else None) or Work()
        return {
            "id": self.seed.id,
            "title": self.seed.title,
            "openalex_match": self.openalex.method,
            "openalex_score": "" if self.openalex.score is None else f"{self.openalex.score:.2f}",
            "openalex": oa.ids.get("openalex", ""),
            "openalex_title": oa.title,
            "s2_match": self.s2.method if self.s2 else "not used",
            "s2": s2.ids.get("s2", ""),
            "links": ";".join(f"{k}={v}" for k, v in sorted(self.links.items())),
            "notes": "; ".join(self.notes),
        }


class KnownRecords:
    """Records already screened (by DOI or title), so they are not screened twice."""

    def __init__(self, records: Iterable[dict] = ()) -> None:
        self._by_doi: dict[str, str] = {}
        self._by_title: dict[str, str] = {}
        for record in records:
            source = record.get("source") or "known"
            if record.get("doi"):
                self._by_doi[normalise_doi(record["doi"])] = source
            if record.get("title"):
                self._by_title[normalise_title(record["title"])] = source

    def match(self, work: Work) -> str | None:
        """Return the source label of a matching known record, or None."""
        if work.doi and work.doi in self._by_doi:
            return self._by_doi[work.doi]
        return self._by_title.get(normalise_title(work.title))


@dataclass(frozen=True)
class DateWindow:
    """Inclusive publication window, e.g. 2018 to 2026-08-31."""

    year_min: int
    date_max: str  # YYYY-MM-DD

    def contains(self, work: Work) -> bool:
        if not work.year and not work.date:
            return True
        if work.year < self.year_min:
            return False
        return work.date <= self.date_max if work.date else work.year <= int(self.date_max[:4])


@dataclass
class Candidate:
    """A paper linked to one or more seeds, with how it was found."""

    work: Work
    seeds: set = field(default_factory=set)
    directions: set = field(default_factory=set)  # "backward", "forward"
    sources: set = field(default_factory=set)  # "openalex", "crossref", "s2"

    def add_link(self, seed_id: str, direction: str, source: str) -> None:
        self.seeds.add(seed_id)
        self.directions.add(direction)
        self.sources.add(source)


class CandidatePool:
    """Collects candidates and merges records of the same paper from different sources.

    Two records are the same paper if they share a DOI, an OpenAlex id, a Semantic
    Scholar id, or an identical normalised title with publication years at most one apart.
    """

    MIN_TITLE_KEY = 20  # very short titles ("Introduction") are too generic to match on

    def __init__(self) -> None:
        self._candidates: list[Candidate] = []
        self._index: dict[str, Candidate] = {}

    def __len__(self) -> int:
        return len(self._candidates)

    def __iter__(self) -> Iterator[Candidate]:
        return iter(self._candidates)

    @classmethod
    def keys(cls, work: Work) -> list[str]:
        keys = [f"doi:{work.doi}"] if work.doi else []
        keys += [f"{source}:{value}" for source, value in work.ids.items()]
        title = normalise_title(work.title)
        if len(title) >= cls.MIN_TITLE_KEY:
            keys.append(f"title:{title}")
        return keys

    def find(self, work: Work) -> Candidate | None:
        for key in self.keys(work):
            found = self._index.get(key)
            if found is None:
                continue
            years_apart = abs(work.year - found.work.year) if work.year and found.work.year else 0
            if key.startswith("title:") and years_apart > 1:
                continue  # same title, different paper
            return found
        return None

    def add(self, work: Work, seed_id: str, direction: str, source: str) -> Candidate:
        candidate = self.find(work)
        if candidate is None:
            candidate = Candidate(work)
            self._candidates.append(candidate)
        else:
            candidate.work.merge(work)
        candidate.add_link(seed_id, direction, source)
        self._reindex(candidate)
        return candidate

    def update(self, work: Work) -> bool:
        """Merge extra metadata into an existing candidate. Returns False if none matches."""
        candidate = self.find(work)
        if candidate is None:
            return False
        candidate.work.merge(work)
        self._reindex(candidate)
        return True

    def discard_matching(self, works: Iterable[Work]) -> int:
        """Remove candidates that are really seeds. Returns how many were removed."""
        drop = {id(c) for c in (self.find(w) for w in works) if c is not None}
        self._candidates = [c for c in self._candidates if id(c) not in drop]
        self._index = {k: c for k, c in self._index.items() if id(c) not in drop}
        return len(drop)

    def _reindex(self, candidate: Candidate) -> None:
        for key in self.keys(candidate.work):
            self._index.setdefault(key, candidate)
