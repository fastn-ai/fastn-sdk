# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""Typed domain methods on top of the unified API: `customer.calendar.*` and `customer.crm.*`. Each method names its
fields (the catalog's own names, e.g. start_time, first_name), fills category/entity, and picks the provider from
what the customer has connected unless `provider=` says otherwise. Everything here is the unified record routes
underneath, so `customer.records(...)` does the same with untyped input. A port of node/src/domain.ts.
"""

from __future__ import annotations

import math
import re
from datetime import date, datetime, timezone
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
    cast,
)

from ._transport import to_iso
from .errors import FastnApiError

if TYPE_CHECKING:
    from typing import Protocol, TypedDict

    from typing_extensions import Unpack

    from ._generated.api import FastnApis
    from ._transport import RequestOptions

    class DomainCallOptions(RequestOptions, total=False):
        """Options on every typed method: the request options plus which provider and connection to run against."""

        #: Connector slug (e.g. "hubspot"). Default: the one provider the customer has connected for the entity.
        provider: str
        #: One of the customer's connections on that provider, when they hold several (ids from customer.connections()).
        connection_id: str

    class ProviderResolver(Protocol):
        """Who answers provider questions for one customer (the Customer object)."""

        @property
        def api(self) -> FastnApis: ...

        def provider_for(self, category: str, entity: str, op: str) -> str: ...

        def forget_provider(self, category: Optional[str] = None, entity: Optional[str] = None) -> None: ...

    class Interval(TypedDict):
        start_time: str
        end_time: str


#: An ISO 8601 timestamp, or a datetime / date (sent as its ISO string).
DateInput = Union[str, datetime, date]
#: One record as the unified API returns it: {"id", "provider", "data", "warnings"?}.
UnifiedRecord = Dict[str, Any]
#: One page of records: {"records", "nextCursor"?, "hasMore"?, "provider", "warnings"?}.
UnifiedPage = Dict[str, Any]
#: The answer of a delete: {"id", "provider", "deleted"?, "warnings"?}.
UnifiedDeleted = Dict[str, Any]

_PROVIDER_ERROR = re.compile(r"PROVIDER|CONNECTION", re.I)
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.(\d{1,9}))?)?(Z|[+-]\d{2}:?\d{2})?)?$", re.I)


def wire_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    """datetime/date values become ISO strings; everything else is sent as given. A key set to None is sent as null,
    which clears the field (as Node sends null); only a key that is absent is left out."""
    return {k: to_iso(v) for k, v in record.items()}


def _id_of(id: str) -> str:
    """An empty id would call the collection route instead of one record: refuse it before the request."""
    if not isinstance(id, str) or not id:
        raise TypeError("a record id is required")
    return id


def parse_iso_ms(value: Any) -> Optional[float]:
    """Unix milliseconds of an ISO 8601 timestamp, or None when it does not parse. Read as JavaScript's Date reads
    it: Z or an offset as given, a date-time with no zone as the machine's local time (a naive datetime too), a bare
    date as UTC midnight."""
    if isinstance(value, datetime):
        value = to_iso(value)
    if not isinstance(value, str):
        return None
    m = _ISO.match(value.strip())
    if not m:
        return None
    y, mo, d, hh, mm, ss, frac, tz = m.groups()
    try:
        dt = datetime(int(y), int(mo), int(d), int(hh or 0), int(mm or 0), int(ss or 0), int((frac or "0")[:3].ljust(3, "0")) * 1000, tzinfo=timezone.utc if tz else None)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone(timezone.utc) if hh is not None else dt.replace(tzinfo=timezone.utc)  # as JavaScript: date-time without a zone = local, a bare date = UTC
    ms = dt.timestamp() * 1000
    if tz and tz.upper() != "Z":
        sign = 1 if tz[0] == "+" else -1
        hrs, mins = int(tz[1:3]), int(tz[-2:])
        ms -= sign * (hrs * 60 + mins) * 60_000
    return ms


def iso_of_ms(ms: float) -> str:
    """Unix milliseconds -> ISO 8601 the way JavaScript's Date.toISOString() spells it."""
    return str(to_iso(datetime.fromtimestamp(ms / 1000, tz=timezone.utc)))


def free_intervals(start: str, end: str, busy: Sequence[Mapping[str, Any]]) -> List[Interval]:
    """The window minus the busy intervals: busy ones are merged first, then cut out of [start, end]."""
    s0, e0 = parse_iso_ms(start), parse_iso_ms(end)
    if s0 is None or e0 is None:
        return []
    parsed: List[Tuple[float, float]] = []
    for b in busy:
        s, e = parse_iso_ms(b.get("start_time")), parse_iso_ms(b.get("end_time"))
        if s is not None and e is not None and e > s:
            parsed.append((s, e))
    parsed.sort(key=lambda x: x[0])
    free: List[Tuple[float, float]] = []
    cursor = s0
    for s, e in parsed:
        if e <= cursor:
            continue
        if s > cursor:
            free.append((cursor, min(s, e0)))
        cursor = max(cursor, e)
        if cursor >= e0:
            break
    if cursor < e0:
        free.append((cursor, e0))
    return [{"start_time": iso_of_ms(a), "end_time": iso_of_ms(b)} for a, b in free if b > a]


def _check_minutes(minutes: Any, what: str) -> float:
    if isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or not math.isfinite(minutes) or minutes <= 0:
        raise TypeError(f"{what} must be a positive number, got {minutes!r}")
    return float(minutes)


def slots_of(free: Sequence[Mapping[str, Any]], minutes: float) -> List[Interval]:
    """Cuts every free interval into back-to-back slots of `minutes` (a positive number); a remainder shorter than a slot is dropped."""
    length = _check_minutes(minutes, "slot minutes") * 60_000
    out: List[Interval] = []
    for f in free:
        s, e = parse_iso_ms(f.get("start_time")), parse_iso_ms(f.get("end_time"))
        if s is None or e is None:
            continue
        t = s
        while t + length <= e:
            out.append({"start_time": iso_of_ms(t), "end_time": iso_of_ms(t + length)})
            t += length
    return out


def _in(d: Mapping[str, Any]) -> Any:
    """A hand-built input dict for a generated method (whose parameter is the operation's TypedDict)."""
    return cast(Any, d)


def _split(opts: Mapping[str, Any]) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
    rest = dict(opts)
    return rest.pop("provider", None), rest.pop("connection_id", None), rest


class Entity:
    """One entity with typed input and output. Wraps the unified record routes with provider resolution and
    datetime handling."""

    def __init__(self, cust: ProviderResolver, category: str, entity: str) -> None:
        self._cust = cust
        self.category = category
        self.entity = entity

    def _scope(self, op: str, opts: Mapping[str, Any]) -> Dict[str, Any]:
        """category/entity/provider/connection_id for one call, with the provider resolved (or taken from opts)."""
        provider, connection_id, _ = _split(opts)
        out: Dict[str, Any] = {"category": self.category, "entity": self.entity, "provider": provider or self._cust.provider_for(self.category, self.entity, op)}
        if connection_id:
            out["connection_id"] = connection_id
        return out

    def _run(self, op: str, opts: Mapping[str, Any], f: Callable[[Dict[str, Any], Dict[str, Any]], Any]) -> Dict[str, Any]:
        """Runs one call; a provider or connection error forgets the cached provider so the next call resolves again."""
        _, _, req_opts = _split(opts)
        try:
            out = f(self._scope(op, opts), req_opts)
            return out if isinstance(out, dict) else {"data": out}
        except FastnApiError as err:
            if _PROVIDER_ERROR.search(err.code or ""):
                self._cust.forget_provider(self.category, self.entity)
            raise

    def create(self, record: Mapping[str, Any], **opts: Unpack[DomainCallOptions]) -> UnifiedRecord:
        """Creates one record. Pass `idempotency_key=` so a retry cannot create it twice."""
        return self._run("create", opts, lambda s, o: self._cust.api.unified.create_unified_record(_in({**s, "record": wire_record(record)}), **o))

    def get(self, id: str, **opts: Unpack[DomainCallOptions]) -> UnifiedRecord:
        """One record by its provider id."""
        return self._run("get", opts, lambda s, o: self._cust.api.unified.get_unified_record(_in({**s, "id": _id_of(id)}), **o))

    def list(self, page_size: Optional[int] = None, cursor: Optional[str] = None, **opts: Unpack[DomainCallOptions]) -> UnifiedPage:
        """A page of records. Pass the page's `nextCursor` as `cursor` to read the next one while `hasMore` is true."""
        page = _page(page_size, cursor)
        return self._run("list", opts, lambda s, o: self._cust.api.unified.list_unified_records(_in({**s, **page}), **o))

    def find(self, filters: Mapping[str, Any], page_size: Optional[int] = None, **opts: Unpack[DomainCallOptions]) -> UnifiedPage:
        """Records matching the filters (the provider's own search). One page only: the search route has no cursor,
        so narrow the filters or raise `page_size` to see more; `list` pages with a cursor."""
        if "cursor" in opts:
            raise TypeError("find() has no cursor: the search route answers one page; narrow the filters, raise page_size, or page with list()")
        page = _page(page_size, None)
        return self._run("search", opts, lambda s, o: self._cust.api.unified.search_unified_records(_in({**s, **page, "filters": wire_record(filters)}), **o))

    def update(self, id: str, patch: Mapping[str, Any], **opts: Unpack[DomainCallOptions]) -> UnifiedRecord:
        """Changes the given fields and leaves the rest."""
        return self._run("update", opts, lambda s, o: self._cust.api.unified.update_unified_record(_in({**s, "id": _id_of(id), "record": wire_record(patch)}), **o))

    def delete(self, id: str, **opts: Unpack[DomainCallOptions]) -> UnifiedDeleted:
        """Deletes (or archives, where the provider only archives) one record."""
        return self._run("delete", opts, lambda s, o: self._cust.api.unified.delete_unified_record(_in({**s, "id": _id_of(id)}), **o))


def _page(page_size: Optional[int], cursor: Optional[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    if page_size is not None:
        out["page_size"] = page_size
    if cursor is not None:
        out["cursor"] = cursor
    return out


# ---------------------------------------------------------------------------------------------------------------
# Scheduling


class Calendar(Entity):
    """scheduling/meeting: free_slots, book, get, find, list, reschedule, cancel."""

    def __init__(self, cust: ProviderResolver) -> None:
        super().__init__(cust, "scheduling", "meeting")

    def free_slots(self, input: Mapping[str, Any], **opts: Unpack[DomainCallOptions]) -> Dict[str, Any]:
        """Busy and free time in a window (scheduling/availability), from the customer's connected calendar.

        `input`: start_time, end_time, timezone?, calendar_id?, event_type_id?, participants?, slot_minutes?. When
        `slot_minutes` is set, `slots` lists every free slot of that length inside the window, back to back.
        """
        record = {k: v for k, v in input.items() if k != "slot_minutes"}
        slot_minutes = input.get("slot_minutes")
        if slot_minutes is not None:
            _check_minutes(slot_minutes, "free_slots: slot_minutes")
        availability = Entity(self._cust, "scheduling", "availability")
        r = availability.create(record, **opts)
        data: Dict[str, Any] = r["data"] if isinstance(r.get("data"), dict) else {}
        start = data.get("start_time") if data.get("start_time") is not None else to_iso(input.get("start_time"))
        end = data.get("end_time") if data.get("end_time") is not None else to_iso(input.get("end_time"))
        busy: List[Interval] = []
        if isinstance(data.get("busy"), list):
            for b in data["busy"]:
                if isinstance(b, dict):
                    busy.append({"start_time": cast(str, b.get("start_time", b.get("start"))), "end_time": cast(str, b.get("end_time", b.get("end")))})
        free = free_intervals(str(start or ""), str(end or ""), busy)
        out: Dict[str, Any] = {"start_time": start, "end_time": end, "busy": busy, "free": free}
        if slot_minutes is not None:
            out["slots"] = slots_of(free, slot_minutes)
        out["provider"] = r.get("provider")
        if r.get("warnings") is not None:
            out["warnings"] = r["warnings"]
        return out

    def book(self, meeting: Mapping[str, Any], **opts: Unpack[DomainCallOptions]) -> UnifiedRecord:
        """Books a meeting. Pass `idempotency_key=` (e.g. your call id) so a retry cannot book it twice."""
        return self.create(meeting, **opts)

    def reschedule(self, id: str, to: Mapping[str, Any], **opts: Unpack[DomainCallOptions]) -> UnifiedRecord:
        """Moves a meeting: `to` = {"start_time", "end_time"?, "duration_minutes"?}."""
        return self.update(id, to, **opts)

    def cancel(self, id: str, **opts: Unpack[DomainCallOptions]) -> UnifiedDeleted:
        """Cancels (deletes) a meeting."""
        return self.delete(id, **opts)


# ---------------------------------------------------------------------------------------------------------------
# CRM


class Notes(Entity):
    """crm/note: add, update, delete. `created_at` defaults to now (HubSpot requires it)."""

    def __init__(self, cust: ProviderResolver) -> None:
        super().__init__(cust, "crm", "note")

    def add(self, note: Mapping[str, Any], **opts: Unpack[DomainCallOptions]) -> UnifiedRecord:
        """Adds a note to a contact or deal: {"body", "parent_id", "parent_type"?, "title"?, "created_at"?}."""
        return self.create(note, **opts)

    def create(self, record: Mapping[str, Any], **opts: Unpack[DomainCallOptions]) -> UnifiedRecord:
        created_at = record.get("created_at")
        return super().create({**record, "created_at": created_at if created_at is not None else datetime.now(timezone.utc)}, **opts)


class Tasks(Entity):
    """crm/task: add, get, list, update, delete."""

    def __init__(self, cust: ProviderResolver) -> None:
        super().__init__(cust, "crm", "task")

    def add(self, task: Mapping[str, Any], **opts: Unpack[DomainCallOptions]) -> UnifiedRecord:
        """Adds a task. Same as create()."""
        return self.create(task, **opts)


class Deals(Entity):
    """crm/opportunity: create, get, list, update, move_stage, delete; stages() lists crm/stage."""

    def __init__(self, cust: ProviderResolver) -> None:
        super().__init__(cust, "crm", "opportunity")
        self._stages = Entity(cust, "crm", "stage")

    def move_stage(self, id: str, stage: str, **opts: Unpack[DomainCallOptions]) -> UnifiedRecord:
        """Moves a deal to a stage (an id from stages())."""
        return self.update(id, {"stage": stage}, **opts)

    def stages(self, page_size: Optional[int] = None, cursor: Optional[str] = None, **opts: Unpack[DomainCallOptions]) -> UnifiedPage:
        """The pipeline stages the customer's CRM has; `records[].id` is what move_stage takes."""
        return self._stages.list(page_size, cursor, **opts)


class Crm:
    """The customer's CRM: contacts (crm/contact), notes, tasks, deals."""

    def __init__(self, cust: ProviderResolver) -> None:
        self.contacts = Entity(cust, "crm", "contact")
        self.notes = Notes(cust)
        self.tasks = Tasks(cust)
        self.deals = Deals(cust)
