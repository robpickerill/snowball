import json

from slr_snowball import cli

from conftest import FakeOpenAlex, paper


def write_seeds(tmp_path):
    seeds = tmp_path / "seeds.csv"
    seeds.write_text("id,title,doi\n1,Seed paper about overload,\n", encoding="utf-8")
    return seeds


def test_missing_api_key_exits_cleanly(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    assert cli.main(["--seeds", str(write_seeds(tmp_path))]) == 2
    assert "OPENALEX_API_KEY" in capsys.readouterr().err


def test_end_to_end_writes_all_outputs(tmp_path, monkeypatch):
    fake = FakeOpenAlex(
        [paper("S", "Seed paper about overload"), paper("C", "A paper citing the seed", 2024)],
        citations={"Seed paper about overload": ["A paper citing the seed"]},
    )
    monkeypatch.setenv("OPENALEX_API_KEY", "test-key")
    monkeypatch.setattr(cli, "OpenAlexSource", lambda http, key, threshold: fake)
    out = tmp_path / "out"
    code = cli.main(
        ["--seeds", str(write_seeds(tmp_path)), "--out", str(out), "--no-crossref", "--s2", "off"]
    )
    assert code == 0
    counts = json.loads((out / "prisma_counts.json").read_text())
    assert counts["unique_candidates"] == 1 and counts["to_screen"] == 1
    for name in ("candidates.csv", "seed_resolution.csv", "run_log.txt"):
        assert (out / name).exists()
