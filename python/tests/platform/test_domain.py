# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Typed calendar and CRM, provider resolution, connect(app), catalog, interval arithmetic (a port of
node/test/unit/domain.test.ts)."""

from __future__ import annotations

import math
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

import httpx
import pytest

import fastn.platform.customer as customer_mod
from fastn.platform import (
    PROVIDER_TTL_SECONDS,
    FastnApiError,
    FastnClient,
    free_intervals,
    slots_of,
)
from fastn.platform.domain import parse_iso_ms, wire_record

from .conftest import Mock, Reply

ALL_OPS = ["get", "list", "create", "delete", "search", "update"]


def providers(rows: List[Dict[str, Any]]) -> Reply:
    return {"body": {"data": rows}}


def hubspot(ops: List[str] = ALL_OPS) -> Dict[str, Any]:
    return {"connectorSlug": "hubspot", "connectorName": "HubSpot", "operations": ops, "connected": True, "healthy": False, "connectionCount": 1}


gcal = {"connectorSlug": "googleCalendar", "connectorName": "Google Calendar", "operations": ALL_OPS, "connected": True, "healthy": False, "connectionCount": 1}
not_connected = {"connectorSlug": "pipedrive", "connectorName": "Pipedrive", "operations": ["get", "list", "create"], "connected": False, "connectionCount": 0}


def fx(mock: Callable[..., Mock], handler: Callable[[str, httpx.Request], Reply]) -> Mock:
    return mock(lambda url, req: {"body": {"data": {"actor": "api_key", "org": {"id": "partner-1"}}}} if url.endswith("/v1/me") else handler(url, req))


def client() -> FastnClient:
    return FastnClient(api_key="k")


class TestProviderResolution:
    def test_pins_the_one_connected_provider_reads_the_list_once_per_entity_and_sends_the_customer_header(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: providers([hubspot(), not_connected]) if "/providers" in url else {"body": {"records": [], "hasMore": False, "provider": "hubspot"}})
        fastn = client()
        c = fastn.customer("acme-1")
        c.crm.contacts.find({"email": "a@b.co"})
        c.crm.contacts.list(page_size=5)
        fastn.customer("acme-1").crm.contacts.list()  # another object for the same ref: no new lookup
        assert m.urls() == ["/v1/unified/crm/contact/providers", "/v1/unified/crm/contact/search?provider=hubspot", "/v1/unified/crm/contact?provider=hubspot&page_size=5", "/v1/unified/crm/contact?provider=hubspot"]
        for x in m.calls:
            assert x.headers["x-end-org-ref"] == "acme-1"
        assert m.json(1) == {"email": "a@b.co"}  # the filters are the body

    def test_provider_option_skips_the_lookup_connection_id_goes_on_the_query(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: {"body": {"id": "1", "provider": "pipedrive", "data": {}}})
        client().customer("acme-1").crm.contacts.get("1", provider="pipedrive", connection_id="conn_9")
        assert m.urls() == ["/v1/unified/crm/contact/1?provider=pipedrive&connection_id=conn_9"]

    def test_no_connected_provider_two_providers_none_able(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: providers([not_connected]))
        with pytest.raises(FastnApiError) as e0:
            client().customer("acme-1").crm.contacts.list()
        assert e0.value.code == "NO_CONNECTED_PROVIDER" and e0.value.status == 404
        m.use(lambda url, req: providers([hubspot(), {**hubspot(), "connectorSlug": "salesforce"}]))
        with pytest.raises(FastnApiError) as e2:
            client().customer("acme-1").crm.contacts.list()
        assert e2.value.code == "PROVIDER_AMBIGUOUS" and e2.value.status == 409 and e2.value.details == {"category": "crm", "entity": "contact", "op": "list", "providers": ["hubspot", "salesforce"]}
        m.use(lambda url, req: providers([hubspot(["get", "list"])]))
        with pytest.raises(FastnApiError) as e3:
            client().customer("acme-1").crm.contacts.create({"email": "x@y.z"})
        assert e3.value.code == "OPERATION_NOT_SUPPORTED"
        m.use(lambda url, req: providers([hubspot(["get", "list"]), {**gcal, "connectorSlug": "zohoCrm", "operations": ["create"]}]))
        assert client().customer("acme-1").crm.contacts.list() is not None  # only hubspot lists: not ambiguous

    def test_a_provider_or_connection_error_forgets_the_cached_answer(self, mock: Callable[..., Mock]) -> None:
        n = {"v": 0}

        def handler(url: str, req: httpx.Request) -> Reply:
            if "/providers" in url:
                return providers([hubspot()])
            n["v"] += 1
            return {"status": 404, "body": {"error": {"code": "UNIFIED_CONNECTION_NOT_FOUND", "message": "gone"}}} if n["v"] == 1 else {"body": {"records": []}}

        m = fx(mock, handler)
        c = client().customer("acme-1")
        with pytest.raises(FastnApiError):
            c.crm.contacts.list()
        c.crm.contacts.list()
        assert len([u for u in m.urls() if u.endswith("/providers")]) == 2

    def test_other_errors_keep_the_cached_provider(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: providers([hubspot()]) if "/providers" in url else {"status": 400, "body": {"error": {"code": "UNIFIED_VALIDATION_FAILED", "message": "bad"}}})
        c = client().customer("acme-1")
        for _ in range(2):
            with pytest.raises(FastnApiError):
                c.crm.contacts.list()
        assert len([u for u in m.urls() if u.endswith("/providers")]) == 1

    def test_request_options_still_reach_the_wire(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: providers([gcal]) if "/providers" in url else {"status": 201, "body": {"id": "evt1", "provider": "googleCalendar", "data": {}}})
        r = client().customer("acme-1").calendar.book({"title": "Intro", "start_time": datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc), "duration_minutes": 30}, idempotency_key="call-7", correlation_id="corr-7")
        assert r["id"] == "evt1"
        post = m.calls[1]
        assert post.headers["idempotency-key"] == "call-7" and post.headers["x-fastn-correlation-id"] == "corr-7"
        assert m.json(1) == {"title": "Intro", "start_time": "2026-11-02T10:00:00.000Z", "duration_minutes": 30}  # the record is the body


class TestCalendar:
    def test_free_slots_posts_an_availability_record_and_returns_busy_free_and_slots(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: providers([gcal]) if "/providers" in url else {"body": {"id": "x", "provider": "googleCalendar", "data": {"start_time": "2026-11-02T09:00:00.000Z", "end_time": "2026-11-02T12:00:00.000Z", "busy": [{"start_time": "2026-11-02T10:00:00.000Z", "end_time": "2026-11-02T10:30:00.000Z"}]}}})
        r = client().customer("acme-1").calendar.free_slots({"start_time": "2026-11-02T09:00:00Z", "end_time": "2026-11-02T12:00:00Z", "timezone": "UTC", "slot_minutes": 60})
        assert m.urls() == ["/v1/unified/scheduling/availability/providers", "/v1/unified/scheduling/availability?provider=googleCalendar"]
        assert m.json(1) == {"start_time": "2026-11-02T09:00:00Z", "end_time": "2026-11-02T12:00:00Z", "timezone": "UTC"}
        assert r["busy"] == [{"start_time": "2026-11-02T10:00:00.000Z", "end_time": "2026-11-02T10:30:00.000Z"}]
        assert r["free"] == [{"start_time": "2026-11-02T09:00:00.000Z", "end_time": "2026-11-02T10:00:00.000Z"}, {"start_time": "2026-11-02T10:30:00.000Z", "end_time": "2026-11-02T12:00:00.000Z"}]
        assert r["slots"] == [{"start_time": "2026-11-02T09:00:00.000Z", "end_time": "2026-11-02T10:00:00.000Z"}, {"start_time": "2026-11-02T10:30:00.000Z", "end_time": "2026-11-02T11:30:00.000Z"}]
        assert r["provider"] == "googleCalendar" and "warnings" not in r

    def test_free_slots_without_slot_minutes_and_with_a_bare_answer(self, mock: Callable[..., Mock]) -> None:
        fx(mock, lambda url, req: providers([gcal]) if "/providers" in url else {"body": {"id": "x", "provider": "googleCalendar", "warnings": ["w"], "data": {"busy": [{"start": "2026-11-02T10:00:00Z", "end": "2026-11-02T10:30:00Z"}]}}})
        r = client().customer("acme-1").calendar.free_slots({"start_time": datetime(2026, 11, 2, 9, tzinfo=timezone.utc), "end_time": "2026-11-02T11:00:00Z"})
        assert "slots" not in r and r["warnings"] == ["w"]
        assert r["start_time"] == "2026-11-02T09:00:00.000Z" and r["end_time"] == "2026-11-02T11:00:00Z"
        assert r["free"] == [{"start_time": "2026-11-02T09:00:00.000Z", "end_time": "2026-11-02T10:00:00.000Z"}, {"start_time": "2026-11-02T10:30:00.000Z", "end_time": "2026-11-02T11:00:00.000Z"}]

    def test_find_reschedule_and_cancel_map_to_search_patch_and_delete(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: providers([gcal]) if "/providers" in url else {"body": {"records": [], "id": "m1", "provider": "googleCalendar", "data": {}}})
        c = client().customer("acme-1")
        c.calendar.find({"start_time": "2026-11-01T00:00:00Z", "end_time": "2026-11-08T00:00:00Z", "query": "Jane"}, page_size=50)
        c.calendar.reschedule("m1", {"start_time": "2026-11-03T10:00:00Z", "end_time": "2026-11-03T10:30:00Z"})
        c.calendar.cancel("m1", idempotency_key="c1")
        c.calendar.get("m1")
        calls = m.calls[1:]
        assert [m.line(x) for x in calls] == [
            "POST /v1/unified/scheduling/meeting/search?provider=googleCalendar&page_size=50",
            "PATCH /v1/unified/scheduling/meeting/m1?provider=googleCalendar",
            "DELETE /v1/unified/scheduling/meeting/m1?provider=googleCalendar",
            "GET /v1/unified/scheduling/meeting/m1?provider=googleCalendar",
        ]
        assert m.json(1) == {"start_time": "2026-11-01T00:00:00Z", "end_time": "2026-11-08T00:00:00Z", "query": "Jane"}
        assert m.json(2) == {"start_time": "2026-11-03T10:00:00Z", "end_time": "2026-11-03T10:30:00Z"}
        assert calls[2].headers["idempotency-key"] == "c1"


class TestCrm:
    def test_contacts_notes_tasks_and_deals_name_their_entities(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: providers([hubspot()]) if "/providers" in url else {"body": {"records": [], "id": "r", "provider": "hubspot", "data": {}}})
        c = client().customer("acme-1")
        c.crm.contacts.create({"first_name": "Jane", "email": "jane@x.io"}, idempotency_key="k1")
        c.crm.contacts.update("c1", {"last_name": "Doe"})
        c.crm.notes.add({"body": "Called", "parent_id": "c1", "parent_type": "contact"})
        c.crm.tasks.add({"subject": "Call back", "due_date": datetime(2026, 11, 5, 9, tzinfo=timezone.utc)})
        c.crm.tasks.delete("t1")
        c.crm.deals.create({"name": "Annual plan", "amount": 1200})
        c.crm.deals.move_stage("d1", "qualifiedtobuy")
        c.crm.deals.stages()
        c.crm.deals.stages(page_size=3, cursor="abc")
        calls = [(i, x) for i, x in enumerate(m.calls) if "/providers" not in str(x.url) and not str(x.url).endswith("/v1/me")]
        assert [m.line(x) for _, x in calls] == [
            "POST /v1/unified/crm/contact?provider=hubspot",
            "PATCH /v1/unified/crm/contact/c1?provider=hubspot",
            "POST /v1/unified/crm/note?provider=hubspot",
            "POST /v1/unified/crm/task?provider=hubspot",
            "DELETE /v1/unified/crm/task/t1?provider=hubspot",
            "POST /v1/unified/crm/opportunity?provider=hubspot",
            "PATCH /v1/unified/crm/opportunity/d1?provider=hubspot",
            "GET /v1/unified/crm/stage?provider=hubspot",
            "GET /v1/unified/crm/stage?provider=hubspot&cursor=abc&page_size=3",
        ]
        assert m.json(calls[0][0]) == {"first_name": "Jane", "email": "jane@x.io"} and calls[0][1].headers["idempotency-key"] == "k1"
        note = m.json(calls[2][0])
        assert {k: note[k] for k in ("body", "parent_id", "parent_type")} == {"body": "Called", "parent_id": "c1", "parent_type": "contact"}
        assert (parse_iso_ms(note["created_at"]) or 0) > (time.time() - 60) * 1000  # created_at defaults to now
        with pytest.raises(TypeError):
            c.crm.contacts.get("")
        with pytest.raises(TypeError):
            c.crm.contacts.update("", {"x": 1})
        assert m.json(calls[3][0]) == {"subject": "Call back", "due_date": "2026-11-05T09:00:00.000Z"}
        assert m.json(calls[6][0]) == {"stage": "qualifiedtobuy"}
        # one providers lookup per entity: contact, note, task, opportunity, stage
        assert sorted(u for u in m.urls() if u.endswith("/providers")) == ["/v1/unified/crm/contact/providers", "/v1/unified/crm/note/providers", "/v1/unified/crm/opportunity/providers", "/v1/unified/crm/stage/providers", "/v1/unified/crm/task/providers"]


class TestConnectAppAndLinks:
    widgets = [
        {"id": "wgt_cal", "name": "Google Calendar", "slug": "google-calendar", "connectorRefs": [{"slug": "googleCalendar", "connectorId": "867f"}]},
        {"id": "wgt_hs", "name": "HubSpot", "slug": "hubspot", "connectorRefs": [{"slug": "hubspot", "connectorId": "9036"}]},
    ]

    def wfx(self, mock: Callable[..., Mock], extra: List[Dict[str, Any]] = []) -> Mock:  # noqa: B006
        return fx(mock, lambda url, req: {"body": {"data": [*self.widgets, *extra]}} if "/v1/widgets" in url else {"status": 201, "body": {"data": {"setupId": "stp_1", "setupUrl": "https://connect.fastn.dev/s/stp_1", "status": "pending", "expiresAt": "2026-11-04T00:00:00Z", "endOrgId": "11111111-aaaa"}}} if req.method == "POST" else {"body": {"data": {"setupId": "stp_1", "status": "revoked", "endOrgId": "11111111-aaaa"}}})

    def test_finds_the_widget_by_connector_slug_once_per_client_and_creates_the_setup_link_for_the_customer(self, mock: Callable[..., Mock]) -> None:
        m = self.wfx(mock)
        fastn = client()
        link = fastn.customer("acme-1").connect("googleCalendar")
        again = fastn.customer("acme-2").connect("hubspot", connection_name="Main CRM", redirect_url="https://app.acme.com/done", expires_in_minutes=60)
        assert {k: link[k] for k in ("setupId", "url", "status", "widgetId", "expiresAt")} == {"setupId": "stp_1", "url": "https://connect.fastn.dev/s/stp_1", "status": "pending", "widgetId": "wgt_cal", "expiresAt": "2026-11-04T00:00:00Z"}
        assert again["widgetId"] == "wgt_hs"
        assert "endOrgId" not in link and "setupUrl" not in link  # fastn's internal customer id never reaches the partner
        posts = [i for i, x in enumerate(m.calls) if x.method == "POST"]
        assert m.json(posts[0]) == {"createIfMissing": True, "widgetId": "wgt_cal", "externalRef": "acme-1", "connectionName": "Google Calendar"}
        assert m.json(posts[1]) == {"createIfMissing": True, "widgetId": "wgt_hs", "externalRef": "acme-2", "connectionName": "Main CRM", "redirectUrl": "https://app.acme.com/done", "expiresInMinutes": 60}
        assert len([u for u in m.urls() if u.startswith("/v1/widgets")]) == 1

    def test_no_widget_404_two_widgets_409_unless_widget_id_is_given(self, mock: Callable[..., Mock]) -> None:
        m = self.wfx(mock, [{"id": "wgt_cal2", "name": "Calendar (EU)", "connectorRefs": [{"slug": "googleCalendar"}]}])
        fastn = client()
        with pytest.raises(FastnApiError) as e0:
            fastn.customer("acme-1").connect("salesforce")
        assert e0.value.code == "WIDGET_NOT_FOUND" and e0.value.status == 404
        with pytest.raises(FastnApiError) as e1:
            fastn.customer("acme-1").connect("googleCalendar")
        assert e1.value.code == "WIDGET_AMBIGUOUS" and e1.value.status == 409
        link = fastn.customer("acme-1").connect("googleCalendar", widget_id="wgt_cal2")
        assert link["widgetId"] == "wgt_cal2"
        post = m.json(next(i for i, x in enumerate(m.calls) if x.method == "POST"))
        assert post["widgetId"] == "wgt_cal2" and post["connectionName"] == "Calendar (EU)"

    def test_request_options_on_connect_reach_the_wire(self, mock: Callable[..., Mock]) -> None:
        m = self.wfx(mock)
        client().customer("acme-1").connect("hubspot", correlation_id="corr-1", label="x")
        post = next(x for x in m.calls if x.method == "POST")
        assert post.headers["x-fastn-correlation-id"] == "corr-1" and m.json(m.calls.index(post))["label"] == "x"

    def test_the_object_form_still_starts_an_oauth_connection_on_the_customer_org(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: {"body": {"data": [{"id": "11111111-aaaa", "externalRef": "acme-1", "parentId": "partner-1"}]}} if "/v1/orgs?" in url else {"body": {"data": {"url": "https://oauth"}}})
        r = client().customer("acme-1").connect({"connectorId": "googleCalendar", "connectionName": "work"})
        assert r["data"]["url"] == "https://oauth"
        call = next(i for i, x in enumerate(m.calls) if x.method == "POST")
        assert "/v1/oauth/" in str(m.calls[call].url)
        assert m.json(call)["connectorId"] == "googleCalendar" and m.json(call)["endOrgId"] == "11111111-aaaa"

    def test_links_get_and_links_cancel_answer_the_links_data(self, mock: Callable[..., Mock]) -> None:
        m = self.wfx(mock)
        c = client().customer("acme-1")
        assert c.links.get("stp_1")["status"] == "revoked"
        assert c.links.cancel("stp_1")["setupId"] == "stp_1"
        assert [m.line(x) for x in m.calls] == ["GET /v1/setup-links/stp_1", "DELETE /v1/setup-links/stp_1"]
        assert "endOrgId" not in c.links.get("stp_1")  # fastn's internal customer id is left out


class TestCatalog:
    cats = [{"id": "ucat_1", "slug": "crm", "name": "CRM", "entities": [{"id": "ue_1", "slug": "contact", "name": "Contact", "connectorSlugs": ["hubspot"], "operations": ["create", "get"], "createFields": [{"field": "first_name", "type": "string", "required": False}, {"field": "email", "type": "string", "required": True}]}]}]

    def test_categories_are_read_once_entity_and_fields_come_from_them_providers_hit_the_entity_route(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: providers([hubspot(), not_connected]) if "/providers" in url else {"body": {"data": self.cats}})
        fastn = client()
        assert [c["slug"] for c in fastn.catalog.categories()] == ["crm"]
        assert fastn.catalog.entity("crm", "contact")["operations"] == ["create", "get"]
        assert [f"{f['field']}{'*' if f.get('required') else ''}" for f in fastn.catalog.fields("crm", "contact")] == ["first_name", "email*"]
        with pytest.raises(FastnApiError) as e1:
            fastn.catalog.entity("crm", "nope")
        assert e1.value.code == "NOT_FOUND"
        with pytest.raises(FastnApiError) as e2:
            fastn.catalog.category("hr")
        assert e2.value.code == "NOT_FOUND"
        assert [f"{p['connectorSlug']}:{p['connected']}" for p in fastn.customer("acme-1").catalog.providers("crm", "contact")] == ["hubspot:True", "pipedrive:False"]
        assert m.urls() == ["/v1/unified/categories", "/v1/unified/crm/contact/providers"]
        assert m.calls[1].headers["x-end-org-ref"] == "acme-1"
        fastn.catalog.refresh()
        fastn.catalog.categories()
        assert m.urls()[-1] == "/v1/unified/categories"


W = ("2026-11-02T09:00:00.000Z", "2026-11-02T12:00:00.000Z")


def iv(a: str, b: str) -> Dict[str, str]:
    return {"start_time": a, "end_time": b}


class TestFreeIntervalArithmetic:
    def test_no_busy_time_is_the_whole_window_busy_covering_the_window_is_nothing(self) -> None:
        assert free_intervals(W[0], W[1], []) == [iv(W[0], W[1])]
        assert free_intervals(W[0], W[1], [iv("2026-11-02T08:00:00.000Z", "2026-11-02T13:00:00.000Z")]) == []
        assert free_intervals("not a date", W[1], []) == []

    def test_overlapping_and_unsorted_busy_intervals_are_merged_ones_outside_the_window_are_ignored(self) -> None:
        busy = [iv("2026-11-02T10:15:00.000Z", "2026-11-02T10:45:00.000Z"), iv("2026-11-02T10:00:00.000Z", "2026-11-02T10:30:00.000Z"), iv("2026-11-02T14:00:00.000Z", "2026-11-02T15:00:00.000Z"), iv("2026-11-02T06:00:00.000Z", "2026-11-02T07:00:00.000Z"), iv("bad", "worse")]
        assert free_intervals(W[0], W[1], busy) == [iv(W[0], "2026-11-02T10:00:00.000Z"), iv("2026-11-02T10:45:00.000Z", W[1])]

    def test_busy_at_the_edges_trims_the_window_slots_drop_the_short_remainder(self) -> None:
        free = free_intervals(W[0], W[1], [iv("2026-11-02T09:00:00.000Z", "2026-11-02T09:20:00.000Z"), iv("2026-11-02T11:50:00.000Z", "2026-11-02T12:00:00.000Z")])
        assert free == [iv("2026-11-02T09:20:00.000Z", "2026-11-02T11:50:00.000Z")]
        assert slots_of(free, 60) == [iv("2026-11-02T09:20:00.000Z", "2026-11-02T10:20:00.000Z"), iv("2026-11-02T10:20:00.000Z", "2026-11-02T11:20:00.000Z")]
        assert slots_of(free, 200) == []

    def test_offsets_and_dates_parse_like_javascript(self) -> None:
        assert parse_iso_ms("2026-10-29T22:04:14+05:30") == parse_iso_ms("2026-10-29T16:34:14Z")
        assert parse_iso_ms("2026-11-02") == parse_iso_ms("2026-11-02T00:00:00.000Z")
        assert parse_iso_ms("2026-11-02T10:00:00.1234567Z") == parse_iso_ms("2026-11-02T10:00:00.123Z")
        assert parse_iso_ms(None) is None and parse_iso_ms("2026-13-40") is None
        assert wire_record({"a": datetime(2026, 1, 1, tzinfo=timezone.utc), "b": None, "c": "x"}) == {"a": "2026-01-01T00:00:00.000Z", "c": "x"}


class TestReviewFixes:
    gcal_row = {"connectorSlug": "googleCalendar", "connectorName": "Google Calendar", "operations": ALL_OPS, "connected": True}

    def test_slot_minutes_must_be_a_positive_number(self, mock: Callable[..., Mock]) -> None:
        free = [iv("2026-11-02T09:00:00.000Z", "2026-11-02T12:00:00.000Z")]
        for bad in [0, -30, math.nan, math.inf, "30", True, None]:
            with pytest.raises(TypeError):
                slots_of(free, bad)  # type: ignore[arg-type]
        m = fx(mock, lambda url, req: {"body": {"data": [self.gcal_row]}})
        with pytest.raises(TypeError):
            client().customer("acme-1").calendar.free_slots({"start_time": "2026-11-02T09:00:00Z", "end_time": "2026-11-02T12:00:00Z", "slot_minutes": -30})
        assert len(m.calls) == 0  # refused before any request

    def test_notes_created_at_present_but_none_still_gets_the_default(self, mock: Callable[..., Mock]) -> None:
        m = fx(mock, lambda url, req: providers([hubspot()]) if "/providers" in url else {"body": {"id": "n1", "provider": "hubspot", "data": {}}})
        client().customer("acme-1").crm.notes.add({"body": "x", "parent_id": "c1", "created_at": None})
        assert (parse_iso_ms(m.json(1)["created_at"]) or 0) > (time.time() - 60) * 1000
        client().customer("acme-2").crm.notes.add({"body": "x", "parent_id": "c1", "created_at": "2026-01-01T00:00:00Z"})
        assert m.json(3)["created_at"] == "2026-01-01T00:00:00Z"  # an explicit value wins

    def test_provider_cache_cleared_when_no_provider_fits_and_re_read_after_the_ttl(self, mock: Callable[..., Mock], monkeypatch: pytest.MonkeyPatch) -> None:
        rows = {"v": [{**self.gcal_row, "connected": False}]}
        m = fx(mock, lambda url, req: providers(rows["v"]) if "/providers" in url else {"body": {"records": []}})
        fastn = client()
        with pytest.raises(FastnApiError) as e0:
            fastn.customer("acme-1").calendar.list()
        assert e0.value.code == "NO_CONNECTED_PROVIDER"
        rows["v"] = [{**self.gcal_row, "operations": ["get"]}]
        with pytest.raises(FastnApiError) as e1:
            fastn.customer("acme-1").calendar.list()
        assert e1.value.code == "OPERATION_NOT_SUPPORTED"
        rows["v"] = [self.gcal_row]
        fastn.customer("acme-1").calendar.list()  # the customer connected: works without a new client
        assert len([u for u in m.urls() if u.endswith("/providers")]) == 3
        fastn.customer("acme-1").calendar.list()  # within the TTL: no new lookup
        assert len([u for u in m.urls() if u.endswith("/providers")]) == 3
        real_now = time.time()
        monkeypatch.setattr(customer_mod, "_now", lambda: real_now + PROVIDER_TTL_SECONDS + 1)
        fastn.customer("acme-1").calendar.list()
        assert len([u for u in m.urls() if u.endswith("/providers")]) == 4  # after the TTL: read again
        fastn.customer("acme-1").forget_provider()
        fastn.customer("acme-1").calendar.list()
        assert len([u for u in m.urls() if u.endswith("/providers")]) == 5

    def test_widgets_a_miss_re_reads_the_list_once(self, mock: Callable[..., Mock]) -> None:
        rows = {"v": [{"id": "wgt_cal", "name": "Google Calendar", "orgId": "partner-1", "connectorRefs": [{"slug": "googleCalendar"}]}]}
        m = fx(mock, lambda url, req: {"body": {"data": rows["v"]}} if "/v1/widgets" in url else {"status": 201, "body": {"data": {"setupId": "stp_1", "setupUrl": "https://x/s", "status": "pending"}}} if req.method == "POST" else {"body": {"data": {}}})
        fastn = client()
        with pytest.raises(FastnApiError) as e0:
            fastn.customer("acme-1").connect("hubspot")
        assert e0.value.code == "WIDGET_NOT_FOUND"
        rows["v"] = [*rows["v"], {"id": "wgt_hs", "name": "HubSpot", "orgId": "partner-1", "connectorRefs": [{"slug": "hubspot"}]}]
        assert fastn.customer("acme-1").connect("hubspot")["widgetId"] == "wgt_hs"
        assert fastn.customer("acme-1").connect("hubspot", widget_id="wgt_hs")["widgetId"] == "wgt_hs"
        assert len([u for u in m.urls() if u.startswith("/v1/widgets")]) == 3  # first read, the re-read on the miss, the re-read on the next miss; then cached

    def test_widgets_inherited_rows_other_orgs_rows_and_the_inactive_version_are_never_offered(self, mock: Callable[..., Mock]) -> None:
        rows = [
            {"id": "wgt_parent_cal", "name": "Google Calendar", "orgId": "platform", "inheritedFrom": {"orgId": "platform"}, "connectorRefs": [{"slug": "googleCalendar"}]},
            {"id": "wgt_cal", "name": "Google Calendar", "orgId": "partner-1", "connectorRefs": [{"slug": "googleCalendar"}]},
            {"id": "wgt_hs_orig", "name": "HubSpot", "orgId": "partner-1", "version": {"groupId": "g1", "kind": "original", "active": False, "originalAvailable": True}, "connectorRefs": [{"slug": "hubspot"}]},
            {"id": "wgt_hs_copy", "name": "HubSpot (ours)", "orgId": "partner-1", "version": {"groupId": "g1", "kind": "custom", "active": True}, "customisedFrom": {"sourceWidgetId": "wgt_hs_orig"}, "connectorRefs": [{"slug": "hubspot"}]},
            {"id": "wgt_other", "name": "Salesforce", "orgId": "partner-2", "connectorRefs": [{"slug": "salesforce"}]},
            {"id": "wgt_slugs", "name": "Slack", "orgId": "partner-1", "connectorSlugs": ["slack"]},
        ]
        fx(mock, lambda url, req: {"body": {"data": rows}} if "/v1/widgets" in url else {"status": 201, "body": {"data": {"setupId": "stp_1", "setupUrl": "https://x/s", "status": "pending"}}} if req.method == "POST" else {"body": {"data": {}}})
        fastn = client()
        assert fastn.customer("acme-1").connect("googleCalendar")["widgetId"] == "wgt_cal"  # not ambiguous with the parent's row
        assert fastn.customer("acme-1").connect("hubspot")["widgetId"] == "wgt_hs_copy"  # the active version only
        assert fastn.customer("acme-1").connect("slack")["widgetId"] == "wgt_slugs"
        with pytest.raises(FastnApiError) as e0:
            fastn.customer("acme-1").connect("salesforce")
        assert e0.value.code == "WIDGET_NOT_FOUND"
        with pytest.raises(FastnApiError) as e1:
            fastn.customer("acme-1").connect("googleCalendar", widget_id="wgt_parent_cal")
        assert e1.value.code == "WIDGET_NOT_FOUND"
