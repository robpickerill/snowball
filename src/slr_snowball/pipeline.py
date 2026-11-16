"""One round of snowballing: find seeds, follow links, merge, flag what to screen."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from .duplicates import DuplicateFinder
from .http import RetriesExhausted
from .models import (
    BACKWARD,
    FORWARD,
    Candidate,
    CandidatePool,
    DateWindow,
    KnownRecords,
    Match,
    Seed,
    SeedReport,
    Work,
)
from .sources import CitationSource, CrossrefSource, OpenAlexSource
from .text import natural_key

S2_FALLBACK, S2_ALL, S2_OFF = "fallback", "all", "off"
DEFAULT_WINDOW = DateWindow(2018, "2026-08-31")


@dataclass
class SnowballResult:
    reports: list[SeedReport]
    rows: list[dict]
    raw_links: dict[str, int] = field(default_factory=dict)
    seeds_dropped_from_candidates: int = 0

    def counts(self) -> dict:
        """Numbers for the PRISMA 2020 "citation searching" box."""
        return {
            "seeds": len(self.reports),
            "seeds_found_openalex": sum(r.openalex.found for r in self.reports),
            "seeds_found_semantic_scholar": sum(bool(r.s2 and r.s2.found) for r in self.reports),
            "raw_links": dict(sorted(self.raw_links.items())),
            "unique_candidates": len(self.rows),
            "already_screened": sum(1 for r in self.rows if r["already_screened"]),
            "outside_date_window": sum(
                1 for r in self.rows if not r["in_date_window"] and not r["already_screened"]
            ),
            "to_screen": sum(1 for r in self.rows if r["to_screen"]),
            "possible_duplicates_flagged": sum(1 for r in self.rows if r["possible_duplicate_of"]),
            "seeds_with_failed_lookups": [r.seed.id for r in self.reports if r.notes],
        }


class Snowballer:
    """Backward and forward snowballing from a list of seeds.

    OpenAlex is the main source. Crossref adds publisher reference lists. Semantic
    Scholar is used, by default, only where OpenAlex cannot find a seed or returns
    no references or no citations for it (``s2_mode="all"`` uses it for every seed).
    """

    def __init__(
        self,
        openalex: OpenAlexSource,
        crossref: CrossrefSource | None = None,
        semantic_scholar: CitationSource | None = None,
        s2_mode: str = S2_FALLBACK,
        known: KnownRecords | None = None,
        window: DateWindow | None = None,
        duplicates: DuplicateFinder | None = None,
    ) -> None:
        if s2_mode not in (S2_FALLBACK, S2_ALL, S2_OFF):
            raise ValueError(f"s2_mode must be fallback, all or off, not {s2_mode!r}")
        self.openalex = openalex
        self.crossref = crossref
        self.s2 = semantic_scholar if s2_mode != S2_OFF else None
        self.s2_mode = s2_mode
        self.known = known or KnownRecords()
        self.window = window or DEFAULT_WINDOW
        self.duplicates = duplicates or DuplicateFinder()

    def run(self, seeds: Iterable[Seed]) -> SnowballResult:
        pool, raw = CandidatePool(), Counter()
        reports: list[SeedReport] = []
        seed_works: list[Work] = []

        for seed in seeds:
            report = self._snowball_seed(seed, pool, raw)
            reports.append(report)
            seed_works += [m.work for m in (report.openalex, report.s2) if m and m.found]

        dropped = pool.discard_matching(seed_works)  # seeds citing each other are not candidates
        self._fill_from_openalex(pool)
        flags = self.duplicates.find(list(pool))
        rows = [self._row(c, flags) for c in pool]
        rows.sort(key=lambda r: (not r["to_screen"], -r["n_seeds"], -r["year"]))
        return SnowballResult(reports, rows, dict(raw), dropped)

    def _snowball_seed(self, seed: Seed, pool: CandidatePool, raw: Counter) -> SeedReport:
        report = SeedReport(seed, self.openalex.find(seed))
        oa_refs: list[Work] = []
        oa_cits: list[Work] = []

        if report.openalex.found:
            work = report.openalex.work
            oa_refs = self.openalex.references(work)
            oa_cits = self.openalex.citations(work)
            self._link(pool, raw, report, oa_refs, BACKWARD, "openalex")
            self._link(pool, raw, report, oa_cits, FORWARD, "openalex")

        if self.crossref:
            target = (
                report.openalex.work if report.openalex.found else self.crossref.find(seed).work
            )
            if target and target.doi:
                before = self.crossref.unresolved
                self._link(
                    pool, raw, report, self.crossref.references(target), BACKWARD, "crossref"
                )
                raw["crossref_refs_without_doi"] += self.crossref.unresolved - before

        if self.s2:
            want_refs = self.s2_mode == S2_ALL or not oa_refs
            want_cits = self.s2_mode == S2_ALL or not oa_cits
            if want_refs or want_cits:
                self._use_semantic_scholar(seed, report, pool, raw, want_refs, want_cits)
        return report

    def _use_semantic_scholar(
        self,
        seed: Seed,
        report: SeedReport,
        pool: CandidatePool,
        raw: Counter,
        want_refs: bool,
        want_cits: bool,
    ) -> None:
        """Ask Semantic Scholar. If it keeps rate limiting, note it and carry on."""
        try:
            report.s2 = self.s2.find(seed)
            if not report.s2.found:
                return
            if want_refs:
                refs = self.s2.references(report.s2.work)
                self._link(pool, raw, report, refs, BACKWARD, "s2")
            if want_cits:
                cits = self.s2.citations(report.s2.work)
                self._link(pool, raw, report, cits, FORWARD, "s2")
        except RetriesExhausted:
            if report.s2 is None:
                report.s2 = Match(None, "FAILED")
            report.notes.append("semantic scholar failed (rate limited), rerun with S2_API_KEY")

    @staticmethod
    def _link(
        pool: CandidatePool,
        raw: Counter,
        report: SeedReport,
        works: list[Work],
        direction: str,
        source: str,
    ) -> None:
        key = f"{source}_{direction}"
        raw[key] += len(works)
        report.links[key] = report.links.get(key, 0) + len(works)
        for work in works:
            pool.add(work, report.seed.id, direction, source)

    def _fill_from_openalex(self, pool: CandidatePool) -> None:
        """Crossref and Semantic Scholar hits often lack abstracts: fetch OpenAlex records by DOI."""
        dois = [c.work.doi for c in pool if c.work.doi and "openalex" not in c.work.ids]
        for work in self.openalex.works_by_dois(dois):
            pool.update(work)

    def _row(self, candidate: Candidate, flags: dict[str, list[str]]) -> dict:
        work = candidate.work
        already = self.known.match(work) or ""
        in_window = self.window.contains(work)
        return {
            "record_id": work.record_id,
            "openalex": work.ids.get("openalex", ""),
            "s2": work.ids.get("s2", ""),
            "doi": work.doi,
            "title": work.title,
            "year": work.year,
            "date": work.date,
            "venue": work.venue,
            "type": work.type,
            "cited_by": work.cited_by,
            "direction": ";".join(sorted(candidate.directions)),
            "found_by": ";".join(sorted(candidate.sources)),
            "n_seeds": len(candidate.seeds),
            "seeds": ";".join(sorted(candidate.seeds, key=natural_key)),
            "already_screened": already,
            "in_date_window": in_window,
            "to_screen": in_window and not already,
            "possible_duplicate_of": ";".join(flags.get(work.record_id, [])),
            "abstract": work.abstract[:3000],
        }
