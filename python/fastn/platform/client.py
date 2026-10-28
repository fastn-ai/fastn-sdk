# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""The fastn platform REST API client, generated from fastn's OpenAPI spec, plus the customer flow.

    from fastn.platform import FastnClient

    fastn = FastnClient(api_key=os.environ["FASTN_API_KEY"])          # https://api.fastn.dev
    orgs = fastn.orgs.list_orgs({"type": "end_org"})

    customer = fastn.customer("acme-42")                                # the id YOU use for this customer
    customer.register({"name": "Acme Dental"})
    link = customer.connect("googleCalendar")                           # {"url": ...} to send the customer to
    customer.calendar.book({"title": "Intro call", "start_time": "...", "end_time": "..."}, idempotency_key="booking-123")
    page = customer.crm.contacts.find({"email": "jane@example.com"})
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Optional, cast

import httpx

from ._generated.api import (
    API_GROUPS,
    ActivityApi,
    AgentApi,
    ApiKeysApi,
    AuthApi,
    BillingApi,
    ConnectionsApi,
    ConnectorsApi,
    EmbedApi,
    EnvironmentsApi,
    EventsApi,
    ExecutionApi,
    FastnApis,
    ObserveApi,
    OnboardingApi,
    OrgsApi,
    SyncApi,
    TeamsApi,
    UnifiedApi,
    UsersApi,
    WorkflowsApi,
    build_apis,
)
from ._generated.ops import OPS
from ._http import default_user_agent
from ._transport import HttpxTransport, RequestLog
from ._version import VERSION
from .catalog import Catalog
from .customer import Customer, CustomerContext

if TYPE_CHECKING:
    from typing_extensions import Unpack

    from ._transport import RequestOptions, Transport

DEFAULT_BASE_URL = "https://api.fastn.dev"
__all__ = ["DEFAULT_BASE_URL", "VERSION", "FastnClient", "Webhooks"]


def _data_of(r: Any) -> Any:
    return r["data"] if isinstance(r, dict) and "data" in r else r


def _rows(r: Any) -> List[Any]:
    return list(r["data"]) if isinstance(r, dict) and isinstance(r.get("data"), list) else []


def _in(d: Mapping[str, Any]) -> Any:
    return cast(Any, d)


