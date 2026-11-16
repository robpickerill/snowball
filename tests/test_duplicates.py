from slr_snowball.duplicates import DuplicateFinder
from slr_snowball.models import Candidate, Work


def cand(rid, title, year):
    return Candidate(Work(title=title, year=year, ids={"openalex": rid}))


def test_flags_preprint_and_published_version():
    found = DuplicateFinder().find(
        [
            cand("W1", "Metastable failures in distributed systems: a study", 2022),
            cand("W2", "Metastable failures in distributed systems - a study.", 2023),
            cand("W3", "Something else entirely about caches", 2022),
        ]
    )
    assert found == {"W1": ["W2"], "W2": ["W1"]}


def test_ignores_similar_titles_far_apart_in_time():
    found = DuplicateFinder().find(
        [
            cand("W1", "Overload control at scale", 2018),
            cand("W2", "Overload control at scale", 2024),
        ]
    )
    assert found == {}


def test_threshold_is_respected():
    finder = DuplicateFinder(threshold=0.95)
    assert not finder.similar(
        "Overload control for microservices", "Overload control for databases"
    )
