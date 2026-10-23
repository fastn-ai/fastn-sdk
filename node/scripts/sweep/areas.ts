// Sweep steps for the resource-heavy areas: Connectors, Connections, Embed, Events, Workflows, Unified API.
// Each area creates its own throw-away objects named sdk_sweep_<run> and deletes them at the end of its block.
import type { Ctx, Step } from "./plan.js";

type Mk = (area: string) => (op: string, rest?: Omit<Step, "area" | "op">) => Step;
const dataOf = (r: any) => r?.data ?? r;
const list = (r: any): any[] => { const d = dataOf(r); return Array.isArray(d) ? d : Array.isArray(d?.items) ? d.items : Array.isArray(d?.data) ? d.data : Array.isArray(d?.actions) ? d.actions : []; };
const need = (c: Ctx, ...keys: string[]) => keys.every((k) => c.ids[k] !== undefined && c.ids[k] !== null);
const ECHO = "https://httpbin.org";

export function connectorsPlan(ctx: Ctx, S: Mk): Step[] {
  const C = S("Connectors");
  const run = ctx.run, slug = `sdkSweep${run}`;   // connector slugs must match /^[a-z][a-zA-Z0-9]*$/
  return [
    C("listConnectors", { after: (r, c) => { const rows = list(r); c.ids.anyConnector = rows.find((x) => x.slug === "hubspot") ?? rows[0]; return `${rows.length} connectors`; } }),
    C("listConnectorHealth"),
    C("getPlatformProviderBySlug", { input: { platformSlug: "google" }, expect: [404], after: (r, c) => { c.ids.platformProviderId = dataOf(r)?.id; } }),
    C("getPlatformProvider", { input: (c) => need(c, "platformProviderId") && { id: c.ids.platformProviderId } }),
    C("createConnector", {
      input: {
        name: `SDK Sweep ${run}`, slug, description: "throw-away connector made by the SDK sweep", domain: ECHO, visibility: "private", category: "developer-tools",
        authMethods: [
          { type: "NO_AUTH", title: "None", isDefault: true },
          { type: "API_KEY", title: "API key", inputContract: { type: "object", properties: { apiKey: { type: "string", title: "API key" } }, required: ["apiKey"] }, authConfig: { apiKeyName: "X-Api-Key" } },
        ],
      },
      after: (r, c) => { const d = dataOf(r); c.ids.connectorId = d?.id; c.ids.connectorSlug = d?.slug ?? slug; c.ids.authMethods = d?.authMethods; return `connector ${c.ids.connectorId} (${c.ids.connectorSlug})`; },
    }),
    C("getConnector", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId }, after: (r, c) => { const d = dataOf(r); if (!c.ids.authMethods) c.ids.authMethods = d?.authMethods; c.ids.apiKeyMethodId = (c.ids.authMethods ?? []).find((m: any) => m.type === "API_KEY")?.id; return `auth methods ${(c.ids.authMethods ?? []).length}`; } }),
    C("updateConnector", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId, description: "updated by the sweep" } }),
    C("listConnectorVersions", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId }, after: (r, c) => { c.ids.connectorVersionId = list(r)[0]?.id; return `${list(r).length} versions`; } }),
    C("getConnectorVersion", { input: (c) => need(c, "connectorId", "connectorVersionId") && { id: c.ids.connectorId, versionId: c.ids.connectorVersionId } }),
    C("getConnectorVersionUsage", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId } }),
    C("getConnectorMethods", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId } }),
    C("getConnectorEntities", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId } }),
    C("listWebhookConfigs", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId } }),
    // auth methods
    C("listAuthMethods", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId } }),
    C("createAuthMethod", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId, type: "BEARER", title: "Bearer token" }, after: (r, c) => { c.ids.authMethodId = dataOf(r)?.id; return `auth method ${c.ids.authMethodId}`; } }),
    C("getAuthMethod", { input: (c) => need(c, "authMethodId") && { id: c.ids.authMethodId }, note: "spec lists GET /v1/auth-methods/{id}; the server answers 405" }),
    C("updateAuthMethod", { input: (c) => need(c, "authMethodId") && { id: c.ids.authMethodId, bodyId: c.ids.authMethodId, title: "Bearer token (updated)" } }),
    // auth providers
    C("listAuthProviders", { after: (r, c) => { c.ids.anyAuthProviderId = list(r)[0]?.id; return `${list(r).length} providers`; } }),
    C("createAuthProvider", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId, name: `SDK sweep ${run}`, clientId: "client", clientSecret: "secret", authorizationUrl: `${ECHO}/anything/authorize`, authorization: { tokenUrl: `${ECHO}/anything/token`, grantType: "authorization_code" }, params: { scope: "read" } }, after: (r, c) => { c.ids.authProviderId = dataOf(r)?.id; return `auth provider ${c.ids.authProviderId}`; } }),
    C("getAuthProvider", { input: (c) => need(c, "authProviderId") && { id: c.ids.authProviderId } }),
    C("listAuthProviderScopes", { input: (c) => need(c, "authProviderId") && { id: c.ids.authProviderId } }),
    C("updateAuthProvider", { input: (c) => need(c, "authProviderId") && { id: c.ids.authProviderId, description: "updated by the sweep" } }),
    // entities + folders
    C("listConnectorEntities", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId } }),
    C("createConnectorEntity", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId, name: "Ping", slug: "ping", description: "sweep entity" }, after: (r, c) => { c.ids.entityId = dataOf(r)?.id; return `entity ${c.ids.entityId}`; }, expect: [400], note: "400 'connector does not exist' for a connector created a moment earlier, by id or slug: platform finding" }),
    C("getConnectorEntity", { input: (c) => need(c, "entityId") && { id: c.ids.entityId } }),
    C("updateConnectorEntity", { input: (c) => need(c, "entityId") && { id: c.ids.entityId, description: "updated" } }),
    C("listActionFolders", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId } }),
    C("createActionFolder", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId, name: "Sweep folder" }, after: (r, c) => { c.ids.folderId = dataOf(r)?.id; return `folder ${c.ids.folderId}`; } }),
    C("getActionFolder", { input: (c) => need(c, "folderId") && { id: c.ids.folderId } }),
    C("updateActionFolder", { input: (c) => need(c, "folderId") && { id: c.ids.folderId, name: "Sweep folder (renamed)" } }),
    // actions
    C("createAction", {
      input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId, name: "Ping", slug: "ping", type: "HTTP", method: "GET", path: "/anything/ping", description: "GET echo", httpConfig: { url: `${ECHO}/anything/ping`, method: "GET" }, inputContract: { type: "object", properties: { q: { type: "string" } } }, ...(c.ids.folderId ? { folderId: c.ids.folderId } : {}) },
      after: (r, c) => { const d = dataOf(r); c.ids.actionId = d?.id; c.ids.actionSlug = d?.slug ?? "ping"; return `action ${c.ids.actionId}`; },
    }),
    C("createAction", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId, name: "Ping two", slug: "pingTwo", type: "HTTP", method: "GET", path: "/anything/two", httpConfig: { url: `${ECHO}/anything/two`, method: "GET" } }, after: (r, c) => { c.ids.action2Id = dataOf(r)?.id; return `second action ${c.ids.action2Id}`; }, note: "second action, removed by batchDeleteActions" }),
    C("listActions", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId } }),
    C("getAction", { input: (c) => need(c, "actionId") && { id: c.ids.actionId } }),
    C("updateAction", { input: (c) => need(c, "actionId") && { id: c.ids.actionId, description: "GET echo (updated)" } }),
    C("listActionVersions", { input: (c) => need(c, "actionId") && { id: c.ids.actionId }, after: (r, c) => { c.ids.actionVersionId = list(r)[0]?.id; } }),
    C("getActionVersion", { input: (c) => need(c, "actionId", "actionVersionId") && { id: c.ids.actionId, versionId: c.ids.actionVersionId } }),
    C("createActionVersion", { input: (c) => need(c, "actionId") && { id: c.ids.actionId, bump: "major" }, expect: [400, 409] }),
    C("getActionVersionDiff", { input: (c) => need(c, "connectorId", "actionSlug") && { id: c.ids.connectorId, actionSlug: c.ids.actionSlug }, expect: [400, 404] }),
    C("exportAction", { input: (c) => need(c, "actionId") && { id: c.ids.actionId } }),
    C("exportActions", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId } }),
    C("getActionReview", { input: (c) => need(c, "actionId") && { id: c.ids.actionId }, expect: [404] }),
    C("createActionReviewComment", { input: (c) => need(c, "actionId") && { id: c.ids.actionId, body: "sweep comment" }, expect: [400, 404] }),
    C("setActionTestResult", { input: (c) => need(c, "actionId") && { id: c.ids.actionId, testStatus: "passed", lastTestEvidence: { by: "sdk sweep" } } }),
    C("executeAction", { input: (c) => need(c, "actionId", "connectorId") && { id: c.ids.actionId, connectorId: c.ids.connectorId, input: { q: "sweep" } }, expect: [400, 402, 404, 422, 424], note: "runs the echo action with the NO_AUTH method" }),
    C("mockAction", { input: (c) => need(c, "actionId") && { id: c.ids.actionId, body: { input: { q: "sweep" } } }, expect: [400, 404] }),
    C("saveActionMockStub", { input: (c) => need(c, "actionId", "connectorId") && { id: c.ids.actionId, connectorId: c.ids.connectorId, responseStatus: 200, responseBody: { ok: true } } }),
    C("generateActionMock", { input: (c) => need(c, "connectorSlug", "actionSlug") && { connectorSlug: c.ids.connectorSlug, actionSlug: c.ids.actionSlug }, expect: [400, 404] }),
    C("listMockStubs", { input: (c) => need(c, "connectorSlug", "actionSlug") && { connectorSlug: c.ids.connectorSlug, actionSlug: c.ids.actionSlug } }),
    C("createMockStub", { input: (c) => need(c, "connectorSlug", "actionSlug") && { connectorSlug: c.ids.connectorSlug, actionSlug: c.ids.actionSlug, connectorId: c.ids.connectorId, name: "sweep stub", response: { status: 200, body: { stub: true } } }, after: (r, c) => { c.ids.stubId = dataOf(r)?.id; return `stub ${c.ids.stubId}`; } }),
    C("updateMockStub", { input: (c) => need(c, "stubId") && { connectorSlug: c.ids.connectorSlug, actionSlug: c.ids.actionSlug, stubId: c.ids.stubId, name: "sweep stub (renamed)" } }),
    C("regenerateMockStubs", { input: (c) => need(c, "connectorSlug", "actionSlug") && { connectorSlug: c.ids.connectorSlug, actionSlug: c.ids.actionSlug, connectorId: c.ids.connectorId }, expect: [400, 404] }),
    C("deleteMockStub", { input: (c) => need(c, "stubId") && { connectorSlug: c.ids.connectorSlug, actionSlug: c.ids.actionSlug, stubId: c.ids.stubId } }),
    C("promoteAction", { input: (c) => need(c, "actionId") && { id: c.ids.actionId }, expect: [400, 409] }),
    C("proposeActionUpdate", { input: (c) => need(c, "actionId") && { id: c.ids.actionId, description: "GET echo (proposed)" }, expect: [400, 404, 409] }),
    C("importActions", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId, format: "fastn", content: JSON.stringify({ actions: [] }), preview: true }, expect: [400, 422] }),
    C("batchDeleteActions", { input: (c) => need(c, "action2Id") && { ids: [c.ids.action2Id] } }),
    C("deleteAction", { input: (c) => need(c, "actionId") && { id: c.ids.actionId } }),
    C("restoreAction", { input: (c) => need(c, "actionId") && { id: c.ids.actionId } }),
    // webhook config
    C("createWebhookConfig", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId, type: "APP", events: [{ id: "ping.received", label: "Ping received" }], enabled: true }, after: (r, c) => { c.ids.webhookConfigId = dataOf(r)?.id; return `webhook config ${c.ids.webhookConfigId}`; } }),
    C("getWebhookConfig", { input: (c) => need(c, "webhookConfigId") && { id: c.ids.webhookConfigId } }),
    C("updateWebhookConfig", { input: (c) => need(c, "webhookConfigId") && { id: c.ids.webhookConfigId, enabled: true, subscription: "" } }),
    C("listWebhookConfigConnectors"),
    C("executeWebhookSubscription", { input: (c) => need(c, "webhookConfigId") && { id: c.ids.webhookConfigId, eventId: "ping.received", webhookUrl: `${ECHO}/anything/hook` }, expect: [400, 404, 422] }),
    // (deleteWebhookConfig runs in connectorsCleanup: the Events block needs the config for an app event trigger)
    // probes, requests, changes, staleness, proposals, pins
    C("probeConnector", { input: (c) => need(c, "connectorId", "actionSlug") && { connectorId: c.ids.connectorId, actionSlug: c.ids.actionSlug, params: {} }, expect: [400, 404, 422], after: (r, c) => { c.ids.probeId = dataOf(r)?.id ?? dataOf(r)?.probeId; } }),
    C("probeConnectorValues", { input: (c) => need(c, "connectorId", "actionSlug") && { connectorId: c.ids.connectorId, actionSlug: c.ids.actionSlug, params: {} }, expect: [400, 404, 422] }),
    C("mergeProbes", { input: (c) => need(c, "probeId") && { parentProbeId: c.ids.probeId, subProbes: [] }, expect: [400, 404] }),
    C("listConnectorRequests"),
    C("createConnectorRequest", { input: { name: `SDK sweep ${run}`, websiteUrl: "https://example.com", note: "sweep", source: "api" }, after: (r, c) => { c.ids.connectorRequestId = dataOf(r)?.id; return `request ${c.ids.connectorRequestId}`; } }),
    C("updateConnectorRequest", { input: (c) => need(c, "connectorRequestId") && { id: c.ids.connectorRequestId, status: "declined" }, expect: [403] }),
    C("listConnectorChanges", { after: (r, c) => { c.ids.connectorChangeId = list(r)[0]?.id; return `${list(r).length} changes`; } }),
    C("listConnectorChangeConsumers", { input: (c) => need(c, "connectorChangeId") && { id: c.ids.connectorChangeId } }),
    C("setConnectorChangeStatus", { input: (c) => need(c, "connectorChangeId") && { id: c.ids.connectorChangeId, status: "new" }, expect: [400, 403] }),
    C("proposeConnectorChangeFix", { input: (c) => need(c, "connectorChangeId") && { id: c.ids.connectorChangeId }, expect: [400, 403, 404, 409] }),
    C("listConnectorStaleness", { after: (r, c) => { c.ids.stalenessId = list(r)[0]?.id; } }),
    C("scanConnectorStaleness", { expect: [400, 403, 409] }),
    C("setConnectorStalenessStatus", { input: (c) => need(c, "stalenessId") && { id: c.ids.stalenessId, status: "open" }, expect: [400, 403] }),
    C("listConnectorUpdateProposals", { after: (r, c) => { const p = list(r)[0]; c.ids.proposalId = p?.id; c.ids.proposalItemId = p?.items?.[0]?.id; } }),
    C("getConnectorUpdateProposal", { input: (c) => need(c, "proposalId") && { id: c.ids.proposalId } }),
    C("runConnectorUpdateAgent", { input: (c) => need(c, "proposalId") && { id: c.ids.proposalId }, expect: [400, 403, 404, 409] }),
    C("decideConnectorUpdateProposalItem", { input: (c) => need(c, "proposalId", "proposalItemId") && { id: c.ids.proposalId, itemId: c.ids.proposalItemId, decision: "reject", note: "sweep" }, expect: [400, 403, 409] }),
    C("applyConnectorUpdateProposal", { input: (c) => need(c, "proposalId") && { id: c.ids.proposalId }, expect: [400, 403, 404, 409] }),
    C("listConnectorVersionPins"),
    C("upsertConnectorVersionPin", { input: (c) => need(c, "connectorSlug", "orgCreated") && { connectorSlug: c.ids.connectorSlug, endOrgId: c.ids.orgCreated, versionMajor: 1 }, after: (r, c) => { c.ids.pinId = dataOf(r)?.id; return `pin ${c.ids.pinId}`; }, expect: [400, 404] }),
    C("deleteConnectorVersionPin", { input: (c) => need(c, "pinId") && { id: c.ids.pinId } }),
    // v2 routes by slug
    C("listConnectorActionsBySlug", { input: (c) => need(c, "connectorSlug") && { connector: c.ids.connectorSlug } }),
    C("getConnectorActionSchema", { input: (c) => need(c, "connectorSlug", "actionSlug") && { connector: c.ids.connectorSlug, action: c.ids.actionSlug } }),
    C("getConnectorConnectionStatus", { input: (c) => need(c, "connectorSlug") && { connector: c.ids.connectorSlug } }),
    C("discoverMcpConnectorTools", { input: (c) => need(c, "connectorSlug") && { connector: c.ids.connectorSlug }, expect: [400, 404, 422] }),
    C("syncMcpTools", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId }, expect: [400, 422] }),
    // lifecycle
    C("activateConnector", { input: (c) => need(c, "connectorId", "orgCreated") && { id: c.ids.connectorId, endOrgId: c.ids.orgCreated }, expect: [400, 404, 409] }),
    C("publishConnectorVersion", { input: (c) => need(c, "connectorId", "connectorVersionId") && { id: c.ids.connectorId, versionId: c.ids.connectorVersionId, commit: "sweep" }, expect: [400, 409] }),
    C("revertConnector", { input: (c) => need(c, "connectorId", "connectorVersionId") && { id: c.ids.connectorId, versionId: c.ids.connectorVersionId }, expect: [400, 409] }),
    C("promoteConnector", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId, stage: "live", commit: "sweep" }, expect: [400, 403, 409], note: "test -> live on the throw-away connector" }),
    C("forkConnector", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId }, after: (r, c) => { c.ids.forkConnectorId = dataOf(r)?.id; return `fork ${c.ids.forkConnectorId}`; }, expect: [400, 409] }),
    C("importConnectors", { input: { connectors: [] }, expect: [400, 422] }),
  ];
}

