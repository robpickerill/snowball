"""The interface every source implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from ..models import Match, Seed, Work
from ..text import title_similarity


class CitationSource(ABC):
    """A database that can find a paper and list its references and citing papers."""

    name: str = "source"

    def __init__(self, title_threshold: float = 0.90) -> None:
        self.title_threshold = title_threshold

    @abstractmethod
    def find(self, seed: Seed) -> Match:
        """Locate the seed, by DOI first and then by title."""

    @abstractmethod
    def references(self, work: Work) -> list[Work]:
        """Papers the work cites (backward snowballing)."""

    @abstractmethod
    def citations(self, work: Work) -> list[Work]:
        """Papers that cite the work (forward snowballing)."""

    def best_title_match(self, seed: Seed, works: Sequence[Work]) -> Match:
        """Pick the closest title; accept it only above the threshold."""
        best, score = None, 0.0
        for work in works:
            s = title_similarity(seed.title, work.title)
            if s > score:
                best, score = work, s
        if best is not None and score >= self.title_threshold:
            return Match(best, "title-match", score)
        return Match.not_found(score or None)
