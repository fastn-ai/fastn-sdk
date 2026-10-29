# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Read-only checks against a live environment: orgs, the customer context, paginate, typed 404s, events. Safe on
production (nothing is created). The read-only part of node/test/live/prod.test.ts; the parts that create a throw-away
customer org live in test_customer_scope_live.py and never run on production.
"""

from __future__ import annotations

import os
import re
from typing import Any, Iterator, List

import pytest

from fastn.platform import FastnApiError, FastnClient, RequestLog, paginate

from ._shared import BASE_URL, E2E, data_of, evidence, guard_production, live

guard_production()
pytestmark = live
ev = evidence("readonly")
log: List[RequestLog] = []


@pytest.fixture(scope="module")
def fastn() -> Iterator[FastnClient]:
    client = FastnClient(api_key=os.environ["FASTN_API_KEY"], base_url=BASE_URL, on_request=log.append)
    yield client
    ev("requests", [f"{x.method} {x.url.replace(BASE_URL, '')} -> {x.status} {x.duration_ms:.0f}ms" for x in log])
    client.close()


def test_list_orgs_answers_and_the_e2e_customer_resolves_to_a_fastn_id(fastn: FastnClient) -> None:
    res = fastn.orgs.list_orgs({"type": "end_org"})
    rows = res.get("data") or []
    ev("listOrgs", {"count": len(rows), "keys": list(rows[0].keys()) if rows else []})
    assert isinstance(rows, list)
    c = fastn.customer(E2E)
    id_ = c.id()
    assert re.match(r"^[0-9a-f-]{36}$|^org_", id_)
    org = c.get()
    ev("getTenant", data_of(org))
    assert data_of(org)["id"] == id_
    conns = c.connections()
    ev("connections", [{"connector": x.get("connectorSlug") or x.get("connector") or x.get("connectorId"), "status": x.get("status")} for x in conns.get("data") or []])
    assert isinstance(conns.get("data"), list) and len(conns["data"]) > 0
    me = fastn.me()
    assert me.get("org", {}).get("id")


def test_paginate_walks_list_events_and_stops_on_a_list_that_ignores_paging(fastn: FastnClient) -> None:
    rows: List[Any] = list(paginate(lambda i: fastn.events.list_events(i), {}, page_size=2, max_pages=3))  # type: ignore[arg-type]
    ev("paginate events", {"rows": len(rows)})
    orgs: List[Any] = list(paginate(lambda i: fastn.orgs.list_orgs(i), {"type": "end_org"}, page_size=2))  # type: ignore[arg-type]
    assert 0 < len(orgs) < 50


def test_a_wrong_id_is_a_typed_404(fastn: FastnClient) -> None:
    with pytest.raises(FastnApiError) as ei:
        fastn.orgs.get_tenant({"id": "00000000-0000-0000-0000-000000000000"})
    err = ei.value
    ev("getTenant 404", {"status": err.status, "code": err.code, "message": err.message, "requestId": err.request_id})
    assert err.status in (404, 403) and err.request_id


def test_event_subscriptions_and_events_list(fastn: FastnClient) -> None:
    subs = fastn.events.list_event_subscriptions()
    ev("subscriptions", [{"id": s.get("id"), "url": re.sub(r"//[^/]+", "//<host>", str(s.get("url") or "")), "status": s.get("status")} for s in subs.get("data") or []])
    evs = fastn.events.list_events({"limit": 2})
    ev("events", {"n": len(evs.get("data") or [])})
    assert isinstance(evs.get("data"), list)


def test_providers_for_scheduling_meeting_include_google_calendar(fastn: FastnClient) -> None:
    p = fastn.customer(E2E).records("scheduling", "meeting", provider="googleCalendar").providers()
    ev("providers", data_of(p))
    assert any(x.get("connectorSlug") == "googleCalendar" for x in p.get("data") or [])