export function connectorsCleanup(_ctx: Ctx, S: Mk): Step[] {
  const C = S("Connectors");
  return [
    // cleanup of the connector tree (deletes count as tested calls)
    C("deleteWebhookConfig", { input: (c) => need(c, "webhookConfigId") && { id: c.ids.webhookConfigId } }),
    C("deleteActionFolder", { input: (c) => need(c, "folderId") && { id: c.ids.folderId } }),
    C("deleteConnectorEntity", { input: (c) => need(c, "entityId") && { id: c.ids.entityId } }),
    C("deleteAuthProvider", { input: (c) => need(c, "authProviderId") && { id: c.ids.authProviderId } }),
    C("deleteAuthMethod", { input: (c) => need(c, "authMethodId") && { id: c.ids.authMethodId }, note: "spec lists DELETE /v1/auth-methods/{id}; the server answers 405" }),
    C("deleteConnector", { input: (c) => need(c, "forkConnectorId") && { id: c.ids.forkConnectorId }, note: "the fork" }),
    C("deleteConnector", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId } }),
    C("restoreConnector", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId } }),
    C("deleteConnector", { input: (c) => need(c, "connectorId") && { id: c.ids.connectorId }, note: "again after restore, so nothing is left behind" }),
  ];
}

export function connectionsPlan(ctx: Ctx, S: Mk): Step[] {
  const K = S("Connections");
  const run = ctx.run;
  return [
    K("listConnections", { after: (r, c) => { c.ids.anyConnection = list(r)[0]; return `${list(r).length} connections`; } }),
    K("getConnection", { input: (c) => need(c, "anyConnection") && { id: c.ids.anyConnection.id } }),
    K("getConnectionByName", { input: (c) => need(c, "anyConnection") && { connectorId: c.ids.anyConnection.connectorId ?? c.ids.anyConnection.connector_id ?? c.ids.anyConnection.connectorSlug, name: c.ids.anyConnection.name ?? "default" }, expect: [404] }),
    K("listSaasConnectors"),
    K("upsertSaasConnector", { input: (c) => need(c, "connectorSlug") && { connectorId: c.ids.connectorSlug, scopes: ["read"] }, expect: [400, 404] }),
    K("listSaasConnectorConnections", { input: (c) => need(c, "connectorSlug") && { connectorId: c.ids.connectorSlug }, expect: [404] }),
    K("deleteSaasConnector", { input: (c) => need(c, "connectorSlug") && { connectorId: c.ids.connectorSlug }, expect: [404] }),
    // a stored API-key connection for the sweep customer, through the customer scope (fills endOrgId)
    K("storeConnections", { customer: true, input: (c) => need(c, "connectorId", "apiKeyMethodId") && { connectorId: c.ids.connectorId, authMethodId: c.ids.apiKeyMethodId, authType: "API_KEY", credentials: { apiKey: `sweep-${run}` }, name: `sweep-${run}` }, after: (r, c) => { const d = dataOf(r); c.ids.storedConnectionId = d?.id ?? d?.connectionId ?? d?.connections?.[0]?.id; return `connection ${c.ids.storedConnectionId} on ${d?.endOrgId ?? d?.orgId ?? "?"}`; } }),
    K("updateConnection", { input: (c) => need(c, "storedConnectionId") && { id: c.ids.storedConnectionId, name: `sweep-${run}-renamed` } }),
    K("setDefaultConnection", { input: (c) => need(c, "storedConnectionId") && { id: c.ids.storedConnectionId } }),
    K("refreshConnection", { input: (c) => need(c, "storedConnectionId") && { id: c.ids.storedConnectionId }, expect: [400, 409, 422], note: "not OAuth, refresh has nothing to do" }),
    K("initiateOauthConnection", { customer: true, input: (c) => need(c, "anyConnector") && { connectorId: c.ids.anyConnector.slug ?? c.ids.anyConnector.id, connectionName: `sweep-${run}`, returnUrl: "https://example.com/done" }, after: (r) => `authorizationUrl ${dataOf(r)?.authorizationUrl ? "present" : "missing"}; endOrgId filled by the SDK`, expect: [400, 404, 422] }),
    K("createConnectLink", { input: (c) => need(c, "anyConnector") && { connectorId: c.ids.anyConnector.slug ?? c.ids.anyConnector.id, connectionName: `sweep-${run}`, expiresInMinutes: 10 }, expect: [400, 404] }),
    K("deleteConnections", { input: (c) => need(c, "storedConnectionId") && { id: c.ids.storedConnectionId } }),
  ];
}

