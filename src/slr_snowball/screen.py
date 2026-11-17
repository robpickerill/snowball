"""Command-line entry point: ``slr-screen``, keyword screening of ``candidates.csv``."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .files import _read_csv_with, _write_csv
from .keywords import EXCLUDED, KEYWORD_HIT, NO_ABSTRACT, KeywordRule, screen

SCREEN_COLUMNS = [
    "keyword_status",
    "sampled",
    "your_decision",
    "record_id",
    "title",
    "year",
    "venue",
    "doi",
    "n_seeds",
    "seeds",
    "matched_terms",
    "abstract",
]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="slr-screen",
        description="Keep to-screen candidates whose title or abstract has a topic term and a "
        "context term.",
    )
    p.add_argument(
        "--candidates", type=Path, required=True, help="candidates.csv from slr-snowball"
    )
    p.add_argument("--terms", type=Path, required=True, help="TOML file with [topic] and [context]")
    p.add_argument("--out", type=Path, required=True, help="output folder")
    p.add_argument("--sample", type=int, default=0, help="excluded records to mark for a check")
    p.add_argument("--seed", type=int, help="random seed for --sample (required with it)")
    p.add_argument("--check", type=Path, help="CSV of known includes (title, abstract) to test")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.sample and args.seed is None:
        parser.error("--sample needs --seed")
    try:
        rule = KeywordRule.load(args.terms)
        rows = _read_csv_with(args.candidates, {"to_screen", "title", "abstract"})
        check = _read_csv_with(args.check, {"title", "abstract"}) if args.check else []
    except (ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 2

    screened = screen([r for r in rows if r["to_screen"] == "True"], rule, args.sample, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    _write_csv(
        args.out / "keyword_screen.csv",
        SCREEN_COLUMNS,
        ({c: r.get(c, "") for c in SCREEN_COLUMNS} for r in screened),
    )
    status = Counter(r["keyword_status"] for r in screened)
    counts = {
        "terms_file": str(args.terms),
        "to_screen": len(screened),
        "keyword_hit": status[KEYWORD_HIT],
        "manual_no_abstract": status[NO_ABSTRACT],
        "excluded_by_keywords": status[EXCLUDED],
        "sampled_from_excluded": sum(1 for r in screened if r["sampled"]),
        "sample_seed": args.seed,
    }
    (args.out / "keyword_counts.json").write_text(
        json.dumps(counts, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(counts, indent=2))

    if check:
        missed = [(rule.classify(r["title"], r["abstract"])[0], r["title"]) for r in check]
        missed = [m for m in missed if m[0] != KEYWORD_HIT]
        print(f"Check: {len(check) - len(missed)} of {len(check)} are keyword hits.")
        for s, title in missed:
            print(f"  {s}: {title}")
    return 0
