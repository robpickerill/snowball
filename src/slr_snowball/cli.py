"""Command-line entry point: ``slr-snowball`` (or ``python -m slr_snowball``)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import __version__
from .files import OutputWriter, read_known, read_seeds
from .http import ApiError, HttpClient
from .models import DateWindow
from .pipeline import S2_ALL, S2_FALLBACK, S2_OFF, Snowballer
from .sources import CrossrefSource, OpenAlexSource, SemanticScholarSource


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="slr-snowball",
        description="Backward and forward citation snowballing with OpenAlex, Crossref and "
        "Semantic Scholar.",
    )
    p.add_argument(
        "--seeds", type=Path, required=True, help="CSV of included studies: id,title,doi"
    )
    p.add_argument("--known", type=Path, help="CSV of records already screened: source,title,doi")
    p.add_argument("--out", type=Path, default=Path("snowball_out"), help="output folder")
    p.add_argument("--year-min", type=int, default=2018, help="earliest publication year kept")
    p.add_argument("--date-max", default="2026-08-31", help="latest publication date kept")
    p.add_argument(
        "--title-threshold",
        type=float,
        default=0.90,
        help="minimum title similarity when a seed is matched by title",
    )
    p.add_argument(
        "--s2",
        choices=[S2_FALLBACK, S2_ALL, S2_OFF],
        default=S2_FALLBACK,
        help="when to use Semantic Scholar (default: only where OpenAlex has gaps)",
    )
    p.add_argument("--no-crossref", action="store_true", help="skip the Crossref reference check")
    p.add_argument("--crossref-mailto", help="contact e-mail for Crossref's polite pool (optional)")
    p.add_argument(
        "--pause", type=float, default=0.0, help="seconds to wait after each OpenAlex/Crossref call"
    )
    p.add_argument(
        "--s2-pause",
        type=float,
        default=None,
        help="seconds between Semantic Scholar calls (default 1 with a key, 3 without)",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    openalex_key = os.environ.get("OPENALEX_API_KEY", "")
    if not openalex_key:
        print("Set OPENALEX_API_KEY (free key from openalex.org).", file=sys.stderr)
        return 2
    s2_key = os.environ.get("S2_API_KEY") or None

    log: list[str] = []
    http = HttpClient(pause=args.pause, log=log)
    s2_pause = args.s2_pause if args.s2_pause is not None else (1.0 if s2_key else 3.0)
    s2_http = HttpClient(pause=s2_pause, max_tries=8, log=log)

    snowballer = Snowballer(
        openalex=OpenAlexSource(http, openalex_key, args.title_threshold),
        crossref=None if args.no_crossref else CrossrefSource(http, args.crossref_mailto),
        semantic_scholar=SemanticScholarSource(s2_http, s2_key, args.title_threshold),
        s2_mode=args.s2,
        known=read_known(args.known) if args.known else None,
        window=DateWindow(args.year_min, args.date_max),
    )
    sources = ["OpenAlex (backward, forward)"]
    if not args.no_crossref:
        sources.append("Crossref (backward)")
    if args.s2 != S2_OFF:
        sources.append(f"Semantic Scholar (backward, forward; mode={args.s2})")
    run_info = {
        "run_date": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "tool_version": __version__,
        "sources": sources,
        "date_window": [args.year_min, args.date_max],
    }

    try:
        result = snowballer.run(read_seeds(args.seeds))
    except ApiError as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1

    counts = OutputWriter(args.out).write(result, run_info, log)
    print(json.dumps(counts, indent=2))
    failed = [r.seed.id for r in result.reports if r.notes]
    missing = [
        r.seed.id
        for r in result.reports
        if not r.openalex.found and not (r.s2 and r.s2.found) and not r.notes
    ]
    if missing:
        print(f"Seeds not found anywhere: {', '.join(missing)}", file=sys.stderr)
    if failed:
        print(
            f"Lookups failed for seeds {', '.join(failed)} (rate limited). "
            "Get a free Semantic Scholar key, set S2_API_KEY and run again.",
            file=sys.stderr,
        )
    return 0
