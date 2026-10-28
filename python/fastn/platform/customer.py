# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Everything about one of your customers, addressed by the id YOU gave fastn (the `orgId` of createTenant, also
called externalRef / endOrgRef). fastn's own org id is resolved and cached when a call needs it. A port of
node/src/customer.ts.
"""

from __future__ import annotations

import re
import threading
import time
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Mapping, Optional, Tuple, Union, cast

from ._generated.api import build_apis
from .catalog import Catalog, rows_of
from .domain import Calendar, Crm
from .errors import FastnApiError

if TYPE_CHECKING:
    from typing_extensions import Unpack

    from ._generated.api import FastnApis
    from ._transport import OpDef, RequestOptions, Transport

#: How long (seconds) a customer's provider list and the account's widget list are reused before being read again.
PROVIDER_TTL_SECONDS = 60.0
WIDGET_TTL_SECONDS = 60.0

#: One customer org row as GET /v1/orgs returns it ({"id", "externalRef", ...}).
CustomerRow = Dict[str, Any]
#: A setup link, as created: {"setupId", "url", "status", "expiresAt"?, "widgetId", ...}.
SetupLink = Dict[str, Any]

# Operations whose body field named endOrgId / externalRef is the org being created or edited, not the customer the
# call runs for: customer.api leaves those alone. Short term; the spec does not say per operation which field is the
# customer yet (KAT-8650), so the SDK keys off the field name and lists the exceptions here.
NOT_A_CUSTOMER_FIELD = frozenset({"createTenant", "updateTenant"})
# Routes that take endOrgId as fastn's id OR the partner's ref (resolved under the caller's org): the ref is sent as
# is, so no lookup is needed and createIfMissing works for a customer that is not registered yet.
TAKES_REF_AS_END_ORG_ID = frozenset({"createEmbedToken"})
# connect(app, ...) options (snake_case) -> the createSetupLink body field.
_CONNECT_OPTIONS = {
    "widget_id": "widgetId", "connection_name": "connectionName", "label": "label", "redirect_url": "redirectUrl",
    "expires_in_minutes": "expiresInMinutes", "metadata": "metadata", "allow_additional_connection": "allowAdditionalConnection",
}

#: The clock the caches use (seconds); tests replace it.
_now = time.time

#: Event names a partner can watch on an app, in plain words, mapped to the app's own event ids. Any id from the
#: app's catalog (customer.watchable_events(app)) is accepted as well.
EVENT_ALIASES: Dict[str, Dict[str, str]] = {
    "hubspot": {
        "contact.created": "contact.creation", "contact.updated": "contact.propertyChange", "contact.deleted": "contact.deletion",
        "company.created": "company.creation", "company.updated": "company.propertyChange", "company.deleted": "company.deletion",
        "deal.created": "deal.creation", "deal.updated": "deal.propertyChange", "deal.deleted": "deal.deletion",
        # HubSpot has no stage-only event: a stage move arrives as deal.propertyChange with propertyName "dealstage".
        "deal.stageChanged": "deal.propertyChange",
        "ticket.created": "ticket.creation", "ticket.updated": "ticket.propertyChange", "ticket.deleted": "ticket.deletion",
    },
}
#: A watch on an app's changes for one customer, as created or listed: {"id", "app", "events" (the app's own ids),
#: "status", "name", "connectionId", "accountId", "connectorId", ...}; never fastn's internal customer id.
Watch = Dict[str, Any]
#: One app call made during a request, from customer.call_log(correlation_id).
CallLogEntry = Dict[str, Any]
_WATCH_ID = re.compile(r"^[0-9a-f-]{36}$|^trg_", re.I)


def _to_watch(t: Any, app: str) -> Watch:
    """A trigger row as the API returns it, as a Watch (the app's event ids, no internal customer id)."""
    t = t if isinstance(t, dict) else {}
    rest = {k: v for k, v in t.items() if k not in ("endOrgId", "end_org_id", "appTrigger")}
    inner: Dict[str, Any] = t["appTrigger"] if isinstance(t.get("appTrigger"), dict) else {}  # the API nests the app part of a trigger
    raw_events = inner.get("events") if inner.get("events") is not None else t.get("events")
    events: List[str] = []
    if isinstance(raw_events, list):
        for e in raw_events:
            eid = e if isinstance(e, str) else (e.get("id") if isinstance(e, dict) else None)
            if eid:
                events.append(str(eid))
    pick = lambda k: inner[k] if inner.get(k) is not None else t.get(k)  # noqa: E731
    return {**rest, "id": t.get("id"), "app": app, "events": events, "status": t.get("status"), "name": t.get("name"), "connectionId": pick("connectionId"), "accountId": pick("accountId"), "connectorId": pick("connectorId")}


def _connector_id_of(t: Any) -> Any:
    inner: Dict[str, Any] = t["appTrigger"] if isinstance(t, dict) and isinstance(t.get("appTrigger"), dict) else {}
    return inner.get("connectorId") if inner.get("connectorId") is not None else (t.get("connectorId") if isinstance(t, dict) else None)


def without_internal_id(d: Any) -> Any:
    """Setup-link answers carry fastn's internal customer id; the partner's own ref is the one name for the customer."""
    if not isinstance(d, dict):
        return d
    return {k: v for k, v in d.items() if k not in ("endOrgId", "end_org_id")}


def data_of(r: Any) -> Any:
    return r.get("data") if isinstance(r, dict) and r.get("data") is not None else r


def _data_in(r: Any) -> Any:
    """`data` when the answer has that key (even when it is null), else the answer itself."""
    return r["data"] if isinstance(r, dict) and "data" in r else r


def _in(d: Mapping[str, Any]) -> Any:
    """A hand-built input dict for a generated method (whose parameter is the operation's TypedDict)."""
    return cast(Any, d)


class _Lookup:
    def __init__(self) -> None:
        self.done = threading.Event()
        self.row: Optional[CustomerRow] = None
        self.error: Optional[BaseException] = None


class CustomerContext:
    """Shared between every Customer object of one client: the caller's org and the ref -> fastn id cache."""

    def __init__(self, caller_org_id: Callable[[], str]) -> None:
        #: fastn's id of the caller's own org (from whoami), resolved once per client.
        self.caller_org_id = caller_org_id
        #: ref -> fastn org id, filled from every row a lookup sees.
        self.ids: Dict[str, str] = {}
        #: ref -> lookup in flight, so concurrent id() calls share one listOrgs.
        self.lookups: Dict[str, _Lookup] = {}
        #: "ref/category/entity" -> (read at, the providers the customer has connected for that entity).
        self.providers: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        #: (read at, the account's own widgets: inherited and inactive rows left out); re-read on a miss.
        self.widgets: Optional[Tuple[float, List[Dict[str, Any]]]] = None
        #: connector slug -> connector row, for watch().
        self.connectors: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()


class _ScopedTransport:
    """The customer's transport: every call carries x-end-org-ref, and where the route takes the customer in the body
    instead (`externalRef` or `endOrgId`), that field is filled in too."""

    def __init__(self, customer: Customer, transport: Transport) -> None:
        self._c = customer
        self._t = transport

    def call(self, op: OpDef, input: Mapping[str, Any], opts: Mapping[str, Any]) -> Any:
        keys = op.body.keys or {} if op.body is not None and op.body.kind == "fields" else {}
        body: Mapping[str, Any] = input
        ref = self._c.ref
        if op.id not in NOT_A_CUSTOMER_FIELD and input.get("externalRef") is None and input.get("endOrgId") is None:
            if "externalRef" in keys:
                body = {**input, "externalRef": ref}
            elif "endOrgId" in keys:
                body = {**input, "endOrgId": ref if op.id in TAKES_REF_AS_END_ORG_ID else self._c.id()}
        return self._t.call(op, body, {"customer": {"ref": ref}, **opts})


class _Links:
    """Setup links this customer was sent: links.get(setup_id), links.cancel(setup_id)."""

    def __init__(self, root: FastnApis) -> None:
        self._root = root

    def get(self, setup_id: str, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        r = self._root.embed.get_setup_link(_in({"id": setup_id}), **opts)
        return dict(without_internal_id(data_of(r)) or {})

    def cancel(self, setup_id: str, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        r = self._root.embed.cancel_setup_link(_in({"id": setup_id}), **opts)
        return dict(without_internal_id(data_of(r)) or {})


class Customer:
    def __init__(self, root: FastnApis, transport: Transport, ref: str, ctx: CustomerContext) -> None:
        self._root = root
        self.ref = ref
        self._ctx = ctx
        self._scoped = _ScopedTransport(self, transport)
        self._api: Optional[FastnApis] = None
        self._catalog: Optional[Catalog] = None
        self._calendar: Optional[Calendar] = None
        self._crm: Optional[Crm] = None
        self.links = _Links(root)

    @property
    def api(self) -> FastnApis:
        """Every API area, run for this customer. Each call carries x-end-org-ref, and where the route takes the
        customer in the body instead (`externalRef` or `endOrgId`, e.g. initiateOauthConnection, storeConnections,
        createEventSubscription, createSecret), that field is filled in too, because the platform reads the header
        only on unified record and workflow execute routes. Pass the field yourself to override."""
        if self._api is None:
            self._api = build_apis(self._scoped)
        return self._api

    @property
    def catalog(self) -> Catalog:
        """The unified catalog as this customer sees it: categories, entities, fields, and which providers they connected."""
        if self._catalog is None:
            self._catalog = Catalog(self.api)
        return self._catalog

    @property
    def calendar(self) -> Calendar:
        """Typed calendar methods on the customer's connected calendar: free_slots, book, find, get, reschedule, cancel."""
        if self._calendar is None:
            self._calendar = Calendar(self)
        return self._calendar

    @property
    def crm(self) -> Crm:
        """Typed CRM methods on the customer's connected CRM: contacts, notes, tasks, deals."""
        if self._crm is None:
            self._crm = Crm(self)
        return self._crm

    # ── providers ──
    def provider_for(self, category: str, entity: str, op: str) -> str:
        """The one provider this customer has connected for an entity that supports `op`, from the catalog's providers
        list (cached per client for PROVIDER_TTL_SECONDS). No connected provider: 404 NO_CONNECTED_PROVIDER (send the
        customer a setup link). Several: 409 PROVIDER_AMBIGUOUS (pass `provider=` on the call)."""
        key = f"{self.ref}/{category}/{entity}"
        with self._ctx.lock:
            entry = self._ctx.providers.get(key)
        if entry is None or _now() - entry[0] > PROVIDER_TTL_SECONDS:
            rows = self.catalog.providers(category, entity)
            entry = (_now(), rows)
            with self._ctx.lock:
                self._ctx.providers[key] = entry
        connected = [x for x in entry[1] if isinstance(x, dict) and x.get("connected")]
        able = [x for x in connected if not isinstance(x.get("operations"), list) or op in x["operations"]]
        path = f"/v1/unified/{category}/{entity}/providers"
        if len(able) == 1:
            return str(able[0].get("connectorSlug"))
        with self._ctx.lock:  # the next call reads the list again: a reconnect is picked up at once
            self._ctx.providers.pop(key, None)
        slugs = [str(x.get("connectorSlug")) for x in connected]
        if not connected:
            raise FastnApiError(f'customer "{self.ref}" has no connected provider for {category}/{entity}; send them a setup link (customer.connect(app))', status=404, code="NO_CONNECTED_PROVIDER", method="GET", path=path, details={"category": category, "entity": entity, "op": op})
        if not able:
            raise FastnApiError(f'none of the providers customer "{self.ref}" connected for {category}/{entity} ({", ".join(slugs)}) supports {op}', status=404, code="OPERATION_NOT_SUPPORTED", method="GET", path=path, details={"category": category, "entity": entity, "op": op, "connected": slugs})
        able_slugs = [str(x.get("connectorSlug")) for x in able]
        raise FastnApiError(f'customer "{self.ref}" has {len(able)} providers connected for {category}/{entity} ({", ".join(able_slugs)}); pass provider= on the call', status=409, code="PROVIDER_AMBIGUOUS", method="GET", path=path, details={"category": category, "entity": entity, "op": op, "providers": able_slugs})

    def forget_provider(self, category: Optional[str] = None, entity: Optional[str] = None) -> None:
        """Forgets the cached providers of one entity (or all of this customer's), so the next call reads them again."""
        with self._ctx.lock:
            if category and entity:
                self._ctx.providers.pop(f"{self.ref}/{category}/{entity}", None)
            else:
                for k in [k for k in self._ctx.providers if k.startswith(f"{self.ref}/")]:
                    del self._ctx.providers[k]

    # ── identity ──
    def id(self) -> str:
        """fastn's id of this customer org (the `id` createTenant returned). Cached after the first lookup."""
        with self._ctx.lock:
            cached = self._ctx.ids.get(self.ref)
        if cached:
            return cached
        found = self.find()
        if not found:
            raise FastnApiError(f'customer "{self.ref}" is not registered; call customer.register({{"name": ...}}) first', status=404, code="NOT_FOUND", method="GET", path="/v1/orgs")
        return str(found["id"])

    def find(self) -> Optional[CustomerRow]:
        """The customer org row, or None when this ref is unknown to fastn. Only orgs under the caller's own org are
        considered (listOrgs with parent_id, and the row's parentId is checked), so a staff key that sees every org can
        never resolve another partner's customer. Every row seen fills the client's ref -> id cache, and concurrent
        lookups of one ref share a single request. GET /v1/orgs has no filter by ref yet (KAT-8615), so a cold lookup
        downloads the partner's customer list once."""
        ctx, ref = self._ctx, self.ref
        with ctx.lock:
            lookup = ctx.lookups.get(ref)
            owner = lookup is None
            if lookup is None:
                lookup = ctx.lookups[ref] = _Lookup()
        if not owner:
            lookup.done.wait()
            if lookup.error is not None:
                raise lookup.error
            return lookup.row
        try:
            parent = ctx.caller_org_id()
            res = self._root.orgs.list_orgs(_in({"type": "end_org", "parent_id": parent}))
            row: Optional[CustomerRow] = None
            for r in rows_of(res):
                if not isinstance(r, dict) or not isinstance(r.get("id"), str):
                    continue
                parent_id = r.get("parentId")
                if parent_id is None:
                    parent_id = r.get("parent_id")
                if parent_id != parent:
                    continue  # fail closed: a row without our parent is not ours
                refs = [x for x in (r.get("externalRef"), r.get("orgId"), r.get("external_ref")) if isinstance(x, str) and x]
                with ctx.lock:
                    for x in refs:
                        ctx.ids[x] = r["id"]
                if ref in refs and row is None:
                    row = r
            lookup.row = row
            return row
        except BaseException as e:
            lookup.error = e
            raise
        finally:
            with ctx.lock:
                ctx.lookups.pop(ref, None)
            lookup.done.set()

    def _set_id(self, value: Optional[str]) -> None:
        with self._ctx.lock:
            if value:
                self._ctx.ids[self.ref] = value
            else:
                self._ctx.ids.pop(self.ref, None)

    # ── lifecycle ──
    def register(self, input: Mapping[str, Any], **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """Creates the customer org under your account (idempotent: returns the existing org when the ref is known).
        `input["name"]` is the display name; the ref becomes its orgId/externalRef."""
        existing = self.find()
        if existing:
            return {"data": existing, "existed": True}
        try:
            # plan defaults to "free": the API rejects a paid default plan for anyone but a platform admin.
            res = self._root.orgs.create_tenant(_in({"plan": "free", **input, "orgId": self.ref}), **opts)
            d = data_of(res)
            id_ = d.get("id") if isinstance(d, dict) else None
            if isinstance(id_, str):
                self._set_id(id_)
            return dict(res) if isinstance(res, dict) else {"data": res}
        except FastnApiError as err:
            if err.is_conflict:
                row = self.find()
                if row:
                    return {"data": row, "existed": True}
            raise

    def remove(self, **opts: Unpack[RequestOptions]) -> None:
        """Suspends and then deletes the customer org (the API refuses to delete an active org). Connections and data
        go with it; there is no undo. If the delete fails, the org is checked first: gone (the answer was lost) counts
        as removed; otherwise it is set back to active and the error says which state it is in."""
        id_ = self.id()
        self._root.orgs.update_tenant(_in({"id": id_, "status": "suspended"}), **opts)
        try:
            self._root.orgs.delete_tenant(_in({"id": id_}), **opts)
        except Exception as err:
            try:
                self._root.orgs.get_tenant(_in({"id": id_}), **opts)
                gone = False
            except FastnApiError as e:
                gone = e.is_not_found
            if gone:
                self._set_id(None)
                return
            state = "active again"
            try:
                self._root.orgs.update_tenant(_in({"id": id_, "status": "active"}), **opts)
            except Exception:
                state = "still suspended"
            note = f' (customer "{self.ref}" was suspended before the delete; it is {state})'
            if isinstance(err, (FastnApiError,)) or hasattr(err, "message"):
                err.message = f"{getattr(err, 'message', str(err))}{note}"  # type: ignore[attr-defined]
            err.args = (f"{err.args[0] if err.args else err}{note}",) + tuple(err.args[1:])
            raise err
        self._set_id(None)

    # ── connecting ──
    def connect(self, app_or_input: Union[str, Mapping[str, Any]], **options: Any) -> Dict[str, Any]:
        """`connect("googleCalendar")`: a setup link for the app, by connector slug. The account's widget for that app is
        looked up (listWidgets, matched on connectorRefs), the link is created for this customer (the org is created on
        the fly when it does not exist yet) and `url` is where to send the customer. Options: widget_id, connection_name
        (default the widget's name), label, redirect_url, expires_in_minutes, metadata, allow_additional_connection,
        plus any request option. No widget for the app: 404 WIDGET_NOT_FOUND; several: 409 WIDGET_AMBIGUOUS (pass
        widget_id).

        `connect({"connectorId": ..., ...})`: starts an OAuth connection directly (initiateOauthConnection) and returns
        the answer with the URL to send the customer to. The connection is stored on the customer org (endOrgId is
        filled in)."""
        if not isinstance(app_or_input, str):
            return dict(self._root.connections.initiate_oauth_connection(_in({**app_or_input, "endOrgId": self.id()}), **options) or {})
        app = app_or_input
        connect_opts = {k: v for k, v in options.items() if k in _CONNECT_OPTIONS}
        opts = {k: v for k, v in options.items() if k not in _CONNECT_OPTIONS}
        widget = self._widget_for(app, connect_opts.get("widget_id"), opts)
        body: Dict[str, Any] = {"createIfMissing": True}
        for k, v in connect_opts.items():
            if k not in ("widget_id", "connection_name") and v is not None:
                body[_CONNECT_OPTIONS[k]] = v
        body["widgetId"] = widget["id"]
        body["externalRef"] = self.ref
        connection_name = connect_opts.get("connection_name")
        body["connectionName"] = connection_name if connection_name is not None else (widget.get("name") or app)
        r = self._root.embed.create_setup_link(_in(body), **opts)
        d = dict(without_internal_id(data_of(r)) or {})
        setup_url = d.pop("setupUrl", None)
        return {**d, "setupId": d.get("setupId"), "url": setup_url if setup_url is not None else d.get("url"), "status": d.get("status"), "widgetId": widget["id"]}

    def _own_widgets(self, fresh: bool, opts: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """The account's own widgets that a customer can be offered: rows inherited from the parent account are read-only
        and left out, as is any row that is not the caller's org's, and of a customised integration (two rows, the
        original and the copy) only the active version is kept. Read once and reused for WIDGET_TTL_SECONDS; `fresh` reads again."""
        with self._ctx.lock:
            entry = self._ctx.widgets
        if fresh or entry is None or _now() - entry[0] > WIDGET_TTL_SECONDS:
            r = self._root.embed.list_widgets(_in({}), **opts)
            try:
                me: Optional[str] = self._ctx.caller_org_id()
            except Exception:
                me = None
            rows = []
            for w in rows_of(r):
                if not isinstance(w, dict) or w.get("inheritedFrom"):
                    continue
                if me and w.get("orgId") and w.get("orgId") != me:
                    continue
                version = w.get("version")
                if isinstance(version, dict) and version.get("active") is False:
                    continue
                rows.append(w)
            entry = (_now(), rows)
            with self._ctx.lock:
                self._ctx.widgets = entry
        return entry[1]

    def _widget_for(self, app: str, widget_id: Optional[str], opts: Mapping[str, Any]) -> Dict[str, Any]:
        """The account's widget for an app (by connector slug), or the one named by `widget_id`. A miss reads the list once more."""

        def slug_of(w: Dict[str, Any]) -> List[str]:
            out: List[Any] = []
            if isinstance(w.get("connectorRefs"), list):
                out += [c.get("slug") for c in w["connectorRefs"] if isinstance(c, dict)]
            if isinstance(w.get("connectorSlugs"), list):
                out += list(w["connectorSlugs"])
            return [x for x in out if isinstance(x, str)]

        widgets = self._own_widgets(False, opts)

        def pick() -> List[Dict[str, Any]]:
            return [x for x in widgets if x.get("id") == widget_id] if widget_id else [w for w in widgets if app in slug_of(w)]

        matches = pick()
        if not matches:  # made after the last read?
            widgets = self._own_widgets(True, opts)
            matches = pick()
        if len(matches) == 1:
            return matches[0]
        if widget_id:
            raise FastnApiError(f"widget {widget_id} is not one of your account's own active widgets", status=404, code="WIDGET_NOT_FOUND", method="GET", path="/v1/widgets", details={"widgetId": widget_id})
        if not matches:
            raise FastnApiError(f'no widget on your account connects "{app}"; create one in fastn (Widgets) or pass widget_id', status=404, code="WIDGET_NOT_FOUND", method="GET", path="/v1/widgets", details={"app": app, "widgets": [{"id": w.get("id"), "name": w.get("name"), "connectors": slug_of(w)} for w in widgets]})
        raise FastnApiError(f'{len(matches)} widgets on your account connect "{app}" ({", ".join(str(w.get("id")) for w in matches)}); pass widget_id', status=409, code="WIDGET_AMBIGUOUS", method="GET", path="/v1/widgets", details={"app": app, "widgets": [{"id": w.get("id"), "name": w.get("name")} for w in matches]})

    def connect_with_credentials(self, input: Mapping[str, Any], **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """Stores a connection made with typed-in credentials (API key, basic auth, custom fields) on the customer org.
        `input`: connectorId, credentials, name?, authMethodId? (default: the connector's first non-OAuth method).
        Prefer setup_link(): fastn's hosted page collects the credentials, so they never pass through your backend.
        The platform checks the fields, not the SDK: an incomplete INPUT credential set answers 400
        CREDENTIALS_INCOMPLETE with the missing names in `FastnApiError.body["missing"]`."""
        auth_method_id = input.get("authMethodId")
        if auth_method_id is None:
            auth_method_id = self.auth_fields(str(input.get("connectorId")), None, **opts)["authMethodId"]
        return dict(self._root.connections.store_connections(_in({**input, "authMethodId": auth_method_id, "endOrgId": self.id()}), **opts) or {})

    def auth_fields(self, connector_id: str, auth_method_id: Optional[str] = None, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """The credential fields a connector's auth method lists in its inputContract: {"authMethodId", "authType",
        "names", "required", "schema"}. With no auth_method_id the connector's first non-OAuth method is used. For an
        INPUT method these are the fields to send; for API_KEY, BEARER, BASIC and the like the platform stores one
        fixed key per type, which the contract does not always name (KAT-8616), so treat `names` as a hint."""
        res = self._root.connectors.list_auth_methods(_in({"connectorId": connector_id}), **opts)
        methods = [m for m in rows_of(res) if isinstance(m, dict)]
        m: Optional[Dict[str, Any]] = None
        if auth_method_id:
            m = next((x for x in methods if x.get("id") == auth_method_id), None)
        else:
            m = next((x for x in methods if "oauth" not in str(x.get("authType", x.get("type", ""))).lower()), None) or (methods[0] if methods else None)
        if m is None:
            raise FastnApiError(f"auth_fields({connector_id}): auth method {auth_method_id or '(any)'} not found", status=404, code="NOT_FOUND", method="GET", path="/v1/auth-methods", body=res)
        schema = m.get("inputContract") or m.get("input_contract") or {}
        if not isinstance(schema, dict):
            schema = {}
        names = list(schema.get("properties") or {})
        req = schema.get("required")
        required: List[Any] = list(req) if isinstance(req, list) else []
        return {"authMethodId": m.get("id"), "authType": m.get("authType", m.get("type")), "names": names, "required": required, "schema": schema}

    def run_action(self, connector: str, action: str, input: Optional[Mapping[str, Any]] = None, mock_mode: bool = False, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """Runs one raw connector action with this customer's own connection, for what the unified API does not cover
        (e.g. updating a HubSpot deal's stage, logging a call). The action is named by connector slug and action slug.
        The customer's connection for that connector is pinned by id (and its installation too, when one exists), so
        the call never runs with your own org's connection. The provider's answer is returned under `data.response`."""
        id_ = self.id()
        conns = self.connections(None, **opts)
        insts = self._root.embed.list_installations(_in({"end_org_id": id_}), **opts)
        acts = self._root.connectors.list_connector_actions_by_slug(_in({"connector": connector}), **opts)

        def rows(r: Any) -> List[Dict[str, Any]]:
            if isinstance(r, dict) and isinstance(r.get("data"), dict) and isinstance(r["data"].get("actions"), list):
                return [x for x in r["data"]["actions"] if isinstance(x, dict)]
            return [x for x in rows_of(r) if isinstance(x, dict)]

        inst = next((i for i in rows(insts) if i.get("endOrgId") == id_ and isinstance(i.get("connections"), dict) and connector in i["connections"]), None)
        conn_id = inst["connections"].get(connector) if inst else None
        conn_rows = rows(conns)
        conn = next((c for c in conn_rows if conn_id is not None and c.get("id") == conn_id), None)
        if conn is None:
            conn = next((c for c in conn_rows if c.get("connectorSlug") == connector or (isinstance(c.get("connector"), dict) and c["connector"].get("slug") == connector)), None)
        if conn is None:
            raise FastnApiError(f'customer "{self.ref}" has no {connector} connection to run {action} with', status=404, code="CONNECTION_NOT_FOUND", details={"connector": connector}, method="POST", path="/v1/actions/{id}/execute")
        act = next((a for a in rows(acts) if a.get("slug") == action), None)
        if not act or not act.get("id"):
            raise FastnApiError(f'connector {connector} has no action "{action}"', status=404, code="NOT_FOUND", details={"connector": connector, "action": action}, method="GET", path="/v2/connectors/{connector}/actions")
        body: Dict[str, Any] = {"id": act["id"], "connectorId": conn.get("connectorId"), "connectionName": conn.get("name"), "connectionId": conn.get("id")}
        if inst:
            body["installationId"] = inst.get("id")
        body["input"] = dict(input or {})
        if mock_mode:
            body["mockMode"] = True
        return dict(self._root.connectors.execute_action(_in(body), **opts) or {})

    # ── watching an app's changes ──
    def watch(self, app: str, events: List[str], account_id: Optional[str] = None, connection_id: Optional[str] = None, name: Optional[str] = None, **opts: Unpack[RequestOptions]) -> Watch:
        """Starts sending this customer's changes at an app (a new HubSpot contact, a deal moved) to your webhook, as
        `connector.event` and `unified.event` events. Events are named in plain words ("contact.created",
        "deal.stageChanged"; see EVENT_ALIASES) or as the app names them ("contact.creation"); unknown names are
        refused with 400 EVENT_NOT_FOUND and the list of valid ones. The connector is found by slug, the customer's
        account on it by its connections (none: 404 CONNECTION_NOT_FOUND; several: 409 CONNECTION_AMBIGUOUS, pass
        connection_id); apps that route events by account number (HubSpot: the portal id) take it in `account_id`."""
        if not isinstance(events, (list, tuple)) or len(events) == 0:
            raise TypeError("watch(app, events): at least one event name is required")
        connector = self._connector_by_slug(app, opts)
        catalog = self.watchable_events(app, **opts)
        id_ = self.id()
        conns = self.connections(None, **opts)
        by_id = {e.get("id"): e for e in catalog if isinstance(e, dict)}
        aliases = EVENT_ALIASES.get(app, {})
        picked: List[Dict[str, Any]] = []
        for name_ in events:
            event_id = aliases.get(name_, name_)
            row = by_id.get(event_id)
            if row is None:
                valid = [str(e.get("id")) for e in catalog if isinstance(e, dict)]
                raise FastnApiError(f'"{name_}" is not an event of {app}; valid: {", ".join([*aliases, *valid])}', status=400, code="EVENT_NOT_FOUND", method="GET", path="/v1/connector-events", details={"app": app, "event": name_, "valid": valid})
            entry: Dict[str, Any] = {"id": row["id"], "label": row.get("label") or row["id"]}
            if row.get("description"):
                entry["description"] = row["description"]
            picked.append(entry)
        uniq: Dict[str, Dict[str, Any]] = {}  # two plain names can map to one id
        for e in picked:
            uniq.setdefault(str(e["id"]), e)
        events_out = list(uniq.values())
        rows = [c for c in rows_of(conns) if isinstance(c, dict)]
        of_app = [c for c in rows if c.get("connectorId") == connector.get("id") or (isinstance(c.get("connector"), dict) and c["connector"].get("slug") == app)]
        if connection_id:
            connection = next((c for c in rows if c.get("id") == connection_id), None)
            if connection is None:
                raise FastnApiError(f'connection {connection_id} is not one of customer "{self.ref}"\'s accounts', status=404, code="CONNECTION_NOT_FOUND", method="GET", path="/v1/connections", details={"app": app, "connectionId": connection_id})
            if not any(c is connection for c in of_app):
                other = connection["connector"].get("slug") if isinstance(connection.get("connector"), dict) and connection["connector"].get("slug") else connection.get("connectorId")
                raise FastnApiError(f"connection {connection_id} is a {other} account, not {app}", status=400, code="CONNECTION_MISMATCH", method="GET", path="/v1/connections", details={"app": app, "connectionId": connection_id, "connector": other})
        else:
            if len(of_app) == 0:
                raise FastnApiError(f'customer "{self.ref}" has no {app} account to watch; send them a setup link first', status=404, code="CONNECTION_NOT_FOUND", method="GET", path="/v1/connections", details={"app": app, "connections": []})
            if len(of_app) > 1:
                raise FastnApiError(f'customer "{self.ref}" has {len(of_app)} {app} accounts; pass connection_id', status=409, code="CONNECTION_AMBIGUOUS", method="GET", path="/v1/connections", details={"app": app, "connections": [c.get("id") for c in of_app]})
            connection = of_app[0]
        body: Dict[str, Any] = {
            "name": name if name is not None else f"{app} changes for {self.ref}", "status": "ACTIVE", "type": "WEBHOOK", "routes": [], "endOrgId": id_,
            "connectorId": connector.get("id"), "connectorName": connector.get("name") or app, "connectionId": connection.get("id"), "events": events_out,
        }
        if account_id:
            body["accountId"] = account_id
        r = self._root.events.create_app_event_trigger(_in(body), **opts)
        return _to_watch(data_of(r), app)

    def watches(self, app: Optional[str] = None, **opts: Unpack[RequestOptions]) -> List[Watch]:
        """The watches on this customer's apps (every app, or one)."""
        id_ = self.id()
        connector = self._connector_by_slug(app, opts) if app else None
        # every page: the list is 20 per page by default, and the connectorId query does not match the nested app part, so filter here
        rows: List[Any] = []
        cursor: Optional[str] = None
        for _ in range(1000):
            page: Dict[str, Any] = {"end_org_id": id_, "limit": 100}
            if cursor:
                page["cursor"] = cursor
            r = self._root.events.list_app_event_triggers(_in(page), **opts)
            rows.extend(rows_of(r))
            meta: Dict[str, Any] = r["meta"] if isinstance(r, dict) and isinstance(r.get("meta"), dict) else {}
            nxt = meta.get("nextCursor") if meta.get("nextCursor") is not None else (r.get("nextCursor") if isinstance(r, dict) else None)
            cursor = str(nxt) if nxt else None
            if not cursor:
                break
        out: List[Watch] = []
        for t in rows:
            if not isinstance(t, dict):
                continue
            if connector is not None and _connector_id_of(t) != connector.get("id"):
                continue
            inner: Dict[str, Any] = t["appTrigger"] if isinstance(t.get("appTrigger"), dict) else {}
            out.append(_to_watch(t, app or inner.get("connectorSlug") or t.get("connectorSlug") or ""))
        return out

    def unwatch(self, app_or_watch_id: str, **opts: Unpack[RequestOptions]) -> List[str]:
        """Stops a watch: by its id (one of this customer's watches, else 404 WATCH_NOT_FOUND), or every watch on an app. Answers the ids removed."""
        by_id = bool(_WATCH_ID.match(app_or_watch_id))
        mine = self.watches(None if by_id else app_or_watch_id, **opts)
        ids = [str(w["id"]) for w in mine if not by_id or w["id"] == app_or_watch_id]
        if by_id and not ids:
            raise FastnApiError(f'watch {app_or_watch_id} is not one of customer "{self.ref}"\'s watches', status=404, code="WATCH_NOT_FOUND", method="GET", path="/v1/app-triggers", details={"watchId": app_or_watch_id})
        for id_ in ids:
            self._root.events.delete_app_event_trigger(_in({"id": id_}), **opts)
        return ids

    def watchable_events(self, app: str, **opts: Unpack[RequestOptions]) -> List[Dict[str, Any]]:
        """The events an app can report (its own ids, labels and payload shapes), from the connector's catalog."""
        connector = self._connector_by_slug(app, opts)
        r = self._root.events.list_connector_events(_in({"connectorId": connector.get("id")}), **opts)
        if isinstance(r, dict) and isinstance(r.get("data"), dict) and isinstance(r["data"].get("events"), list):
            return list(r["data"]["events"])
        return rows_of(r)

    def _connector_by_slug(self, app: str, opts: Mapping[str, Any]) -> Dict[str, Any]:
        """The connector row for an app slug (id, name), read once per client."""
        with self._ctx.lock:
            row = self._ctx.connectors.get(app)
        if row is not None:
            return row
        r: Any = self._root.connectors.list_connectors(_in({"slug": app}), **opts)
        rows = rows_of(r)
        if not rows and isinstance(r, dict) and isinstance(r.get("data"), dict) and isinstance(r["data"].get("items"), list):
            rows = list(r["data"]["items"])
        rows = [cast(Dict[str, Any], c) for c in rows if isinstance(c, dict)]
        found: Optional[Dict[str, Any]] = next((c for c in rows if c.get("slug") == app), rows[0] if len(rows) == 1 else None)
        if not found or not found.get("id"):
            raise FastnApiError(f'no connector with slug "{app}"', status=404, code="CONNECTOR_NOT_FOUND", method="GET", path="/v1/connectors", details={"app": app})
        with self._ctx.lock:
            self._ctx.connectors[app] = found
        return found

    # ── accounts and the customer row ──
    def disconnect(self, account_id: str, **opts: Unpack[RequestOptions]) -> None:
        """Removes one of the customer's accounts (they get `connection.revoked`); calls on that app stop working. The id
        must be one of this customer's accounts (404 CONNECTION_NOT_FOUND otherwise): one key serves every customer, so
        an id mixed up on your side can never touch another customer."""
        if not account_id:
            raise TypeError("disconnect(account_id): the account id is required (customer.connections())")
        self._own_account(account_id, opts)
        self._root.connections.delete_connections(_in({"id": account_id}), **opts)

    def rename_account(self, account_id: str, name: str, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """Renames one of the customer's accounts (the name shown to them). The id must be one of this customer's accounts."""
        if not account_id or not name:
            raise TypeError("rename_account(account_id, name): both are required")
        self._own_account(account_id, opts)
        r = self._root.connections.update_connection(_in({"id": account_id, "name": name}), **opts)
        return cast(Dict[str, Any], _data_in(r))

    def _own_account(self, account_id: str, opts: Mapping[str, Any]) -> Dict[str, Any]:
        """The customer's connection row for an account id, or 404 CONNECTION_NOT_FOUND when it is not theirs."""
        row = next((c for c in rows_of(self.connections(None, **opts)) if isinstance(c, dict) and c.get("id") == account_id), None)
        if row is None:
            raise FastnApiError(f'account {account_id} is not one of customer "{self.ref}"\'s accounts', status=404, code="CONNECTION_NOT_FOUND", method="GET", path="/v1/connections", details={"accountId": account_id})
        return row

    def update(self, changes: Mapping[str, Any], **opts: Unpack[RequestOptions]) -> CustomerRow:
        """Changes the customer's display name, or pauses and resumes them: {"name": ..., "status": "suspended" | "active"}."""
        r = self._root.orgs.update_tenant(_in({"id": self.id(), **changes}), **opts)
        return cast(Dict[str, Any], _data_in(r))

    def call_log(self, correlation_id: str, **opts: Any) -> List[CallLogEntry]:
        """What fastn did for one of your request ids (sent as `correlation_id`): one entry per app call."""
        if not correlation_id:
            raise TypeError("call_log(correlation_id): the id is required")
        r = self.api.unified.list_unified_calls(_in({"correlation_id": correlation_id}), **opts)
        return [{k: v for k, v in x.items() if k not in ("endOrgId", "end_org_id")} for x in rows_of(r) if isinstance(x, dict)]

    # ── reads and links ──
    def get(self, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """The customer org (getTenant by fastn id)."""
        return dict(self._root.orgs.get_tenant(_in({"id": self.id()}), **opts) or {})

    def connections(self, input: Optional[Mapping[str, Any]] = None, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """Connections this customer has made (listConnections filtered to the customer org)."""
        return dict(self._root.connections.list_connections(_in({**(input or {}), "endOrgId": self.id()}), **opts) or {})

    def setup_link(self, input: Mapping[str, Any], **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """A setup link the customer opens to connect their tools. The org is created on the fly when it does not exist
        yet (createIfMissing), so this works before register()."""
        return dict(self._root.embed.create_setup_link(_in({"createIfMissing": True, **input, "externalRef": self.ref}), **opts) or {})

    def embed_token(self, input: Optional[Mapping[str, Any]] = None, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """A short-lived token for the embedded widget, scoped to this customer (endOrgId = your ref)."""
        return dict(self._root.embed.create_embed_token(_in({"createIfMissing": True, **(input or {}), "endOrgId": self.ref}), **opts) or {})

    def records(self, category: str, entity: str, provider: Optional[str] = None, connection_id: Optional[str] = None) -> Records:
        """Unified records for this customer: `customer.records("crm", "contact").create({...})`. Same names as the
        catalog; every call carries x-end-org-ref and the given provider."""
        return Records(self.api, category, entity, provider, connection_id)


class Records:
    """A unified record call scoped to one customer; `category`/`entity`/`provider` come from the catalog."""

    def __init__(self, api: FastnApis, category: str, entity: str, provider: Optional[str] = None, connection_id: Optional[str] = None) -> None:
        self._api = api
        self.category = category
        self.entity = entity
        self.provider = provider
        self.connection_id = connection_id

    def _base(self) -> Dict[str, Any]:
        return {"category": self.category, "entity": self.entity, "provider": self.provider or None, "connection_id": self.connection_id or None}

    def create(self, record: Mapping[str, Any], **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """POST a canonical record. Pass `idempotency_key=` so a retry cannot create it twice."""
        return self._api.unified.create_unified_record(_in({**self._base(), "record": record}), **opts)

    def get(self, id: str, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        return self._api.unified.get_unified_record(_in({**self._base(), "id": id}), **opts)

    def list(self, input: Optional[Mapping[str, Any]] = None, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        return self._api.unified.list_unified_records(_in({**self._base(), **(input or {})}), **opts)

    def search(self, filters: Mapping[str, Any], **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        return self._api.unified.search_unified_records(_in({**self._base(), "filters": filters}), **opts)

    def update(self, id: str, record: Mapping[str, Any], **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        return self._api.unified.update_unified_record(_in({**self._base(), "id": id, "record": record}), **opts)

    def delete(self, id: str, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        return self._api.unified.delete_unified_record(_in({**self._base(), "id": id}), **opts)

    def providers(self, **opts: Unpack[RequestOptions]) -> Dict[str, Any]:
        """Which providers are mapped for this entity and whether the customer has connected them."""
        return self._api.unified.list_unified_entity_providers(_in({"category": self.category, "entity": self.entity}), **opts)
