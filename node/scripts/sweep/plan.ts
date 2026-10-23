// The sweep plan: one or more steps per published operation, in an order where creates come before reads and
// deletes come last. Steps that need a value from an earlier step read it from ctx.ids and are skipped (not failed)
// when that value is missing.
import type { FastnClient } from "../../src/index.js";
import { connectorsPlan, connectorsCleanup, connectionsPlan, embedPlan, embedCleanup, eventsPlan, workflowsPlan, unifiedPlan } from "./areas.js";

export interface Ctx { fastn: FastnClient; run: string; customerRef: string; ids: Record<string, any>; notes: string[] }
export interface Step {
  area: string;
  op: string;
  /** The input, or a function returning it; returning undefined skips the step. */
  input?: Record<string, unknown> | ((ctx: Ctx) => Promise<Record<string, unknown> | undefined | false> | Record<string, unknown> | undefined | false);
  opts?: Record<string, unknown>;
  /** Called with the answer; may return a note for the report. */
  after?: (res: any, ctx: Ctx) => void | string | Promise<void | string>;
  /** 4xx statuses that are the correct answer for this call (e.g. 404 after a delete). */
  expect?: number[];
  /** Run through customer(ref).api instead of the root client. */
  customer?: boolean;
  skip?: string;
  note?: string;
}

const dataOf = (r: any) => r?.data ?? r;
const first = (r: any) => { const d = dataOf(r); const arr = Array.isArray(d) ? d : Array.isArray(d?.items) ? d.items : Array.isArray(d?.data) ? d.data : []; return arr[0]; };
const need = (ctx: Ctx, key: string) => ctx.ids[key];