export function embedPlan(ctx: Ctx, S: Mk): Step[] {
  const M = S("Embed");
  const run = ctx.run;
  return [
    M("listWidgets", { after: (r, c) => { c.ids.anyWidgetId = list(r)[0]?.id; return `${list(r).length} widgets`; } }),
    M("createWidget", { input: (c) => { const conn = c.ids.connectorId ? { connectorId: c.ids.connectorId, slug: c.ids.connectorSlug } : c.ids.anyConnector ? { connectorId: c.ids.anyConnector.id, slug: c.ids.anyConnector.slug } : undefined; return conn && { name: `SDK sweep ${run}`, description: "throw-away widget", status: "draft", connector_refs: [conn] }; }, after: (r, c) => { c.ids.widgetId = dataOf(r)?.id; return `widget ${c.ids.widgetId}`; } }),
    M("getWidget", { input: (c) => need(c, "widgetId") && { id: c.ids.widgetId } }),
    M("updateWidget", { input: (c) => need(c, "widgetId") && { id: c.ids.widgetId, description: "updated by the sweep" } }),
    M("forkWidget", { input: (c) => need(c, "widgetId") && { id: c.ids.widgetId, name: `SDK sweep ${run} fork` }, after: (r, c) => { c.ids.widgetForkId = dataOf(r)?.id; return `fork ${c.ids.widgetForkId}`; }, expect: [400, 409] }),
    M("setWidgetActiveVersion", { input: (c) => need(c, "widgetId") && { id: c.ids.widgetId, activeWidgetId: c.ids.widgetId }, expect: [400, 404, 409] }),
    M("getWidgetEmbedStatus"), M("getWidgetInsights"), M("getLiveWidgetInsights"), M("getTenantInsights"), M("getLiveTenantInsights"),
    M("getForkLineage", { input: (c) => need(c, "widgetId") && { ids: c.ids.widgetId } }),
    M("forkIntegration", { input: (c) => need(c, "widgetId") && { id: c.ids.widgetId }, expect: [400, 404, 409] }),
    // setup links and embed tokens for the sweep customer
    M("createSetupLink", { input: (c) => need(c, "widgetId") && { widgetId: c.ids.widgetId, connectionName: `sweep-${run}`, externalRef: `sdk_sweep_${run}_org` }, after: (r, c) => { const d = dataOf(r); c.ids.setupLinkId = d?.setupId ?? d?.id; return `setup link ${c.ids.setupLinkId} ${d?.status}`; } }),
    M("getSetupLink", { input: (c) => need(c, "setupLinkId") && { id: c.ids.setupLinkId } }),
    M("getSetupLinkStatus", { input: (c) => need(c, "setupLinkId") && { id: c.ids.setupLinkId } }),
    M("completeSetupLink", { input: (c) => need(c, "setupLinkId") && { id: c.ids.setupLinkId, connections: {} }, after: (r, c) => { c.ids.installationId = dataOf(r)?.installationId; return `installation ${c.ids.installationId}`; }, expect: [400, 403, 409, 422] }),
    M("createSetupLink", { input: (c) => need(c, "widgetId") && { widgetId: c.ids.widgetId, connectionName: `sweep-${run}-2`, externalRef: `sdk_sweep_${run}_org` }, after: (r, c) => { c.ids.setupLink2Id = dataOf(r)?.setupId ?? dataOf(r)?.id; }, note: "second link, cancelled below" }),
    M("cancelSetupLink", { input: (c) => need(c, "setupLink2Id") && { id: c.ids.setupLink2Id } }),
    M("createEmbedToken", { input: { endOrgId: `sdk_sweep_${run}_org`, userId: "sweep-user", createIfMissing: true }, after: (r) => `token ${dataOf(r)?.token ? "present" : "missing"}` }),
    // configs, installations
    M("listConfigs"),
    M("createConfig", { input: (c) => need(c, "widgetId", "orgCreated") && { widget_id: c.ids.widgetId, end_org_id: c.ids.orgCreated, config: { entities: [], directions: [] } }, after: (r, c) => { c.ids.configId = dataOf(r)?.id; return `config ${c.ids.configId}`; }, expect: [400, 422] }),
    M("getConfig", { input: (c) => need(c, "configId") && { id: c.ids.configId } }),
    M("updateConfig", { input: (c) => need(c, "configId") && { id: c.ids.configId, config: { entities: [], directions: [], unifiedValues: { note: "sweep" } } } }),
    M("updateConfigDecisions", { input: (c) => need(c, "configId") && { id: c.ids.configId, decisions: [] }, expect: [400] }),
    M("listConfigEntries", { input: (c) => need(c, "configId") && { id: c.ids.configId }, expect: [400], note: "400 unless the config has an array-typed configuration" }),
    M("createConfigEntry", { input: (c) => need(c, "configId") && { id: c.ids.configId, bodyId: `entry_${run}`, values: { note: "sweep" } }, after: (r, c) => { c.ids.entryId = dataOf(r)?.id ?? `entry_${run}`; return `entry ${c.ids.entryId}`; }, expect: [400, 422] }),
    M("getConfigEntry", { input: (c) => need(c, "configId", "entryId") && { id: c.ids.configId, entryId: c.ids.entryId } }),
    M("updateConfigEntry", { input: (c) => need(c, "configId", "entryId") && { id: c.ids.configId, entryId: c.ids.entryId, bodyId: c.ids.entryId, values: { note: "sweep 2" } }, expect: [400, 422] }),
    M("deleteConfigEntry", { input: (c) => need(c, "configId", "entryId") && { id: c.ids.configId, entryId: c.ids.entryId } }),
    M("listConfigWorkflows", { input: (c) => need(c, "configId") && { id: c.ids.configId } }),
    M("getConfigFieldOptions", { input: (c) => need(c, "configId") && { id: c.ids.configId, fieldId: "note" }, expect: [400, 404, 422] }),
    M("upgradeConfig", { input: (c) => need(c, "configId") && { id: c.ids.configId }, expect: [400, 409] }),
    M("forkConfig", { input: (c) => need(c, "configId") && { id: c.ids.configId }, after: (r, c) => { c.ids.configForkId = dataOf(r)?.id; }, expect: [400, 409] }),
    M("listInstallations", { after: (r) => `${list(r).length} installations` }),
    M("createInstallation", { input: (c) => need(c, "widgetId", "orgCreated") && { target_type: "widget", target_id: c.ids.widgetId, end_org_id: c.ids.orgCreated, label: `sweep ${run}`, slug: `sweep-${run}`, status: "draft", defer_config: true }, after: (r, c) => { c.ids.installation2Id = dataOf(r)?.id; if (!c.ids.installationId) c.ids.installationId = c.ids.installation2Id; return `installation ${c.ids.installation2Id}`; }, expect: [400, 422] }),
    M("getInstallation", { input: (c) => need(c, "installationId") && { id: c.ids.installationId } }),
    M("updateInstallation", { input: (c) => need(c, "installationId") && { id: c.ids.installationId, label: `sweep ${run} (renamed)` } }),
    M("getInstallationResolvedConfig", { input: (c) => need(c, "installationId") && { id: c.ids.installationId }, expect: [400, 404] }),
    M("createConfigDraft", { input: (c) => need(c, "widgetId") && { widget_id: c.ids.widgetId, proposal: { entities: [], directions: [] } }, after: (r, c) => { c.ids.draftId = dataOf(r)?.id; return `draft ${c.ids.draftId}`; }, expect: [400, 422] }),
    M("getConfigDraft", { input: (c) => need(c, "draftId") && { id: c.ids.draftId } }),
    M("proposeConfiguration", { input: { directions: [{ integrationScope: "sweep", mappings: [{ sourceField: "a", targetField: "b" }] }] }, expect: [400, 404, 422] }),
    M("listEmbedShareLinks" as any, { skip: "backend-only route (not in the SDK)" }),
  ].filter((s) => s.op !== "listEmbedShareLinks");
}

