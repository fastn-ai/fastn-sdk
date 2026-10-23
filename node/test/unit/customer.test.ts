import { describe, it, expect, vi } from "vitest";
import { FastnClient } from "../../src/index.js";

function fx(handler: (url: string, init: any) => { status?: number; body: unknown } | undefined) {
  const calls: { url: string; init: any }[] = [];
  const fetch = vi.fn(async (url: string, init: any) => {
    calls.push({ url, init });
    if (url.endsWith("/v1/me")) return new Response(JSON.stringify({ data: { actor: "api_key", org: { id: "partner-1", type: "partner" } } }), { status: 200, headers: { "content-type": "application/json" } });
    const r = handler(url, init) ?? { body: { data: {} } };
    return new Response(JSON.stringify(r.body), { status: r.status ?? 200, headers: { "content-type": "application/json" } });
  });
  return { fetch: fetch as unknown as typeof globalThis.fetch, calls, urls: () => calls.map((x) => x.url.replace("https://api.fastn.dev", "")) };
}
const orgRow = { id: "11111111-aaaa", externalRef: "acme-1", orgId: "acme-1", name: "Acme", type: "end_org", parentId: "partner-1" };
const foreignRow = { id: "99999999-zzzz", externalRef: "acme-1", orgId: "acme-1", name: "Other partner's Acme", type: "end_org", parentId: "partner-2" };

