"""A small HTTP client with retries, back-off and a call log safe to publish."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import Any

import requests

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF = 60  # seconds
_SECRET_PARAMS = re.compile(r"(api_key|mailto)=[^&]+")


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
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        max_tries: int = 5,
        timeout: float = 60.0,
        pause: float = 0.0,
        sleep: Callable[[float], None] = time.sleep,
        log: list[str] | None = None,
    ) -> None:
        self.session = session or requests.Session()
        self.max_tries = max_tries
        self.timeout = timeout
        self.pause = pause
        self._sleep = sleep
        self.log: list[str] = log if log is not None else []

    def get_json(
        self, url: str, params: dict | None = None, headers: dict | None = None
    ) -> Any | None:
        for attempt in range(self.max_tries):
            try:
                response = self.session.get(
                    url, params=params, headers=headers, timeout=self.timeout
                )
            except requests.RequestException as exc:
                self.log.append(f"ERR {redact(url)} {type(exc).__name__}")
                self._sleep(2**attempt)
                continue

            self.log.append(f"{response.status_code} {redact(response.url)}")
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
                self._sleep(self._wait_time(response, attempt))
                continue
            raise ApiError(f"{response.status_code} from {redact(response.url)}")
        raise RetriesExhausted(f"gave up on {redact(url)} after {self.max_tries} tries")

    @staticmethod
    def _wait_time(response: requests.Response, attempt: int) -> float:
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            return float(retry_after)
        return float(min(2**attempt, MAX_BACKOFF))
