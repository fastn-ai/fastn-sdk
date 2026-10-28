// @fastn-ai/sdk - the fastn platform REST API for Node (generated from fastn's OpenAPI spec) plus workspace tool calls (see ./tools).
//
//   import { FastnClient } from "@fastn-ai/sdk";
//   const fastn = new FastnClient({ apiKey: process.env.FASTN_API_KEY! });
//   const orgs = await fastn.orgs.listOrgs({ type: "end_org" });
//
//   const customer = fastn.customer("acme-42");                  // the id YOU use for this customer
//   await customer.register({ name: "Acme Dental" });
//   const link = await customer.connect("googleCalendar");                          // { url } to send the customer to
//   await customer.calendar.book({ title: "Intro call", start_time: "...", end_time: "..." }, { idempotencyKey: "booking-123" });
//   const { records } = await customer.crm.contacts.find({ email: "jane@example.com" });

import { buildApis, type FastnApis } from "./generated/api.js";
import { FetchTransport, type RequestOptions, type RequestLog, type Transport } from "./transport.js";
import { Customer, type CustomerContext } from "./customer.js";
import { Catalog } from "./catalog.js";
import { OPS } from "./generated/ops.js";
import { ToolsClient, type ToolsClientConfig } from "./tools.js";
import { VERSION } from "./version.js";
import { defaultUserAgent } from "./http.js";

export interface FastnClientConfig {
  /** Your fastn API key (Settings > API keys). Sent as x-api-key. */
  apiKey: string;
  /** Default https://api.fastn.dev. Use https://api.fastn-test.dev for the development environment. */
  baseUrl?: string;
  /** Per-request timeout, default 60000. */
  timeoutMs?: number;
  /** Retries for GET and idempotent calls on 429/502/503/504 and network errors, default 2. */
  retries?: number;
  /** Options applied to every call (e.g. { customer: { ref: "acme-42" } } to scope a whole client to one customer). */
  defaults?: RequestOptions;
  /** Called after every HTTP attempt, for your logs. */
  onRequest?: (info: RequestLog) => void;
  /** A fetch implementation, default globalThis.fetch (Node 20+). */
  fetch?: typeof fetch;
  userAgent?: string;
  /** Your fastn Connect workspace (connect.fastn.dev): its key and endpoint. Enables fastn.tools and customer(ref).tools. */
  tools?: Pick<ToolsClientConfig, "key" | "url" | "timeoutMs">;
}

export const DEFAULT_BASE_URL = "https://api.fastn.dev";
const dataOf = (r: any): any => (r && typeof r === "object" && "data" in r ? r.data : r);
export { VERSION };

export class FastnClient {
  readonly transport: Transport;
  readonly baseUrl: string;
  /** All API areas, keyed by OpenAPI tag: orgs, embed, connections, unified, events, workflows, ... */
  readonly api: FastnApis;
  /** The workspace's tools (every connector turned on there), when `tools` was configured. */
  readonly tools?: ToolsClient;
  private readonly customers: CustomerContext;
  private meCache: Promise<any> | undefined;
  private catalogCache: Catalog | undefined;

