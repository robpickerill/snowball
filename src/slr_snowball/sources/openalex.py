"""OpenAlex (https://docs.openalex.org). Needs a free API key."""

from __future__ import annotations

from collections.abc import Iterable

from ..http import HttpClient
from ..models import Match, Seed, Work
from ..text import normalise_doi, rebuild_abstract, short_openalex_id
from .base import CitationSource

FIELDS = (
    "id",
    "doi",
    "title",
    "publication_year",
    "publication_date",
    "type",
    "primary_location",
    "referenced_works",
    "abstract_inverted_index",
    "cited_by_count",
)


def parse_openalex(raw: dict) -> Work:
    source = (raw.get("primary_location") or {}).get("source") or {}
    return Work(
        title=raw.get("title") or "",
        doi=raw.get("doi") or "",
        year=raw.get("publication_year") or 0,
        date=raw.get("publication_date") or "",
        venue=source.get("display_name") or "",
        type=raw.get("type") or "",
        cited_by=raw.get("cited_by_count") or 0,
        abstract=rebuild_abstract(raw.get("abstract_inverted_index")),
        ids={"openalex": short_openalex_id(raw["id"])},
        reference_ids=[short_openalex_id(r) for r in raw.get("referenced_works") or []],
    )


class OpenAlexSource(CitationSource):
    name = "openalex"
    BASE_URL = "https://api.openalex.org"
    BATCH_SIZE = 50  # values allowed in one OR filter
    PAGE_SIZE = 200  # largest page OpenAlex returns

    def __init__(self, http: HttpClient, api_key: str, title_threshold: float = 0.90) -> None:
        super().__init__(title_threshold)
        if not api_key:
            raise ValueError("An OpenAlex API key is required (free from openalex.org).")
        self.http = http
        self.api_key = api_key

    def find(self, seed: Seed) -> Match:
        if seed.doi:
            raw = self._get(f"/works/doi:{normalise_doi(seed.doi)}")
            if raw:
                return Match(parse_openalex(raw), "doi")
        page = self._get("/works", search=seed.title, **{"per-page": 5})
        return self.best_title_match(
            seed, [parse_openalex(r) for r in (page or {}).get("results") or []]
        )

    def references(self, work: Work) -> list[Work]:
        return self._batched("openalex", work.reference_ids)

    def citations(self, work: Work) -> list[Work]:
        if "openalex" not in work.ids:
            return []
        results: list[Work] = []
        cursor: str | None = "*"
        while cursor:
            page = self._get(
                "/works",
                filter=f"cites:{work.ids['openalex']}",
                cursor=cursor,
                **{"per-page": self.PAGE_SIZE},
            )
            batch = (page or {}).get("results") or []
            if not batch:
                break
            results += [parse_openalex(r) for r in batch]
            cursor = page.get("meta", {}).get("next_cursor")
        return results

    def works_by_dois(self, dois: Iterable[str]) -> list[Work]:
        """Full records for a list of DOIs (used to fill in Crossref and Semantic Scholar hits)."""
        return self._batched("doi", [normalise_doi(d) for d in dois if d])

    def _batched(self, field: str, values: list[str]) -> list[Work]:
        results: list[Work] = []
        for start in range(0, len(values), self.BATCH_SIZE):
            chunk = "|".join(values[start : start + self.BATCH_SIZE])
            page = self._get("/works", filter=f"{field}:{chunk}", **{"per-page": self.BATCH_SIZE})
            results += [parse_openalex(r) for r in (page or {}).get("results") or []]
        return results

    def _get(self, path: str, **params) -> dict | None:
        params = {"select": ",".join(FIELDS), **params, "api_key": self.api_key}
        return self.http.get_json(self.BASE_URL + path, params)
