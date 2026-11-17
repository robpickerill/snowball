"""Reading the input CSVs and writing the output files."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Sequence
from pathlib import Path

from .models import KnownRecords, Seed
from .pipeline import SnowballResult

CANDIDATE_COLUMNS = [
    "record_id",
    "openalex",
    "s2",
    "doi",
    "title",
    "year",
    "date",
    "venue",
    "type",
    "cited_by",
    "direction",
    "found_by",
    "n_seeds",
    "seeds",
    "already_screened",
    "in_date_window",
    "to_screen",
    "possible_duplicate_of",
    "abstract",
]
SEED_COLUMNS = [
    "id",
    "title",
    "openalex_match",
    "openalex_score",
    "openalex",
    "openalex_title",
    "s2_match",
    "s2",
    "links",
    "notes",
]


def read_csv(path: Path, columns: set[str]) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        missing = columns - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing column(s): {', '.join(sorted(missing))}")
        return list(reader)


def read_seeds(path: Path) -> list[Seed]:
    """CSV with columns id, title, doi. Optional: year, s2_id. doi may be blank."""
    rows = read_csv(path, {"id", "title", "doi"})
    return [
        Seed(
            id=r["id"].strip(),
            title=r["title"].strip(),
            doi=(r.get("doi") or "").strip(),
            year=(r.get("year") or "").strip(),
            s2_id=(r.get("s2_id") or "").strip(),
        )
        for r in rows
    ]


def read_known(path: Path) -> KnownRecords:
    """CSV with columns source, title, doi (other columns are ignored)."""
    return KnownRecords(read_csv(path, {"source", "title", "doi"}))


def write_csv(path: Path, columns: Sequence[str], rows: Iterable[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)


RIS_TYPES = {
    "conference-paper": "CONF",
    "conference": "CONF",
    "article": "JOUR",
    "journalarticle": "JOUR",
    "review": "JOUR",
    "editorial": "JOUR",
    "preprint": "UNPB",
    "book": "BOOK",
    "book-chapter": "CHAP",
    "dissertation": "THES",
    "report": "RPRT",
}


def write_ris(path: Path, rows: Iterable[dict]) -> None:
    """One RIS record per row, keyword status and sampling as KW tags, matched terms as N1."""
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            tags = [
                ("TY", RIS_TYPES.get(r.get("type", ""), "GEN")),
                ("AN", r.get("record_id", "")),
                ("TI", r["title"]),
                ("PY", r.get("year", "")),
                ("T2", r.get("venue", "")),
                ("DO", r.get("doi", "")),
                ("KW", r["keyword_status"]),
                ("KW", "sampled" if r["sampled"] else ""),
                ("N1", r["matched_terms"]),
                ("AB", r["abstract"]),
            ]
            for tag, value in tags:
                if value := " ".join(str(value).split()):
                    f.write(f"{tag}  - {value}\n")
            f.write("ER  - \n")


class OutputWriter:
    """Writes candidates.csv, seed_resolution.csv, prisma_counts.json and run_log.txt."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def write(self, result: SnowballResult, run_info: dict, call_log: Sequence[str]) -> dict:
        write_csv(self.out_dir / "candidates.csv", CANDIDATE_COLUMNS, result.rows)
        write_csv(
            self.out_dir / "seed_resolution.csv", SEED_COLUMNS, (r.to_row() for r in result.reports)
        )
        counts = {**run_info, **result.counts()}
        (self.out_dir / "prisma_counts.json").write_text(
            json.dumps(counts, indent=2) + "\n", encoding="utf-8"
        )
        log = f"Run {run_info.get('run_date', '')}\n" + "\n".join(call_log) + "\n"
        (self.out_dir / "run_log.txt").write_text(log, encoding="utf-8")
        return counts
