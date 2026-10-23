import type { FastnApis } from "./generated/api.js";
import type * as T from "./generated/types.js";
import type { RequestOptions, Transport, OpDef } from "./transport.js";
import type { ToolsClient } from "./tools.js";
import { buildApis } from "./generated/api.js";
import { FastnApiError } from "./errors.js";

/** One customer org row as GET /v1/orgs returns it. */
export type CustomerRow = T.JsonObject & { id: string; externalRef?: string };

/** Shared between every Customer object of one client: the caller's org and the ref -> fastn id cache. */
export interface CustomerContext {
  /** fastn's id of the caller's own org (from whoami), resolved once per client. */
  callerOrgId(): Promise<string>;
  /** ref -> fastn org id, filled from every row a lookup sees. */
  ids: Map<string, string>;
  /** ref -> lookup in flight, so concurrent id() calls share one listOrgs. */
  lookups: Map<string, Promise<CustomerRow | undefined>>;
}

/** A unified record call scoped to one customer; `category`/`entity`/`provider` come from the catalog. */
export interface RecordScope { category: string; entity: string; provider?: string; connectionId?: string }

/**
 * Operations whose body field named endOrgId / externalRef is the org being created or edited, not the customer the
 * call runs for: customer.api leaves those alone. Short term; the spec does not say per operation which field is the
 * customer yet (KAT-8650), so the SDK keys off the field name and lists the exceptions here.
 */
const NOT_A_CUSTOMER_FIELD = new Set(["createTenant", "updateTenant"]);
/**
 * Routes that take endOrgId as fastn's id OR the partner's ref (resolved under the caller's org): the ref is sent as
 * is, so no lookup is needed and createIfMissing works for a customer that is not registered yet.
 */
const TAKES_REF_AS_END_ORG_ID = new Set(["createEmbedToken"]);

/**
 * Everything about one of your customers, addressed by the id YOU gave fastn (the `orgId` of createTenant,
 * also called externalRef / endOrgRef). fastn's own org id is resolved and cached when a call needs it.
 */
export class Customer {
  private readonly scoped: Transport;
  private apiCache?: FastnApis;
  private toolsCache?: ToolsClient;

  constructor(private readonly root: FastnApis, t: Transport, readonly ref: string, private readonly ctx: CustomerContext, private readonly toolsClient?: ToolsClient) {
    this.scoped = {
      call: async (op: OpDef, input: Record<string, unknown>, opts?: RequestOptions) => {
        const keys = op.body?.kind === "fields" ? op.body.keys ?? {} : {};
        let body = input;
        if (!NOT_A_CUSTOMER_FIELD.has(op.id) && input.externalRef === undefined && input.endOrgId === undefined) {
          if ("externalRef" in keys) body = { ...input, externalRef: ref };
          else if ("endOrgId" in keys) body = { ...input, endOrgId: TAKES_REF_AS_END_ORG_ID.has(op.id) ? ref : await this.id() };
        }
        return t.call(op, body, { customer: { ref }, ...opts });
      },
    };
  }

  /**
   * Every API area, run for this customer. Each call carries x-end-org-ref, and where the route takes the customer
   * in the body instead (`externalRef` or `endOrgId`, e.g. initiateOauthConnection, storeConnections,
   * createEventSubscription, createSecret), that field is filled in too, because the platform reads the header only
   * on unified record and workflow execute routes. Pass the field yourself to override. Built on first use.
   */
  get api(): FastnApis { return (this.apiCache ??= buildApis(this.scoped)); }

  private get fastnId(): string | undefined { return this.ctx.ids.get(this.ref); }
  private set fastnId(v: string | undefined) { if (v) this.ctx.ids.set(this.ref, v); else this.ctx.ids.delete(this.ref); }

  /** This customer's workspace tools (every connector turned on in fastn Connect), with X-Org-Id = ref on each call. */
  get tools(): ToolsClient {
    if (!this.toolsClient) throw new TypeError("customer(ref).tools: create the FastnClient with tools: { key, url } first");
    return (this.toolsCache ??= this.toolsClient.customer(this.ref));
  }

  /** fastn's id of this customer org (the `id` createTenant returned). Cached after the first lookup. */
  async id(): Promise<string> {
    if (this.fastnId) return this.fastnId;
    const found = await this.find();
    if (!found) throw new FastnApiError(`customer "${this.ref}" is not registered; call customer.register({ name }) first`, { status: 404, code: "NOT_FOUND", method: "GET", path: "/v1/orgs" });
    return found.id;
  }

