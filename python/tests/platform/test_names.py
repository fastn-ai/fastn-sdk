"""Named apps, categories, entities and HubSpot events: same values as the Node SDK, same wire format as strings."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

import httpx

from fastn.platform import EVENT_ALIASES, Apps, Categories, Entities, FastnClient, HubSpotEvents

from .conftest import Mock, Reply

NODE_NAMES = Path(__file__).resolve().parents[3] / "node" / "src" / "names.ts"


def _node_block(name: str) -> dict[str, str]:
    src = NODE_NAMES.read_text()
    block = src[src.index(f"export const {name} = {{"):]
    block = block[: block.index("} as const;")]
    return dict(re.findall(r'^\s+(\w+): "([^"]+)",', block, re.M))


def _py(cls: type) -> dict[str, str]:
    return {k: v for k, v in vars(cls).items() if not k.startswith("_") and isinstance(v, str)}


def test_every_name_is_the_exact_string_the_api_takes() -> None:
    assert Apps.googleCalendar == "googleCalendar" and Apps.hubspot == "hubspot"
    assert Categories.knowledgeBase == "knowledge_base" and Entities.engagementType == "engagement_type"
    assert all(k == v for k, v in _py(Apps).items())


def test_the_names_are_the_same_as_in_the_node_sdk() -> None:
    for name, cls in (("Apps", Apps), ("Categories", Categories), ("Entities", Entities), ("HubSpotEvents", HubSpotEvents)):
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
