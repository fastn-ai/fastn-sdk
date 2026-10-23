import type { FastnApis } from "./generated/api.js";
import type * as T from "./generated/types.js";
import type { RequestOptions, Transport, OpDef } from "./transport.js";
import type { ToolsClient } from "./tools.js";
import { buildApis } from "./generated/api.js";
import { FastnApiError } from "./errors.js";

/** Shared between every Customer object of one client: the caller's org and the ref -> fastn id cache. */
export interface CustomerContext {
  /** fastn's id of the caller's own org (from whoami), resolved once per client. */
  callerOrgId(): Promise<string>;
  ids: Map<string, string>;
}

/** A unified record call scoped to one customer; `category`/`entity`/`provider` come from the catalog. */
export interface RecordScope { category: string; entity: string; provider?: string; connectionId?: string }

/**
 * Everything about one of your customers, addressed by the id YOU gave fastn (the `orgId` of createTenant,
 * also called externalRef / endOrgRef). fastn's own org id is resolved and cached when a call needs it.
 */
export class Customer {
  /**
   * Every API area, run for this customer. Each call carries x-end-org-ref, and where the route takes the customer
   * in the body instead (`externalRef` or `endOrgId`, e.g. initiateOauthConnection, storeConnections,
   * createEventSubscription, createSecret), that field is filled in too, because the platform reads the header only
   * on unified record and workflow execute routes. Pass the field yourself to override.
   */
  readonly api: FastnApis;

  constructor(private readonly root: FastnApis, private readonly t: Transport, readonly ref: string, private readonly ctx: CustomerContext, private readonly toolsClient?: ToolsClient) {
    const scoped: Transport = {
      call: async (op: OpDef, input: Record<string, unknown>, opts?: RequestOptions) => {
        const keys = op.body?.kind === "fields" ? op.body.keys ?? {} : {};
        let body = input;
        if ("externalRef" in keys && input.externalRef === undefined && input.endOrgId === undefined) body = { ...input, externalRef: ref };
        else if ("endOrgId" in keys && input.endOrgId === undefined) body = { ...input, endOrgId: await this.id() };
        return t.call(op, body, { customer: { ref }, ...opts });
      },
    };
    this.api = buildApis(scoped);
  }

  private get fastnId(): string | undefined { return this.ctx.ids.get(this.ref); }
  private set fastnId(v: string | undefined) { if (v) this.ctx.ids.set(this.ref, v); else this.ctx.ids.delete(this.ref); }

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

