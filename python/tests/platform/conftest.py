# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""One HTTP mock for every platform unit suite (a port of node/test/helpers.ts on top of pytest-httpx).

`mock(httpx_mock, source)`: `source` is a queue of replies or a handler `(url, request) -> reply`; `fallback` answers
when the queue is empty or the handler returns None. A reply is {"status", "body", "headers"} or an Exception.
Backoff sleeps are replaced with a no-op so retry tests run instantly.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import httpx
import pytest

import fastn.platform._http as http_mod

_THIS_DIR = str(Path(__file__).resolve().parent)
BASE = "https://api.fastn.dev"
Reply = Union[Dict[str, Any], Exception, None]


def pytest_collection_modifyitems(items: List[pytest.Item]) -> None:
    for item in items:
        path = str(Path(str(item.fspath)).resolve())
        if path.startswith(_THIS_DIR):
            item.add_marker(pytest.mark.platform)
            if "/live/" not in path.replace("\\", "/"):  # the live suites talk to a real environment: never mock them
                item.add_marker(pytest.mark.httpx_mock(assert_all_responses_were_requested=False, assert_all_requests_were_expected=False, can_send_already_matched_responses=True))


@pytest.fixture
def assert_all_responses_were_requested() -> bool:
    """pytest-httpx before 0.31 (the last releases for Python 3.8) reads this fixture instead of the marker above, and
    would fail a test whose mock was never hit (a guard that raises before any request)."""
    return False


@pytest.fixture(autouse=True)
def no_sleep(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> List[float]:
    """Backoff waits are recorded, not slept (unit tests only; the live suites keep real waits)."""
    waited: List[float] = []
    if "/live/" not in str(request.node.fspath).replace("\\", "/"):
        monkeypatch.setattr(http_mod, "sleep", lambda s: waited.append(s))
    return waited


class Mock:
    def __init__(self, httpx_mock: Any, source: Union[List[Reply], Callable[[str, httpx.Request], Reply]], fallback: Reply = None) -> None:
        self.calls: List[httpx.Request] = []
        self.fallback: Reply = {"status": 200, "body": {"data": {}}} if fallback is None else fallback
        self.use(source)

        def cb(request: httpx.Request) -> httpx.Response:
            self.calls.append(request)
            r: Reply = (self.queue.pop(0) if self.queue else None) if self.queue is not None else self.handler(str(request.url), request)  # type: ignore[misc]
            if r is None:
                r = self.fallback
            if isinstance(r, Exception):
                raise r
            assert isinstance(r, dict)
            status = int(r.get("status", 200))
            body = r.get("body")
            content = b"" if body is None or status == 204 else (body.encode() if isinstance(body, str) else json.dumps(body).encode())
            headers = {"content-type": "application/json", "x-request-id": "req_1", **(r.get("headers") or {})}
            return httpx.Response(status, content=content, headers=headers)

        # pytest-httpx 0.31+ sends a callback once unless is_reusable=True; older releases (the last ones for
        # Python 3.8) have no such option and reuse the last registered callback by themselves.
        if "is_reusable" in inspect.signature(httpx_mock.add_callback).parameters:
            httpx_mock.add_callback(cb, is_reusable=True)
        else:
            httpx_mock.add_callback(cb)

    def use(self, source: Union[List[Reply], Callable[[str, httpx.Request], Reply]]) -> None:
        """Replaces the reply queue / handler (what a second mockFetch() does in the Node suite)."""
        self.queue: Optional[List[Reply]] = list(source) if isinstance(source, list) else None
        self.handler: Callable[[str, httpx.Request], Reply] = (lambda u, r: None) if isinstance(source, list) else source

    def urls(self, base: str = BASE) -> List[str]:
        return [str(r.url).replace(base, "") for r in self.calls]

    def json(self, i: int) -> Any:
        return json.loads(self.calls[i].content) if self.calls[i].content else None

    def line(self, r: httpx.Request, base: str = BASE) -> str:
        return f"{r.method} {str(r.url).replace(base, '')}"


@pytest.fixture
def mock(httpx_mock: Any) -> Callable[..., Mock]:
    def make(source: Union[List[Reply], Callable[[str, httpx.Request], Reply]], fallback: Optional[Reply] = None) -> Mock:
        return Mock(httpx_mock, source, fallback)

    return make
