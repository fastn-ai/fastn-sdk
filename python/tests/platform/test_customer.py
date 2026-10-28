# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""The customer context (a port of node/test/unit/customer.test.ts)."""

from __future__ import annotations

import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, List

import httpx
import pytest

from fastn.platform import FastnApiError, FastnClient, FastnNetworkError

from .conftest import Mock, Reply

ME = {"body": {"data": {"actor": "api_key", "org": {"id": "partner-1", "type": "partner"}}}}
org_row = {"id": "11111111-aaaa", "externalRef": "acme-1", "orgId": "acme-1", "name": "Acme", "type": "end_org", "parentId": "partner-1"}
foreign_row = {"id": "99999999-zzzz", "externalRef": "acme-1", "orgId": "acme-1", "name": "Other partner's Acme", "type": "end_org", "parentId": "partner-2"}


def fx(mock: Callable[..., Mock], handler: Callable[[str, httpx.Request], Reply]) -> Mock:
    """Every request through the API mock; whoami always answers the partner org."""
    return mock(lambda url, req: ME if url.endswith("/v1/me") else handler(url, req))


def client(**extra: Any) -> FastnClient:
    return FastnClient(api_key="k", **extra)


def test_resolves_fastns_org_id_under_the_callers_org_only_and_caches_it_on_the_client(mock: Callable[..., Mock]) -> None:
    m = fx(mock, lambda url, req: {"body": {"data": [org_row]}} if "/v1/orgs?" in url else {"body": {"data": [{"id": "conn_1"}]}} if "/v1/connections" in url else {"body": {"data": org_row}})
    fastn = client()
    c = fastn.customer("acme-1")
    assert c.id() == "11111111-aaaa"
    c.connections()
    c.get()
    fastn.customer("acme-1").get()  # a second object for the same ref: no new lookup
    assert m.urls() == ["/v1/me", "/v1/orgs?type=end_org&parent_id=partner-1", "/v1/connections?endOrgId=11111111-aaaa", "/v1/orgs/11111111-aaaa", "/v1/orgs/11111111-aaaa"]


def test_never_matches_another_partners_customer_even_when_the_key_sees_every_org(mock: Callable[..., Mock]) -> None:
    fx(mock, lambda url, req: {"body": {"data": [foreign_row]}} if "/v1/orgs?" in url else None)
    with pytest.raises(FastnApiError, match="not registered") as ei:
        client().customer("acme-1").id()
    assert ei.value.status == 404 and ei.value.code == "NOT_FOUND"


def test_register_creates_once_and_returns_the_existing_org_afterwards(mock: Callable[..., Mock]) -> None:
    created = {"v": False}

    def handler(url: str, req: httpx.Request) -> Reply:
        if "/v1/orgs?type=end_org" in url:
            return {"body": {"data": [org_row] if created["v"] else []}}
        if req.method == "POST":
            created["v"] = True
            return {"status": 201, "body": {"data": org_row}}
        return {"body": {}}

    m = fx(mock, handler)
    c = client().customer("acme-1")
    first = c.register({"name": "Acme"})
    assert first["data"]["id"] == "11111111-aaaa"
    assert m.json(2) == {"plan": "free", "name": "Acme", "orgId": "acme-1"}
    again = c.register({"name": "Acme"})
    assert again["existed"] is True and len([x for x in m.calls if x.method == "POST"]) == 1
    assert c.id() == "11111111-aaaa" and len(m.calls) == 4


def test_register_recovers_from_a_conflict_by_reading_the_org(mock: Callable[..., Mock]) -> None:
    n = {"orgs": 0}

    def handler(url: str, req: httpx.Request) -> Reply:
        if "/v1/orgs?" in url:
            n["orgs"] += 1
            return {"body": {"data": [] if n["orgs"] == 1 else [org_row]}}
        if req.method == "POST":
            return {"status": 409, "body": {"error": {"code": "CONFLICT", "message": "exists"}}}
        return None

    fx(mock, handler)
    r = client().customer("acme-1").register({"name": "Acme"})
    assert r == {"data": org_row, "existed": True}


