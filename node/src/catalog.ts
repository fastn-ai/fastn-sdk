// The unified catalog: which categories and entities exist, the fields each entity takes, and which providers a
// customer has connected for it. `fastn.catalog` answers for the account; `customer.catalog` answers for one customer
// (providers reflect that customer's own connections).
import type { FastnApis } from "./generated/api.js";
import type { RequestOptions } from "./transport.js";
import { FastnApiError } from "./errors.js";

/** One operation a unified entity supports. */
export type UnifiedOperation = "create" | "get" | "list" | "search" | "update" | "delete";

/** One field an entity takes on create (the names are the ones the typed methods and `records()` send). */
export interface CatalogField {
  /** Wire name, e.g. first_name. */
  field: string;
  label?: string;
  /** string, number, boolean, date (ISO 8601 string), array or object. */
  type: string;
  required?: boolean;
  description?: string;
  /** Allowed values, when the field is an enum. */
  options?: Array<string | number | { value: string | number; label?: string }>;
  [key: string]: unknown;
}

/** One entity of a category, e.g. crm/contact. */
export interface CatalogEntity {
  id: string;
  slug: string;
  name: string;
  description?: string;
  /** Every provider mapped for this entity on the platform (connected or not). */
  connectorSlugs: string[];
  /** Operations at least one provider supports. Per-provider operations come from providers(). */
  operations: UnifiedOperation[];
  createFields: CatalogField[];
  [key: string]: unknown;
}

/** One category, e.g. crm or scheduling, with its entities. */
export interface CatalogCategory {
  id: string;
  slug: string;
  name: string;
  description?: string;
  entities: CatalogEntity[];
  [key: string]: unknown;
}

/** One provider mapped for an entity, and whether the calling org (or customer) has connected it. */
export interface EntityProvider {
  connectorSlug: string;
  connectorName: string;
  operations: UnifiedOperation[];
  connected: boolean;
  verifyStatus?: string | null;
  healthy?: boolean | null;
  connectionCount?: number;
  [key: string]: unknown;
}

const notFound = (what: string, path: string) => new FastnApiError(`${what} is not in the unified catalog`, { status: 404, code: "NOT_FOUND", method: "GET", path });

export class Catalog {
  private cache?: Promise<CatalogCategory[]>;
  constructor(private readonly api: FastnApis) {}

  /** Every category with its entities and fields (GET /v1/unified/categories). Cached for the life of the client. */
  categories(opts?: RequestOptions): Promise<CatalogCategory[]> {
    this.cache ??= this.api.unified.listUnifiedCategories({}, opts).then(
      (r: any) => (Array.isArray(r?.data) ? r.data : Array.isArray(r) ? r : []) as CatalogCategory[],
      (e) => { this.cache = undefined; throw e; },
    );
    return this.cache;
  }

  /** One category by slug, e.g. "crm". Throws NOT_FOUND when there is none. */
  async category(slug: string, opts?: RequestOptions): Promise<CatalogCategory> {
    const c = (await this.categories(opts)).find((x) => x.slug === slug);
    if (!c) throw notFound(`category "${slug}"`, "/v1/unified/categories");
    return c;
  }

  /** One entity, e.g. ("crm", "contact"): its operations, providers and create fields. */
  async entity(category: string, entity: string, opts?: RequestOptions): Promise<CatalogEntity> {
    const e = (await this.category(category, opts)).entities?.find((x) => x.slug === entity);
    if (!e) throw notFound(`entity "${category}/${entity}"`, "/v1/unified/categories");
    return e;
  }

  /** The fields an entity takes on create, with `required` flags. */
  async fields(category: string, entity: string, opts?: RequestOptions): Promise<CatalogField[]> {
    return (await this.entity(category, entity, opts)).createFields ?? [];
  }

  /**
   * The providers mapped for an entity and, for the org this catalog belongs to, which are connected
   * (GET /v1/unified/{category}/{entity}/providers). Through `customer.catalog` the `connected` flags are the
   * customer's own.
   */
  async providers(category: string, entity: string, opts?: RequestOptions): Promise<EntityProvider[]> {
    const r: any = await this.api.unified.listUnifiedEntityProviders({ category, entity }, opts);
    return (Array.isArray(r?.data) ? r.data : Array.isArray(r) ? r : []) as EntityProvider[];
  }

  /** Forgets the cached categories, so the next call reads the catalog again. */
  refresh(): void { this.cache = undefined; }
}
