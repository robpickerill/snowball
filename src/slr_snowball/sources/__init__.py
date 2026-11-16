"""Bibliographic databases that the pipeline can query."""

from .base import CitationSource
from .crossref import CrossrefSource
from .openalex import OpenAlexSource
from .semantic_scholar import SemanticScholarSource

__all__ = ["CitationSource", "CrossrefSource", "OpenAlexSource", "SemanticScholarSource"]
