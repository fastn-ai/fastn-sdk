"""fastn.platform: the fastn platform REST API for Python, generated from fastn's OpenAPI spec, plus a small
hand-written layer that makes the common partner flow easy. The same surface as the Node SDK (@fastn-ai/sdk).

    from fastn.platform import FastnClient

    fastn = FastnClient(api_key=os.environ["FASTN_API_KEY"])
    customer = fastn.customer("acme-42")
    customer.register({"name": "Acme Dental"})
    link = customer.connect("googleCalendar")                 # link["url"]: send the customer here
    booked = customer.calendar.book({...}, idempotency_key="booking-123")
    page = customer.crm.contacts.find({"email": "jane@example.com"})
"""

from ._generated.ops import SPEC_FILE, SPEC_VERSION
from ._transport import RequestLog
from ._version import VERSION
from .catalog import Catalog
from .client import DEFAULT_BASE_URL, FastnClient, Webhooks
from .customer import EVENT_ALIASES, PROVIDER_TTL_SECONDS, WIDGET_TTL_SECONDS, Customer, Records
from .domain import Calendar, Crm, Deals, Entity, Notes, Tasks, free_intervals, slots_of
from .errors import FastnApiError, FastnNetworkError
from .events import parse_event, read_event_headers, sign_event_body, verify_event_signature
from .names import Apps, Categories, Entities, HubSpotEvents
from .paginate import paginate

__all__ = [
    "Apps",
    "Categories",
    "Entities",
    "HubSpotEvents",
    "DEFAULT_BASE_URL",
    "EVENT_ALIASES",
    "PROVIDER_TTL_SECONDS",
    "SPEC_FILE",
    "SPEC_VERSION",
    "VERSION",
    "WIDGET_TTL_SECONDS",
    "Calendar",
    "Catalog",
    "Crm",
    "Customer",
    "Deals",
    "Entity",
    "FastnApiError",
    "FastnClient",
    "FastnNetworkError",
    "Notes",
    "Records",
    "RequestLog",
    "Tasks",
    "Webhooks",
    "free_intervals",
    "paginate",
    "parse_event",
    "read_event_headers",
    "sign_event_body",
    "slots_of",
    "verify_event_signature",
]
