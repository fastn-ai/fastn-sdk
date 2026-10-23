// Proves customer scoping end to end on an environment where a throw-away connector can be made: a connection stored
// with typed-in credentials through customer.connectWithCredentials() lands on the customer org, is listed by
// customer.connections(), and is not listed as one of the partner's own connections. Skipped when the environment's
// connector quota refuses a new connector (reported in the evidence).
// Env: LIVE=1, FASTN_API_KEY, FASTN_TEST_CUSTOMER; FASTN_BASE_URL (default https://api.fastn-test.dev).
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import fs from "node:fs";
import { FastnClient, FastnApiError } from "../../src/index.js";

const BASE_URL = process.env.FASTN_BASE_URL ?? "https://api.fastn-test.dev";
if (/api\.fastn\.dev/.test(BASE_URL) && process.env.LIVE_PROD !== "1") throw new Error("FASTN_BASE_URL points at production; set LIVE_PROD=1 to run the live suite there");
const LIVE = process.env.LIVE === "1" && !!process.env.FASTN_API_KEY && !!process.env.FASTN_TEST_CUSTOMER;
const d = describe.skipIf(!LIVE);
const EV = new URL("./evidence.jsonl", import.meta.url).pathname;
const ev = (step: string, data: unknown) => fs.appendFileSync(EV, JSON.stringify({ suite: "customer-scope", at: new Date().toISOString(), step, data }) + "\n");
const run = new Date().toISOString().slice(11, 19).replace(/:/g, "");
const dataOf = (r: any) => r?.data ?? r;
const E2E = process.env.FASTN_TEST_CUSTOMER ?? "";

let fastn: FastnClient;
let connectorId: string | undefined, connectionId: string | undefined, quotaBlocked = "";
beforeAll(() => { fastn = new FastnClient({ apiKey: process.env.FASTN_API_KEY!, baseUrl: BASE_URL }); });
afterAll(async () => {
  if (connectionId) await fastn.connections.deleteConnections({ id: connectionId }).catch((e) => ev("cleanup connection", e.message));
  if (connectorId) await fastn.connectors.deleteConnector({ id: connectorId }).catch((e) => ev("cleanup connector", e.message));
});

d("customer scope: a credential connection lands on the customer, not the partner", () => {
  it("makes a throw-away API-key connector (or records why it cannot)", async () => {
    try {
      const c = dataOf(await fastn.connectors.createConnector({
        name: `SDK scope ${run}`, slug: `sdkScope${run}`, domain: "https://httpbin.org", visibility: "private",
        authMethods: [{ type: "API_KEY", title: "API key", isDefault: true, inputContract: { type: "object", properties: { apiKey: { type: "string" } }, required: ["apiKey"] }, authConfig: { apiKeyName: "X-Api-Key" } }],
      } as any));
      connectorId = c.id; ev("connector", { id: c.id, slug: c.slug });
    } catch (e) {
      if (e instanceof FastnApiError && (e.code === "quota_exceeded" || e.status === 403)) { quotaBlocked = e.message; ev("connector", `cannot create a connector here: ${e.message}`); return; }
      throw e;
    }
    expect(connectorId).toBeTruthy();
  });
  it("authFields() reads the credential fields from the auth method", async (t) => {
    if (!connectorId) { t.skip(); return; }
    const f = await fastn.customer(E2E).authFields(connectorId);
    ev("authFields", f);
    expect(f.names).toContain("apiKey"); expect(f.required).toContain("apiKey"); expect(f.authType).toMatch(/API_KEY/i);
  });
  it("connectWithCredentials() checks required fields, then stores the connection on the customer org", async (t) => {
    if (!connectorId) { t.skip(); return; }
    const customer = fastn.customer(E2E);
    await expect(customer.connectWithCredentials({ connectorId, credentials: {} })).rejects.toThrow(/missing credential field/);
    const stored = dataOf(await customer.connectWithCredentials({ connectorId, credentials: { apiKey: `scope-${run}` }, name: `sdk-scope-${run}` }));
    connectionId = stored.id ?? stored.connectionId ?? stored.connections?.[0]?.id;
    ev("stored", { id: connectionId, endOrgId: stored.endOrgId ?? stored.orgId });
    expect(connectionId).toBeTruthy();
    const mine = dataOf(await customer.connections()) as any[];
    const partnerOwn = dataOf(await fastn.connections.listConnections({ connectorId } as any)) as any[];
    ev("where it landed", { customerHasIt: mine.some((x) => x.id === connectionId), partnerListHasIt: partnerOwn.some((x) => x.id === connectionId), customerId: await customer.id() });
    expect(mine.some((x) => x.id === connectionId)).toBe(true);
    expect(partnerOwn.some((x) => x.id === connectionId && !x.endOrgId && !x.end_org_id)).toBe(false);
  });
  it("connect() returns an OAuth URL for the customer, or the platform's reason why not", async (t) => {
    if (!connectorId) { t.skip(); return; }
    const r = await fastn.customer(E2E).connect({ connectorId, connectionName: `sdk-scope-oauth-${run}`, returnUrl: "https://example.com/done" }).catch((e: FastnApiError) => e);
    if (r instanceof FastnApiError) { ev("connect", { status: r.status, message: r.message }); expect(r.status).toBeLessThan(500); expect(r.message).toMatch(/OAuth|oauth/); }
    else { ev("connect", { authorizationUrl: !!dataOf(r).authorizationUrl }); expect(dataOf(r).authorizationUrl).toMatch(/^https:/); }
  });
});