def test_concurrent_lookups_share_one_list_orgs_and_every_row_seen_fills_the_cache(mock: Callable[..., Mock]) -> None:
    other = {**org_row, "id": "22222222-bbbb", "externalRef": "beta-2", "orgId": "beta-2"}

    def handler(url: str, req: httpx.Request) -> Reply:
        if "/v1/orgs?" in url:
            time.sleep(0.3)  # keep the lookup in flight while the other threads arrive
            return {"body": {"data": [org_row, other]}}
        return None

    m = fx(mock, handler)
    fastn = client()
    with ThreadPoolExecutor(3) as pool:
        futures: List[Future[Any]] = [pool.submit(fastn.customer("acme-1").id), pool.submit(fastn.customer("acme-1").id), pool.submit(fastn.customer("acme-1").find)]
        ids = [f.result() for f in futures]
    assert ids[0] == "11111111-aaaa" and ids[1] == "11111111-aaaa" and ids[2]["id"] == "11111111-aaaa"  # type: ignore[index]
    assert fastn.customer("beta-2").id() == "22222222-bbbb"
    assert m.urls() == ["/v1/me", "/v1/orgs?type=end_org&parent_id=partner-1"]


def test_a_failed_lookup_is_not_cached_and_reaches_every_waiter(mock: Callable[..., Mock]) -> None:
    n = {"orgs": 0}

    def handler(url: str, req: httpx.Request) -> Reply:
        if "/v1/orgs?" in url:
            n["orgs"] += 1
            if n["orgs"] == 1:
                time.sleep(0.2)
                return {"status": 500, "body": {"error": "boom"}}
            return {"body": {"data": [org_row]}}
        return None

    fx(mock, handler)
    fastn = client(retries=0)
    results: List[Any] = []

    def run() -> None:
        try:
            results.append(fastn.customer("acme-1").id())
        except FastnApiError as e:
            results.append(e)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(isinstance(r, FastnApiError) and r.status == 500 for r in results)
    assert fastn.customer("acme-1").id() == "11111111-aaaa"  # the next lookup works


def test_unknown_ref_fails_clearly(mock: Callable[..., Mock]) -> None:
    fx(mock, lambda url, req: {"body": {"data": []}})
    with pytest.raises(FastnApiError, match="not registered"):
        client().customer("ghost").id()
    with pytest.raises(TypeError, match="ref is required"):
        client().customer("")


def test_remove_suspends_then_deletes_a_failed_delete_puts_the_org_back_to_active_and_says_so(mock: Callable[..., Mock]) -> None:
    m = fx(mock, lambda url, req: {"body": {"data": [org_row]}} if "/v1/orgs?" in url else {"status": 503, "body": {"error": "down"}} if req.method == "DELETE" else {"body": {"data": org_row}})
    c = client(retries=0).customer("acme-1")
    with pytest.raises(FastnApiError, match="suspended before the delete; it is active again"):
        c.remove()
    writes = [f"{x.method} {str(x.url).replace('https://api.fastn.dev', '')} {x.content.decode()}" for x in m.calls if x.method != "GET"]
    assert writes == ['PUT /v1/orgs/11111111-aaaa {"status":"suspended"}', "DELETE /v1/orgs/11111111-aaaa ", 'PUT /v1/orgs/11111111-aaaa {"status":"active"}']


def test_remove_treats_a_lost_delete_answer_as_removed_when_the_org_is_gone(mock: Callable[..., Mock]) -> None:
    m = fx(mock, lambda url, req: {"body": {"data": [org_row]}} if "/v1/orgs?" in url else httpx.ReadError("socket hang up") if req.method == "DELETE" else {"status": 404, "body": {"error": "Not found", "code": "NOT_FOUND"}} if req.method == "GET" else {"body": {"data": org_row}})
    c = client(retries=0).customer("acme-1")
    c.remove()
    assert [m.line(x) for x in m.calls][-3:] == ["PUT /v1/orgs/11111111-aaaa", "DELETE /v1/orgs/11111111-aaaa", "GET /v1/orgs/11111111-aaaa"]


def test_remove_reports_still_suspended_when_the_rollback_fails_too(mock: Callable[..., Mock]) -> None:
    def handler(url: str, req: httpx.Request) -> Reply:
        if "/v1/orgs?" in url:
            return {"body": {"data": [org_row]}}
        if req.method == "DELETE":
            return httpx.ReadError("socket hang up")
        if req.method == "PUT" and b"active" in req.content:
            return {"status": 500, "body": {"error": "down"}}
        return {"body": {"data": org_row}}

    fx(mock, handler)
    with pytest.raises(FastnNetworkError, match="it is still suspended"):
        client(retries=0).customer("acme-1").remove()


