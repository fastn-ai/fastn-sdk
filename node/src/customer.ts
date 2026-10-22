import type { FastnApis } from "./generated/api.js";
import type * as T from "./generated/types.js";
import type { RequestOptions, Transport, OpDef } from "./transport.js";
import type { ToolsClient } from "./tools.js";
import { buildApis } from "./generated/api.js";
import { FastnApiError } from "./errors.js";

/** A unified record call scoped to one customer; `category`/`entity`/`provider` come from the catalog. */
export interface RecordScope { category: string; entity: string; provider?: string; connectionId?: string }

/**
 * Everything about one of your customers, addressed by the id YOU gave fastn (the `orgId` of createTenant,
 * also called externalRef / endOrgRef). fastn's own org id is resolved and cached when a call needs it.
 */
export class Customer {
  /** Every API area, with x-end-org-ref already set on each call. */
  readonly api: FastnApis;
  private fastnId: string | undefined;

  constructor(private readonly root: FastnApis, private readonly t: Transport, readonly ref: string, private readonly toolsClient?: ToolsClient) {
    const scoped: Transport = { call: (op: OpDef, input: Record<string, unknown>, opts?: RequestOptions) => t.call(op, input, { customer: { ref }, ...opts }) };
    this.api = buildApis(scoped);
  }

  /** This customer's workspace tools (every connector turned on in fastn Connect), with X-Org-Id = ref on each call. */
  get tools(): ToolsClient {
    if (!this.toolsClient) throw new TypeError("customer(ref).tools: create the FastnClient with tools: { key, url } first");
    return this.toolsClient.customer(this.ref);
  }

  /** fastn's id of this customer org (the `id` createTenant returned). Cached after the first lookup. */
  async id(): Promise<string> {
    if (this.fastnId) return this.fastnId;
    const found = await this.find();
    if (!found) throw new FastnApiError(`customer "${this.ref}" is not registered; call customer.register({ name }) first`, 404, "NOT_FOUND", undefined, "GET", "/v1/orgs", undefined, undefined);
    return (this.fastnId = found.id);
  }

  /** The customer org row, or undefined when this ref is unknown to fastn. */
  async find(): Promise<(T.JsonObject & { id: string; externalRef?: string }) | undefined> {
    const res = await this.root.orgs.listOrgs({ type: "end_org" });
    const rows: any[] = Array.isArray(res?.data) ? res.data : [];
    const row = rows.find((r) => r.externalRef === this.ref || r.orgId === this.ref || r.external_ref === this.ref);
    if (row) this.fastnId = row.id;
    return row;
  }

  /**
   * Creates the customer org under your account (idempotent: returns the existing org when the ref is known).
   * `input.name` is the display name; the ref becomes its orgId/externalRef.
   */
  async register(input: Omit<T.CreateTenantInput, "orgId" | "external_ref" | "externalRef">, opts?: RequestOptions): Promise<T.JsonObject> {
    const existing = await this.find();
    if (existing) return { data: existing, existed: true };
    try {
      // plan defaults to "free": the API rejects a paid default plan for anyone but a platform admin.
      const res = await this.root.orgs.createTenant({ plan: "free", ...input, orgId: this.ref }, opts);
      const id = res?.data?.id ?? res?.id;
      if (typeof id === "string") this.fastnId = id;
      return res;
    } catch (err) {
      if (err instanceof FastnApiError && err.isConflict) { const row = await this.find(); if (row) return { data: row, existed: true }; }
      throw err;
    }
  }

  /**
   * Suspends and then deletes the customer org (the API refuses to delete an active org). Connections and data go
   * with it; there is no undo.
   */
  async remove(opts?: RequestOptions): Promise<void> {
    const id = await this.id();
    await this.root.orgs.updateTenant({ id, status: "suspended" } as any, opts);
    await this.root.orgs.deleteTenant({ id }, opts);
    this.fastnId = undefined;
  }

  /** The customer org (getTenant by fastn id). */
  async get(opts?: RequestOptions): Promise<T.GetTenantOutput> { return this.root.orgs.getTenant({ id: await this.id() }, opts); }

  /** Connections this customer has made (listConnections filtered to the customer org). */
  async connections(input: Omit<T.ListConnectionsInput, "endOrgId"> = {}, opts?: RequestOptions): Promise<T.ListConnectionsOutput> {
    return this.root.connections.listConnections({ ...input, endOrgId: await this.id() }, opts);
  }

  /**
   * A setup link the customer opens to connect their tools. The org is created on the fly when it does not exist
   * yet (createIfMissing), so this works before register().
   */
  setupLink(input: Omit<T.CreateSetupLinkInput, "externalRef" | "endOrgId" | "useCallerOrg">, opts?: RequestOptions): Promise<T.CreateSetupLinkOutput> {
    return this.root.embed.createSetupLink({ createIfMissing: true, ...input, externalRef: this.ref }, opts);
  }

  /** A short-lived token for the embedded widget, scoped to this customer (endOrgId = your ref). */
  embedToken(input: Omit<T.CreateEmbedTokenInput, "endOrgId"> = {}, opts?: RequestOptions): Promise<T.CreateEmbedTokenOutput> {
    return this.root.embed.createEmbedToken({ createIfMissing: true, ...input, endOrgId: this.ref }, opts);
  }

  /**
   * Unified records for this customer: `customer.records({ category: "crm", entity: "contact" }).create({...})`.
   * Same names as the catalog; every call carries x-end-org-ref and the given provider.
   */
  records(scope: RecordScope) { return new Records(this.api, scope); }
}

export class Records {
  constructor(private readonly api: FastnApis, readonly scope: RecordScope) {}
  private base(): Record<string, string> {
    const { category, entity, provider, connectionId } = this.scope;
    return { category, entity, ...(provider ? { provider } : {}), ...(connectionId ? { connection_id: connectionId } : {}) };
  }
  /** POST a canonical record. Pass `opts.idempotencyKey` so a retry cannot create it twice. */
  create(record: Record<string, any>, opts?: RequestOptions) { return this.api.unified.createUnifiedRecord({ ...this.base(), record } as any, opts); }
  get(id: string, opts?: RequestOptions) { return this.api.unified.getUnifiedRecord({ ...this.base(), id } as any, opts); }
  list(input: Record<string, any> = {}, opts?: RequestOptions) { return this.api.unified.listUnifiedRecords({ ...this.base(), ...input } as any, opts); }
  search(filters: Record<string, any>, opts?: RequestOptions) { return this.api.unified.searchUnifiedRecords({ ...this.base(), filters } as any, opts); }
  update(id: string, record: Record<string, any>, opts?: RequestOptions) { return this.api.unified.updateUnifiedRecord({ ...this.base(), id, record } as any, opts); }
  delete(id: string, opts?: RequestOptions) { return this.api.unified.deleteUnifiedRecord({ ...this.base(), id } as any, opts); }
  /** Which providers are mapped for this entity and whether the customer has connected them. */
  providers(opts?: RequestOptions) { return this.api.unified.listUnifiedEntityProviders({ category: this.scope.category, entity: this.scope.entity } as any, opts); }
}