  constructor(cfg: FastnClientConfig) {
    if (!cfg?.apiKey || typeof cfg.apiKey !== "string") throw new TypeError("FastnClient: apiKey is required");
    this.baseUrl = (cfg.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.transport = new FetchTransport({
      apiKey: cfg.apiKey, baseUrl: this.baseUrl, timeoutMs: cfg.timeoutMs ?? 60_000, retries: cfg.retries ?? 2,
      fetch: cfg.fetch, onRequest: cfg.onRequest, defaultOptions: cfg.defaults, userAgent: cfg.userAgent ?? defaultUserAgent(),
    });
    this.api = buildApis(this.transport);
    Object.assign(this, this.api);
    if (cfg.tools) this.tools = new ToolsClient({ ...cfg.tools, fetch: cfg.fetch, userAgent: cfg.userAgent });
    this.customers = { ids: new Map(), lookups: new Map(), providers: new Map(), callerOrgId: async () => { const me = await this.me(); const id = me?.org?.id; if (typeof id !== "string" || !id) throw new TypeError("whoami did not answer the caller's org id"); return id; } };
  }

  /** Who this API key is (GET /v1/me): actor, role, org, parentOrg. Cached for the life of the client. */
  me(): Promise<NonNullable<import("./generated/types.js").WhoamiOutput["data"]>> {
    this.meCache ??= this.api.users.whoami().then((r: any) => r?.data ?? r, (e) => { this.meCache = undefined; throw e; });
    return this.meCache;
  }

  /** The unified catalog: fastn.catalog.categories(), .entity("crm", "contact"), .fields(...), .providers(...). */
  get catalog(): Catalog { return (this.catalogCache ??= new Catalog(this.api)); }

  /** Your webhook: fastn.webhooks.create({ url, eventTypes }), list(), get(id), update(id, {...}), delete(id), test(id), rotateSecret(id), deliveries(id), replay(deliveryId). */
  readonly webhooks = {
    create: (input: import("./generated/types.js").CreateEventSubscriptionInput, opts?: RequestOptions) => this.api.events.createEventSubscription(input, opts).then(dataOf),
    list: (opts?: RequestOptions) => this.api.events.listEventSubscriptions({} as any, opts).then((r: any) => (Array.isArray(r?.data) ? r.data : []) as any[]),
    get: (id: string, opts?: RequestOptions) => this.api.events.getEventSubscription({ id }, opts).then(dataOf),
    update: (id: string, changes: Omit<import("./generated/types.js").UpdateEventSubscriptionInput, "id">, opts?: RequestOptions) => this.api.events.updateEventSubscription({ id, ...changes } as any, opts).then(dataOf),
    delete: (id: string, opts?: RequestOptions) => this.api.events.deleteEventSubscription({ id }, opts).then(dataOf),
    /** Sends an endpoint.test event now. */
    test: (id: string, opts?: RequestOptions) => this.api.events.testEventSubscription({ id }, opts).then(dataOf),
    /** A new signing secret; deliveries are signed with it from now on. */
    rotateSecret: (id: string, opts?: RequestOptions) => this.api.events.rotateEventSubscriptionSecret({ id }, opts).then(dataOf),
    /** Deliveries of one webhook, newest first (the route pages by `limit` only). */
    deliveries: (id: string, input: { limit?: number; status?: "pending" | "delivered" | "dead" } = {}, opts?: RequestOptions) => this.api.events.listEventDeliveries({ id, ...input } as any, opts).then((r: any) => (Array.isArray(r?.data) ? r.data : []) as any[]),
    replay: (deliveryId: string, opts?: RequestOptions) => this.api.events.replayEventDelivery({ id: deliveryId }, opts).then(dataOf),
  };

  /** One of your customers, by the id you use for them. */
  customer(ref: string): Customer {
    if (!ref) throw new TypeError("customer(ref): ref is required");
    return new Customer(this.api, this.transport, ref, this.customers, this.tools);
  }

  /** Calls any operation by its operationId, e.g. fastn.call("listOrgs", { type: "end_org" }). */
  call<K extends keyof typeof OPS>(operationId: K, input: Record<string, unknown> = {}, opts?: RequestOptions): Promise<any> {
    const op = OPS[operationId];
    if (!op) throw new TypeError(`unknown operation "${String(operationId)}"`);
    return this.transport.call(op, input, opts);
  }

}
// Every API area is also reachable directly: fastn.orgs.listOrgs(...) === fastn.api.orgs.listOrgs(...)
export interface FastnClient extends FastnApis {}

export { Customer, Records, PROVIDER_TTL_MS, WIDGET_TTL_MS, EVENT_ALIASES, type RecordScope, type CustomerRow, type ConnectOptions, type SetupLink, type WatchOptions, type Watch, type HubSpotEvent, type CallLogEntry } from "./customer.js";
export { Catalog, type CatalogCategory, type CatalogEntity, type CatalogField, type EntityProvider, type UnifiedOperation } from "./catalog.js";
export {
  Entity, Calendar, Crm, Notes, Tasks, Deals, freeIntervals, slotsOf,
  type DomainCallOptions, type DateInput, type UnifiedRecord, type UnifiedPage, type UnifiedDeleted, type PageInput, type FindInput, type ProviderResolver,
  type MeetingCreate, type Meeting, type MeetingFilters, type FreeSlotsInput, type FreeSlots, type Interval,
  type ContactCreate, type Contact, type ContactFilters, type NoteCreate, type Note, type TaskCreate, type Task, type DealCreate, type Deal, type Stage,
} from "./domain.js";
export { FastnApiError, FastnNetworkError, type FastnApiErrorInfo } from "./errors.js";
export { verifyEventSignature, signEventBody, parseEvent, readEventHeaders, type EventHeaders, type FastnEvent, type VerifyOptions } from "./events.js";
export { paginate, type PaginateOptions } from "./paginate.js";
export { ToolsClient, ToolError, parseMessages, type ToolsClientConfig, type ToolCallOptions, type Tool, type ToolResult } from "./tools.js";
export { type Transport, type RequestOptions, type RequestLog } from "./transport.js";
/** The OpenAPI version (and spec file) this SDK was generated from. */
export { SPEC_VERSION, SPEC_FILE, type OperationId } from "./generated/ops.js";
export type { FastnApis } from "./generated/api.js";
// One Input and one Output type per operation, named after the operationId, plus the spec's named schemas.
export type * from "./generated/types.js";
/**
 * Internals with no compatibility promise: the wire manifest (`OPS`), the fetch transport and their types. They can
 * change in any release. Use them for debugging or to build your own transport, not in application code.
 */
export * as unstable from "./unstable.js";
