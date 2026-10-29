# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Event deliveries (webhooks): signature verification and parsing. A port of node/src/events.ts.

The signature is `sha256=HMAC-SHA256(secret, "<X-Fastn-Timestamp>.<raw body>")`; deliveries older than 5 minutes are
rejected (configurable). Always pass the raw body, never a re-serialised object.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import time
from typing import Any, Dict, Mapping, Optional, Union

#: fastn's internal customer id keys; partner code sees only the id it chose (tenantRef / orgId / externalRef).
INTERNAL_ID_KEYS = ("endOrgId", "end_org_id")

#: What fastn puts on every delivery: {"timestamp", "signature", "event_id", "redelivery"}.
EventHeaders = Dict[str, Any]


def without_internal_ids(value: Any) -> Any:
    """A copy of `value` with fastn's internal customer id keys left out, at every depth."""
    if isinstance(value, list):
        return [without_internal_ids(v) for v in value]
    if isinstance(value, dict):
        return {k: without_internal_ids(v) for k, v in value.items() if k not in INTERNAL_ID_KEYS}
    return value


def read_event_headers(headers: Mapping[str, Any]) -> EventHeaders:
    """Reads the fastn headers out of any header bag (a WSGI/ASGI mapping, httpx Headers, a plain dict), case-insensitively."""

    def get(name: str) -> Optional[str]:
        v = headers.get(name)
        if v is None:
            for k in headers:
                if isinstance(k, str) and k.lower() == name:
                    v = headers[k]
                    break
        if isinstance(v, (list, tuple)):
            v = v[0] if v else None
        if isinstance(v, bytes):
            v = v.decode("utf-8", "replace")
        return None if v is None else str(v)

    return {
        "timestamp": get("x-fastn-timestamp") or "",
        "signature": get("x-fastn-signature") or "",
        "event_id": get("x-fastn-event-id"),
        "redelivery": (get("x-fastn-redelivery") or "").lower() == "true",
    }


def _is_event_headers(h: Any) -> bool:
    return isinstance(h, dict) and isinstance(h.get("signature"), str) and isinstance(h.get("timestamp"), str)


def sign_event_body(secret: str, timestamp: Union[str, int], raw_body: Union[str, bytes]) -> str:
    body = raw_body.encode("utf-8") if isinstance(raw_body, str) else bytes(raw_body)
    return "sha256=" + hmac.new(secret.encode("utf-8"), f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()


def verify_event_signature(
    secret: str,
    headers: Mapping[str, Any],
    raw_body: Union[str, bytes],
    *,
    tolerance_seconds: float = 300,
    now: Optional[float] = None,
) -> bool:
    """True when the signature matches the body as fastn signed it. `tolerance_seconds=0` disables the timestamp check."""
    h = headers if _is_event_headers(headers) else read_event_headers(headers)
    if not h.get("signature") or not h.get("timestamp") or not secret:
        return False
    if tolerance_seconds > 0:
        try:
            ts = float(h["timestamp"])
        except (TypeError, ValueError):
            return False
        current = now if now is not None else math.floor(time.time())
        if not math.isfinite(ts) or abs(current - ts) > tolerance_seconds:
            return False
    expected = sign_event_body(secret, h["timestamp"], raw_body)
    return hmac.compare_digest(expected.encode("utf-8"), str(h["signature"]).encode("utf-8"))


def parse_event(
    secret: str,
    headers: Mapping[str, Any],
    raw_body: Union[str, bytes],
    *,
    tolerance_seconds: float = 300,
    now: Optional[float] = None,
    internal_ids: bool = False,
) -> Dict[str, Any]:
    """Verifies and parses one delivery. Raises ValueError when the signature is wrong; returns the event (with the
    fastn headers under "headers") otherwise. `event["id"]` is stable across retries: drop repeats by id.

    The body names the customer by the id the partner chose (tenantRef) and by fastn's internal id (endOrgId); the
    internal one is left out unless `internal_ids=True`.
    """
    h = read_event_headers(headers)
    if not verify_event_signature(secret, h, raw_body, tolerance_seconds=tolerance_seconds, now=now):
        raise ValueError("fastn event signature does not match (wrong secret, altered body, or stale timestamp)")
    parsed = json.loads(raw_body if isinstance(raw_body, str) else bytes(raw_body).decode("utf-8"))
    event = parsed if internal_ids else without_internal_ids(parsed)
    if not isinstance(event, dict):
        event = {"data": event}
    return {**event, "headers": h}