  /**
   * The customer org row, or undefined when this ref is unknown to fastn. Only orgs under the caller's own org are
   * considered (listOrgs with parent_id, and the row's parentId is checked), so a staff key that sees every org can
   * never resolve another partner's customer.
   */
  async find(): Promise<(T.JsonObject & { id: string; externalRef?: string }) | undefined> {
    const parent = await this.ctx.callerOrgId();
    const res = await this.root.orgs.listOrgs({ type: "end_org", parent_id: parent });
    const rows: any[] = Array.isArray(res?.data) ? res.data : [];
    const row = rows.find((r) => (r.externalRef === this.ref || r.orgId === this.ref || r.external_ref === this.ref) && (r.parentId ?? r.parent_id) === parent);   // fail closed: a row without a parent is not ours
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
   * with it; there is no undo. The org is looked up under the caller's own org only (see find()). If the delete
   * fails, the org is set back to active and the error says which state it is in.
   */
  async remove(opts?: RequestOptions): Promise<void> {
    const id = await this.id();
    await this.root.orgs.updateTenant({ id, status: "suspended" } as any, opts);
    try {
      await this.root.orgs.deleteTenant({ id }, opts);
    } catch (err) {
      let state = "active again";
      try { await this.root.orgs.updateTenant({ id, status: "active" } as any, opts); } catch { state = "still suspended"; }
      const e = err as Error;
      e.message = `${e.message} (customer "${this.ref}" was suspended before the delete; it is ${state})`;
      throw e;
    }
    this.fastnId = undefined;
  }

  /**
   * Starts an OAuth connection for this customer: returns the URL to send the customer to. The connection is stored
   * on the customer org (endOrgId is filled in), never on your own org.
   */
  async connect(input: Omit<T.InitiateOauthConnectionInput, "endOrgId">, opts?: RequestOptions): Promise<T.InitiateOauthConnectionOutput> {
    return this.root.connections.initiateOauthConnection({ ...input, endOrgId: await this.id() }, opts);
  }

  /**
   * Stores a connection made with typed-in credentials (API key, basic auth, custom fields) on the customer org.
   * Prefer setupLink(): fastn's hosted page collects the credentials, so they never pass through your backend.
   * Required fields are checked against the auth method's inputContract before anything is sent.
   */
  async connectWithCredentials(input: Omit<T.StoreConnectionsInput, "endOrgId" | "orgId" | "authMethodId"> & { authMethodId?: string }, opts?: RequestOptions): Promise<T.StoreConnectionsOutput> {
    const fields = await this.authFields(input.connectorId, input.authMethodId, opts);
    const missing = fields.required.filter((f) => (input.credentials as Record<string, unknown> | undefined)?.[f] === undefined);
    if (missing.length) throw new TypeError(`connectWithCredentials(${input.connectorId}): missing credential field(s) ${missing.join(", ")}; the auth method "${fields.authMethodId}" takes ${fields.names.join(", ") || "(no fields listed)"}`);
    return this.root.connections.storeConnections({ ...input, authMethodId: input.authMethodId ?? fields.authMethodId, endOrgId: await this.id() }, opts);
  }

  /**
   * The credential fields a connector's auth method asks for (from its inputContract): names, required ones, and the
   * JSON schema. With no authMethodId the connector's first non-OAuth method is used.
   */
  async authFields(connectorId: string, authMethodId?: string, opts?: RequestOptions): Promise<{ authMethodId: string; authType?: string; names: string[]; required: string[]; schema: Record<string, any> }> {
    const res: any = await this.root.connectors.listAuthMethods({ connectorId } as any, opts);
    const methods: any[] = Array.isArray(res?.data) ? res.data : Array.isArray(res) ? res : [];
    const m = authMethodId ? methods.find((x) => x.id === authMethodId) : methods.find((x) => !/oauth/i.test(String(x.authType ?? x.type ?? ""))) ?? methods[0];
    if (!m) throw new FastnApiError(`authFields(${connectorId}): auth method ${authMethodId ?? "(any)"} not found`, 404, "NOT_FOUND", undefined, "GET", "/v1/auth-methods", undefined, res);
    const schema: Record<string, any> = m.inputContract ?? m.input_contract ?? {};
    const names = Object.keys(schema.properties ?? {});
    const required: string[] = Array.isArray(schema.required) ? schema.required : [];
    return { authMethodId: m.id, authType: m.authType ?? m.type, names, required, schema };
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

type Base = Pick<T.ListUnifiedRecordsInput, "category" | "entity" | "provider" | "connection_id">;
export class Records {
  constructor(private readonly api: FastnApis, readonly scope: RecordScope) {}
  private base(): Base {
    const { category, entity, provider, connectionId } = this.scope;
    return { category, entity, ...(provider ? { provider } : {}), ...(connectionId ? { connection_id: connectionId } : {}) };
  }
  /** POST a canonical record. Pass `opts.idempotencyKey` so a retry cannot create it twice. */
  create(record: T.CreateUnifiedRecordInput["record"], opts?: RequestOptions): Promise<T.CreateUnifiedRecordOutput> { return this.api.unified.createUnifiedRecord({ ...this.base(), record }, opts); }
  get(id: string, opts?: RequestOptions): Promise<T.GetUnifiedRecordOutput> { return this.api.unified.getUnifiedRecord({ ...this.base(), id }, opts); }
  list(input: Omit<T.ListUnifiedRecordsInput, keyof Base> = {}, opts?: RequestOptions): Promise<T.ListUnifiedRecordsOutput> { return this.api.unified.listUnifiedRecords({ ...this.base(), ...input }, opts); }
  search(filters: T.SearchUnifiedRecordsInput["filters"], opts?: RequestOptions): Promise<T.SearchUnifiedRecordsOutput> { return this.api.unified.searchUnifiedRecords({ ...this.base(), filters }, opts); }
  update(id: string, record: T.UpdateUnifiedRecordInput["record"], opts?: RequestOptions): Promise<T.UpdateUnifiedRecordOutput> { return this.api.unified.updateUnifiedRecord({ ...this.base(), id, record }, opts); }
  delete(id: string, opts?: RequestOptions): Promise<T.DeleteUnifiedRecordOutput> { return this.api.unified.deleteUnifiedRecord({ ...this.base(), id }, opts); }
  /** Which providers are mapped for this entity and whether the customer has connected them. */
  providers(opts?: RequestOptions): Promise<T.ListUnifiedEntityProvidersOutput> { return this.api.unified.listUnifiedEntityProviders({ category: this.scope.category, entity: this.scope.entity }, opts); }
}