def test_setup_link_and_embed_token_carry_the_ref_records_carry_x_end_org_ref(mock: Callable[..., Mock]) -> None:
    m = fx(mock, lambda url, req: {"body": {"data": {}}})
    c = client().customer("acme-1")
    c.setup_link({"widgetId": "w1", "connectionName": "Google Calendar"})
    assert m.json(0) == {"createIfMissing": True, "widgetId": "w1", "connectionName": "Google Calendar", "externalRef": "acme-1"}
    c.embed_token({"userId": "u1"})
    assert m.json(1) == {"createIfMissing": True, "userId": "u1", "endOrgId": "acme-1"}
    meetings = c.records("scheduling", "meeting", provider="googleCalendar")
    meetings.create({"title": "x"}, idempotency_key="b1")
    assert str(m.calls[2].url) == "https://api.fastn.dev/v1/unified/scheduling/meeting?provider=googleCalendar"
    assert m.calls[2].headers["x-end-org-ref"] == "acme-1" and m.calls[2].headers["idempotency-key"] == "b1"
    meetings.search({"query": "x"})
    meetings.update("m1", {"title": "y"})
    meetings.delete("m1")
    meetings.get("m1")
    meetings.list({"page_size": 5})
    meetings.providers()
    assert [m.line(x) for x in m.calls[3:]] == [
        "POST /v1/unified/scheduling/meeting/search?provider=googleCalendar", "PATCH /v1/unified/scheduling/meeting/m1?provider=googleCalendar",
        "DELETE /v1/unified/scheduling/meeting/m1?provider=googleCalendar", "GET /v1/unified/scheduling/meeting/m1?provider=googleCalendar",
        "GET /v1/unified/scheduling/meeting?provider=googleCalendar&page_size=5", "GET /v1/unified/scheduling/meeting/providers",
    ]
    for x in m.calls[3:]:
        assert x.headers["x-end-org-ref"] == "acme-1"


def test_customer_api_fills_the_customer_into_the_body_where_the_route_takes_it_there(mock: Callable[..., Mock]) -> None:
    m = fx(mock, lambda url, req: {"body": {"data": [org_row]}} if "/v1/orgs?" in url else {"body": {"data": {"authorizationUrl": "https://accounts.example/oauth"}}})
    fastn = client()
    c = fastn.customer("acme-1")
    # endOrgId routes get fastn's id of the customer (resolved once)
    c.api.connections.initiate_oauth_connection({"connectorId": "googleCalendar", "connectionName": "work"})
    oauth = next(x for x in m.calls if str(x.url).endswith("/v1/oauth/initiate"))
    assert m.json(m.calls.index(oauth)) == {"connectorId": "googleCalendar", "connectionName": "work", "endOrgId": "11111111-aaaa"}
    assert oauth.headers["x-end-org-ref"] == "acme-1"
    c.api.events.create_event_subscription({"url": "https://partner.app/hook", "events": ["unified.event"]})  # type: ignore[typeddict-unknown-key]
    assert m.json(-1)["endOrgId"] == "11111111-aaaa"
    # externalRef routes get the ref itself
    c.api.embed.create_setup_link({"widgetId": "w1", "connectionName": "x"})
    assert m.json(-1) == {"widgetId": "w1", "connectionName": "x", "externalRef": "acme-1"}
    # an explicit value wins
    c.api.connections.initiate_oauth_connection({"connectorId": "hubspot", "connectionName": "x", "endOrgId": "other"})
    assert m.json(-1)["endOrgId"] == "other"
    # routes without a customer field are untouched (only the header)
    c.api.orgs.list_orgs({"type": "end_org"})
    assert m.calls[-1].content == b"" and m.calls[-1].headers["x-end-org-ref"] == "acme-1"
    # the org being edited is not "the customer": updateTenant's externalRef is left alone
    c.api.orgs.update_tenant({"id": "some-org", "name": "Renamed"})
    assert m.json(-1) == {"name": "Renamed"}
    # camelCase aliases work on the scoped api too
    c.api.orgs.updateTenant({"id": "some-org", "name": "Renamed"})
    assert m.json(-1) == {"name": "Renamed"}
    # createEmbedToken takes the ref itself (id-or-ref route), so it works before register() and needs no lookup
    m.use(lambda url, req: {"body": {"data": {"token": "emb_x"}}})
    before = len(m.calls)
    client().customer("new-cust").api.embed.create_embed_token({"createIfMissing": True, "userId": "u1"})
    assert m.urls()[before:] == ["/v1/embed/token"]
    assert m.json(-1) == {"createIfMissing": True, "userId": "u1", "endOrgId": "new-cust"}
    # connect() helper, object form
    m.use(lambda url, req: {"body": {"data": [org_row]}} if "/v1/orgs?" in url else {"body": {"data": {"authorizationUrl": "https://accounts.example/oauth"}}})
    r = c.connect({"connectorId": "googleCalendar", "connectionName": "work", "returnUrl": "https://partner.app/done"})
    assert r["data"]["authorizationUrl"].startswith("https://")
    assert m.json(-1) == {"connectorId": "googleCalendar", "connectionName": "work", "returnUrl": "https://partner.app/done", "endOrgId": "11111111-aaaa"}