export function embedCleanup(_ctx: Ctx, S: Mk): Step[] {
  const M = S("Embed");
  return [
    M("deleteInstallation", { input: (c) => need(c, "installation2Id") && { id: c.ids.installation2Id }, note: "the one made by createInstallation" }),
    M("deleteInstallation", { input: (c) => need(c, "installationId") && c.ids.installationId !== c.ids.installation2Id && { id: c.ids.installationId }, note: "the one made by completeSetupLink" }),
    M("deleteConfig", { input: (c) => need(c, "configForkId") && { id: c.ids.configForkId }, note: "the fork" }),
    M("deleteConfig", { input: (c) => need(c, "configId") && { id: c.ids.configId } }),
    M("deleteWidget", { input: (c) => need(c, "widgetForkId") && { id: c.ids.widgetForkId }, note: "the fork" }),
    M("deleteWidget", { input: (c) => need(c, "widgetId") && { id: c.ids.widgetId } }),
    M("revokeEmbedShareLink", { input: { id: "esl_missing" }, expect: [404], note: "no share link can be created with an API key (backend-only); 404 proves the route" }),
  ];
}

export function eventsPlan(ctx: Ctx, S: Mk): Step[] {
  const V = S("Events");
  const run = ctx.run;
  const hook = "https://httpbin.org/anything/sdk-sweep";
  return [
    V("listEventSubscriptions", { after: (r) => `${list(r).length} subscriptions` }),
    V("createEventSubscription", { customer: true, input: { url: hook, eventTypes: ["connection.connected", "unified.event"], description: `sdk sweep ${run}` }, after: (r, c) => { const d = dataOf(r); c.ids.subId = d?.id; return `subscription ${c.ids.subId} endOrgId ${d?.endOrgId ?? "(none)"}`; } }),
    V("getEventSubscription", { input: (c) => need(c, "subId") && { id: c.ids.subId } }),
    V("updateEventSubscription", { input: (c) => need(c, "subId") && { id: c.ids.subId, description: "updated by the sweep" } }),
    V("rotateEventSubscriptionSecret", { input: (c) => need(c, "subId") && { id: c.ids.subId } }),
    V("testEventSubscription", { input: (c) => need(c, "subId") && { id: c.ids.subId }, after: (r, c) => { c.ids.deliveryId = dataOf(r)?.deliveryId ?? dataOf(r)?.id; } }),
    V("listEventDeliveries", { input: (c) => need(c, "subId") && { id: c.ids.subId }, after: (r, c) => { if (!c.ids.deliveryId) c.ids.deliveryId = list(r)[0]?.id; return `${list(r).length} deliveries`; } }),
    V("replayEventDelivery", { input: (c) => need(c, "deliveryId") && { id: c.ids.deliveryId }, expect: [400, 404, 409] }),
    V("listEvents", { input: { limit: 5 }, after: (r, c) => { c.ids.eventId = list(r)[0]?.id; return `${list(r).length} events`; } }),
    V("countEvents"), V("eventCounts"),
    V("getEvent", { input: (c) => need(c, "eventId") && { id: c.ids.eventId } }),
    V("getEventAttempts", { input: (c) => need(c, "eventId") && { id: c.ids.eventId } }),
    V("replayEvent", { input: (c) => need(c, "eventId") && { id: c.ids.eventId }, expect: [400, 404, 409] }),
    V("listDlq", { after: (r, c) => { c.ids.dlqId = list(r)[0]?.id; } }),
    V("replayDlqEntry", { input: (c) => need(c, "dlqId") && { id: c.ids.dlqId }, expect: [400, 404, 409] }),
    V("deleteDlqEntry", { input: (c) => need(c, "dlqId") && { id: c.ids.dlqId }, expect: [404] }),
    V("getAlertLimits"),
    V("listAlertChannelTargets", { input: (c) => need(c, "anyConnection") && { connectionId: c.ids.anyConnection.id, connectorSlug: c.ids.anyConnection.connectorSlug ?? c.ids.anyConnection.connectorId ?? "slack" }, expect: [400, 404, 422] }),
    V("testAlert", { input: { id: "alert_missing" }, expect: [404] }),
    // triggers: webhook, scheduler, app event
    V("listWebhookTriggers"),
    V("createWebhookTrigger", { input: { name: `sdk sweep ${run}`, status: "DISABLED", authMethod: "NONE" }, after: (r, c) => { c.ids.webhookTriggerId = dataOf(r)?.id; return `webhook trigger ${c.ids.webhookTriggerId}`; } }),
    V("getWebhookTrigger", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId } }),
    V("updateWebhookTrigger", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId, name: `sdk sweep ${run} (renamed)` } }),
    V("getWebhookTriggerStats", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId } }),
    V("setTriggerStatus", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId, status: "DISABLED" } }),
    V("setTriggerReporting", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId, countOnlyField: null } }),
    V("getTriggerMonitoring", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId } }),
    V("getTriggerOutcomes", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId, days: 1 } }),
    V("getTriggersMonitoring"),
    V("resetCircuitBreaker", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId }, expect: [400, 404] }),
    V("replayAllTriggerDlq", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId }, expect: [400, 404, 409], note: "409 on a disabled trigger is the documented answer" }),
    V("forkTrigger", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId, name: `sdk sweep ${run} fork` }, after: (r, c) => { c.ids.triggerForkId = dataOf(r)?.id; }, expect: [400, 409] }),
    V("bulkDeleteWebhookTriggers", { input: (c) => need(c, "triggerForkId") && { ids: [c.ids.triggerForkId] }, note: "the fork" }),
    V("deleteWebhookTrigger", { input: (c) => need(c, "webhookTriggerId") && { id: c.ids.webhookTriggerId } }),
    V("listSchedulers"),
    V("createScheduler", { input: { name: `sdk sweep ${run}`, status: "DISABLED", rate: { value: 1, unit: "days" }, timezone: "UTC" }, after: (r, c) => { c.ids.schedulerId = dataOf(r)?.id; return `scheduler ${c.ids.schedulerId}`; } }),
    V("getScheduler", { input: (c) => need(c, "schedulerId") && { id: c.ids.schedulerId } }),
    V("updateScheduler", { input: (c) => need(c, "schedulerId") && { id: c.ids.schedulerId, name: `sdk sweep ${run} (renamed)` } }),
    V("getSchedulerStats", { input: (c) => need(c, "schedulerId") && { id: c.ids.schedulerId } }),
    V("triggerSchedulerNow", { input: (c) => need(c, "schedulerId") && { id: c.ids.schedulerId }, expect: [400, 409] }),
    V("disableSchedulersByRoute", { input: { routeIds: ["wf_missing"] }, expect: [400, 404] }),
    V("bulkDeleteSchedulers", { input: (c) => need(c, "schedulerId") && { ids: [c.ids.schedulerId] } }),
    V("deleteScheduler", { input: (c) => need(c, "schedulerId") && { id: c.ids.schedulerId }, expect: [404], note: "already removed by bulk delete" }),
    V("listAppWebhookRegistrations"), V("listAppWebhookRegistrationStats"),
    V("createAppWebhookRegistration", { input: (c) => need(c, "connectorId") && { connectorId: c.ids.connectorId, connectorName: c.ids.connectorSlug, verificationType: "APP_LEVEL", events: [{ id: "ping.received", label: "Ping received", type: "WEBHOOK" }] }, after: (r, c) => { c.ids.appWebhookId = dataOf(r)?.id; return `registration ${c.ids.appWebhookId}`; }, expect: [400, 422] }),
    V("getAppWebhookRegistration", { input: (c) => need(c, "appWebhookId") && { id: c.ids.appWebhookId } }),
    V("updateAppWebhookRegistration", { input: (c) => need(c, "appWebhookId") && { id: c.ids.appWebhookId, status: "DISABLED" } }),
    V("getAppWebhookRegistrationStats", { input: (c) => need(c, "appWebhookId") && { id: c.ids.appWebhookId } }),
    V("generateAppWebhookRegistrationUrl", { input: (c) => need(c, "appWebhookId") && { id: c.ids.appWebhookId } }),
    V("deleteAppWebhookRegistration", { input: (c) => need(c, "appWebhookId") && { id: c.ids.appWebhookId } }),
    V("listAppEventTriggers"),
    V("listConnectorEvents", { input: (c) => need(c, "anyConnector") && { connectorId: c.ids.anyConnector.id } }),
    V("listConnectorWebhookConfigEvents", { input: (c) => need(c, "anyConnector") && { connectorId: c.ids.anyConnector.id } }),
    V("createAppEventTrigger", { input: (c) => need(c, "connectorId") && { name: `sdk sweep ${run}`, status: "DISABLED", connectorId: c.ids.connectorId, connectorName: c.ids.connectorSlug, type: "WEBHOOK", events: [{ id: "ping.received", label: "Ping received" }] }, after: (r, c) => { c.ids.appTriggerId = dataOf(r)?.id; return `app trigger ${c.ids.appTriggerId}`; }, expect: [400, 422] }),
    V("getAppEventTrigger", { input: (c) => need(c, "appTriggerId") && { id: c.ids.appTriggerId } }),
    V("updateAppEventTrigger", { input: (c) => need(c, "appTriggerId") && { id: c.ids.appTriggerId, name: `sdk sweep ${run} (renamed)` } }),
    V("getAppEventTriggerStats", { input: (c) => need(c, "appTriggerId") && { id: c.ids.appTriggerId } }),
    V("retryTriggerSubscription", { input: (c) => need(c, "appTriggerId") && { id: c.ids.appTriggerId }, expect: [400, 404, 409, 422] }),
    V("sendTestAppEvent", { input: (c) => need(c, "orgId", "connectorId") && { orgId: c.ids.orgId, connectorId: c.ids.connectorId, triggerId: c.ids.appTriggerId, payload: { event: "ping.received", sweep: run } }, expect: [400, 404, 422] }),
    V("bulkDeleteAppEventTriggers", { input: (c) => need(c, "appTriggerId") && { ids: [c.ids.appTriggerId] } }),
    V("deleteAppEventTrigger", { input: (c) => need(c, "appTriggerId") && { id: c.ids.appTriggerId }, expect: [404], note: "already removed by bulk delete" }),
    V("getInstallationTriggers", { input: (c) => need(c, "installationId") && { id: c.ids.installationId }, note: "installation from the Embed block (deleted there if Embed ran first)", expect: [404] }),
    V("createInstallationTrigger", { input: (c) => need(c, "installationId", "webhookTriggerId") && { id: c.ids.installationId, templateTriggerId: c.ids.webhookTriggerId }, expect: [400, 404, 422] }),
    V("updateInstallationTrigger", { input: (c) => need(c, "installationId", "webhookTriggerId") && { id: c.ids.installationId, triggerId: c.ids.webhookTriggerId, settings: { name: "x" } }, expect: [400, 404] }),
    V("deleteInstallationTrigger", { input: (c) => need(c, "installationId", "webhookTriggerId") && { id: c.ids.installationId, triggerId: c.ids.webhookTriggerId }, expect: [400, 404] }),
    V("deleteEventSubscription", { input: (c) => need(c, "subId") && { id: c.ids.subId } }),
  ];
}