class Webhooks:
    """Your webhook: fastn.webhooks.create({"url", "eventTypes"}), list(), get(id), update(id, {...}), delete(id),
    test(id), rotate_secret(id), deliveries(id), replay(delivery_id). Each answers the `data` directly."""

    def __init__(self, api: FastnApis) -> None:
        self._api = api

    def create(self, input: Mapping[str, Any], **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """Creates a subscription; the answer carries `secret` once: the signing secret for parse_event."""
        return cast(Dict[str, Any], _data_of(self._api.events.create_event_subscription(_in(input), **opts)))

    def list(self, **opts: Unpack[RequestOptions]) -> List[Dict[str, Any]]:
        return _rows(self._api.events.list_event_subscriptions(_in({}), **opts))

    def get(self, id: str, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        return cast(Dict[str, Any], _data_of(self._api.events.get_event_subscription(_in({"id": id}), **opts)))

    def update(self, id: str, changes: Mapping[str, Any], **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        return cast(Dict[str, Any], _data_of(self._api.events.update_event_subscription(_in({"id": id, **changes}), **opts)))

    def delete(self, id: str, **opts: Unpack[RequestOptions]) -> Any:
        return _data_of(self._api.events.delete_event_subscription(_in({"id": id}), **opts))

    def test(self, id: str, **opts: Unpack[RequestOptions]) -> Any:
        """Sends an endpoint.test event now."""
        return _data_of(self._api.events.test_event_subscription(_in({"id": id}), **opts))

    def rotate_secret(self, id: str, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """A new signing secret; deliveries are signed with it from now on."""
        return cast(Dict[str, Any], _data_of(self._api.events.rotate_event_subscription_secret(_in({"id": id}), **opts)))

    def deliveries(self, id: str, limit: Optional[int] = None, status: Optional[str] = None, **opts: Unpack[RequestOptions]) -> List[Dict[str, Any]]:
        input: Dict[str, Any] = {"id": id}
        if limit is not None:
            input["limit"] = limit
        if status is not None:
            input["status"] = status
        return _rows(self._api.events.list_event_deliveries(_in(input), **opts))

    def replay(self, delivery_id: str, **opts: Unpack[RequestOptions]) -> Any:
        return _data_of(self._api.events.replay_event_delivery(_in({"id": delivery_id}), **opts))


class FastnClient:
    """One client per API key. Every API area is on the client directly (`fastn.orgs`, `fastn.unified`, ...) and
    under `fastn.api`; `fastn.customer(ref)` scopes calls to one of your customers."""

    # Every API area, keyed by its OpenAPI tag (snake_case, plus the Node SDK's camelCase alias where it differs).
    activity: ActivityApi
    agent: AgentApi
    api_keys: ApiKeysApi
    apiKeys: ApiKeysApi
    auth: AuthApi
    billing: BillingApi
    connections: ConnectionsApi
    connectors: ConnectorsApi
    embed: EmbedApi
    environments: EnvironmentsApi
    events: EventsApi
    execution: ExecutionApi
    observe: ObserveApi
    onboarding: OnboardingApi
    orgs: OrgsApi
    sync: SyncApi
    teams: TeamsApi
    unified: UnifiedApi
    users: UsersApi
    workflows: WorkflowsApi

    def __init__(
        self,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 60.0,
        retries: int = 2,
        defaults: Optional[Mapping[str, Any]] = None,
        on_request: Optional[Callable[[RequestLog], None]] = None,
        http: Optional[httpx.Client] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """
        api_key: your fastn API key (Settings > API keys), sent as x-api-key.
        base_url: default https://api.fastn.dev; https://api.fastn-test.dev is the development environment.
        timeout: per-request timeout in seconds (default 60).
        retries: retries for GET and idempotent calls on 429/502/503/504 and network errors (default 2).
        defaults: options applied to every call, e.g. {"customer": {"ref": "acme-42"}} to scope a whole client.
        on_request: called after every HTTP attempt with a RequestLog, for your logs (never receives the api key).
        http: an httpx.Client to send with (default: one owned by the client, closed by close()).
        """
        if not api_key or not isinstance(api_key, str):
            raise TypeError("FastnClient: api_key is required")
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.transport: Transport = HttpxTransport(
            api_key=api_key, base_url=self.base_url, timeout=timeout, retries=retries, http=http,
            user_agent=user_agent or default_user_agent(), on_request=on_request, default_options=defaults,
        )
        #: All API areas, keyed by OpenAPI tag: orgs, embed, connections, unified, events, workflows, ...
        self.api: FastnApis = build_apis(self.transport)
        for snake_name, camel_name in API_GROUPS:
            setattr(self, snake_name, getattr(self.api, snake_name))
            setattr(self, camel_name, getattr(self.api, snake_name))
        self._customers = CustomerContext(self._caller_org_id)
        #: Your webhook subscriptions: create, list, get, update, delete, test, rotate_secret, deliveries, replay.
        self.webhooks = Webhooks(self.api)
        self._me: Optional[Dict[str, Any]] = None
        self._me_lock = threading.Lock()
        self._catalog: Optional[Catalog] = None

    def _caller_org_id(self) -> str:
        me = self.me()
        org = me.get("org") if isinstance(me, dict) else None
        id_ = org.get("id") if isinstance(org, dict) else None
        if not isinstance(id_, str) or not id_:
            raise TypeError("whoami did not answer the caller's org id")
        return id_

    def me(self) -> Dict[str, Any]:
        """Who this API key is (GET /v1/me): actor, role, org, parentOrg. Cached for the life of the client."""
        with self._me_lock:
            if self._me is None:
                r = self.api.users.whoami()
                d = r.get("data") if isinstance(r, dict) and r.get("data") is not None else r
                self._me = dict(d) if isinstance(d, dict) else {"data": d}
            return self._me

    @property
    def catalog(self) -> Catalog:
        """The unified catalog: fastn.catalog.categories(), .entity("crm", "contact"), .fields(...), .providers(...)."""
        if self._catalog is None:
            self._catalog = Catalog(self.api)
        return self._catalog

    def customer(self, ref: str) -> Customer:
        """One of your customers, by the id you use for them."""
        if not ref:
            raise TypeError("customer(ref): ref is required")
        return Customer(self.api, self.transport, ref, self._customers)

    def call(self, operation_id: str, input: Optional[Mapping[str, Any]] = None, **opts: Unpack[RequestOptions]) -> Any:
        """Calls any operation by its operationId, e.g. fastn.call("listOrgs", {"type": "end_org"})."""
        op = OPS.get(operation_id)
        if op is None:
            raise TypeError(f'unknown operation "{operation_id}"')
        return self.transport.call(op, input or {}, opts)

    def close(self) -> None:
        """Closes the HTTP client this client owns (one passed in as `http` is left open)."""
        close = getattr(self.transport, "close", None)
        if callable(close):
            close()

    def __enter__(self) -> FastnClient:
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()