  /**
   * The customer org row, or undefined when this ref is unknown to fastn. Only orgs under the caller's own org are
   * considered (listOrgs with parent_id, and the row's parentId is checked), so a staff key that sees every org can
   * never resolve another partner's customer. Every row seen fills the client's ref -> id cache, and concurrent
   * lookups of one ref share a single request. GET /v1/orgs has no filter by ref yet (KAT-8615), so a cold lookup
   * downloads the partner's customer list once.
   */
  find(): Promise<CustomerRow | undefined> {
    const { ref, ctx } = this;
    let p = ctx.lookups.get(ref);
    if (!p) {
      p = (async () => {
        const parent = await ctx.callerOrgId();
        const res = await this.root.orgs.listOrgs({ type: "end_org", parent_id: parent });
        const rows: any[] = Array.isArray(res?.data) ? res.data : [];
        let row: CustomerRow | undefined;
        for (const r of rows) {
          if ((r.parentId ?? r.parent_id) !== parent || typeof r.id !== "string") continue;   // fail closed: a row without our parent is not ours
          const refs = [r.externalRef, r.orgId, r.external_ref].filter((x): x is string => typeof x === "string" && x.length > 0);
          for (const x of refs) ctx.ids.set(x, r.id);
          if (refs.includes(ref)) row ??= r;
        }
        return row;
      })();
      ctx.lookups.set(ref, p);
      p.then(() => ctx.lookups.delete(ref), () => ctx.lookups.delete(ref));
    }
    return p;
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
   * fails, the org is checked first: gone (the answer was lost) counts as removed; otherwise it is set back to
   * active and the error says which state it is in.
   */
  async remove(opts?: RequestOptions): Promise<void> {
    const id = await this.id();
    await this.root.orgs.updateTenant({ id, status: "suspended" }, opts);
    try {
      await this.root.orgs.deleteTenant({ id }, opts);
    } catch (err) {
      const gone = await this.root.orgs.getTenant({ id }, opts).then(() => false, (e) => e instanceof FastnApiError && e.isNotFound);
      if (gone) { this.fastnId = undefined; return; }
      let state = "active again";
      try { await this.root.orgs.updateTenant({ id, status: "active" }, opts); } catch { state = "still suspended"; }
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
   * The platform checks the fields, not the SDK: an incomplete INPUT credential set answers 400 CREDENTIALS_INCOMPLETE
   * with the missing names in `FastnApiError.body.missing`; the other auth types store one fixed key per type that
   * the method's contract does not always name (see authFields()), so a client-side check would refuse connections
   * the platform accepts.
   */
  async connectWithCredentials(input: Omit<T.StoreConnectionsInput, "endOrgId" | "orgId" | "authMethodId"> & { authMethodId?: string }, opts?: RequestOptions): Promise<T.StoreConnectionsOutput> {
    const authMethodId = input.authMethodId ?? (await this.authFields(input.connectorId, undefined, opts)).authMethodId;
    return this.root.connections.storeConnections({ ...input, authMethodId, endOrgId: await this.id() }, opts);
  }

  /**
   * The credential fields a connector's auth method lists in its inputContract: names, required ones, and the JSON
   * schema. With no authMethodId the connector's first non-OAuth method is used. For an INPUT method these are the
   * fields to send (top level or under `credentials.custom`); for API_KEY, BEARER, BASIC and the like the platform
   * stores one fixed key per type, which the contract does not always name (KAT-8616), so treat `names` as a hint.
   */
  async authFields(connectorId: string, authMethodId?: string, opts?: RequestOptions): Promise<{ authMethodId: string; authType?: string; names: string[]; required: string[]; schema: Record<string, any> }> {
    const res: any = await this.root.connectors.listAuthMethods({ connectorId } as any, opts);
    const methods: any[] = Array.isArray(res?.data) ? res.data : Array.isArray(res) ? res : [];
    const m = authMethodId ? methods.find((x) => x.id === authMethodId) : methods.find((x) => !/oauth/i.test(String(x.authType ?? x.type ?? ""))) ?? methods[0];
    if (!m) throw new FastnApiError(`authFields(${connectorId}): auth method ${authMethodId ?? "(any)"} not found`, { status: 404, code: "NOT_FOUND", method: "GET", path: "/v1/auth-methods", body: res });
    const schema: Record<string, any> = m.inputContract ?? m.input_contract ?? {};
    const names = Object.keys(schema.properties ?? {});
    const required: string[] = Array.isArray(schema.required) ? schema.required : [];
    return { authMethodId: m.id, authType: m.authType ?? m.type, names, required, schema };
  }

  /**
   * Runs one raw connector action with this customer's own connection, for what the unified API does not cover
   * (e.g. updating a HubSpot deal's stage, logging a call). The action is named by connector slug and action slug.
   * The customer's connection for that connector is pinned by id (and its installation too, when one exists), so
   * the call never runs with your own org's connection. The provider's answer is returned under `response`.
   * The pin is honoured on fastn's hosted environments; a self-hosted stack without the gateway falls back to
   * picking a connection by name from the calling org's pool (platform ticket KAT-8626).
   */
  async runAction(input: { connector: string; action: string; input?: Record<string, any>; mockMode?: boolean }, opts?: RequestOptions): Promise<T.ExecuteActionOutput> {
    const id = await this.id();
    const [conns, insts, acts] = await Promise.all([
      this.connections(undefined, opts),
      this.root.embed.listInstallations({ end_org_id: id }, opts),
      this.root.connectors.listConnectorActionsBySlug({ connector: input.connector } as any, opts),
    ]);
    const rows = (r: any): any[] => (Array.isArray(r?.data) ? r.data : Array.isArray(r?.data?.actions) ? r.data.actions : Array.isArray(r) ? r : []);
    const inst = rows(insts).find((i) => i.endOrgId === id && i.connections && typeof i.connections === "object" && input.connector in i.connections);
    const connId: string | undefined = inst?.connections?.[input.connector];
    const conn = rows(conns).find((c) => c.id === connId) ?? rows(conns).find((c) => c.connectorSlug === input.connector || c.connector?.slug === input.connector);
    if (!conn) throw new FastnApiError(`customer "${this.ref}" has no ${input.connector} connection to run ${input.action} with`, { status: 404, code: "CONNECTION_NOT_FOUND", details: { connector: input.connector }, method: "POST", path: "/v1/actions/{id}/execute" });
    const action = rows(acts).find((a) => a.slug === input.action);
    if (!action?.id) throw new FastnApiError(`connector ${input.connector} has no action "${input.action}"`, { status: 404, code: "NOT_FOUND", details: { connector: input.connector, action: input.action }, method: "GET", path: "/v2/connectors/{connector}/actions" });
    return this.root.connectors.executeAction({ id: action.id, connectorId: conn.connectorId, connectionName: conn.name, connectionId: conn.id, ...(inst ? { installationId: inst.id } : {}), input: input.input ?? {}, ...(input.mockMode ? { mockMode: true } : {}) } as any, opts);
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
  private base() {
    const { category, entity, provider, connectionId } = this.scope;
    return { category, entity, provider: provider || undefined, connection_id: connectionId || undefined };
  }
  /** POST a canonical record. Pass `opts.idempotencyKey` so a retry cannot create it twice. */
  create(record: T.CreateUnifiedRecordInput["record"], opts?: RequestOptions): Promise<T.CreateUnifiedRecordOutput> { return this.api.unified.createUnifiedRecord({ ...this.base(), record }, opts); }
  get(id: string, opts?: RequestOptions): Promise<T.GetUnifiedRecordOutput> { return this.api.unified.getUnifiedRecord({ ...this.base(), id }, opts); }
  list(input: Omit<T.ListUnifiedRecordsInput, "category" | "entity" | "provider" | "connection_id"> = {}, opts?: RequestOptions): Promise<T.ListUnifiedRecordsOutput> { return this.api.unified.listUnifiedRecords({ ...this.base(), ...input }, opts); }
  search(filters: T.SearchUnifiedRecordsInput["filters"], opts?: RequestOptions): Promise<T.SearchUnifiedRecordsOutput> { return this.api.unified.searchUnifiedRecords({ ...this.base(), filters }, opts); }
  update(id: string, record: T.UpdateUnifiedRecordInput["record"], opts?: RequestOptions): Promise<T.UpdateUnifiedRecordOutput> { return this.api.unified.updateUnifiedRecord({ ...this.base(), id, record }, opts); }
  delete(id: string, opts?: RequestOptions): Promise<T.DeleteUnifiedRecordOutput> { return this.api.unified.deleteUnifiedRecord({ ...this.base(), id }, opts); }
  /** Which providers are mapped for this entity and whether the customer has connected them. */
  providers(opts?: RequestOptions): Promise<T.ListUnifiedEntityProvidersOutput> { return this.api.unified.listUnifiedEntityProviders({ category: this.scope.category, entity: this.scope.entity }, opts); }
}
