import csv
import json

import pytest

from slr_snowball import screen as screen_cli
from slr_snowball.keywords import EXCLUDED, KEYWORD_HIT, NO_ABSTRACT, KeywordRule, screen

RULE = KeywordRule(
    {
        "topic": {"F1": ["metastab*", "retry storm"], "capacity": ["autoscal*"]},
        "context": {"D": ["cloud*", "data center*"], "systems": ["api"]},
    }
)


def test_needs_a_topic_and_a_context_term():
    assert RULE.classify("Metastable failures in the cloud", "x")[0] == KEYWORD_HIT
    assert RULE.classify("Metastable failures", "in power grids")[0] == EXCLUDED
    assert RULE.classify("Cloud storage", "costs")[0] == EXCLUDED


def test_title_or_abstract_can_supply_either_term():
    assert RULE.classify("Autoscaling policies", "Evaluated on a public cloud.")[0] == KEYWORD_HIT


def test_terms_match_at_word_starts_only():
    assert RULE.classify("Retry storms in a cloud", "x")[0] == EXCLUDED  # no * on "retry storm"
    assert RULE.classify("A retry storm", "rapid metastable growth")[0] == EXCLUDED  # not "api"
    assert RULE.classify("A retry storm", "behind an API")[0] == KEYWORD_HIT
    assert RULE.classify("A retry storm", "drawn as a wordcloud")[0] == EXCLUDED


def test_hyphens_and_case_are_ignored():
    status, matched = RULE.classify("METASTABILITY in Data-Centers", "x")
    assert status == KEYWORD_HIT
    assert matched == "F1: metastab*; D: data center*"


def test_missing_abstract_goes_to_manual_even_on_a_title_hit():
    assert RULE.classify("Metastable failures in the cloud", " ") == (
        NO_ABSTRACT,
        "F1: metastab*; D: cloud*",
    )


@pytest.mark.parametrize(
    "data",
    [
        {"topic": {"F1": ["metastab*"]}},
        {"topic": {"F1": ["x"]}, "context": {}},
        {"topic": {"F1": []}, "context": {"D": ["cloud"]}},
        {"topic": {"F1": "metastab*"}, "context": {"D": ["cloud"]}},
        {"topic": {"F1": ["*"]}, "context": {"D": ["cloud"]}},
        {"topic": {"F1": ["x"]}, "context": {"F1": ["y"]}},
        {"topic": {"F1": ["x"]}, "context": {"D": ["y"]}, "extra": {}},
    ],
)
def test_malformed_keywords_file_is_rejected(data):
    with pytest.raises(ValueError):
        KeywordRule(data)


def rows(n):
    return [{"title": f"Paper {i}", "abstract": "about nothing"} for i in range(n)]


def test_sample_is_deterministic_and_only_from_excluded():
    pool = [{"title": "Metastable cloud", "abstract": "x"}, *rows(50)]
    picks = [
        [r["title"] for r in screen(pool, RULE, 10, seed) if r["sampled"]] for seed in (7, 7, 8)
    ]
    assert picks[0] == picks[1] and picks[0] != picks[2]
    assert len(picks[0]) == 10 and "Metastable cloud" not in picks[0]
    assert len([r for r in screen(rows(3), RULE, 10, 7) if r["sampled"]]) == 3


def test_output_is_sorted_hits_then_manual_then_excluded():
    pool = [
        {"title": "Nothing", "abstract": "x"},
        {"title": "Metastable cloud", "abstract": ""},
        {"title": "Metastable cloud", "abstract": "x"},
    ]
    assert [r["keyword_status"] for r in screen(pool, RULE)] == [KEYWORD_HIT, NO_ABSTRACT, EXCLUDED]


def write_csv(path, header, data):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(data)
    return path


def test_cli_screens_only_to_screen_rows_and_reports_check(tmp_path, capsys):
    candidates = write_csv(
        tmp_path / "candidates.csv",
        ["record_id", "title", "to_screen", "abstract"],
        [
            ["1", "Metastable failures in the cloud", "True", "x"],
            ["2", "Metastable failures in the cloud", "False", "x"],
            ["3", "Unrelated", "True", "x"],
            ["4", "Unrelated", "True", ""],
        ],
    )
    check = write_csv(
        tmp_path / "included.csv",
        ["title", "abstract"],
        [["Autoscaling in the cloud", "x"], ["FloodGuard", "Protects services."]],
    )
    out = tmp_path / "out"
    args = ["--candidates", str(candidates), "--terms", "data/round1/keywords.toml"]
    args += ["--out", str(out), "--sample", "5", "--seed", "1", "--check", str(check)]
    assert screen_cli.main(args) == 0

    counts = json.loads((out / "keyword_counts.json").read_text())
    assert (counts["to_screen"], counts["hit"], counts["excluded"]) == (3, 1, 1)
    assert counts["no_abstract"] == 1 and counts["sampled"] == 1
    with open(out / "keyword_screen.csv", newline="", encoding="utf-8-sig") as f:
        screened = list(csv.DictReader(f))
    assert [r["record_id"] for r in screened] == ["1", "4", "3"]
    assert screened[2]["sampled"] == "True" and screened[0]["decision"] == ""
    assert "1 of 2 are keyword hits" in capsys.readouterr().out


def test_cli_sample_without_seed_fails(tmp_path):
    with pytest.raises(SystemExit):
        screen_cli.main(["--candidates", "c", "--terms", "t", "--out", "o", "--sample", "5"])


def test_committed_keywords_file_loads():
    rule = KeywordRule.load("data/round1/keywords.toml")
    assert {"F1", "F2"} <= set(rule.topic) and "D" in rule.context
