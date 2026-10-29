# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""The HTTP transport: builds one request per operation from the wire manifest, sends it with httpx, retries where it
is safe, and turns answers into values or FastnApiError / FastnNetworkError. A port of node/src/transport.ts.

Everything here is reachable under `fastn.platform.unstable` and has no compatibility promise.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Optional, Tuple
from urllib.parse import quote, urlencode

import httpx

from . import _http
from ._http import RETRY_STATUS, error_info, merge_options, parse_loose, retry_delay
from .errors import FastnApiError, FastnNetworkError

if TYPE_CHECKING:
    from typing import Protocol, TypedDict


@dataclass(frozen=True)
class ParamDef:
    """One input key that goes on the path, the query string or a header."""

    key: str
    name: str
    location: str  # "path" | "query" | "header"
    required: bool = False


@dataclass(frozen=True)
class BodyDef:
    """`fields`: the input's named keys form the JSON body; `whole`: one input key is the entire body."""

    kind: str  # "fields" | "whole"
    content_type: str = "application/json"
    #: fields: input key -> wire name.
    keys: Optional[Mapping[str, str]] = None
    #: whole: the input key that carries the body.
    key: Optional[str] = None
    required: bool = False
    #: fields: the spec allows extra body fields (additionalProperties); unknown input keys are sent as given.
    open: bool = False
    #: fields: the input keys the spec marks required (the platform enforces them).
    required_keys: Tuple[str, ...] = ()


@dataclass(frozen=True)
class OpDef:
    id: str
    method: str
    path: str
    params: Tuple[ParamDef, ...] = ()
    body: Optional[BodyDef] = None
    #: The platform de-duplicates this operation by Idempotency-Key, so a call that carries one may be retried.
    idempotent: bool = False


if TYPE_CHECKING:

    class CustomerRef(TypedDict, total=False):
        """`{"ref": ...}` is the id you chose for the customer; `{"id": ...}` is fastn's own id of that customer org."""

        ref: str
        id: str

    class RequestOptions(TypedDict, total=False):
        """Per-call options. Everything here is optional and applies to any operation."""

        #: Sent as Idempotency-Key. On operations the platform de-duplicates by it (unified record writes, workflow
        #: execute; see the method's doc) a retry with the same key returns the first answer instead of acting twice,
        #: and the SDK retries those on 429/502/503/504. Other writes are never retried, key or not.
        idempotency_key: str
        #: Sent as X-Fastn-Correlation-Id: your own id for the request; look it up later with unified.list_unified_calls.
        correlation_id: str
        #: The customer the call is for: {"ref": <your id>} (x-end-org-ref) or {"id": <fastn's id>} (x-end-org-id).
        customer: CustomerRef
        #: Sent as x-installation-id.
        installation_id: str
        #: Sent as x-fastn-target-org: run as another org you are a member of (user tokens only).
        target_org: str
        #: Extra headers, sent as given.
        headers: Mapping[str, str]
        #: Body fields the SDK does not know yet, sent as given (merged over the generated body). Not validated.
        extra_body: Mapping[str, Any]
        #: Query parameters the SDK does not know yet, sent as given.
        extra_query: Mapping[str, Any]
        #: Overrides the client's timeout (seconds) for this call.
        timeout: float
        #: Overrides the client's retry count for this call (0 = never retry).
        retries: int

    class Transport(Protocol):
        def call(self, op: OpDef, input: Mapping[str, Any], opts: Mapping[str, Any]) -> Any: ...


@dataclass
class RequestLog:
    """What `on_request` receives after every attempt. Never carries the api key."""

    op_id: str
    method: str
    url: str
    path: str
    status: int
    duration_ms: float
    attempt: int
    request_id: Optional[str] = None
    correlation_id: Optional[str] = None


#: Options the SDK turns into headers on every call; the same header set per operation by an input field wins.
CROSS_HEADERS: Tuple[Tuple[str, str], ...] = (
    ("idempotency_key", "idempotency-key"),
    ("correlation_id", "x-fastn-correlation-id"),
    ("installation_id", "x-installation-id"),
    ("target_org", "x-fastn-target-org"),
)


