// @fastn-ai/sdk - the fastn platform REST API for Node (generated from fastn's OpenAPI spec) plus workspace tool calls (see ./tools).
//
//   import { FastnClient } from "@fastn-ai/sdk";
//   const fastn = new FastnClient({ apiKey: process.env.FASTN_API_KEY! });
//   const orgs = await fastn.orgs.listOrgs({ type: "end_org" });
//
//   const customer = fastn.customer("acme-42");                  // the id YOU use for this customer
//   await customer.register({ name: "Acme Dental" });
//   const link = await customer.setupLink({ widgetId, connectionName: "Google Calendar" });
//   const meetings = customer.records({ category: "scheduling", entity: "meeting", provider: "googleCalendar" });
//   await meetings.create({ title: "Intro call", start_time: "...", end_time: "..." }, { idempotencyKey: "booking-123" });

import { buildApis, type FastnApis } from "./generated/api.js";
import { FetchTransport, type RequestOptions, type RequestLog, type Transport } from "./transport.js";
import { Customer } from "./customer.js";
import { SPEC_VERSION, SPEC_FILE, OPS } from "./generated/ops.js";
import { ToolsClient, type ToolsClientConfig } from "./tools.js";
import { VERSION } from "./version.js";

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
  /** A fetch implementation, default globalThis.fetch (Node 18+). */
  fetch?: typeof fetch;
  userAgent?: string;
  /** Your fastn Connect workspace (connect.fastn.dev): its key and endpoint. Enables fastn.tools and customer(ref).tools. */
  tools?: Pick<ToolsClientConfig, "key" | "url" | "timeoutMs">;
}

export const DEFAULT_BASE_URL = "https://api.fastn.dev";
export { VERSION };

export class FastnClient {
  readonly transport: Transport;
  readonly baseUrl: string;
  /** All API areas, keyed by OpenAPI tag: orgs, embed, connections, unified, events, workflows, ... */
  readonly api: FastnApis;
  /** The workspace's tools (every connector turned on there), when `tools` was configured. */
  readonly tools?: ToolsClient;

  constructor(cfg: FastnClientConfig) {
    if (!cfg?.apiKey || typeof cfg.apiKey !== "string") throw new TypeError("FastnClient: apiKey is required");
    this.baseUrl = (cfg.baseUrl ?? DEFAULT_BASE_URL).replace(/\/+$/, "");
    this.transport = new FetchTransport({
      apiKey: cfg.apiKey, baseUrl: this.baseUrl, timeoutMs: cfg.timeoutMs ?? 60_000, retries: cfg.retries ?? 2,
      fetch: cfg.fetch, onRequest: cfg.onRequest, defaultOptions: cfg.defaults, userAgent: cfg.userAgent ?? `fastn-ai-sdk/${VERSION} node/${typeof process !== "undefined" ? process.versions?.node ?? "" : ""}`,
    });
    this.api = buildApis(this.transport);
    Object.assign(this, this.api);
    if (cfg.tools) this.tools = new ToolsClient({ ...cfg.tools, fetch: cfg.fetch, userAgent: cfg.userAgent });
  }

  /** One of your customers, by the id you use for them. */
  customer(ref: string): Customer {
    if (!ref) throw new TypeError("customer(ref): ref is required");
    return new Customer(this.api, this.transport, ref, this.tools);
  }

  /** Calls any operation by its operationId, e.g. fastn.call("listOrgs", { type: "end_org" }). */
  call<K extends keyof typeof OPS>(operationId: K, input: Record<string, unknown> = {}, opts?: RequestOptions): Promise<any> {
    const op = OPS[operationId];
    if (!op) throw new TypeError(`unknown operation "${String(operationId)}"`);
    return this.transport.call(op, input, opts);
  }

  /** The OpenAPI version this SDK was generated from. */
  static readonly specVersion = SPEC_VERSION;
  static readonly specFile = SPEC_FILE;
}
// Every API area is also reachable directly: fastn.orgs.listOrgs(...) === fastn.api.orgs.listOrgs(...)
export interface FastnClient extends FastnApis {}

export { Customer, Records, type RecordScope } from "./customer.js";
export { FastnApiError, FastnNetworkError } from "./errors.js";
export { verifyEventSignature, signEventBody, parseEvent, readEventHeaders, type EventHeaders, type FastnEvent, type VerifyOptions } from "./events.js";
export { paginate, type PaginateOptions } from "./paginate.js";
export { ToolsClient, ToolError, parseMessages, type ToolsClientConfig, type ToolCallOptions, type Tool, type ToolResult } from "./tools.js";
export { FetchTransport, type Transport, type RequestOptions, type RequestLog, type OpDef, type FetchTransportConfig } from "./transport.js";
export { OPS, SPEC_VERSION, type OperationId } from "./generated/ops.js";
export type { FastnApis } from "./generated/api.js";
export type * from "./generated/types.js";
