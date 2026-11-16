"""A small HTTP client with retries, back-off and a call log safe to publish."""

from __future__ import annotations

import itertools
import logging
import random
import re
import time
from collections.abc import Callable
from typing import Any

import requests

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF = 60  # seconds
_SECRET_PARAMS = re.compile(r"(api_key|mailto)=[^&]+")
logger = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """Raised when an API refuses the request outright (for example a bad key)."""


class RetriesExhausted(ApiError):
    """Raised when a call still fails after every retry (usually rate limiting)."""


def redact(url: str) -> str:
    """Hide API keys and e-mail addresses so the call log can be shared."""
    return _SECRET_PARAMS.sub(r"\1=REDACTED", url)


class HttpClient:
    """GET JSON with retries. Every call is recorded in ``self.log``.

    Returns the decoded JSON on 200 and ``None`` on 404. Raises :class:`ApiError`
    on other 4xx and :class:`RetriesExhausted` if it still fails after ``max_tries``.
    A 429 streak keeps retrying past ``max_tries`` until it has waited ``rate_limit_budget``
    seconds. With ``throttle_wait`` set, a 429 waits that long instead of backing off.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        max_tries: int = 5,
        timeout: float = 60.0,
        pause: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        log: list[str] | None = None,
        rate_limit_budget: float = 0.0,
        rand: Callable[[], float] = random.random,
        throttle_wait: float | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.max_tries = max_tries
        self.timeout = timeout
        self.pause = pause
        self._sleep = sleep
        self.rate_limit_budget = rate_limit_budget
        self._rand = rand
        self.throttle_wait = throttle_wait
        self.log: list[str] = log if log is not None else []

    def get_json(
        self, url: str, params: dict | None = None, headers: dict | None = None
    ) -> Any | None:
        throttled, waited = False, 0.0
        for attempt in itertools.count():
            if attempt >= self.max_tries and not (throttled and waited < self.rate_limit_budget):
                break
            try:
                response = self.session.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )
            except requests.RequestException as exc:
                self.log.append(f"ERR {redact(url)} {type(exc).__name__}")
                throttled = False
                logger.warning(
                    "%s on %s, retry in %ss", type(exc).__name__, redact(url), 2**attempt
                )
                self._sleep(2**attempt)
                continue

            self.log.append(f"{response.status_code} {redact(response.url)}")
            logger.debug("%s %s", response.status_code, redact(response.url))
            if response.status_code == 200:
                if self.pause:
                    self._sleep(self.pause)
                return response.json()
            if response.status_code == 404:
                return None
            if response.status_code in (401, 403):
                raise ApiError(
                    f"{response.status_code} from {redact(response.url)}: check the API key"
                )
            if response.status_code in RETRY_STATUSES:
                wait = self._wait_time(response, attempt)
                throttled = response.status_code == 429
                if throttled:
                    waited += wait
                logger.warning(
                    "%s from %s, retry in %gs", response.status_code, redact(response.url), wait
                )
                self._sleep(wait)
                continue
            raise ApiError(f"{response.status_code} from {redact(response.url)}")
        raise RetriesExhausted(f"gave up on {redact(url)} after {attempt} tries")

    def _wait_time(self, response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return float(retry_after)
        if response.status_code == 429 and self.throttle_wait is not None:
            return self.throttle_wait + self._rand()
        return min(2**attempt, MAX_BACKOFF) * (1 + self._rand() / 2)
