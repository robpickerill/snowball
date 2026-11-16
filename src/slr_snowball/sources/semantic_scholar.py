"""Semantic Scholar Graph API (https://api.semanticscholar.org).

Covers venues OpenAlex misses (USENIX, OpenReview). Works without a key but is
heavily rate-limited, so pace calls; a free key raises the limit.
"""

from __future__ import annotations

from ..http import HttpClient
from ..models import Match, Seed, Work
from ..text import normalise_doi
from .base import CitationSource

FIELDS = (
    "paperId,externalIds,title,year,publicationDate,venue,publicationTypes,citationCount,abstract"
)


def parse_s2(raw: dict) -> Work:
    types = raw.get("publicationTypes") or []
    return Work(
        title=raw.get("title") or "",
        doi=(raw.get("externalIds") or {}).get("DOI") or "",
        year=raw.get("year") or 0,
        date=raw.get("publicationDate") or "",
        venue=raw.get("venue") or "",
        type=types[0].lower() if types else "",
        cited_by=raw.get("citationCount") or 0,
        abstract=raw.get("abstract") or "",
        ids={"s2": raw["paperId"]},
    )


class SemanticScholarSource(CitationSource):
    name = "s2"
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    PAGE_SIZE = 1000

    def __init__(
        self, http: HttpClient, api_key: str | None = None, title_threshold: float = 0.90
    ) -> None:
        super().__init__(title_threshold)
        self.http = http
        self.headers = {"x-api-key": api_key} if api_key else None

    def find(self, seed: Seed) -> Match:
        if seed.s2_id:
            raw = self._get(f"/paper/{seed.s2_id}", fields=FIELDS)
            if raw and raw.get("paperId"):
                return Match(parse_s2(raw), "s2_id")
        if seed.doi:
            raw = self._get(f"/paper/DOI:{normalise_doi(seed.doi)}", fields=FIELDS)
            if raw and raw.get("paperId"):
                return Match(parse_s2(raw), "doi")
        page = self._get("/paper/search", query=seed.title, fields=FIELDS, limit=5)
        hits = [parse_s2(r) for r in (page or {}).get("data") or [] if r.get("paperId")]
        return self.best_title_match(seed, hits)

    def references(self, work: Work) -> list[Work]:
        return self._linked(work, "references", "citedPaper")

    def citations(self, work: Work) -> list[Work]:
        return self._linked(work, "citations", "citingPaper")

    def _linked(self, work: Work, endpoint: str, key: str) -> list[Work]:
        if "s2" not in work.ids:
            return []
        results: list[Work] = []
        offset: int | None = 0
        while offset is not None:
            page = self._get(
                f"/paper/{work.ids['s2']}/{endpoint}",
                fields=FIELDS,
                offset=offset,
                limit=self.PAGE_SIZE,
            )
            if not page:
                break
            # publishers can withhold lists: entries then come back empty
            results += [
                parse_s2(item[key])
                for item in page.get("data") or []
                if (item.get(key) or {}).get("paperId")
            ]
            offset = page.get("next")
        return results

    def _get(self, path: str, **params) -> dict | None:
        return self.http.get_json(self.BASE_URL + path, params, headers=self.headers)