export function workflowsPlan(ctx: Ctx, S: Mk): Step[] {
  const W = S("Workflows");
  const run = ctx.run;
  const code = `export default async function (input) { return { ok: true, echo: input, sweep: "${run}" }; }`;
  return [
    W("listWorkflows", { after: (r) => `${list(r).length} workflows` }),
    W("listWorkflowCategories"), W("listWorkflowLabels"),
    W("createWorkflowCategory", { input: { name: `sdk sweep ${run}`, colour: "brand" }, after: (r, c) => { c.ids.categoryId = dataOf(r)?.id; return `category ${c.ids.categoryId}`; } }),
    W("updateWorkflowCategory", { input: (c) => need(c, "categoryId") && { id: c.ids.categoryId, name: `sdk sweep ${run} (renamed)` } }),
    W("createWorkflowLabel", { input: { name: `sdk-sweep-${run}`, colour: "chart-1" }, after: (r, c) => { c.ids.labelId = dataOf(r)?.id; return `label ${c.ids.labelId}`; } }),
    W("updateWorkflowLabel", { input: (c) => need(c, "labelId") && { id: c.ids.labelId, colour: "chart-2" } }),
    W("runWorkflowCode", { input: { code, input: { hello: "world" }, mockMode: true }, expect: [400, 402, 422] }),
    W("createWorkflow", { input: (c) => ({ slug: `sdk_sweep_${run}`, name: `SDK sweep ${run}`, description: "throw-away workflow", code, categoryId: c.ids.categoryId ?? null, executionTier: "instant", enabled: true }), after: (r, c) => { c.ids.workflowId = dataOf(r)?.id; return `workflow ${c.ids.workflowId}`; } }),
    W("getWorkflow", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId } }),
    W("updateWorkflow", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId, description: "updated by the sweep" } }),
    W("saveWorkflowDraft", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId, code: code.replace("ok: true", "ok: true, draft: true") } }),
    W("editWorkflowCode", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId, oldString: "draft: true", newString: "draft: false" }, expect: [400, 404, 409] }),
    W("setWorkflowLabels", { input: (c) => need(c, "workflowId", "labelId") && { id: c.ids.workflowId, labelIds: [c.ids.labelId] } }),
    W("getWorkflowConnectorManifest", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId } }),
    W("refreshWorkflowManifest", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId } }),
    W("setWorkflowConnectorScope", { input: (c) => need(c, "workflowId", "connectorSlug") && { id: c.ids.workflowId, slug: c.ids.connectorSlug, scope: "SAAS" }, expect: [400, 404] }),
    W("saveWorkflowValidation", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId, status: "pass", mode: "mock", results: [{ id: "t1", status: "pass" }] } }),
    W("createTestCaseDraft", { input: (c) => need(c, "workflowId") && { scope: c.ids.workflowId, testCases: [{ id: "t1", group: "basic", scenario: "returns ok", pass: "ok is true", mode: "mock" }] }, after: (r, c) => { c.ids.testDraftId = dataOf(r)?.draftId ?? dataOf(r)?.id; return `draft ${c.ids.testDraftId}`; }, expect: [400, 422] }),
    W("getTestCaseDraft", { input: (c) => need(c, "testDraftId") && { id: c.ids.testDraftId } }),
    W("testSavedWorkflow", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId, input: { hello: "test" }, mockMode: true }, expect: [400, 402, 422] }),
    W("publishWorkflow", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId, message: "sweep" }, after: (r, c) => { const d = dataOf(r); c.ids.versionId = d?.versionId ?? d?.version?.id ?? d?.id; return `published ${c.ids.versionId}`; }, expect: [400, 409] }),
    W("listWorkflowVersions", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId }, after: (r, c) => { const v = list(r)[0]; if (!c.ids.versionId) c.ids.versionId = v?.id; return `${list(r).length} versions`; } }),
    W("getWorkflowVersion", { input: (c) => need(c, "workflowId", "versionId") && { id: c.ids.workflowId, versionId: c.ids.versionId } }),
    W("executeWorkflow", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId, input: { hello: "execute" } }, after: (r, c) => { const d = dataOf(r); c.ids.wfExecutionId = d?.executionId ?? d?.id; return `execution ${c.ids.wfExecutionId}`; }, expect: [400, 402, 404, 409, 422] }),
    W("listExecutions", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId }, after: (r, c) => { if (!c.ids.wfExecutionId) c.ids.wfExecutionId = list(r)[0]?.id; return `${list(r).length} executions`; } }),
    W("listWorkflowExecutions", { input: { limit: 5 } }),
    W("getWorkflowExecutionCounts"),
    W("searchExecutionLogs", { input: { limit: 5 } }),
    W("getWorkflowExecution", { input: (c) => need(c, "workflowId", "wfExecutionId") && { id: c.ids.workflowId, executionId: c.ids.wfExecutionId } }),
    W("getExecutionLogs", { input: (c) => need(c, "workflowId", "wfExecutionId") && { id: c.ids.workflowId, executionId: c.ids.wfExecutionId } }),
    W("replayExecution", { input: (c) => need(c, "workflowId", "wfExecutionId") && { id: c.ids.workflowId, executionId: c.ids.wfExecutionId }, expect: [400, 404, 409] }),
    W("submitWorkflowExecutionFeedback", { input: (c) => need(c, "wfExecutionId") && { executionId: c.ids.wfExecutionId, helpful: true, comment: "sweep" }, expect: [400, 404] }),
    W("cancelWorkflowExecution", { input: (c) => need(c, "workflowId", "wfExecutionId") && { id: c.ids.workflowId, executionId: c.ids.wfExecutionId }, expect: [400, 404, 409] }),
    W("listWorkflowDeployments", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId } }),
    W("deployWorkflowVersion", { input: (c) => need(c, "workflowId", "versionId", "liveEnvId") && { id: c.ids.workflowId, env_id: c.ids.liveEnvId, version_id: c.ids.versionId }, expect: [400, 403, 409] }),
    W("promoteWorkflow", { input: (c) => need(c, "workflowId", "versionId", "liveEnvId") && { id: c.ids.workflowId, env_id: c.ids.liveEnvId, version_id: c.ids.versionId, message: "sweep" }, after: (r, c) => { c.ids.promotionId = dataOf(r)?.id ?? dataOf(r)?.promotionId; }, expect: [400, 403, 409] }),
    W("listWorkflowPromotions", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId } }),
    W("cancelWorkflowPromotion", { input: (c) => need(c, "workflowId", "promotionId") && { id: c.ids.workflowId, promotionId: c.ids.promotionId }, expect: [400, 404, 409] }),
    W("rollbackWorkflowDeployment", { input: (c) => need(c, "workflowId", "liveEnvId") && { id: c.ids.workflowId, env_id: c.ids.liveEnvId, env_version: 1 }, expect: [400, 403, 404, 409] }),
    W("generateWorkflowDocs", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId, audience: "technical" }, expect: [400, 402, 409], note: "LLM call" }),
    W("getWorkflowDocs", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId }, expect: [404] }),
    W("listWorkflowDocVersions", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId }, after: (r, c) => { c.ids.docVersionId = list(r)[0]?.id; } }),
    W("getWorkflowDocVersion", { input: (c) => need(c, "workflowId", "docVersionId") && { id: c.ids.workflowId, versionId: c.ids.docVersionId } }),
    W("listWorkflowDiffReports", { input: { limit: 5 } }), W("listWorkflowStateKeys", { input: { limit: 5 } }), W("listWorkflowTables"),
    W("forkWorkflow", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId, name: `SDK sweep ${run} fork` }, after: (r, c) => { c.ids.workflowForkId = dataOf(r)?.id; }, expect: [400, 409] }),
    W("getGithubIntegrationStatus"),
    W("listGithubRepositories", { expect: [400, 404, 409] }), W("listGithubReviews", { expect: [400, 404, 409] }),
    W("setGithubPublishGate", { input: { gatePublish: false }, expect: [400, 404, 409] }),
    W("startGithubInstallation", { input: { returnUrl: "https://example.com/done" }, expect: [400, 404, 409] }),
    W("syncWorkflowsToGithub", { expect: [400, 404, 409] }),
    W("cancelGithubSync", { input: { syncId: "sync_missing" }, expect: [400, 404] }),
    W("disconnectGithubIntegration", { expect: [400, 404, 409] }),
    // cleanup
    W("deleteWorkflow", { input: (c) => need(c, "workflowForkId") && { id: c.ids.workflowForkId }, note: "the fork" }),
    W("deleteWorkflow", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId } }),
    W("restoreWorkflow", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId }, expect: [400, 404, 409] }),
    W("deleteWorkflow", { input: (c) => need(c, "workflowId") && { id: c.ids.workflowId }, expect: [404], note: "again after restore" }),
    W("deleteWorkflowLabel", { input: (c) => need(c, "labelId") && { id: c.ids.labelId } }),
    W("deleteWorkflowCategory", { input: (c) => need(c, "categoryId") && { id: c.ids.categoryId } }),
  ];
}