describe("customer context", () => {
  it("resolves fastn's org id under the caller's org only and caches it on the client", async () => {
    const m = fx((url) => url.includes("/v1/orgs?") ? { body: { data: [orgRow] } } : url.includes("/v1/connections") ? { body: { data: [{ id: "conn_1" }] } } : { body: { data: orgRow } });
    const fastn = new FastnClient({ apiKey: "k", fetch: m.fetch });
    const c = fastn.customer("acme-1");
    expect(await c.id()).toBe("11111111-aaaa");
    await c.connections(); await c.get();
    await fastn.customer("acme-1").get();                       // a second object for the same ref: no new lookup
    expect(m.urls()).toEqual(["/v1/me", "/v1/orgs?type=end_org&parent_id=partner-1", "/v1/connections?endOrgId=11111111-aaaa", "/v1/orgs/11111111-aaaa", "/v1/orgs/11111111-aaaa"]);
  });
  it("never matches another partner's customer, even when the key sees every org", async () => {
    const m = fx((url) => url.includes("/v1/orgs?") ? { body: { data: [foreignRow] } } : undefined);
    await expect(new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("acme-1").id()).rejects.toThrow(/not registered/);
  });
  it("register creates once and returns the existing org afterwards", async () => {
    let created = false;
    const m = fx((url, init) => {
      if (url.includes("/v1/orgs?type=end_org")) return { body: { data: created ? [orgRow] : [] } };
      if (init.method === "POST") { created = true; return { status: 201, body: { data: orgRow } }; }
      return { body: {} };
    });
    const c = new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("acme-1");
    const first = await c.register({ name: "Acme" });
    expect(first.data.id).toBe("11111111-aaaa"); expect(JSON.parse(m.calls[2].init.body)).toEqual({ plan: "free", name: "Acme", orgId: "acme-1" });
    const again = await c.register({ name: "Acme" });
    expect(again.existed).toBe(true); expect(m.calls.filter((x) => x.init.method === "POST").length).toBe(1);
    expect(await c.id()).toBe("11111111-aaaa"); expect(m.calls.length).toBe(4);
  });
  it("unknown ref fails clearly", async () => {
    const m = fx(() => ({ body: { data: [] } }));
    await expect(new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("ghost").id()).rejects.toThrow(/not registered/);
  });
  it("remove suspends then deletes; a failed delete puts the org back to active and says so", async () => {
    const m = fx((url, init) => url.includes("/v1/orgs?") ? { body: { data: [orgRow] } } : init.method === "DELETE" ? { status: 503, body: { error: "down" } } : { body: { data: orgRow } });
    const c = new FastnClient({ apiKey: "k", fetch: m.fetch, retries: 0 }).customer("acme-1");
    await expect(c.remove()).rejects.toThrow(/suspended before the delete; it is active again/);
    const writes = m.calls.filter((x) => x.init.method !== "GET").map((x) => `${x.init.method} ${x.url.replace("https://api.fastn.dev", "")} ${x.init.body ?? ""}`);
    expect(writes).toEqual([
      'PUT /v1/orgs/11111111-aaaa {"status":"suspended"}', "DELETE /v1/orgs/11111111-aaaa ", 'PUT /v1/orgs/11111111-aaaa {"status":"active"}',
    ]);
  });
  it("setupLink / embedToken carry the ref; records carry x-end-org-ref", async () => {
    const m = fx(() => ({ body: { data: {} } }));
    const c = new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("acme-1");
    await c.setupLink({ widgetId: "w1", connectionName: "Google Calendar" });
    expect(JSON.parse(m.calls[0].init.body)).toEqual({ createIfMissing: true, widgetId: "w1", connectionName: "Google Calendar", externalRef: "acme-1" });
    await c.embedToken({ userId: "u1" });
    expect(JSON.parse(m.calls[1].init.body)).toEqual({ createIfMissing: true, userId: "u1", endOrgId: "acme-1" });
    const meetings = c.records({ category: "scheduling", entity: "meeting", provider: "googleCalendar" });
    await meetings.create({ title: "x" }, { idempotencyKey: "b1" });
    expect(m.calls[2].url).toBe("https://api.fastn.dev/v1/unified/scheduling/meeting?provider=googleCalendar");
    expect(m.calls[2].init.headers["x-end-org-ref"]).toBe("acme-1"); expect(m.calls[2].init.headers["idempotency-key"]).toBe("b1");
    await meetings.search({ query: "x" }); await meetings.update("m1", { title: "y" }); await meetings.delete("m1"); await meetings.get("m1"); await meetings.list({ page_size: 5 });
    expect(m.calls.slice(3).map((x) => `${x.init.method} ${x.url.replace("https://api.fastn.dev", "")}`)).toEqual([
      "POST /v1/unified/scheduling/meeting/search?provider=googleCalendar", "PATCH /v1/unified/scheduling/meeting/m1?provider=googleCalendar",
      "DELETE /v1/unified/scheduling/meeting/m1?provider=googleCalendar", "GET /v1/unified/scheduling/meeting/m1?provider=googleCalendar", "GET /v1/unified/scheduling/meeting?provider=googleCalendar&page_size=5"]);
    for (const x of m.calls.slice(3)) expect(x.init.headers["x-end-org-ref"]).toBe("acme-1");
  });
  it("customer.api fills the customer into the body where the route takes it there", async () => {
    const m = fx((url) => url.includes("/v1/orgs?") ? { body: { data: [orgRow] } } : { body: { data: { authorizationUrl: "https://accounts.example/oauth" } } });
    const fastn = new FastnClient({ apiKey: "k", fetch: m.fetch });
    const c = fastn.customer("acme-1");
    // endOrgId routes get fastn's id of the customer (resolved once)
    await c.api.connections.initiateOauthConnection({ connectorId: "googleCalendar", connectionName: "work" });
    const oauth = m.calls.find((x) => x.url.endsWith("/v1/oauth/initiate"))!;
    expect(JSON.parse(oauth.init.body)).toEqual({ connectorId: "googleCalendar", connectionName: "work", endOrgId: "11111111-aaaa" });
    expect(oauth.init.headers["x-end-org-ref"]).toBe("acme-1");
    await c.api.events.createEventSubscription({ url: "https://partner.app/hook", events: ["unified.event"] } as any);
    expect(JSON.parse(m.calls.at(-1)!.init.body).endOrgId).toBe("11111111-aaaa");
    // externalRef routes get the ref itself
    await c.api.embed.createSetupLink({ widgetId: "w1", connectionName: "x" });
    expect(JSON.parse(m.calls.at(-1)!.init.body)).toEqual({ widgetId: "w1", connectionName: "x", externalRef: "acme-1" });
    // an explicit value wins
    await c.api.connections.initiateOauthConnection({ connectorId: "hubspot", endOrgId: "other" });
    expect(JSON.parse(m.calls.at(-1)!.init.body).endOrgId).toBe("other");
    // routes without a customer field are untouched (only the header)
    await c.api.orgs.listOrgs({ type: "end_org" });
    expect(m.calls.at(-1)!.init.body).toBeUndefined();
    // connect() helper
    const r: any = await c.connect({ connectorId: "googleCalendar", returnUrl: "https://partner.app/done" });
    expect(r.data.authorizationUrl).toContain("https://");
    expect(JSON.parse(m.calls.at(-1)!.init.body)).toEqual({ connectorId: "googleCalendar", returnUrl: "https://partner.app/done", endOrgId: "11111111-aaaa" });
  });
  it("connectWithCredentials checks the auth method's fields before sending", async () => {
    const methods = { data: [{ id: "am_oauth", authType: "OAUTH_2", inputContract: {} }, { id: "am_key", authType: "API_KEY", inputContract: { type: "object", required: ["apiKey"], properties: { apiKey: { type: "string" }, region: { type: "string" } } } }] };
    const m = fx((url) => url.includes("/v1/orgs?") ? { body: { data: [orgRow] } } : url.includes("/v1/auth-methods") ? { body: methods } : { status: 201, body: { data: { id: "conn_9" } } });
    const c = new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("acme-1");
    const f = await c.authFields("acme-crm");
    expect(f).toMatchObject({ authMethodId: "am_key", authType: "API_KEY", names: ["apiKey", "region"], required: ["apiKey"] });
    await expect(c.connectWithCredentials({ connectorId: "acme-crm", credentials: { region: "eu" } })).rejects.toThrow(/missing credential field\(s\) apiKey/);
    const r: any = await c.connectWithCredentials({ connectorId: "acme-crm", credentials: { apiKey: "s3cret" }, name: "Acme CRM" });
    expect(r.data.id).toBe("conn_9");
    const sent = JSON.parse(m.calls.at(-1)!.init.body);
    expect(sent).toEqual({ connectorId: "acme-crm", credentials: { apiKey: "s3cret" }, name: "Acme CRM", authMethodId: "am_key", endOrgId: "11111111-aaaa" });
  });
  it("runAction pins the customer's own connection and installation for a raw connector action", async () => {
    const conn = { id: "ucl:p:cust:hs:default", name: "Inline CRM", connectorId: "hs-uuid", connectorSlug: "hubspot" };
    const m = fx((url) => {
      if (url.includes("/v1/orgs?")) return { body: { data: [orgRow] } };
      if (url.includes("/v1/connections")) return { body: { data: [conn] } };
      if (url.includes("/v1/installations")) return { body: { data: [{ id: "inst_other", endOrgId: "other", connections: { hubspot: "x" } }, { id: "inst_1", endOrgId: "11111111-aaaa", connections: { hubspot: conn.id } }] } };
      if (url.includes("/v2/connectors/hubspot/actions")) return { body: { data: [{ id: "act_upd", slug: "updateDeal" }] } };
      if (url.includes("/v2/connectors/slack/actions")) return { body: { data: [] } };
      if (url.includes("/v1/actions/act_upd/execute")) return { body: { data: { success: true, response: { id: "deal_1" } } } };
      return undefined;
    });
    const c = new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("acme-1");
    const r: any = await c.runAction({ connector: "hubspot", action: "updateDeal", input: { dealId: "deal_1", properties: { dealstage: "qualifiedtobuy" } } });
    expect(r.data.response.id).toBe("deal_1");
    const exec = m.calls.find((x) => x.url.endsWith("/v1/actions/act_upd/execute"))!;
    expect(JSON.parse(exec.init.body)).toEqual({ connectorId: "hs-uuid", connectionName: "Inline CRM", connectionId: conn.id, installationId: "inst_1", input: { dealId: "deal_1", properties: { dealstage: "qualifiedtobuy" } } });
    await expect(c.runAction({ connector: "hubspot", action: "noSuchAction" })).rejects.toThrow(/no action "noSuchAction"/);
    await expect(c.runAction({ connector: "slack", action: "postMessage" })).rejects.toThrow(/no slack connection/);
  });
});
