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
    return HttpClient(session=FakeSession(responses), sleep=waits.append, rand=lambda: 0.0), waits


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
        session=FakeSession([FakeResponse(429)] * 9),
        max_tries=9,
        sleep=lambda s: None,
        rand=lambda: 0.0,
    )
    assert http._wait_time(FakeResponse(429), 8) == 60.0


def test_other_4xx_raises_instead_of_returning_none():
    http, waits = client([FakeResponse(400)])
    with pytest.raises(ApiError, match="400"):
        http.get_json("https://api.example.org/x")
    assert waits == []


def test_retry_wait_is_logged_with_key_redacted(caplog):
    http, _ = client([FakeResponse(429, headers={"Retry-After": "3"}), FakeResponse(200, {})])
    http.get_json("https://api.example.org/x")
    warnings = [r.getMessage() for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1 and "429" in warnings[0] and "3s" in warnings[0]
    assert "SECRET" not in caplog.text


def budgeted(responses, budget):
    waits = []
    http = HttpClient(
        session=FakeSession(responses),
        max_tries=2,
        sleep=waits.append,
        rate_limit_budget=budget,
        rand=lambda: 0.0,
    )
    return http, waits


def test_429_streak_retries_past_max_tries_within_budget():
    http, waits = budgeted([FakeResponse(429)] * 4 + [FakeResponse(200, {"ok": 1})], budget=100)
    assert http.get_json("https://api.example.org/x") == {"ok": 1}
    assert waits == [1.0, 2.0, 4.0, 8.0]


def test_429_streak_gives_up_once_budget_spent():
    http, waits = budgeted([FakeResponse(429)] * 10, budget=7)
    with pytest.raises(RetriesExhausted, match="after 3 tries"):
        http.get_json("https://api.example.org/x")
    assert waits == [1.0, 2.0, 4.0]


def test_budget_does_not_extend_server_errors():
    http, waits = budgeted([FakeResponse(503)] * 10, budget=100)
    with pytest.raises(RetriesExhausted):
        http.get_json("https://api.example.org/x")
    assert waits == [1.0, 2.0]


def test_backoff_jitter_adds_up_to_half():
    http = HttpClient(session=FakeSession([]), rand=lambda: 1.0)
    assert http._wait_time(FakeResponse(429), 3) == 12.0
    assert http._wait_time(FakeResponse(429, headers={"Retry-After": "3"}), 3) == 3.0


def throttled(responses, rand=0.0):
    waits = []
    http = HttpClient(
        session=FakeSession(responses),
        sleep=waits.append,
        throttle_wait=5.0,
        rand=lambda: rand,
    )
    return http, waits


def test_throttle_wait_replaces_backoff_on_429():
    http, waits = throttled([FakeResponse(429)] * 4 + [FakeResponse(200, {"ok": 1})], rand=0.5)
    assert http.get_json("https://api.example.org/x") == {"ok": 1}
    assert waits == [5.5] * 4


def test_throttle_wait_still_honours_retry_after():
    http, waits = throttled(
        [FakeResponse(429, headers={"Retry-After": "2"}), FakeResponse(200, {})]
    )
    http.get_json("https://api.example.org/x")
    assert waits == [2.0]


def test_throttle_wait_leaves_server_errors_on_backoff():
    http, waits = throttled([FakeResponse(503)] * 3 + [FakeResponse(200, {})])
    http.get_json("https://api.example.org/x")
    assert waits == [1.0, 2.0, 4.0]