export function buildPlan(ctx: Ctx): Step[] {
  const run = ctx.run;
  const tag = `sdk_sweep_${run}`;
  const S = (area: string) => (op: string, rest: Omit<Step, "area" | "op"> = {}): Step => ({ area, op, ...rest });

  // ── Users ──
  const U = S("Users");
  const users: Step[] = [
    U("whoami", { after: (r, c) => { c.ids.me = dataOf(r); c.ids.orgId = dataOf(r)?.org?.id; return `org ${c.ids.orgId} role ${dataOf(r)?.role}`; } }),
    U("getMyOrgDomain"), U("getMySuggestions"), U("getMyMemberships"), U("getMyPreferences"),
    U("updateMyPreferences", { input: { nav_layout: "side" } }),
    U("listUsers", { after: (r, c) => { c.ids.anyUserId = first(r)?.id; return `${(dataOf(r)?.length ?? dataOf(r)?.items?.length)} users`; } }),
    U("listPendingUsers"),
    U("listRoles", { after: (r) => `${(dataOf(r) ?? []).length} roles` }),
    U("createRole", { input: { name: `${tag}_role`, description: "sweep", baseRole: "viewer", permissions: { workflows: { actions: ["read"] } } }, after: (r, c) => { c.ids.roleId = dataOf(r)?.id; return `role ${c.ids.roleId}`; } }),
    U("getRole", { input: (c) => need(c, "roleId") && { id: c.ids.roleId } }),
    U("updateRole", { input: (c) => need(c, "roleId") && { id: c.ids.roleId, description: "sweep updated" } }),
    U("inviteUser", { input: { email: `${tag}@example.com`, firstName: "Sweep", lastName: run, role: "viewer" }, after: (r, c) => { const d = dataOf(r); c.ids.invitedUserId = d?.id ?? d?.userId ?? d?.user?.id; c.ids.invitedMembershipId = d?.membershipId ?? d?.membership?.id; return `user ${c.ids.invitedUserId} membership ${c.ids.invitedMembershipId}`; } }),
    U("getUser", { input: (c) => need(c, "invitedUserId") && { userId: c.ids.invitedUserId } }),
    U("listUserMemberships", { input: (c) => need(c, "invitedUserId") && { userId: c.ids.invitedUserId }, after: (r, c) => { const m = first(r); if (m?.id && !c.ids.invitedMembershipId) c.ids.invitedMembershipId = m.id; return `membership ${m?.id}`; } }),
    U("getUserPermissions", { input: (c) => need(c, "invitedUserId") && { userId: c.ids.invitedUserId } }),
    U("updateUserPermissions", { input: (c) => need(c, "invitedUserId") && { userId: c.ids.invitedUserId, permissions: { workflows: { actions: ["read"] } } } }),
    U("updateUserRole", { input: (c) => need(c, "invitedUserId") && { userId: c.ids.invitedUserId, role: "developer" } }),
    U("resendInvite", { input: (c) => need(c, "invitedUserId") && { userId: c.ids.invitedUserId } }),
    U("approvePendingUser", { input: (c) => need(c, "invitedMembershipId") && { id: c.ids.invitedMembershipId }, expect: [400, 404, 409], note: "invited users are not pending approval; 4xx expected" }),
    U("rejectPendingUser", { input: (c) => need(c, "invitedMembershipId") && { id: c.ids.invitedMembershipId }, expect: [400, 404, 409], note: "same" }),
    U("removeUserMembership", { input: (c) => need(c, "invitedUserId") && need(c, "invitedMembershipId") && { userId: c.ids.invitedUserId, membershipId: c.ids.invitedMembershipId } }),
    U("reactivateUser", { input: (c) => need(c, "invitedUserId") && { userId: c.ids.invitedUserId }, expect: [400, 404, 409] }),
    U("removeUser", { input: (c) => need(c, "invitedUserId") && { userId: c.ids.invitedUserId }, expect: [404] }),
    U("deleteRole", { input: (c) => need(c, "roleId") && { id: c.ids.roleId } }),
  ];

  // ── Orgs ──
  const O = S("Orgs");
  const orgs: Step[] = [
    O("listOrgs", { input: { type: "end_org" }, after: (r) => `${(dataOf(r) ?? []).length} customer orgs` }),
    O("createTenant", { input: { name: `Sweep Clinic ${run}`, orgId: `${tag}_org`, plan: "free" }, after: (r, c) => { c.ids.orgCreated = dataOf(r)?.id; return `org ${c.ids.orgCreated}`; } }),
    O("getTenant", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated } }),
    O("updateTenant", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated, name: `Sweep Clinic ${run} Ltd` } }),
    O("getOrgConfig", { input: (c) => need(c, "orgId") && { id: c.ids.orgId } }),
    O("updateOrgConfig", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated, orgName: `Sweep Clinic ${run} Ltd` } }),
    O("getAccountSettings", { input: (c) => need(c, "orgId") && { id: c.ids.orgId } }),
    O("updateAccountSettings", { input: (c) => need(c, "orgId") && { id: c.ids.orgId, autoApproveDomain: false } }),
    O("getOrgDbConfig", { input: (c) => need(c, "orgId") && { id: c.ids.orgId } }),
    O("listOrgDbConfigOverrides", { input: (c) => need(c, "orgId") && { id: c.ids.orgId } }),
    O("enableOrgDbConfig", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated }, expect: [400, 403, 404, 409] }),
    O("updateOrgV1Bridge", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated, enabled: false }, expect: [400, 403, 404] }),
    O("disableOrgDbConfig", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated }, expect: [400, 403, 404, 409] }),
    O("deleteOrgDbConfig", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated }, expect: [400, 403, 404] }),
    O("assignOrgAdmin", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated, email: `${tag}_admin@example.com` }, expect: [400, 403, 404] }),
    O("getHubSettings", { after: (r, c) => { c.ids.hubConfig = dataOf(r)?.config ?? dataOf(r); } }),
    O("updateHubSettings", { input: (c) => ({ config: c.ids.hubConfig && typeof c.ids.hubConfig === "object" && !Array.isArray(c.ids.hubConfig) ? c.ids.hubConfig : {} }), note: "re-saves the current hub settings unchanged" }),
    O("listSecrets"),
    O("createSecret", { input: { name: `${tag.toUpperCase()}_SECRET`, value: "sweep-value", type: "text", environment: "live" }, after: (r, c) => { c.ids.secretId = dataOf(r)?.id; return `secret ${c.ids.secretId}`; } }),
    O("updateSecret", { input: (c) => need(c, "secretId") && { id: c.ids.secretId, value: "sweep-value-2", environment: "live" } }),
    O("deleteSecret", { input: (c) => need(c, "secretId") && { id: c.ids.secretId }, opts: { extraQuery: { environment: "live" } } }),
  ];

  // ── Billing ──
  const B = S("Billing");
  const billing: Step[] = [
    B("listPlans"), B("getPlan", { input: { tier: "free" } }), B("getMyEntitlements"), B("getBillingSubscription"), B("listBillingInvoices"), B("getBillingPaymentMethod"),
    B("listQuotas"), B("getQuotaUsage"), B("checkQuota", { input: { dimension: "tenants_per_saas" } }),
    B("getUsage", { input: (c) => need(c, "orgCreated") && { end_org_id: c.ids.orgCreated } }), B("getAiUsage"),
    B("getThrottle"),
    B("updateThrottle", { input: { resource: "api", maxPerMinute: null }, expect: [400, 403] }),
    B("setQuotaLimit", { input: (c) => need(c, "orgCreated") && { endOrgId: c.ids.orgCreated, limits: [{ dimension: "events_per_day", maxValue: 400, enforcement: "soft" }] }, expect: [400, 403], note: "a customer-level override on the sweep org" }),
    B("deleteQuotaLimit", { input: (c) => need(c, "orgCreated") && { dimension: "events_per_day", endOrgId: c.ids.orgCreated }, expect: [400, 403, 404] }),
    B("getMyPlanChangeRequest", { expect: [404] }),
    B("createPlanChangeRequest", { input: { requestedPlan: "launch" }, expect: [400, 403, 409] }),
    B("cancelMyPlanChangeRequest", { expect: [400, 404, 409] }),
  ];

  // ── Activity / Auth / Teams / API Keys ──
  const activity: Step[] = [
    S("Activity")("getMyActivity"), S("Activity")("trackPageActivity", { input: { page: "/sdk-sweep" } }), S("Activity")("trackActivity", { input: { event: "login", source: "sdk-sweep" } }),
    S("Auth")("getProfile", { expect: [401, 403], note: "needs a user token; an API key gets 401" }),
    S("Auth")("getProfileSecurity", { expect: [401, 403] }),
    S("Auth")("updateProfile", { input: { jobTitle: "sweep" }, expect: [401, 403] }),
    S("Teams")("listGrants"), S("Teams")("listSystemGrants"),
    S("Teams")("createGrant", { input: { body: { name: `${tag}_grant`, description: "sweep", permissions: ["workflows:read"] } }, after: (r, c) => { c.ids.grantId = dataOf(r)?.id; return `grant ${c.ids.grantId}`; } }),
    S("Teams")("updateGrant", { input: (c) => need(c, "grantId") && { id: c.ids.grantId }, opts: { extraBody: { description: "sweep updated" } }, note: "the spec lists only id; description sent via extraBody" }),
    S("Teams")("deleteGrant", { input: (c) => need(c, "grantId") && { id: c.ids.grantId } }),
    S("API Keys")("listApiKeys", { after: (r, c) => { const rows: any[] = dataOf(r) ?? []; const k = rows.find((k) => k.id && k.id !== c.ids.me?.sub?.replace("apikey:", "")) ?? rows[0]; c.ids.apiKeyId = k?.id; c.ids.apiKeyName = k?.name; return `${rows.length} keys`; } }),
    S("API Keys")("getApiKey", { input: (c) => need(c, "apiKeyId") && { id: c.ids.apiKeyId } }),
    S("API Keys")("updateApiKey", { input: (c) => need(c, "apiKeyId") && { id: c.ids.apiKeyId, name: c.ids.apiKeyName ?? "sdk key" }, note: "re-saves the key's own name" }),
    S("API Keys")("revokeApiKey", { skip: "would revoke a real key; the sweep key cannot create one (createApiKey is a backend-only route)" }),
  ];

  // ── Environments ──
  const E = S("Environments");
  const environments: Step[] = [
    E("listEnvironments", { after: (r, c) => { c.ids.liveEnvId = (dataOf(r) ?? []).find((e: any) => e.slug === "live")?.id; return `${(dataOf(r) ?? []).length} environments`; } }),
    E("createEnvironment", { input: { name: `Sweep ${run}`, slug: `sweep-${run}` }, after: (r, c) => { c.ids.envId = dataOf(r)?.id; return `env ${c.ids.envId}`; } }),
    E("setEnvironmentReviewRequirement", { input: (c) => need(c, "envId") && { id: c.ids.envId, requiresReview: true } }),
    E("listEnvironmentConfigs"),
    E("createEnvironmentConfig", { input: (c) => ({ key: `${tag}_cfg`, values: { [c.ids.envId ? `sweep-${run}` : "live"]: "v1" } }) }),
    E("getEnvConfig", { input: { key: `${tag}_cfg` }, expect: [404], note: "404 when the create above was refused for a live-scoped key" }),
    E("upsertEnvironmentConfig", { input: (c) => ({ key: `${tag}_cfg`, values: { [c.ids.envId ? `sweep-${run}` : "live"]: "v2" } }) }),
    E("bulkUpsertEnvironmentConfigs", { input: (c) => ({ items: [{ key: `${tag}_cfg2`, values: { [c.ids.envId ? `sweep-${run}` : "live"]: "v1" } }] }) }),
    E("removeEnvironmentConfigKey", { input: { key: `${tag}_cfg` } }),
    E("removeEnvironmentConfigKey", { input: { key: `${tag}_cfg2` } }),
    E("deleteEnvironment", { input: (c) => need(c, "envId") && { id: c.ids.envId } }),
  ];

  // ── Onboarding ──
  const N = S("Onboarding");
  const onboarding: Step[] = [
    N("getOnboarding"), N("getOnboardingStatus"), N("getSetupJourney"), N("getOnboardingProductProfile", { expect: [404] }),
    N("updateSetupJourney", { input: { screen: "sdk-sweep" }, note: "harmless field" }),
    N("updateOnboarding", { input: { useCase: "sdk sweep" } }),
    N("submitOnboarding", { input: { heardFrom: "other", jobRole: "developer", useCase: "sdk sweep" }, expect: [400, 409], note: "already onboarded -> 4xx expected" }),
    N("saveOnboardingProductProfile", { input: { domain: "example.com", company: { name: "Sweep" } } }),
    N("setOnboardingAgentDomain", { input: { domain: "example.com" } }),
    N("clearOnboardingAgentDomain"),
    N("claimOnboardingCredits", { expect: [400, 403, 409] }),
    N("joinOnboardingOrg", { input: (c) => need(c, "orgId") && { orgId: c.ids.orgId }, expect: [400, 403, 409] }),
    // (the user-session-only onboarding routes answer 401 with an API key; the runner reports that as user-token-only)
  ];

  // ── Observe ──
  const V = S("Observe");
  const observe: Step[] = [
    V("listAlerts"), V("listAlertChannels"), V("getAlertCatalog"),
    V("createAlert", { input: { name: `${tag}_alert`, mode: "threshold", metric: "error_rate", condition: "gt", threshold: 90, window: "1h", enabled: false }, after: (r, c) => { c.ids.alertId = dataOf(r)?.id; return `alert ${c.ids.alertId}`; } }),
    V("updateAlert", { input: (c) => need(c, "alertId") && { id: c.ids.alertId, threshold: 200 } }),
    V("listAlertEvents", { input: (c) => need(c, "alertId") && { id: c.ids.alertId } }),
    V("enableDefaultAlerts", { expect: [400, 409] }),
    V("deleteAlert", { input: (c) => need(c, "alertId") && { id: c.ids.alertId } }),
    V("listAuditLog", { input: { limit: 5 } }), V("listAuditLogActions"), V("listAuditLogResourceTypes"), V("listAuditLogUsers"),
    V("listTraces", { after: (r, c) => { c.ids.traceId = first(r)?.id; } }),
    V("getTrace", { input: (c) => need(c, "traceId") && { id: c.ids.traceId } }),
  ];

  // ── Sync / Execution ──
  const sync: Step[] = [
    S("Sync")("listSyncJobs"),
    S("Sync")("createSyncJob", { input: (c) => need(c, "connectorSlug") && { connectorId: c.ids.connectorSlug, entity: "contacts", direction: "inbound" }, after: (r, c) => { c.ids.syncJobId = dataOf(r)?.id; return `job ${c.ids.syncJobId}`; }, expect: [400, 404] }),
    S("Sync")("getSyncJob", { input: (c) => need(c, "syncJobId") && { id: c.ids.syncJobId } }),
    S("Sync")("triggerSync", { input: (c) => need(c, "syncJobId") && { id: c.ids.syncJobId }, expect: [400, 409] }),
    S("Sync")("deleteSyncJob", { input: (c) => need(c, "syncJobId") && { id: c.ids.syncJobId } }),
    S("Execution")("listConnectorExecutions", { after: (r, c) => { c.ids.executionId = first(r)?.id; } }),
    S("Execution")("getConnectorExecution", { input: (c) => need(c, "executionId") && { id: c.ids.executionId } }),
    S("Execution")("executeRequest", { input: (c) => need(c, "connectorSlug") && { connectorId: c.ids.connectorSlug, path: "/get", method: "GET" }, expect: [400, 404, 422], note: "raw request on the sweep connector" }),
    S("Execution")("executeConnectorActionBySlug", { input: (c) => need(c, "connectorSlug") && need(c, "actionSlug") && { connector: c.ids.connectorSlug, action: c.ids.actionSlug, body: { input: {} } }, expect: [400, 404, 422] }),
    S("Execution")("executeMockAction", { input: (c) => need(c, "connectorSlug") && need(c, "actionSlug") && { connectorSlug: c.ids.connectorSlug, actionSlug: c.ids.actionSlug, body: { input: {} } }, expect: [400, 404] }),
  ];

  // ── Agent ──
  const A = S("Agent");
  const agent: Step[] = [
    A("agentListOrchestratorSessions"),
    A("agentCreateOrchestratorSession", { input: { title: `${tag}` }, after: (r, c) => { const d = dataOf(r); c.ids.sessionId = d?.session?.threadId ?? d?.threadId ?? d?.id; return `session ${c.ids.sessionId}`; } }),
    A("agentRenameOrchestratorSession", { input: (c) => need(c, "sessionId") && { id: c.ids.sessionId, title: `${tag} renamed` } }),
    A("agentGetOrchestratorMessages", { input: (c) => need(c, "sessionId") && { id: c.ids.sessionId } }),
    A("agentUploadOrchestratorAttachment", { input: (c) => need(c, "sessionId") && { id: c.ids.sessionId, mediaType: "text/plain", base64: Buffer.from("sdk sweep").toString("base64"), filename: "sweep.txt" }, after: (r, c) => { c.ids.attachmentId = r?.attachment?.attachmentId ?? dataOf(r)?.attachmentId ?? dataOf(r)?.id; return `attachment ${c.ids.attachmentId}`; } }),
    A("agentGetOrchestratorAttachment", { input: (c) => need(c, "sessionId") && need(c, "attachmentId") && { id: c.ids.sessionId, attachmentId: c.ids.attachmentId } }),
    A("agentGetOrchestratorFile", { input: (c) => need(c, "sessionId") && { id: c.ids.sessionId, path: "sweep.txt" }, expect: [404] }),
    A("agentInjectOrchestratorMessage", { input: (c) => need(c, "sessionId") && { id: c.ids.sessionId, message: { id: `m_${run}`, role: "user", parts: [{ type: "text", text: "hello from the sdk sweep" }] } } }),
    A("agentStopOrchestratorSession", { input: (c) => need(c, "sessionId") && { id: c.ids.sessionId }, expect: [400, 409] }),
    A("agentOrchestratorStream", { skip: "long-running LLM stream (SSE); costs credits and never ends by itself" }),
    A("submitOrchestratorFeedback", { input: (c) => need(c, "sessionId") && { threadId: c.ids.sessionId, messageIndex: 0, agentId: "orchestrator", result: "Pass", messageText: "sdk sweep" }, expect: [400, 404] }),
    A("agentDeleteOrchestratorSession", { input: (c) => need(c, "sessionId") && { id: c.ids.sessionId } }),
    A("agentBuildPlan", { input: { prompt: "Sync HubSpot contacts to a Google Sheet once a day" }, note: "LLM call" }),
    A("agentSuggestConnectors", { input: { useCase: "book meetings from a phone call" }, note: "LLM call" }),
    A("agentErrorDiagnosis", { input: { error: "TypeError: Cannot read properties of undefined (reading 'id')", workflowCode: "export default async (input) => input.contact.id" }, note: "LLM call" }),
    A("agentGenerateWorkflowDocs", { input: { code: "export default async (input, ctx) => ({ ok: true })", name: "sweep" }, note: "LLM call" }),
    A("researchSaas", { input: { domain: "example.com" }, note: "LLM/web call" }),
    A("getSaasResearch", { input: { domain: "example.com" }, expect: [404] }),
    A("matchProductConnector", { input: { domain: "hubspot.com", productName: "HubSpot" } }),
    A("reviseProductProfile", { input: { domain: "example.com", field: "what", instruction: "say it is a test company", product: { name: "Example", description: null, entities: [], apiDocsUrl: null, webhooks: [] } }, note: "LLM call" }),
    A("fetchWebPage", { input: { url: "https://example.com", maxChars: 500 } }),
    A("searchWeb", { input: { query: "fastn.ai", maxResults: 2 } }),
  ];

  return [
    ...users, ...orgs, ...billing, ...activity, ...environments, ...onboarding, ...observe, ...agent,
    ...connectorsPlan(ctx, S), ...sync, ...connectionsPlan(ctx, S), ...embedPlan(ctx, S), ...eventsPlan(ctx, S), ...workflowsPlan(ctx, S), ...unifiedPlan(ctx, S),
    ...embedCleanup(ctx, S), ...connectorsCleanup(ctx, S), ...teardown(ctx, S),
  ];
}

type Mk = (area: string) => (op: string, rest?: Omit<Step, "area" | "op">) => Step;

function teardown(_ctx: Ctx, S: Mk): Step[] {
  const O = S("Orgs");
  return [
    O("updateTenant", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated, status: "suspended" }, note: "teardown: suspend the sweep org" }),
    O("deleteTenant", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated }, note: "teardown" }),
    O("getTenant", { input: (c) => need(c, "orgCreated") && { id: c.ids.orgCreated }, expect: [404], note: "gone after delete" }),
  ];
}
