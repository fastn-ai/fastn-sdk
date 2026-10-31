"""Named apps, categories, entities and HubSpot events: same values as the Node SDK, same wire format as strings."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import httpx
import pytest

from fastn.platform import (
    EVENT_ALIASES,
    Apps,
    Categories,
    CustomerStatus,
    Entities,
    EventOutcomes,
    EventTypes,
    FastnClient,
    HubSpotEvents,
    OrgTypes,
    Plans,
    UnifiedActions,
    parse_event,
    sign_event_body,
)

from .conftest import Mock, Reply

NODE_NAMES = Path(__file__).resolve().parents[3] / "node" / "src" / "names.ts"


def _node_block(name: str) -> dict[str, str]:
    src = NODE_NAMES.read_text()
    block = src[src.index(f"export const {name} = {{"):]
    block = block[: block.index("} as const;")]
    return dict(re.findall(r'(\w+): "([^"]+)"', block))


def _py(cls: type) -> dict[str, str]:
    return {k: v for k, v in vars(cls).items() if not k.startswith("_") and isinstance(v, str)}


def test_every_name_is_the_exact_string_the_api_takes() -> None:
    assert Apps.googleCalendar == "googleCalendar" and Apps.hubspot == "hubspot"
    assert Categories.knowledgeBase == "knowledge_base" and Entities.engagementType == "engagement_type"
    assert all(k == v for k, v in _py(Apps).items())


def test_the_names_are_the_same_as_in_the_node_sdk() -> None:
    for name, cls in (("Apps", Apps), ("Categories", Categories), ("Entities", Entities), ("HubSpotEvents", HubSpotEvents), ("EventTypes", EventTypes), ("UnifiedActions", UnifiedActions), ("Plans", Plans), ("CustomerStatus", CustomerStatus), ("OrgTypes", OrgTypes), ("EventOutcomes", EventOutcomes)):
        assert _py(cls) == _node_block(name), name


def test_hubspot_events_are_exactly_the_plain_names_the_sdk_maps() -> None:
    assert set(_py(HubSpotEvents).values()) == set(EVENT_ALIASES["hubspot"])


def test_catalog_fields_with_names_is_the_same_call_as_with_strings(mock: Callable[..., Mock]) -> None:
    entity = {"slug": "contact", "operations": [], "createFields": [{"field": "email", "label": "Email", "type": "string", "required": False}]}

    def handler(url: str, req: httpx.Request) -> Reply:
        return {"body": {"data": [{"slug": "crm", "entities": [entity]}]}} if "/unified/categories" in url else {"status": 404, "body": {}}

    mock(handler)
    fastn = FastnClient(api_key="k", retries=0)
    assert fastn.catalog.fields(Categories.crm, Entities.contact) == fastn.catalog.fields("crm", "contact")


def test_a_missing_or_empty_name_throws_a_clear_type_error_before_any_request(mock: Callable[..., Mock]) -> None:
    m = mock(lambda url, req: {"body": {"data": []}})
    c = FastnClient(api_key="k", retries=0).customer("acme-1")
    with pytest.raises(TypeError, match=r"connect\(app\): got None"):
        c.connect(None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match=r"watch\(app, events\): got an empty string"):
        c.watch("", ["contact.created"])
    with pytest.raises(TypeError, match="got an empty string"):
        c.unwatch("")  # never "every app"
    with pytest.raises(TypeError):
        c.watchable_events(None)  # type: ignore[arg-type]
    assert len(m.calls) == 0


def test_a_parsed_event_compares_equal_to_the_named_values() -> None:
    body = '{"id": "evt_1", "type": "setup_link.completed", "app": "googleCalendar", "tenantRef": "acme-1"}'
    import time

    ts = int(time.time())
    ev = parse_event("whsec_t", {"x-fastn-timestamp": str(ts), "x-fastn-signature": sign_event_body("whsec_t", ts, body)}, body)
    assert ev["type"] == EventTypes.setupLinkCompleted and ev["app"] == Apps.googleCalendar