def test_connect_with_credentials_fills_the_auth_method_and_customer_and_leaves_the_field_check_to_the_platform(mock: Callable[..., Mock]) -> None:
    methods = {"data": [{"id": "am_oauth", "authType": "OAUTH_2", "inputContract": {}}, {"id": "am_key", "authType": "API_KEY", "inputContract": {"type": "object", "required": ["apiKey"], "properties": {"apiKey": {"type": "string"}, "region": {"type": "string"}}}}]}
    incomplete = {"v": False}

    def handler(url: str, req: httpx.Request) -> Reply:
        if "/v1/orgs?" in url:
            return {"body": {"data": [org_row]}}
        if "/v1/auth-methods" in url:
            return {"body": methods}
        if incomplete["v"]:
            return {"status": 400, "body": {"error": "Incomplete credentials for this connector: missing accountId", "code": "CREDENTIALS_INCOMPLETE", "missing": ["accountId"]}}
        return {"status": 201, "body": {"data": {"id": "conn_9"}}}

    m = fx(mock, handler)
    c = client().customer("acme-1")
    f = c.auth_fields("acme-crm")
    assert f["authMethodId"] == "am_key" and f["authType"] == "API_KEY" and f["names"] == ["apiKey", "region"] and f["required"] == ["apiKey"]
    assert str(m.calls[-1].url) == "https://api.fastn.dev/v1/auth-methods?connectorId=acme-crm"
    # a BEARER/API_KEY connection whose stored key differs from the contract name is sent as given (the platform accepts it)
    r = c.connect_with_credentials({"connectorId": "acme-crm", "credentials": {"accessToken": "s3cret"}, "name": "Acme CRM"})
    assert r["data"]["id"] == "conn_9"
    assert m.json(-1) == {"connectorId": "acme-crm", "credentials": {"accessToken": "s3cret"}, "name": "Acme CRM", "authMethodId": "am_key", "endOrgId": "11111111-aaaa"}
    # an explicit authMethodId skips the auth-method lookup
    before = len(m.calls)
    c.connect_with_credentials({"connectorId": "acme-crm", "authMethodId": "am_in", "credentials": {"custom": {"accountId": "a", "applicationKey": "b"}}})
    assert m.urls()[before:] == ["/v1/connections"]
    # the platform's answer for an incomplete INPUT set comes through with the missing names
    incomplete["v"] = True
    with pytest.raises(FastnApiError) as ei:
        c.connect_with_credentials({"connectorId": "acme-crm", "authMethodId": "am_in", "credentials": {"custom": {}}})
    assert ei.value.code == "CREDENTIALS_INCOMPLETE" and ei.value.body["missing"] == ["accountId"]
    # an unknown auth method is a typed 404
    with pytest.raises(FastnApiError, match="not found") as e2:
        c.auth_fields("acme-crm", "am_missing")
    assert e2.value.code == "NOT_FOUND"


