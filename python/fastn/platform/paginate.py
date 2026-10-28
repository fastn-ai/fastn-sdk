# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Pages through a list operation that takes `limit` + `offset` (most fastn list calls) or `cursor`. A port of
node/src/paginate.ts."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional


def default_rows(res: Any) -> Optional[List[Any]]:
    """`data` when it is a list, else `data.items` / `items` / `records` / `rows`."""
    if isinstance(res, list):
        return res
    if not isinstance(res, dict):
        return None
    if isinstance(res.get("data"), list):
        return list(res["data"])
    data: Dict[str, Any] = res["data"] if isinstance(res.get("data"), dict) else {}
    for k in ("items", "records", "rows"):
        if isinstance(data.get(k), list):
            return list(data[k])
        if isinstance(res.get(k), list):
            return list(res[k])
    return None


def default_next(res: Any) -> Optional[str]:
    """`nextCursor` / `data.nextCursor` / `pagination.nextCursor` / `data.pagination.nextCursor`."""
    if not isinstance(res, dict):
        return None
    data: Dict[str, Any] = res["data"] if isinstance(res.get("data"), dict) else {}
    pg: Dict[str, Any] = res["pagination"] if isinstance(res.get("pagination"), dict) else {}
    dpg: Dict[str, Any] = data["pagination"] if isinstance(data.get("pagination"), dict) else {}
    for v in (res.get("nextCursor"), data.get("nextCursor"), pg.get("nextCursor"), dpg.get("nextCursor")):
        if v is not None:
            return str(v)
    return None


def paginate(
    fn: Callable[[Dict[str, Any]], Any],
    input: Optional[Mapping[str, Any]] = None,
    *,
    page_size: int = 100,
    limit_key: str = "limit",
    offset_key: Optional[str] = "offset",
    cursor_key: str = "cursor",
    rows: Callable[[Any], Optional[List[Any]]] = default_rows,
    next_cursor: Callable[[Any], Optional[str]] = default_next,
    max_pages: int = 1000,
) -> Iterator[Any]:
    """`for org in paginate(fastn.orgs.list_orgs, {"type": "end_org"}): ...`

    Stops when a page comes back shorter than `page_size` (offset lists), without a next cursor (cursor lists), or
    when a list ignores paging and answers the same rows again. `offset_key=None` for cursor-only lists.
    """
    offset = 0
    cursor: Optional[str] = None
    pages = 0
    last_page: Optional[str] = None
    while pages < max_pages:
        pages += 1
        page: Dict[str, Any] = {**(input or {}), limit_key: page_size}
        if cursor:
            page[cursor_key] = cursor
        elif offset_key:
            page[offset_key] = offset
        res = fn(page)
        page_rows = rows(res) or []
        # A list that ignores limit/offset answers the same rows every time; stop instead of looping.
        sig = json.dumps([page_rows[0], page_rows[-1], len(page_rows)] if page_rows else None, sort_keys=True, default=str)
        if sig == last_page:
            return
        last_page = sig
        yield from page_rows
        nxt = next_cursor(res)
        if nxt and nxt != cursor:
            cursor = nxt
            continue
        if not offset_key or len(page_rows) < page_size:
            return
        offset += len(page_rows)
