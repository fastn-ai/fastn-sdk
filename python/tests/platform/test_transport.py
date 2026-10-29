# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Request shape, errors and retries (a port of node/test/unit/transport.test.ts)."""

from __future__ import annotations

from typing import Any, Callable, List, cast

import httpx
import pytest

from fastn.platform import FastnApiError, FastnClient, FastnNetworkError, RequestLog
from fastn.platform.unstable import OPS

from .conftest import Mock


def client(**extra: Any) -> FastnClient:
    return FastnClient(api_key="k_test", **{"retries": 2, **extra})


class TestRequestShape:
    def test_path_query_and_api_key_header(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {"data": []}}])
        client().orgs.list_orgs({"type": "end_org", "include_usage": "true"})
        assert str(m.calls[0].url) == "https://api.fastn.dev/v1/orgs?type=end_org&include_usage=true"
        assert m.calls[0].method == "GET"
        assert m.calls[0].headers["x-api-key"] == "k_test"
        assert m.calls[0].headers["user-agent"].startswith("fastn-python-sdk/")
        assert m.calls[0].content == b""

    def test_path_params_are_encoded_and_required(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {}}])
        client().orgs.get_tenant({"id": "a/b c"})
        assert str(m.calls[0].url) == "https://api.fastn.dev/v1/orgs/a%2Fb%20c"
        with pytest.raises(TypeError, match='"id" is required'):
            client().orgs.get_tenant({})  # type: ignore[typeddict-item]

    def test_body_fields_are_mapped_to_wire_names_and_none_is_sent_as_null(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"status": 201, "body": {"data": {"id": "org_1"}}}])
        res = client().orgs.create_tenant({"name": "Acme", "orgId": "acme-1", "slug": None})  # type: ignore[typeddict-item]
        assert res == {"data": {"id": "org_1"}}
        assert m.json(0) == {"name": "Acme", "orgId": "acme-1", "slug": None}  # None is sent as null (it clears a field); a missing key is left out
        assert m.calls[0].headers["content-type"] == "application/json"

    def test_open_bodies_pass_extra_fields_through_closed_bodies_drop_them(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {}}, {"body": {}}])
        c = client()
        assert OPS["updateOrgConfig"].body is not None and OPS["updateOrgConfig"].body.open is True
        c.orgs.update_org_config({"id": "org_1", "orgName": "Acme", "setupLinkRedirectUrls": ["https://app.acme.com/connected"]})  # type: ignore[typeddict-unknown-key]
        assert m.json(0) == {"orgName": "Acme", "setupLinkRedirectUrls": ["https://app.acme.com/connected"]}
        assert OPS["createTenant"].body is not None and not OPS["createTenant"].body.open
        c.orgs.create_tenant({"name": "Acme", "orgId": "acme-1", "plan": "free", "surprise": 1})  # type: ignore[typeddict-unknown-key]
        assert "surprise" not in m.json(1)

    def test_free_form_body_uses_the_specs_input_name(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {}}, {"body": {}}])
        c = client()
        c.unified.create_unified_record({"category": "crm", "entity": "contact", "provider": "hubspot", "record": {"email": "a@b.c"}})
        assert str(m.calls[0].url) == "https://api.fastn.dev/v1/unified/crm/contact?provider=hubspot"
        assert m.json(0) == {"email": "a@b.c"}
        c.unified.search_unified_records({"category": "crm", "entity": "contact", "filters": {"email": "a@b.c"}})
        assert m.json(1) == {"email": "a@b.c"}

    def test_header_params_and_cross_cutting_options_become_headers(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {}}, {"body": {}}])
        c = client()
        c.unified.create_unified_record({"category": "scheduling", "entity": "meeting", "endOrgRef": "cust-1", "record": {}}, idempotency_key="k1", correlation_id="c1")
        h = m.calls[0].headers
        assert h["x-end-org-ref"] == "cust-1" and h["idempotency-key"] == "k1" and h["x-fastn-correlation-id"] == "c1"
        c.unified.update_unified_record({"category": "scheduling", "entity": "meeting", "id": "m1", "record": {}}, customer={"ref": "cust-1"}, installation_id="inst_1")
        assert m.calls[1].headers["x-end-org-ref"] == "cust-1" and m.calls[1].headers["x-installation-id"] == "inst_1"
        assert m.calls[1].method == "PATCH"

    def test_renamed_collisions_keep_the_path_value_and_send_the_body_value(self) -> None:
        op = OPS["updateConfigEntry"]
        assert next(p for p in op.params if p.location == "path" and p.name == "id").key == "id"
        assert op.body is not None and op.body.keys is not None
        assert op.body.keys["bodyId"] == "id" and op.body.keys["bodyConnectorId"] == "connectorId"

    def test_defaults_from_the_client_apply_to_every_call(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {}}])
        client(defaults={"customer": {"ref": "cust-9"}, "headers": {"x-custom": "1"}}).unified.list_unified_records({"category": "crm", "entity": "contact"})
        assert m.calls[0].headers["x-end-org-ref"] == "cust-9" and m.calls[0].headers["x-custom"] == "1"

    def test_customer_id_sends_x_end_org_id_and_a_per_call_customer_overrides_the_default(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {}}, {"body": {}}])
        c = client(defaults={"customer": {"ref": "cust-9"}})
        c.unified.list_unified_records({"category": "crm", "entity": "contact"}, customer={"id": "0b3241c4-fastn"})
        assert m.calls[0].headers["x-end-org-id"] == "0b3241c4-fastn" and "x-end-org-ref" not in m.calls[0].headers
        c.unified.list_unified_records({"category": "crm", "entity": "contact"})
        assert m.calls[1].headers["x-end-org-ref"] == "cust-9" and "x-end-org-id" not in m.calls[1].headers

    def test_extra_body_and_extra_query_send_fields_the_sdk_does_not_know(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {}}, {"body": {}}, {"body": {}}])
        c = client()
        c.orgs.create_tenant({"name": "Acme", "orgId": "acme-1"}, extra_body={"brandNewField": True})
        assert m.json(0) == {"name": "Acme", "orgId": "acme-1", "brandNewField": True}
        c.orgs.list_orgs({"type": "end_org"}, extra_query={"brand_new": "1", "tags": ["a", "b"]})
        assert str(m.calls[1].url) == "https://api.fastn.dev/v1/orgs?type=end_org&brand_new=1&tags=a&tags=b"
        c.unified.create_unified_record({"category": "crm", "entity": "contact", "record": {"email": "a@b.c"}}, extra_body={"custom_field": 1})
        assert m.json(2) == {"email": "a@b.c", "custom_field": 1}
        with pytest.raises(TypeError, match="takes no request body"):
            c.orgs.list_orgs({}, extra_body={"x": 1})

    def test_call_by_operation_id(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {"data": 1}}])
        assert client().call("listOrgs") == {"data": 1}
        assert str(m.calls[0].url) == "https://api.fastn.dev/v1/orgs"
        with pytest.raises(TypeError, match="unknown operation"):
            client().call("noSuchOp")

    def test_query_values_are_spelled_like_javascript(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {}}])
        client().orgs.list_orgs(cast(Any, {"include_usage": True, "tier": 3}), extra_query={"obj": {"a": 1}, "skip": None})
        assert str(m.calls[0].url) == "https://api.fastn.dev/v1/orgs?tier=3&include_usage=true&obj=%7B%22a%22%3A1%7D"

    def test_on_request_sees_every_attempt_without_the_api_key(self, mock: Callable[..., Mock]) -> None:
        mock([{"status": 503, "body": {"error": "down"}}, {"body": {"data": []}}])
        log: List[RequestLog] = []
        client(on_request=log.append).orgs.list_orgs({}, correlation_id="c-1")
        assert [(x.status, x.attempt, x.op_id, x.path, x.request_id, x.correlation_id) for x in log] == [(503, 0, "listOrgs", "/v1/orgs", "req_1", "c-1"), (200, 1, "listOrgs", "/v1/orgs", "req_1", "c-1")]
        assert "k_test" not in repr(log)