def test_run_action_pins_the_customers_own_connection_and_installation_for_a_raw_connector_action(mock: Callable[..., Mock]) -> None:
    conn = {"id": "ucl:p:cust:hs:default", "name": "Inline CRM", "connectorId": "hs-uuid", "connectorSlug": "hubspot"}

    def handler(url: str, req: httpx.Request) -> Reply:
        if "/v1/orgs?" in url:
            return {"body": {"data": [org_row]}}
        if "/v1/connections" in url:
            return {"body": {"data": [conn]}}
        if "/v1/installations" in url:
            return {"body": {"data": [{"id": "inst_other", "endOrgId": "other", "connections": {"hubspot": "x"}}, {"id": "inst_1", "endOrgId": "11111111-aaaa", "connections": {"hubspot": conn["id"]}}]}}
        if "/v2/connectors/hubspot/actions" in url:
            return {"body": {"data": [{"id": "act_upd", "slug": "updateDeal"}]}}
        if "/v2/connectors/slack/actions" in url:
            return {"body": {"data": []}}
        if "/v1/actions/act_upd/execute" in url:
            return {"body": {"data": {"success": True, "response": {"id": "deal_1"}}}}
        return None

    m = fx(mock, handler)
    c = client().customer("acme-1")
    r = c.run_action("hubspot", "updateDeal", {"dealId": "deal_1", "properties": {"dealstage": "qualifiedtobuy"}})
    assert r["data"]["response"]["id"] == "deal_1"
    exec_ = next(i for i, x in enumerate(m.calls) if str(x.url).endswith("/v1/actions/act_upd/execute"))
    assert m.json(exec_) == {"connectorId": "hs-uuid", "connectionName": "Inline CRM", "connectionId": conn["id"], "installationId": "inst_1", "input": {"dealId": "deal_1", "properties": {"dealstage": "qualifiedtobuy"}}}
    assert "end_org_id=11111111-aaaa" in str(next(x for x in m.calls if "/v1/installations" in str(x.url)).url)  # only this customer's installations
    with pytest.raises(FastnApiError, match='no action "noSuchAction"'):
        c.run_action("hubspot", "noSuchAction")
    with pytest.raises(FastnApiError, match="no slack connection") as ei:
        c.run_action("slack", "postMessage")
    assert ei.value.code == "CONNECTION_NOT_FOUND"


def test_run_action_works_from_the_customers_connection_alone_when_there_is_no_installation(mock: Callable[..., Mock]) -> None:
    conn = {"id": "conn_hs", "name": "HubSpot", "connectorId": "hs-uuid", "connectorSlug": "hubspot"}

    def handler(url: str, req: httpx.Request) -> Reply:
        if "/v1/orgs?" in url:
            return {"body": {"data": [org_row]}}
        if "/v1/connections" in url:
            return {"body": {"data": [conn]}}
        if "/v1/installations" in url:
            return {"body": {"data": []}}
        if "/v2/connectors/hubspot/actions" in url:
            return {"body": {"data": [{"id": "act_log", "slug": "logCall"}]}}
        if "/v1/actions/act_log/execute" in url:
            return {"body": {"data": {"success": True, "response": {"id": "call_1"}}}}
        return None

    m = fx(mock, handler)
    r = client().customer("acme-1").run_action("hubspot", "logCall", {"note": "x"}, mock_mode=True)
    assert r["data"]["response"]["id"] == "call_1"
    exec_ = next(i for i, x in enumerate(m.calls) if str(x.url).endswith("/v1/actions/act_log/execute"))
    assert m.json(exec_) == {"connectorId": "hs-uuid", "connectionName": "HubSpot", "connectionId": "conn_hs", "input": {"note": "x"}, "mockMode": True}


def test_me_is_cached_and_a_failed_whoami_is_not(mock: Callable[..., Mock]) -> None:
    n = {"me": 0}

    def handler(url: str, req: httpx.Request) -> Reply:
        n["me"] += 1
        return {"status": 500, "body": {"error": "down"}} if n["me"] == 1 else ME

    m = mock(handler)
    fastn = client(retries=0)
    with pytest.raises(FastnApiError):
        fastn.me()
    assert fastn.me()["org"]["id"] == "partner-1"
    assert fastn.me()["actor"] == "api_key"
    assert len(m.calls) == 2
