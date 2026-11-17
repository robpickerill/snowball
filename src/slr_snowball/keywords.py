"""Keyword screening: keep a record whose title or abstract has a topic term and a context term."""

from __future__ import annotations

import random
import re
import tomllib
from collections.abc import Sequence
from pathlib import Path

from .text import normalise_title

KEYWORD_HIT = "keyword hit"
NO_ABSTRACT = "manual (no abstract)"
EXCLUDED = "excluded by keywords"
_ORDER = {KEYWORD_HIT: 0, NO_ABSTRACT: 1, EXCLUDED: 2}


def _pattern(term: str) -> re.Pattern:
    """`metastab*` matches word prefixes, `retry storm` whole words. Punctuation counts as a space."""
    words = normalise_title(term.removesuffix("*"))
    if not words:
        raise ValueError(f"empty keyword: {term!r}")
    return re.compile(r"\b" + re.escape(words) + ("" if term.endswith("*") else r"\b"))


def _groups(data: dict, side: str) -> dict[str, list[tuple[str, re.Pattern]]]:
    groups = data.get(side)
    if not isinstance(groups, dict) or not groups:
        raise ValueError(f"[{side}] must hold at least one group of terms")
    out = {}
    for name, terms in groups.items():
        if not isinstance(terms, list) or not terms or not all(isinstance(t, str) for t in terms):
            raise ValueError(f"[{side}] {name} must be a non-empty list of strings")
        out[name] = [(t, _pattern(t)) for t in terms]
    return out


class KeywordRule:
    """Loaded from a TOML file with a [topic] and a [context] table of named term lists."""

    def __init__(self, data: dict) -> None:
        if set(data) != {"topic", "context"}:
            raise ValueError("keywords file must have exactly [topic] and [context]")
        self.topic = _groups(data, "topic")
        self.context = _groups(data, "context")
        if clash := set(self.topic) & set(self.context):
            raise ValueError(f"group names used in both [topic] and [context]: {sorted(clash)}")

    @classmethod
    def load(cls, path: Path) -> KeywordRule:
        with open(path, "rb") as f:
            return cls(tomllib.load(f))

    def classify(self, title: str, abstract: str) -> tuple[str, str]:
        """Return (status, matched_terms) for one record."""
        text = normalise_title(f"{title} {abstract}")
        topic = _hits(self.topic, text)
        context = _hits(self.context, text)
        matched = "; ".join(f"{g}: {', '.join(t)}" for g, t in {**topic, **context}.items())
        if not abstract.strip():
            return NO_ABSTRACT, matched
        return (KEYWORD_HIT if topic and context else EXCLUDED), matched


def _hits(groups: dict[str, list[tuple[str, re.Pattern]]], text: str) -> dict[str, list[str]]:
    found = {name: [t for t, p in terms if p.search(text)] for name, terms in groups.items()}
    return {name: terms for name, terms in found.items() if terms}


def screen(
    rows: Sequence[dict], rule: KeywordRule, sample: int = 0, seed: int | None = None
) -> list[dict]:
    """Classify rows, mark a seeded random sample of the excluded ones, sort hits first."""
    out = []
    for row in rows:
        status, matched = rule.classify(row["title"], row["abstract"])
        out.append({**row, "keyword_status": status, "matched_terms": matched, "sampled": ""})
    excluded = [r for r in out if r["keyword_status"] == EXCLUDED]
    for r in random.Random(seed).sample(excluded, min(sample, len(excluded))):
        r["sampled"] = True
    return sorted(out, key=lambda r: _ORDER[r["keyword_status"]])
