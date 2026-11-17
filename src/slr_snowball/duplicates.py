"""Flag likely duplicates that exact matching misses (e.g. preprint vs published)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from difflib import SequenceMatcher

from .models import Candidate
from .text import normalise_text


class DuplicateFinder:
    """Find candidates with near-identical titles published within ``max_year_gap`` years.

    It only flags pairs; nothing is merged, so the decision stays with the reviewer.
    """

    def __init__(self, threshold: float = 0.95, max_year_gap: int = 1) -> None:
        self.threshold = threshold
        self.max_year_gap = max_year_gap

    def find(self, candidates: Iterable[Candidate]) -> dict[str, list[str]]:
        """Map each flagged record_id to the record_ids it probably duplicates."""
        by_year: dict[int, list[Candidate]] = defaultdict(list)
        for candidate in candidates:
            by_year[candidate.work.year].append(candidate)

        flags: dict[str, set] = defaultdict(set)
        for year, group in by_year.items():
            nearby = [
                c for y in range(year, year + self.max_year_gap + 1) for c in by_year.get(y, [])
            ]
            for a in group:
                for b in nearby:
                    if a is b or (b.work.year == year and id(b) <= id(a)):
                        continue  # each pair is checked once
                    if self.similar(a.work.title, b.work.title):
                        flags[a.work.record_id].add(b.work.record_id)
                        flags[b.work.record_id].add(a.work.record_id)
        return {k: sorted(v) for k, v in flags.items()}

    def similar(self, title_a: str, title_b: str) -> bool:
        a, b = normalise_text(title_a), normalise_text(title_b)
        if not a or not b:
            return False
        m = SequenceMatcher(None, a, b)
        # cheap upper bounds first; the full ratio is only computed when they pass
        return (
            m.real_quick_ratio() >= self.threshold
            and m.quick_ratio() >= self.threshold
            and m.ratio() >= self.threshold
        )