class TestErrorsAndRetries:
    def test_non_2xx_becomes_fastn_api_error_with_status_code_message_and_request_id(self, mock: Callable[..., Mock]) -> None:
        mock([{"status": 404, "body": {"error": {"code": "NOT_FOUND", "message": "Tenant not found", "details": {"id": "x"}}}}])
        with pytest.raises(FastnApiError) as ei:
            client().orgs.get_tenant({"id": "x"})
        err = ei.value
        assert err.status == 404 and err.code == "NOT_FOUND" and err.is_not_found
        assert "Tenant not found" in err.message and err.request_id == "req_1" and err.details == {"id": "x"}
        assert str(err) == "GET /v1/orgs/{id} -> 404 NOT_FOUND: Tenant not found"

    def test_string_error_bodies_are_kept(self, mock: Callable[..., Mock]) -> None:
        mock([{"status": 403, "body": {"error": "Forbidden"}}])
        with pytest.raises(FastnApiError) as ei:
            client().orgs.list_orgs()
        assert ei.value.status == 403 and "Forbidden" in ei.value.message and ei.value.is_auth

    def test_other_error_shapes(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"status": 422, "body": {"message": "bad", "code": 42}}, {"status": 500, "body": "oops", "headers": {"content-type": "text/plain"}}, {"status": 409, "body": {"x": 1}}])
        c = client(retries=0)
        with pytest.raises(FastnApiError) as e1:
            c.orgs.list_orgs()
        assert e1.value.code == "42" and e1.value.message.endswith("bad") and e1.value.is_validation
        with pytest.raises(FastnApiError) as e2:
            c.orgs.list_orgs()
        assert e2.value.message.endswith("HTTP 500") and e2.value.body == "oops"   # a text body: the fallback is the message, the text is the body
        with pytest.raises(FastnApiError) as e3:
            c.orgs.list_orgs()
        assert e3.value.is_conflict and e3.value.message.endswith("HTTP 409") and e3.value.body == {"x": 1}
        assert len(m.calls) == 3

    def test_a_502_with_the_apps_own_4xx_refusal_is_not_retried_but_a_5xx_provider_status_is(self, mock: Callable[..., Mock], no_sleep: List[float]) -> None:
        refusal = {"error": "Provider request failed", "code": "UNIFIED_PROVIDER_ERROR", "providerStatus": 400, "providerError": "Missing attendee email."}
        m = mock([{"status": 502, "body": refusal}, {"status": 502, "body": refusal}, {"status": 502, "body": refusal}])
        with pytest.raises(FastnApiError) as ei:
            client().unified.create_unified_record({"category": "scheduling", "entity": "meeting", "record": {"title": "x"}}, idempotency_key="k")
        assert ei.value.status == 502 and ei.value.code == "UNIFIED_PROVIDER_ERROR" and ei.value.body["providerStatus"] == 400
        assert len(m.calls) == 1 and no_sleep == []
        m2 = mock([{"status": 502, "body": {**refusal, "providerStatus": 503}}, {"body": {"id": "1", "provider": "googleCalendar", "data": {}}}])
        assert client().unified.create_unified_record({"category": "scheduling", "entity": "meeting", "record": {"title": "x"}}, idempotency_key="k")["id"] == "1"
        assert len(m2.calls) == 2

    def test_get_retries_on_503_then_succeeds(self, mock: Callable[..., Mock], no_sleep: List[float]) -> None:
        m = mock([{"status": 503, "body": {"error": "down"}}, {"body": {"data": []}}])
        assert client().orgs.list_orgs() == {"data": []}
        assert len(m.calls) == 2
        assert len(no_sleep) == 1 and 0.5 <= no_sleep[0] <= 0.7

    def test_writes_are_retried_only_where_the_platform_honours_idempotency_key(self, mock: Callable[..., Mock], no_sleep: List[float]) -> None:
        m1 = mock([{"status": 503, "body": {"error": "down"}}, {"status": 503, "body": {"error": "down"}}, {"status": 429, "body": {"error": "slow"}, "headers": {"retry-after": "2"}}, {"status": 201, "body": {"ok": 1}}])
        with pytest.raises(FastnApiError):
            client().orgs.create_tenant({"name": "x"})
        assert len(m1.calls) == 1
        # createTenant does not honour the key: a key is sent, but a lost answer is never retried
        with pytest.raises(FastnApiError):
            client().orgs.create_tenant({"name": "x"}, idempotency_key="k")
        assert len(m1.calls) == 2 and m1.calls[1].headers["idempotency-key"] == "k"
        assert not OPS["createTenant"].idempotent and OPS["createUnifiedRecord"].idempotent and OPS["executeWorkflow"].idempotent
        assert client().unified.create_unified_record({"category": "crm", "entity": "contact", "record": {}}, idempotency_key="k") == {"ok": 1}
        assert len(m1.calls) == 4
        assert no_sleep == [2.0]  # Retry-After is honoured

    def test_retries_stop_at_the_limit_and_4xx_is_never_retried(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"status": 502, "body": ""}, {"status": 502, "body": ""}, {"status": 502, "body": ""}, {"status": 502, "body": ""}])
        with pytest.raises(FastnApiError) as ei:
            client().orgs.list_orgs()
        assert ei.value.status == 502 and len(m.calls) == 3
        m.use([{"status": 400, "body": {"error": "bad"}}, {"body": {}}])
        with pytest.raises(FastnApiError, match="400"):
            client().orgs.list_orgs()
        assert len(m.calls) == 4

    def test_per_call_retries_and_timeout_override_the_client(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"status": 503, "body": ""}, {"status": 503, "body": ""}])
        with pytest.raises(FastnApiError):
            client().orgs.list_orgs({}, retries=0, timeout=5)
        assert len(m.calls) == 1
        assert m.calls[0].extensions["timeout"]["read"] == 5

    def test_a_body_field_set_to_none_is_sent_as_null_and_a_missing_one_is_left_out(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"body": {"data": {}}}, {"body": {"data": {}}}])
        c = client(retries=0)
        c.connections.update_connection({"id": "conn-1", "name": None})         # a mapped body field
        c.orgs.update_tenant({"id": "t-1", "name": "Acme", "externalRef": None})  # an open body
        assert m.json(0) == {"name": None}
        assert m.json(1)["externalRef"] is None and "name" in m.json(1)

    def test_client_defaults_set_retries_and_timeout_and_a_call_still_overrides_them(self, mock: Callable[..., Mock]) -> None:
        m = mock([{"status": 503, "body": ""}, {"status": 503, "body": ""}, {"status": 503, "body": ""}])
        c = client(defaults={"retries": 0, "timeout": 7})
        with pytest.raises(FastnApiError):
            c.orgs.list_orgs()
        assert len(m.calls) == 1   # the default retries=0 is honoured, not the client's constructor retries=2
        assert m.calls[0].extensions["timeout"]["read"] == 7
        with pytest.raises(FastnApiError):
            c.orgs.list_orgs({}, retries=1, timeout=3)
        assert len(m.calls) == 3   # one retry from the call option
        assert m.calls[2].extensions["timeout"]["read"] == 3

    def test_network_failure_becomes_fastn_network_error_after_retries(self, mock: Callable[..., Mock]) -> None:
        m = mock([httpx.ConnectError("ECONNRESET"), httpx.ConnectError("ECONNRESET"), httpx.ConnectError("ECONNRESET")])
        with pytest.raises(FastnNetworkError) as ei:
            client().orgs.list_orgs()
        assert "ECONNRESET" in ei.value.message and len(m.calls) == 3 and ei.value.method == "GET" and ei.value.path == "/v1/orgs"

    def test_empty_204_answers_resolve_to_none(self, mock: Callable[..., Mock]) -> None:
        mock([{"status": 204, "body": None}])
        assert client().orgs.delete_tenant({"id": "org_1"}) is None

    def test_api_key_is_required(self) -> None:
        with pytest.raises(TypeError, match="api_key"):
            FastnClient(api_key="")

    def test_close_and_context_manager(self) -> None:
        with FastnClient(api_key="k") as c:
            assert c.base_url == "https://api.fastn.dev"
        c2 = FastnClient(api_key="k", base_url="https://api.fastn-test.dev/")
        assert c2.base_url == "https://api.fastn-test.dev"
        c2.close()
