# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Proves customer scoping end to end on an environment where a throw-away connector can be made: a connection stored
with typed-in credentials through customer.connect_with_credentials() lands on the customer org, is listed by
customer.connections(), and is not listed as one of the partner's own connections. A port of
node/test/live/customer-scope.test.ts, plus the register/remove round trip of node/test/live/prod.test.ts.
Never runs on production (it creates a connector and a throw-away customer org).
Env: LIVE=1, FASTN_API_KEY, FASTN_TEST_CUSTOMER; FASTN_BASE_URL (default https://api.fastn-test.dev).
"""

from __future__ import annotations

import os
from typing import Any, Dict, Iterator, Optional, cast

import pytest

from fastn.platform import FastnApiError, FastnClient

from ._shared import BASE_URL, E2E, data_of, evidence, guard_production, live, not_on_prod, run

guard_production()
pytestmark = [live, not_on_prod]
ev = evidence("customer-scope")
state: Dict[str, Optional[str]] = {"connector": None, "connection": None, "embed": None, "customer": None}
EMBED_REF = f"sdk_py_embed_{run}"  # a customer that does not exist yet; made by createIfMissing, removed at the end
CUSTOMER_REF = f"sdk_py_test_customer_{run}"


@pytest.fixture(scope="module")
def fastn() -> Iterator[FastnClient]:
    client = FastnClient(api_key=os.environ["FASTN_API_KEY"], base_url=BASE_URL)
    yield client
    for ref_key in ("embed", "customer"):
        ref = state[ref_key]
        if ref:
            try:
                client.customer(ref).remove()
            except Exception as e:  # noqa: BLE001
                ev(f"cleanup {ref_key} customer", str(e))
    if state["connection"]:
        try:
            client.connections.delete_connections({"id": state["connection"]})
        except Exception as e:  # noqa: BLE001
            ev("cleanup connection", str(e))
    if state["connector"]:
        try:
            client.connectors.delete_connector({"id": state["connector"]})
        except Exception as e:  # noqa: BLE001
            ev("cleanup connector", str(e))
    client.close()


def test_register_is_idempotent_and_remove_suspends_then_deletes(fastn: FastnClient) -> None:
    c = fastn.customer(CUSTOMER_REF)
    assert c.find() is None
    created = c.register({"name": f"SDK py test {run}"})
    state["customer"] = CUSTOMER_REF
    ev("register", data_of(created))
    fastn_id = data_of(created)["id"]
    assert fastn_id
    again = c.register({"name": f"SDK py test {run}"})
    assert again["existed"] is True and data_of(again)["id"] == fastn_id
    row = fastn.customer(CUSTOMER_REF).find()
    assert row and row["id"] == fastn_id and row.get("externalRef") == CUSTOMER_REF
    with pytest.raises(FastnApiError) as ei:
        fastn.orgs.delete_tenant({"id": fastn_id})
    assert ei.value.status == 400  # the API wants the org suspended first; remove() does both
    fastn.customer(CUSTOMER_REF).remove()
    state["customer"] = None
    assert fastn.customer(CUSTOMER_REF).find() is None


def test_makes_a_throw_away_api_key_connector_or_records_why_it_cannot(fastn: FastnClient) -> None:
    try:
        c = data_of(fastn.connectors.create_connector({  # type: ignore[typeddict-unknown-key]
            "name": f"SDK py scope {run}", "slug": f"sdkPyScope{run}", "domain": "https://httpbin.org", "visibility": "private",
            "authMethods": [{"type": "API_KEY", "title": "API key", "isDefault": True, "inputContract": {"type": "object", "properties": {"apiKey": {"type": "string"}}, "required": ["apiKey"]}, "authConfig": {"apiKeyName": "X-Api-Key"}}],
        }))
    except FastnApiError as e:
        if e.code == "quota_exceeded" or e.status == 403:
            ev("connector", f"cannot create a connector here: {e.message}")
            pytest.skip(f"connector quota: {e.message}")
        raise
    state["connector"] = c["id"]
    ev("connector", {"id": c["id"], "slug": c.get("slug")})


def test_auth_fields_reads_the_credential_fields_from_the_auth_method(fastn: FastnClient) -> None:
    if not state["connector"]:
        pytest.skip("no connector")
    f = fastn.customer(E2E).auth_fields(state["connector"])
    ev("authFields", f)
    assert "apiKey" in f["names"] and "apiKey" in f["required"] and "API_KEY" in str(f["authType"]).upper()


def test_connect_with_credentials_stores_the_connection_on_the_customer_org(fastn: FastnClient) -> None:
    if not state["connector"]:
        pytest.skip("no connector")
    customer = fastn.customer(E2E)
    stored = data_of(customer.connect_with_credentials({"connectorId": state["connector"], "credentials": {"apiKey": f"scope-{run}"}, "name": f"sdk-py-scope-{run}"}))
    connection_id = stored.get("id") or stored.get("connectionId") or (stored.get("connections") or [{}])[0].get("id")
    state["connection"] = connection_id
    ev("stored", {"id": connection_id, "endOrgId": stored.get("endOrgId") or stored.get("orgId")})
    assert connection_id
    mine = data_of(customer.connections())
    partner_own = data_of(fastn.connections.list_connections(cast(Any, {"connectorId": state["connector"]})))
    ev("where it landed", {"customerHasIt": any(x["id"] == connection_id for x in mine), "partnerListHasIt": any(x["id"] == connection_id for x in partner_own), "customerId": customer.id()})
    assert any(x["id"] == connection_id for x in mine)
    assert not any(x["id"] == connection_id and not x.get("endOrgId") and not x.get("end_org_id") for x in partner_own)


def test_connect_returns_an_oauth_url_for_the_customer_or_the_platforms_reason_why_not(fastn: FastnClient) -> None:
    if not state["connector"]:
        pytest.skip("no connector")
    try:
        r = fastn.customer(E2E).connect({"connectorId": state["connector"], "connectionName": f"sdk-py-scope-oauth-{run}", "returnUrl": "https://example.com/done"})
    except FastnApiError as e:
        ev("connect", {"status": e.status, "message": e.message})
        assert e.status < 500 and "oauth" in e.message.lower()
        return
    ev("connect", {"authorizationUrl": bool(data_of(r).get("authorizationUrl"))})
    assert str(data_of(r).get("authorizationUrl", "")).startswith("https:")


def test_customer_api_create_embed_token_works_for_a_customer_that_is_not_registered_yet(fastn: FastnClient) -> None:
    try:
        r = fastn.customer(EMBED_REF).api.embed.create_embed_token({"createIfMissing": True, "customerName": f"SDK py embed {run}", "userId": f"u_{run}"})
    except FastnApiError as e:
        if e.code == "quota_exceeded" or e.status == 403:
            ev("embed token", f"quota: {e.message}")
            pytest.skip(f"quota: {e.message}")
        raise
    tok = data_of(r)
    ev("embed token", {"hasToken": bool(tok.get("token") or tok.get("embedToken")), "endOrgId": tok.get("endOrgId")})
    assert tok.get("token") or tok.get("embedToken")
    row = fastn.customer(EMBED_REF).find()
    state["embed"] = EMBED_REF if row else None
    ev("embed customer", {"registered": bool(row), "id": row and row.get("id")})
    assert row and row.get("id")