def to_iso(v: Any) -> Any:
    """datetime -> ISO 8601 like JavaScript's Date.toISOString() (UTC, milliseconds, Z); date -> YYYY-MM-DD.
    A naive datetime is read as the machine's local time (Python's convention), never as UTC."""
    if isinstance(v, datetime):
        v = v.astimezone(_UTC).replace(tzinfo=None)  # astimezone() on a naive value assumes local time
        return v.strftime("%Y-%m-%dT%H:%M:%S.") + f"{v.microsecond // 1000:03d}Z"
    if isinstance(v, date):
        return v.isoformat()
    return v


_UTC = timezone.utc


def _json_default(v: Any) -> Any:
    out = to_iso(v)
    if out is v:
        raise TypeError(f"Object of type {type(v).__name__} is not JSON serializable")
    return out


def dumps(payload: Any) -> str:
    """JSON like JSON.stringify: compact, datetimes as ISO strings."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def _qs(v: Any) -> str:
    """A query value as JavaScript's String(v) would spell it."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (dict, list, tuple)):
        return dumps(v)
    return str(to_iso(v))


class HttpxTransport:
    """Sends operations with an httpx.Client. Retries GET and idempotent calls on 429/502/503/504 and network errors."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        timeout: float = 60.0,
        retries: int = 2,
        http: Optional[httpx.Client] = None,
        user_agent: Optional[str] = None,
        on_request: Optional[Callable[[RequestLog], None]] = None,
        default_options: Optional[Mapping[str, Any]] = None,
    ) -> None:
        self._api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.retries = retries
        self.user_agent = user_agent
        self.on_request = on_request
        self.default_options = dict(default_options or {})
        self._http = http
        self._owns_http = http is None

    @property
    def http(self) -> httpx.Client:
        if self._http is None:
            self._http = httpx.Client(timeout=self.timeout)
        return self._http

    def close(self) -> None:
        if self._http is not None and self._owns_http:
            self._http.close()
            self._http = None

    def prepare(self, op: OpDef, input: Mapping[str, Any], opts: Optional[Mapping[str, Any]] = None) -> Tuple[str, Dict[str, str], Optional[str]]:
        """Builds the request without sending it: (url, headers, body). Exposed for tests and for debugging what the SDK sends."""
        o = merge_options(self.default_options, opts)
        path = op.path
        query: List[Tuple[str, str]] = []
        headers: Dict[str, str] = {"accept": "application/json", "x-api-key": self._api_key}
        if self.user_agent:
            headers["user-agent"] = self.user_agent
        for p in op.params:
            v = input.get(p.key)
            if v is None:
                if p.required:
                    raise TypeError(f'{op.id}: "{p.key}" is required ({p.location} {p.name})')
                continue
            if p.location == "path":
                path = path.replace("{" + p.name + "}", quote(str(to_iso(v)), safe="-_.!~*'()"))
            elif p.location == "query":
                if isinstance(v, (list, tuple)):
                    query.extend((p.name, _qs(x)) for x in v)
                else:
                    query = [q for q in query if q[0] != p.name]
                    query.append((p.name, _qs(v)))
            else:
                headers[p.name.lower()] = str(v)
        missing = [m for m in path.split("/") if m.startswith("{") and m.endswith("}")]
        if missing:
            raise TypeError(f"{op.id}: path parameter {', '.join(missing)} not filled")
        for key, header in CROSS_HEADERS:
            val = o.get(key)
            if isinstance(val, str) and val and header not in headers:
                headers[header] = val
        customer = o.get("customer")
        if isinstance(customer, Mapping):
            if customer.get("ref"):
                headers.setdefault("x-end-org-ref", str(customer["ref"]))
            elif customer.get("id"):
                headers.setdefault("x-end-org-id", str(customer["id"]))
        for k, v in (o.get("headers") or {}).items():
            if isinstance(v, str):
                headers[k.lower()] = v
        for k, v in (o.get("extra_query") or {}).items():
            if v is None:
                continue
            query = [q for q in query if q[0] != k]
            if isinstance(v, (list, tuple)):
                query.extend((k, _qs(x)) for x in v)
            else:
                query.append((k, _qs(v)))
        body: Optional[str] = None
        extra_body = o.get("extra_body") or {}
        if op.body is None and extra_body:
            raise TypeError(f"{op.id}: extra_body given, but {op.method} {op.path} takes no request body")
        if op.body is not None:
            payload: Any
            if op.body.kind == "fields":
                obj: Dict[str, Any] = {}
                keys = op.body.keys or {}
                for key, name in keys.items():
                    if key in input:  # a key set to None is sent as null (it clears the field); only a missing key is left out
                        obj[name] = input[key]
                if op.body.open:
                    taken = set(keys) | {p.key for p in op.params}
                    for key, v in input.items():
                        if key not in taken:
                            obj[key] = v
                for k, v in extra_body.items():
                    obj[k] = v
                payload = obj
            else:
                payload = input.get(op.body.key or "")
                if payload is None and extra_body:
                    payload = {}
                if payload is None and op.body.required:
                    raise TypeError(f'{op.id}: "{op.body.key}" (request body) is required')
                if extra_body:
                    if not isinstance(payload, Mapping):
                        raise TypeError(f"{op.id}: extra_body needs an object body")
                    payload = {**payload, **extra_body}
            if payload is not None:
                if op.body.content_type == "application/x-www-form-urlencoded":
                    body = payload if isinstance(payload, str) else urlencode([(k, _qs(v)) for k, v in dict(payload).items()])
                else:
                    body = payload if isinstance(payload, str) else dumps(payload)
                headers["content-type"] = op.body.content_type
        qs = urlencode(query)
        url = f"{self.base_url}{path}" + (f"?{qs}" if qs else "")
        return url, headers, body

    def call(self, op: OpDef, input: Mapping[str, Any], opts: Optional[Mapping[str, Any]] = None) -> Any:
        # Client defaults under the per-call options, so `defaults={"retries": 0, "timeout": 5}` reaches here too.
        o = merge_options(self.default_options, opts)
        url, headers, body = self.prepare(op, input, o)
        retryable = op.method == "GET" or (op.idempotent and "idempotency-key" in headers)
        max_retries = int(o.get("retries", self.retries)) if retryable else 0
        timeout = float(o.get("timeout", self.timeout))
        attempt = 0
        while True:
            t0 = time.monotonic()
            try:
                res = self.http.request(op.method, url, headers=headers, content=body.encode("utf-8") if body is not None else None, timeout=timeout)
            except httpx.HTTPError as err:
                self._log(op, url, 0, t0, attempt, None, headers)
                if attempt < max_retries:
                    _http.sleep(_http.backoff(attempt))
                    attempt += 1
                    continue
                raise FastnNetworkError(f"{op.method} {op.path}: {err.__class__.__name__}: {err}", op.method, op.path, err) from err
            request_id = res.headers.get("x-request-id")
            self._log(op, url, res.status_code, t0, attempt, request_id, headers)
            text = res.text
            parsed = parse_loose(text, res.headers.get("content-type", ""))
            if 200 <= res.status_code < 300:
                return None if text == "" else parsed
            if attempt < max_retries and res.status_code in RETRY_STATUS:
                _http.sleep(retry_delay(res.headers, attempt))
                attempt += 1
                continue
            message, code, details, _ = error_info(parsed, f"HTTP {res.status_code}")
            code_s = None if code is None else str(code)
            raise FastnApiError(
                f"{op.method} {op.path} -> {res.status_code}{(' ' + code_s) if code_s else ''}: {message}",
                status=res.status_code, code=code_s, details=details, method=op.method, path=op.path, request_id=request_id, body=parsed,
            )

    def _log(self, op: OpDef, url: str, status: int, t0: float, attempt: int, request_id: Optional[str], headers: Mapping[str, str]) -> None:
        if self.on_request is None:
            return
        self.on_request(RequestLog(
            op_id=op.id, method=op.method, url=url, path=op.path, status=status, duration_ms=(time.monotonic() - t0) * 1000, attempt=attempt,
            request_id=request_id, correlation_id=headers.get("x-fastn-correlation-id"),
        ))
