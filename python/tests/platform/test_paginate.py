# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""paginate (a port of node/test/unit/paginate.test.ts)."""

from __future__ import annotations

from typing import Any, Dict, List

from fastn.platform import paginate


def test_walks_offset_pages_until_a_short_page() -> None:
    seen: List[Dict[str, Any]] = []
    rows = [{"i": i} for i in range(7)]

    def fn(input: Dict[str, Any]) -> Any:
        seen.append(input)
        return {"data": rows[input["offset"] : input["offset"] + input["limit"]]}

    out = list(paginate(fn, {"status": "x"}, page_size=3))
    assert [r["i"] for r in out] == [0, 1, 2, 3, 4, 5, 6]
    assert seen == [{"status": "x", "limit": 3, "offset": 0}, {"status": "x", "limit": 3, "offset": 3}, {"status": "x", "limit": 3, "offset": 6}]


def test_follows_cursors() -> None:
    pages: Dict[str, Any] = {"start": {"data": {"records": [1, 2], "nextCursor": "c2"}}, "c2": {"data": {"records": [3], "nextCursor": None}}}
    out = list(paginate(lambda i: pages[i.get("cursor", "start")], {}, offset_key=None))
    assert out == [1, 2, 3]


def test_stops_on_a_list_that_ignores_paging_and_on_max_pages() -> None:
    calls = 0

    def same(_: Dict[str, Any]) -> Any:
        nonlocal calls
        calls += 1
        return {"data": [{"a": 1}, {"a": 2}]}

    assert list(paginate(same, page_size=2)) == [{"a": 1}, {"a": 2}]
    assert calls == 2
    assert len(list(paginate(lambda i: {"data": [i["offset"]]}, page_size=1, max_pages=3))) == 3
    assert list(paginate(lambda i: {"nothing": True})) == []