export function unifiedPlan(ctx: Ctx, S: Mk): Step[] {
  const X = S("Unified API");
  const run = ctx.run;
  const customer = !!ctx.customerRef;
  return [
    X("listUnifiedCategories", { after: (r, c) => { c.ids.unifiedCategory = list(r).find((x) => x.id === "crm" || x.slug === "crm") ?? list(r)[0]; return `${list(r).length} categories`; } }),
    X("listUnifiedCatalogCategories"),
    X("listUnifiedCatalogEntities", { after: (r, c) => { const rows = list(r); c.ids.catalogEntity = rows.find((e: any) => e.slug === "contact" || e.entity === "contact") ?? rows[0]; return `${rows.length} entities`; } }),
    X("getUnifiedCatalogEntity", { input: (c) => need(c, "catalogEntity") && { id: c.ids.catalogEntity.id } }),
    X("listUnifiedEntityProviders", { input: { category: "crm", entity: "contact" } }),
    X("listUnifiedCalls", { input: { correlation_id: `sdk-sweep-${run}` } }),
    // records for the test customer (needs a connected provider; otherwise 4xx is the honest answer)
    X("listUnifiedRecords", { customer, input: { category: "crm", entity: "contact", provider: "hubspot", page_size: 2 }, expect: [400, 403, 404, 422, 424], skip: customer ? undefined : "no FASTN_TEST_CUSTOMER" }),
    X("createUnifiedRecord", { customer, input: { category: "crm", entity: "contact", provider: "hubspot", record: { first_name: "Sweep", last_name: run, email: `sweep.${run}@example.com` } }, opts: { correlationId: `sdk-sweep-${run}` }, after: (r, c) => { c.ids.recordId = dataOf(r)?.id ?? r?.id; return `record ${c.ids.recordId}`; }, expect: [400, 403, 404, 422, 424], skip: customer ? undefined : "no FASTN_TEST_CUSTOMER" }),
    X("getUnifiedRecord", { customer, input: (c) => need(c, "recordId") && { category: "crm", entity: "contact", provider: "hubspot", id: c.ids.recordId } }),
    X("searchUnifiedRecords", { customer, input: { category: "crm", entity: "contact", provider: "hubspot", filters: { email: `sweep.${run}@example.com` } }, expect: [400, 403, 404, 422, 424], skip: customer ? undefined : "no FASTN_TEST_CUSTOMER" }),
    X("updateUnifiedRecord", { customer, input: (c) => need(c, "recordId") && { category: "crm", entity: "contact", provider: "hubspot", id: c.ids.recordId, record: { last_name: `${run}-updated` } } }),
    X("deleteUnifiedRecord", { customer, input: (c) => need(c, "recordId") && { category: "crm", entity: "contact", provider: "hubspot", id: c.ids.recordId }, expect: [404], note: "HubSpot contact has no delete in the unified catalog (UNIFIED_UNSUPPORTED_OPERATION); the sweep contact stays in the test portal" }),
    X("listUnifiedCalls", { input: { correlation_id: `sdk-sweep-${run}` }, note: "after the create: should list the call" }),
    // custom entities, mappings, extensions
    X("listUnifiedCustom"),
    X("createUnifiedCustomEntity", { input: (c) => ({ categoryId: c.ids.unifiedCategory?.id ?? "crm", slug: `sweep_${run}`, name: `Sweep ${run}`, schema: { title: { type: "string", label: "Title", required: true } } }), after: (r, c) => { c.ids.customEntityId = dataOf(r)?.id; return `custom entity ${c.ids.customEntityId}`; }, expect: [400, 422] }),
    X("updateUnifiedCustomEntity", { input: (c) => need(c, "customEntityId") && { id: c.ids.customEntityId, description: "updated" } }),
    X("createUnifiedCustomMapping", { input: (c) => need(c, "customEntityId", "connectorSlug") && { id: c.ids.customEntityId, connectorSlug: c.ids.connectorSlug, enabled: true, operations: { list: { actionSlug: c.ids.actionSlug ?? "ping", recordsPath: "$.json", remoteIdPath: "$.id" } } }, after: (r, c) => { c.ids.mappingId = dataOf(r)?.id; return `mapping ${c.ids.mappingId}`; }, expect: [400, 404, 422] }),
    X("updateUnifiedCustomMapping", { input: (c) => need(c, "mappingId") && { id: c.ids.mappingId, enabled: false } }),
    X("testUnifiedCustomEntity", { input: (c) => need(c, "customEntityId", "connectorSlug") && { id: c.ids.customEntityId, op: "list", provider: c.ids.connectorSlug }, expect: [400, 404, 422, 424] }),
    X("upsertUnifiedExtension", { input: (c) => need(c, "catalogEntity") && { entityId: c.ids.catalogEntity.id, schema: { sweep_note: { type: "string", label: "Sweep note" } } }, expect: [400, 404, 422] }),
    X("deleteUnifiedExtension", { input: (c) => need(c, "catalogEntity") && { entityId: c.ids.catalogEntity.id }, expect: [404] }),
    X("deleteUnifiedCustomMapping", { input: (c) => need(c, "mappingId") && { id: c.ids.mappingId } }),
    X("deleteUnifiedCustomEntity", { input: (c) => need(c, "customEntityId") && { id: c.ids.customEntityId } }),
    X("loadUnifiedConfigFieldOptions", { input: (c) => need(c, "anyWidgetId", "catalogEntity") && { widgetId: c.ids.anyWidgetId, entityId: c.ids.catalogEntity.id, connectorSlug: "hubspot", fieldKey: "owner" }, expect: [400, 404, 422, 424] }),
    X("updateInstallationUnifiedValues", { input: { id: "inst_missing", unifiedValues: {} }, expect: [404] }),
  ];
}
