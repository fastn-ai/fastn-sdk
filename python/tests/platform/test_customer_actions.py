# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""watch / unwatch, disconnect, rename_account, update, call_log and fastn.webhooks (a port of
node/test/unit/customer-actions.test.ts)."""

from __future__ import annotations

from typing import Any, Callable, Dict
from urllib.parse import quote

import httpx
import pytest

from fastn.platform import EVENT_ALIASES, FastnApiError, FastnClient

from .conftest import Mock, Reply

org_row = {"id": "11111111-aaaa", "externalRef": "acme-1", "orgId": "acme-1", "name": "Acme", "type": "end_org", "parentId": "partner-1"}
hs_conn: Dict[str, Any] = {"id": "ucl:p:1:9036:default", "name": "Main CRM", "connectorId": "9036", "connector": {"slug": "hubspot", "name": "HubSpot"}, "status": "ACTIVE"}
cal_conn: Dict[str, Any] = {"id": "ucl:p:1:867f:default", "name": "Main calendar", "connectorId": "867f", "connector": {"slug": "googleCalendar", "name": "Google Calendar"}, "status": "ACTIVE"}
events = [{"id": "contact.creation", "label": "Contact Created"}, {"id": "contact.propertyChange", "label": "Contact Property Changed"}, {"id": "deal.propertyChange", "label": "Deal Property Changed"}]


def base(url: str, req: httpx.Request) -> Reply:
    if url.endswith("/v1/me"):
        return {"body": {"data": {"actor": "api_key", "org": {"id": "partner-1"}}}}
    if "/v1/orgs?" in url:
        return {"body": {"data": [org_row]}}
    if "/v1/connectors?" in url:
        return {"body": {"data": [{"id": "9036", "slug": "hubspot", "name": "HubSpot"}]}}
    if "/v1/connections?" in url:
        return {"body": {"data": [hs_conn, cal_conn]}}
    if "/connectors/9036/events" in url:
        return {"body": {"data": events}}
    # the API nests the app part of a trigger under appTrigger (seen live on prod)
    if "/app-triggers" in url and req.method == "POST":
        return {"status": 201, "body": {"data": {"id": "trg-1", "name": "x", "status": "ACTIVE", "endOrgId": "11111111-aaaa", "appTrigger": {"triggerId": "trg-1", "type": "WEBHOOK", "connectorId": "9036", "connectionId": hs_conn["id"], "accountId": "245765780", "events": [{"id": "contact.creation", "label": "Contact Created"}]}}}}
    if "/app-triggers?" in url:
        return {"body": {"data": [{"id": "trg-1", "status": "ACTIVE", "endOrgId": "11111111-aaaa", "appTrigger": {"connectorId": "9036", "events": [{"id": "contact.creation"}]}}, {"id": "trg-2", "status": "ACTIVE", "appTrigger": {"connectorId": "other", "events": []}}]}}
    return {"body": {"data": {}}}


def client() -> FastnClient:
    return FastnClient(api_key="k")


class TestWatchUnwatch:
    def test_maps_plain_event_names_pins_the_account_sends_the_trigger_answers_a_watch_without_internal_ids(self, mock: Callable[..., Mock]) -> None:
        m = mock(base)
        w = client().customer("acme-1").watch("hubspot", ["contact.created", "deal.stageChanged", "contact.propertyChange"], account_id="245765780")
        post = next(i for i, x in enumerate(m.calls) if x.method == "POST")
        assert "/app-triggers" in str(m.calls[post].url)
        body = m.json(post)
        assert {k: body[k] for k in ("connectorId", "connectorName", "connectionId", "accountId", "type", "routes", "status", "endOrgId", "name")} == {"connectorId": "9036", "connectorName": "HubSpot", "connectionId": hs_conn["id"], "accountId": "245765780", "type": "WEBHOOK", "routes": [], "status": "ACTIVE", "endOrgId": "11111111-aaaa", "name": "hubspot changes for acme-1"}
        assert [e["id"] for e in body["events"]] == ["contact.creation", "deal.propertyChange", "contact.propertyChange"]
        assert body["events"][0] == {"id": "contact.creation", "label": "Contact Created"}
        assert {k: w[k] for k in ("id", "app", "events", "accountId", "connectionId", "connectorId", "status")} == {"id": "trg-1", "app": "hubspot", "events": ["contact.creation"], "accountId": "245765780", "connectionId": hs_conn["id"], "connectorId": "9036", "status": "ACTIVE"}
        assert "endOrgId" not in w and "appTrigger" not in w

    def test_refuses_an_unknown_event_name_with_the_valid_list_and_an_empty_list(self, mock: Callable[..., Mock]) -> None:
        m = mock(base)
        with pytest.raises(FastnApiError) as ei:
            client().customer("acme-1").watch("hubspot", ["contact.exploded"])
        err = ei.value
        assert err.code == "EVENT_NOT_FOUND" and err.status == 400 and "contact.created" in err.message and "contact.creation" in err.message
        assert err.details == {"app": "hubspot", "event": "contact.exploded", "valid": ["contact.creation", "contact.propertyChange", "deal.propertyChange"]}
        assert not any(x.method == "POST" for x in m.calls)
        with pytest.raises(TypeError):
            client().customer("acme-1").watch("hubspot", [])

    def test_no_account_404_two_accounts_409_unless_connection_id_is_given(self, mock: Callable[..., Mock]) -> None:
        m = mock(lambda url, req: {"body": {"data": [cal_conn]}} if "/v1/connections?" in url else base(url, req))
        with pytest.raises(FastnApiError) as e0:
            client().customer("acme-1").watch("hubspot", ["contact.created"])
        assert e0.value.code == "CONNECTION_NOT_FOUND" and e0.value.status == 404
        m.use(lambda url, req: {"body": {"data": [hs_conn, {**hs_conn, "id": "ucl:p:1:9036:second"}]}} if "/v1/connections?" in url else base(url, req))
        with pytest.raises(FastnApiError) as e1:
            client().customer("acme-1").watch("hubspot", ["contact.created"])
        assert e1.value.code == "CONNECTION_AMBIGUOUS" and e1.value.status == 409
        w = client().customer("acme-1").watch("hubspot", ["contact.created"], connection_id="ucl:p:1:9036:second", name="custom")
        assert w["id"] == "trg-1"
        post = next(i for i, x in enumerate(m.calls) if x.method == "POST")
        assert m.json(post)["connectionId"] == "ucl:p:1:9036:second" and m.json(post)["name"] == "custom" and "accountId" not in m.json(post)

    def test_watches_lists_only_that_apps_triggers_unwatch_app_deletes_them_unwatch_id_deletes_one(self, mock: Callable[..., Mock]) -> None:
        m = mock(base)
        c = client().customer("acme-1")
        lst = c.watches("hubspot")
        assert [w["id"] for w in lst] == ["trg-1"] and "endOrgId" not in lst[0]
        assert "appTrigger" not in lst[0] and lst[0]["connectionId"] is None and lst[0]["events"] == ["contact.creation"]
        assert next(u for u in m.urls() if "/app-triggers?" in u) == "/v1/app-triggers?limit=100&end_org_id=11111111-aaaa"  # no connectorId query: the API does not match it against the nested app part
        assert [w["id"] for w in c.watches()] == ["trg-1", "trg-2"]
        assert c.unwatch("hubspot") == ["trg-1"]
        assert c.unwatch("trg-1") == ["trg-1"]  # by id: only when it is this customer's
        assert [m.line(x) for x in m.calls if x.method == "DELETE"] == ["DELETE /v1/app-triggers/trg-1", "DELETE /v1/app-triggers/trg-1"]

    def test_two_plain_names_that_map_to_one_id_are_sent_once_a_connection_id_of_another_app_or_another_customer_is_refused(self, mock: Callable[..., Mock]) -> None:
        m = mock(base)
        c = client().customer("acme-1")
        c.watch("hubspot", ["deal.updated", "deal.stageChanged", "deal.propertyChange"], account_id="245765780")
        post = next(i for i, x in enumerate(m.calls) if x.method == "POST")
        assert [e["id"] for e in m.json(post)["events"]] == ["deal.propertyChange"]
        with pytest.raises(FastnApiError) as e0:
            c.watch("hubspot", ["contact.created"], connection_id=cal_conn["id"])
        assert e0.value.code == "CONNECTION_MISMATCH" and e0.value.status == 400 and "googleCalendar" in e0.value.message
        with pytest.raises(FastnApiError) as e1:
            c.watch("hubspot", ["contact.created"], connection_id="ucl:p:9:9036:someone-else")
        assert e1.value.code == "CONNECTION_NOT_FOUND" and e1.value.status == 404
        assert len([x for x in m.calls if x.method == "POST"]) == 1

    def test_watches_reads_every_page_so_unwatch_app_removes_watches_past_the_first_page(self, mock: Callable[..., Mock]) -> None:
        pages = {"": [{"id": f"trg-other-{i}", "status": "ACTIVE", "appTrigger": {"connectorId": "other", "events": []}} for i in range(3)], "p2": [{"id": "trg-hs-old", "status": "ACTIVE", "appTrigger": {"connectorId": "9036", "events": [{"id": "contact.creation"}]}}]}

        def handler(url: str, req: httpx.Request) -> Reply:
            if "/app-triggers?" in url:
                cur = req.url.params.get("cursor", "")
                return {"body": {"data": pages[cur], "meta": {"nextCursor": "p2" if cur == "" else None}}}
            return base(url, req)

        m = mock(handler)
        c = client().customer("acme-1")
        assert [w["id"] for w in c.watches("hubspot")] == ["trg-hs-old"]
        assert c.unwatch("hubspot") == ["trg-hs-old"]
        lists = [u for u in m.urls() if "/app-triggers?" in u]
        assert len(lists) == 4 and "limit=100" in lists[0] and "cursor=p2" in lists[1]
        with pytest.raises(FastnApiError) as ei:
            c.unwatch("3ffc9b08-0000-4000-8000-000000000000")  # not this customer's
        assert ei.value.code == "WATCH_NOT_FOUND" and ei.value.status == 404
        assert [m.line(x) for x in m.calls if x.method == "DELETE"] == ["DELETE /v1/app-triggers/trg-hs-old"]

    def test_the_connector_row_is_read_once_per_client_and_a_missing_one_is_a_404(self, mock: Callable[..., Mock]) -> None:
        m = mock(base)
        fastn = client()
        assert [e["id"] for e in fastn.customer("acme-1").watchable_events("hubspot")] == ["contact.creation", "contact.propertyChange", "deal.propertyChange"]
        fastn.customer("acme-1").watchable_events("hubspot")
        assert len([u for u in m.urls() if "/v1/connectors?" in u]) == 1
        assert "/v1/connectors?slug=hubspot" in m.urls()
        m.use(lambda url, req: {"body": {"data": []}} if "/v1/connectors?" in url else base(url, req))
        with pytest.raises(FastnApiError) as ei:
            fastn.customer("acme-1").watchable_events("nope")
        assert ei.value.code == "CONNECTOR_NOT_FOUND"

    def test_event_aliases_covers_the_pilots_names(self) -> None:
        assert EVENT_ALIASES["hubspot"]["deal.stageChanged"] == "deal.propertyChange"
        assert EVENT_ALIASES["hubspot"]["contact.created"] == "contact.creation"


class TestAccountsAndWebhooks:
    def test_map_to_the_raw_routes_with_the_customers_fastn_id_where_the_route_needs_it(self, mock: Callable[..., Mock]) -> None:
        m = mock(lambda url, req: {"body": {"data": [{"id": "ucall_1", "correlationId": "c1", "operation": "create", "endOrgId": "11111111-aaaa", "status": 201}]}} if "/unified/calls" in url else {"body": {"data": {"id": "x", "name": "Front desk"}}} if req.method == "PUT" else base(url, req))
        c = client().customer("acme-1")
        c.disconnect(hs_conn["id"])
        assert c.rename_account(hs_conn["id"], "Front desk") == {"id": "x", "name": "Front desk"}
        assert c.update({"name": "Acme Dental Ltd", "status": "suspended"}) == {"id": "x", "name": "Front desk"}
        log = c.call_log("c1")
        assert log == [{"id": "ucall_1", "correlationId": "c1", "operation": "create", "status": 201}]  # no internal customer id
        with pytest.raises(FastnApiError) as e0:
            c.disconnect("ucl:p:9:9036:someone-else")  # another customer's account: refused before any write
        assert e0.value.code == "CONNECTION_NOT_FOUND" and e0.value.status == 404
        with pytest.raises(FastnApiError) as e1:
            c.rename_account("ucl:p:9:9036:someone-else", "x")
        assert e1.value.code == "CONNECTION_NOT_FOUND"
        calls = [f"{m.line(x)} {x.content.decode() or 'null'}" for x in m.calls if not str(x.url).endswith("/v1/me") and "/v1/orgs?" not in str(x.url) and "/v1/connections?" not in str(x.url)]
        enc = quote(hs_conn["id"], safe="")
        assert calls == [
            f"DELETE /v1/connections/{enc} null",
            f'PUT /v1/connections/{enc} {{"name":"Front desk"}}',
            'PUT /v1/orgs/11111111-aaaa {"name":"Acme Dental Ltd","status":"suspended"}',
            "GET /v1/unified/calls?correlation_id=c1 null",
        ]
        assert next(x for x in m.calls if "/unified/calls" in str(x.url)).headers["x-end-org-ref"] == "acme-1"
        with pytest.raises(TypeError):
            c.disconnect("")
        with pytest.raises(TypeError):
            c.call_log("")
        with pytest.raises(TypeError):
            c.rename_account(hs_conn["id"], "")

    def test_fastn_webhooks_wraps_the_subscription_routes_and_answers_the_data(self, mock: Callable[..., Mock]) -> None:
        def handler(url: str, req: httpx.Request) -> Reply:
            if "/event-subscriptions" in url and req.method == "POST" and not (url.endswith("/test") or "/rotate" in url or "/replay" in url):
                return {"status": 201, "body": {"data": {"id": "esub_1", "secret": "whsec_x"}}}
            if "/deliveries" in url and req.method == "GET":
                return {"body": {"data": [{"id": "evd_1", "status": "delivered"}]}}
            if url.endswith("/event-subscriptions"):
                return {"body": {"data": [{"id": "esub_1"}]}}
            return {"body": {"data": {"id": "esub_1", "ok": True}}}

        m = mock(handler)
        fastn = client()
        made = fastn.webhooks.create({"url": "https://hooks.example.com/f", "eventTypes": ["connection.connected"]})
        assert made["secret"] == "whsec_x"
        assert [s["id"] for s in fastn.webhooks.list()] == ["esub_1"]
        assert fastn.webhooks.get("esub_1")["ok"] is True
        assert fastn.webhooks.update("esub_1", {"description": "d"})["ok"] is True
        fastn.webhooks.test("esub_1")
        fastn.webhooks.rotate_secret("esub_1")
        assert fastn.webhooks.deliveries("esub_1", limit=5, status="delivered")[0]["id"] == "evd_1"
        fastn.webhooks.replay("evd_1")
        fastn.webhooks.delete("esub_1")
        assert [m.line(x) for x in m.calls] == [
            "POST /v1/event-subscriptions", "GET /v1/event-subscriptions", "GET /v1/event-subscriptions/esub_1", "PATCH /v1/event-subscriptions/esub_1",
            "POST /v1/event-subscriptions/esub_1/test", "POST /v1/event-subscriptions/esub_1/rotate-secret", "GET /v1/event-subscriptions/esub_1/deliveries?status=delivered&limit=5",
            "POST /v1/event-subscriptions/deliveries/evd_1/replay", "DELETE /v1/event-subscriptions/esub_1",
        ]
        assert m.json(0) == {"url": "https://hooks.example.com/f", "eventTypes": ["connection.connected"]}
        assert m.json(3) == {"description": "d"}
