from slr_snowball.text import (
    natural_key,
    normalise_doi,
    normalise_text,
    rebuild_abstract,
    short_openalex_id,
    title_similarity,
)


def test_normalise_doi_strips_prefixes_and_case():
    assert normalise_doi("https://doi.org/10.1145/ABC") == "10.1145/abc"
    assert normalise_doi("http://dx.doi.org/10.1/x") == "10.1/x"
    assert normalise_doi("doi:10.1/x ") == "10.1/x"
    assert normalise_doi(None) == ""


def test_normalise_text_ignores_punctuation_and_spacing():
    assert normalise_text("  Breakwater: Overload  Control!") == "breakwater overload control"


def test_title_similarity():
    assert (
        title_similarity("Metastable Failures in the Wild", "metastable failures in the wild.")
        == 1.0
    )
    assert title_similarity("Metastable Failures in the Wild", "Protego") < 0.5


def test_rebuild_abstract_restores_word_order():
    assert rebuild_abstract({"world": [1], "Hello": [0], "again": [2]}) == "Hello world again"
    assert rebuild_abstract(None) == ""


def test_short_id_and_natural_sort():
    assert short_openalex_id("https://openalex.org/W123") == "W123"
    assert sorted(["10", "2", "a"], key=natural_key) == ["2", "10", "a"]
