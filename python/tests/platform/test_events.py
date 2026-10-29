# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Event signatures (a port of node/test/unit/events.test.ts)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx
import pytest

from fastn.platform import parse_event, read_event_headers, sign_event_body, verify_event_signature

secret = "whsec_test_secret"
body = '{"id":"evt_1","type":"unified.event","data":{"a":1}}'
ts = "1760000000"
sig = "sha256=" + hmac.new(secret.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()


def test_matches_the_platform_format() -> None:
    assert sign_event_body(secret, ts, body) == sig
    assert sign_event_body(secret, int(ts), body.encode()) == sig


def test_verifies_a_good_delivery_from_a_dict_and_from_httpx_headers() -> None:
    assert verify_event_signature(secret, {"x-fastn-timestamp": ts, "x-fastn-signature": sig}, body, now=1760000010) is True
    assert verify_event_signature(secret, httpx.Headers({"X-Fastn-Timestamp": ts, "X-Fastn-Signature": sig}), body.encode(), now=1760000010) is True


def test_rejects_a_changed_body_wrong_secret_stale_timestamp_missing_header() -> None:
    h = {"x-fastn-timestamp": ts, "x-fastn-signature": sig}
    assert verify_event_signature(secret, h, body + " ", now=1760000010) is False
    assert verify_event_signature("other", h, body, now=1760000010) is False
    assert verify_event_signature(secret, h, body, now=1760001000) is False
    assert verify_event_signature(secret, h, body, now=1760001000, tolerance_seconds=0) is True
    assert verify_event_signature(secret, {"x-fastn-timestamp": ts}, body) is False
    assert verify_event_signature("", h, body, now=1760000010) is False
    assert verify_event_signature(secret, {"x-fastn-timestamp": "soon", "x-fastn-signature": sig}, body) is False


def test_parse_event_returns_the_event_and_headers_raises_on_a_bad_signature() -> None:
    ev = parse_event(secret, {"x-fastn-timestamp": ts, "x-fastn-signature": sig, "x-fastn-event-id": "evt_1", "x-fastn-redelivery": "true"}, body, now=1760000010)
    assert ev["id"] == "evt_1" and ev["headers"]["event_id"] == "evt_1" and ev["headers"]["redelivery"] is True
    with pytest.raises(ValueError, match="signature"):
        parse_event(secret, {"x-fastn-timestamp": ts, "x-fastn-signature": "sha256=00"}, body, now=1760000010)


def test_read_event_headers_handles_lists_and_case() -> None:
    assert read_event_headers({"X-Fastn-Timestamp": ["1"], "x-fastn-signature": "s"}) == {"timestamp": "1", "signature": "s", "event_id": None, "redelivery": False}


def test_parse_event_drops_end_org_id_by_default_and_keeps_it_with_internal_ids() -> None:
    raw = json.dumps({"id": "evt_1", "type": "connection.connected", "tenantRef": "acme-1", "endOrgId": "7c9e", "app": "hubspot", "data": {"end_org_id": "7c9e", "items": [{"endOrgId": "7c9e", "ok": 1}]}})
    now = str(int(time.time()))
    headers = {"x-fastn-event-id": "evt_1", "x-fastn-timestamp": now, "x-fastn-signature": sign_event_body("whsec_t", now, raw)}
    e = parse_event("whsec_t", headers, raw)
    assert e["id"] == "evt_1" and e["tenantRef"] == "acme-1" and e["app"] == "hubspot"
    assert "endOrgId" not in e and e["data"] == {"items": [{"ok": 1}]}
    assert parse_event("whsec_t", headers, raw, internal_ids=True)["endOrgId"] == "7c9e"
