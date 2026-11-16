"""Helpers for comparing titles and DOIs and for rebuilding OpenAlex abstracts."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher

_DOI_PREFIX = re.compile(r"^(https?://(dx\.)?doi\.org/|doi:)", re.IGNORECASE)


def normalise_doi(doi: str | None) -> str:
    """Return a bare, lower-case DOI ("10.1145/...") from any common form."""
    return _DOI_PREFIX.sub("", (doi or "").strip().lower())


def normalise_title(title: str | None) -> str:
    """Lower-case a title and reduce it to letters, digits and single spaces."""
    text = unicodedata.normalize("NFKC", title or "").lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def title_similarity(a: str | None, b: str | None) -> float:
    """Similarity of two titles after normalising, from 0.0 to 1.0."""
    return SequenceMatcher(None, normalise_title(a), normalise_title(b)).ratio()


def rebuild_abstract(inverted_index: Mapping[str, Sequence[int]] | None) -> str:
    """OpenAlex stores abstracts as {word: [positions]}. Put the words back in order."""
    positions = {}
    for word, indexes in (inverted_index or {}).items():
        for i in indexes:
            positions[i] = word
    return " ".join(positions[i] for i in sorted(positions))


def short_openalex_id(work_id: str) -> str:
    """Turn "https://openalex.org/W123" into "W123"."""
    return work_id.rsplit("/", 1)[-1]


def natural_key(value: str):
    """Sort key that puts "2" before "10" and copes with non-numeric ids."""
    return (0, int(value), "") if value.isdigit() else (1, 0, value)
