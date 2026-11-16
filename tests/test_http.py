import pytest
import requests

from slr_snowball.http import ApiError, HttpClient, RetriesExhausted, redact


class FakeResponse:
    def __init__(
        self, status, payload=None, url="https://api.example.org/x?api_key=SECRET", headers=None
    ):
        self.status_code = status
        self._payload = payload
        self.url = url
        self.headers = headers or {}

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls += 1
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def client(responses):
    waits = []
    return HttpClient(session=FakeSession(responses), sleep=waits.append), waits


def test_redact_hides_key_and_email():
    assert redact("https://a.org/w?api_key=abc123&x=1") == "https://a.org/w?api_key=REDACTED&x=1"
    assert redact("https://a.org/w?mailto=me@uni.ac.uk") == "https://a.org/w?mailto=REDACTED"


def test_retries_on_429_using_retry_after_then_succeeds():
    http, waits = client(
        [FakeResponse(429, headers={"Retry-After": "3"}), FakeResponse(200, {"ok": 1})]
    )
    assert http.get_json("https://api.example.org/x") == {"ok": 1}
    assert waits == [3.0]
    assert len(http.log) == 2 and all("SECRET" not in line for line in http.log)


def test_network_error_is_retried():
    http, _ = client([requests.ConnectionError("down"), FakeResponse(200, {"ok": 1})])
    assert http.get_json("https://api.example.org/x") == {"ok": 1}
    assert http.log[0].startswith("ERR")


def test_404_returns_none_without_retry():
    http, waits = client([FakeResponse(404)])
    assert http.get_json("https://api.example.org/x") is None
    assert waits == []


def test_bad_key_raises():
    http, _ = client([FakeResponse(403)])
    with pytest.raises(ApiError):
        http.get_json("https://api.example.org/x")


def test_gives_up_after_max_tries():
    http, waits = client([FakeResponse(503)] * 5)
    with pytest.raises(RetriesExhausted):
        http.get_json("https://api.example.org/x")
    assert waits == [1.0, 2.0, 4.0, 8.0, 16.0]


def test_backoff_is_capped():
    http = HttpClient(
        session=FakeSession([FakeResponse(429)] * 9), max_tries=9, sleep=lambda s: None
    )
    assert http._wait_time(FakeResponse(429), 8) == 60.0
