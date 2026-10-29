# ruff: noqa: UP006, UP007, UP035, UP045  (Python 3.8 typing on purpose)
"""The unified catalog: which categories and entities exist, the fields each entity takes, and which providers a
customer has connected for it. `fastn.catalog` answers for the account; `customer.catalog` answers for one customer
(providers reflect that customer's own connections). A port of node/src/catalog.ts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from .errors import FastnApiError

if TYPE_CHECKING:
    from typing_extensions import Unpack

    from ._generated.api import FastnApis
    from ._transport import RequestOptions

#: One operation a unified entity supports: "create" | "get" | "list" | "search" | "update" | "delete".
UnifiedOperation = str
#: One field an entity takes on create: {"field": "first_name", "type": "string", "required": False, ...}.
CatalogField = Dict[str, Any]
#: One entity of a category: {"id", "slug", "name", "connectorSlugs", "operations", "createFields", ...}.
CatalogEntity = Dict[str, Any]
#: One category with its entities: {"id", "slug", "name", "entities", ...}.
CatalogCategory = Dict[str, Any]
#: One provider mapped for an entity: {"connectorSlug", "connectorName", "operations", "connected", ...}.
EntityProvider = Dict[str, Any]


def _not_found(what: str, path: str) -> FastnApiError:
    return FastnApiError(f"{what} is not in the unified catalog", status=404, code="NOT_FOUND", method="GET", path=path)


def rows_of(r: Any) -> List[Any]:
    """The list out of an answer: `data` when it is a list, the answer itself when it is one, else nothing."""
    if isinstance(r, dict) and isinstance(r.get("data"), list):
        return list(r["data"])
    if isinstance(r, list):
        return list(r)
    return []


class Catalog:
    def __init__(self, api: FastnApis) -> None:
        self._api = api
        self._cache: Optional[List[CatalogCategory]] = None

    def categories(self, **opts: Unpack[RequestOptions]) -> List[CatalogCategory]:
        """Every category with its entities and fields (GET /v1/unified/categories). Cached for the life of the client."""
        if self._cache is None:
            self._cache = rows_of(self._api.unified.list_unified_categories(cast(Any, {}), **opts))
        return self._cache

    def category(self, slug: str, **opts: Unpack[RequestOptions]) -> CatalogCategory:
        """One category by slug, e.g. "crm". Raises NOT_FOUND when there is none."""
        for c in self.categories(**opts):
            if isinstance(c, dict) and c.get("slug") == slug:
                return c
        raise _not_found(f'category "{slug}"', "/v1/unified/categories")

    def entity(self, category: str, entity: str, **opts: Unpack[RequestOptions]) -> CatalogEntity:
        """One entity, e.g. ("crm", "contact"): its operations, providers and create fields."""
        for e in self.category(category, **opts).get("entities") or []:
            if isinstance(e, dict) and e.get("slug") == entity:
                return e
        raise _not_found(f'entity "{category}/{entity}"', "/v1/unified/categories")

    def fields(self, category: str, entity: str, **opts: Unpack[RequestOptions]) -> List[CatalogField]:
        """The fields an entity takes on create, with `required` flags."""
        return list(self.entity(category, entity, **opts).get("createFields") or [])

    def providers(self, category: str, entity: str, **opts: Unpack[RequestOptions]) -> List[EntityProvider]:
        """The providers mapped for an entity and, for the org this catalog belongs to, which are connected
        (GET /v1/unified/{category}/{entity}/providers). Through `customer.catalog` the `connected` flags are the
        customer's own."""
        return rows_of(self._api.unified.list_unified_entity_providers(cast(Any, {"category": category, "entity": entity}), **opts))

    def refresh(self) -> None:
        """Forgets the cached categories, so the next call reads the catalog again."""
        self._cache = None
