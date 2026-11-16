"""Crossref (https://api.crossref.org): the reference lists publishers deposit.

Crossref is used for backward snowballing only. References without a DOI are
counted but not followed up.
"""

from __future__ import annotations

from ..http import HttpClient
from ..models import Match, Seed, Work
from ..text import normalise_doi
from .base import CitationSource


class CrossrefSource(CitationSource):
    name = "crossref"
    BASE_URL = "https://api.crossref.org"

    def __init__(self, http: HttpClient, mailto: str | None = None) -> None:
        super().__init__()
        self.http = http
        self.mailto = mailto  # optional contact address for Crossref's "polite" pool
        self.unresolved = 0  # running count of references with no DOI

    def find(self, seed: Seed) -> Match:
        doi = normalise_doi(seed.doi)
        return Match(Work(title=seed.title, doi=doi), "doi") if doi else Match.not_found()

    def references(self, work: Work) -> list[Work]:
        if not work.doi:
            return []
        params = {"mailto": self.mailto} if self.mailto else None
        data = self.http.get_json(f"{self.BASE_URL}/works/{work.doi}", params)
        refs = ((data or {}).get("message") or {}).get("reference") or []
        found = []
        for ref in refs:
            if ref.get("DOI"):
                year = str(ref.get("year") or "")[:4]
                found.append(
                    Work(
                        title=ref.get("article-title") or "",
                        doi=ref["DOI"],
                        year=int(year) if year.isdigit() else 0,
                    )
                )
            else:
                self.unresolved += 1
        return found

    def citations(self, work: Work) -> list[Work]:
        return []  # Crossref's cited-by data is only open to the publisher who deposited it
