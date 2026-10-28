import { describe, it, expect } from "vitest";
import { FastnClient, FastnApiError, EVENT_ALIASES } from "../../src/index.js";
import { mockFetch, type Reply } from "../helpers.js";

const orgRow = { id: "11111111-aaaa", externalRef: "acme-1", orgId: "acme-1", name: "Acme", type: "end_org", parentId: "partner-1" };
const hsConn = { id: "ucl:p:1:9036:default", name: "Main CRM", connectorId: "9036", connector: { slug: "hubspot", name: "HubSpot" }, status: "ACTIVE" };
const calConn = { id: "ucl:p:1:867f:default", name: "Main calendar", connectorId: "867f", connector: { slug: "googleCalendar", name: "Google Calendar" }, status: "ACTIVE" };
const events = [{ id: "contact.creation", label: "Contact Created" }, { id: "contact.propertyChange", label: "Contact Property Changed" }, { id: "deal.propertyChange", label: "Deal Property Changed" }];
const base = (url: string, init: any): Reply => {
  if (url.endsWith("/v1/me")) return { body: { data: { actor: "api_key", org: { id: "partner-1" } } } };
  if (url.includes("/v1/orgs?")) return { body: { data: [orgRow] } };
  if (url.includes("/v1/connectors?")) return { body: { data: [{ id: "9036", slug: "hubspot", name: "HubSpot" }] } };
  if (url.includes("/v1/connections?")) return { body: { data: [hsConn, calConn] } };
  if (url.includes("/connector-events") || url.includes("/events?connectorId") || /connectors\/9036\/events/.test(url)) return { body: { data: events } };
  // the API nests the app part of a trigger under appTrigger (seen live on prod)
  if (url.includes("/app-triggers") && init.method === "POST") return { status: 201, body: { data: { id: "trg-1", name: "x", status: "ACTIVE", endOrgId: "11111111-aaaa", appTrigger: { triggerId: "trg-1", type: "WEBHOOK", connectorId: "9036", connectionId: hsConn.id, accountId: "245765780", events: [{ id: "contact.creation", label: "Contact Created" }] } } } };
  if (url.includes("/app-triggers?")) return { body: { data: [{ id: "trg-1", status: "ACTIVE", endOrgId: "11111111-aaaa", appTrigger: { connectorId: "9036", events: [{ id: "contact.creation" }] } }, { id: "trg-2", status: "ACTIVE", appTrigger: { connectorId: "other", events: [] } }] } };
  return { body: { data: {} } };
};
const client = (m: ReturnType<typeof mockFetch>) => new FastnClient({ apiKey: "k", fetch: m.fetch });

describe("watch / unwatch", () => {
  it("maps plain event names to the app's ids, pins the customer's account, sends the trigger, answers a Watch without internal ids", async () => {
    const m = mockFetch(base);
    const w = await client(m).customer("acme-1").watch("hubspot", ["contact.created", "deal.stageChanged", "contact.propertyChange"], { accountId: "245765780" });
    const post = m.calls.find((x) => x.init.method === "POST")!;
    expect(post.url).toContain("/app-triggers");
    expect(post.json).toMatchObject({ connectorId: "9036", connectorName: "HubSpot", connectionId: hsConn.id, accountId: "245765780", type: "WEBHOOK", routes: [], status: "ACTIVE", endOrgId: "11111111-aaaa", name: "hubspot changes for acme-1" });
    expect(post.json.events.map((e: any) => e.id)).toEqual(["contact.creation", "deal.propertyChange", "contact.propertyChange"]);
    expect(w).toMatchObject({ id: "trg-1", app: "hubspot", events: ["contact.creation"], accountId: "245765780" });
    expect(w).not.toHaveProperty("endOrgId");
  });
  it("refuses an unknown event name with the valid list, and an empty list", async () => {
    const m = mockFetch(base);
    const err = await client(m).customer("acme-1").watch("hubspot", ["contact.exploded" as any]).catch((e) => e);
    expect(err).toBeInstanceOf(FastnApiError); expect(err.code).toBe("EVENT_NOT_FOUND"); expect(err.message).toContain("contact.created"); expect(err.message).toContain("contact.creation");
    expect(m.calls.some((x) => x.init.method === "POST")).toBe(false);
    await expect(client(m).customer("acme-1").watch("hubspot", [])).rejects.toThrow(TypeError);
  });
  it("no account on the app -> 404 CONNECTION_NOT_FOUND; two accounts -> 409 unless connectionId is given", async () => {
    const none = mockFetch((url, init) => url.includes("/v1/connections?") ? { body: { data: [calConn] } } : base(url, init));
    await expect(client(none).customer("acme-1").watch("hubspot", ["contact.created"])).rejects.toMatchObject({ code: "CONNECTION_NOT_FOUND", status: 404 });
    const two = mockFetch((url, init) => url.includes("/v1/connections?") ? { body: { data: [hsConn, { ...hsConn, id: "ucl:p:1:9036:second" }] } } : base(url, init));
    await expect(client(two).customer("acme-1").watch("hubspot", ["contact.created"])).rejects.toMatchObject({ code: "CONNECTION_AMBIGUOUS", status: 409 });
    const w = await client(two).customer("acme-1").watch("hubspot", ["contact.created"], { connectionId: "ucl:p:1:9036:second" });
    expect(w.id).toBe("trg-1");
    expect(two.calls.find((x) => x.init.method === "POST")!.json.connectionId).toBe("ucl:p:1:9036:second");
  });
  it("watches(app) lists only that app's triggers for the customer; unwatch(app) deletes them, unwatch(id) deletes one", async () => {
    const m = mockFetch(base);
    const c = client(m).customer("acme-1");
    const list = await c.watches("hubspot");
    expect(list.map((w) => w.id)).toEqual(["trg-1"]); expect(list[0]).not.toHaveProperty("endOrgId");
    expect(m.urls().find((u) => u.includes("/app-triggers?"))).toBe("/v1/app-triggers?end_org_id=11111111-aaaa");   // no connectorId query: the API does not match it against the nested app part
    expect(list[0]).not.toHaveProperty("appTrigger"); expect(list[0].connectionId).toBeUndefined();
    expect(await c.unwatch("hubspot")).toEqual(["trg-1"]);
    expect(await c.unwatch("3ffc9b08-0000-4000-8000-000000000000")).toEqual(["3ffc9b08-0000-4000-8000-000000000000"]);
    expect(m.calls.filter((x) => x.init.method === "DELETE").map((x) => x.url.replace("https://api.fastn.dev", ""))).toEqual(["/v1/app-triggers/trg-1", "/v1/app-triggers/3ffc9b08-0000-4000-8000-000000000000"]);
  });
  it("the connector row is read once per client", async () => {
    const m = mockFetch(base);
    const fastn = client(m);
    await fastn.customer("acme-1").watchableEvents("hubspot");
    await fastn.customer("acme-1").watchableEvents("hubspot");
    expect(m.urls().filter((u) => u.includes("/v1/connectors?")).length).toBe(1);
  });
  it("EVENT_ALIASES covers the pilot's names", () => {
    expect(EVENT_ALIASES.hubspot["deal.stageChanged"]).toBe("deal.propertyChange");
    expect(EVENT_ALIASES.hubspot["contact.created"]).toBe("contact.creation");
  });
});

describe("disconnect, renameAccount, update, callLog, webhooks", () => {
  it("map to the raw routes with the customer's fastn id where the route needs it", async () => {
    const m = mockFetch((url, init) => url.includes("/unified/calls") ? { body: { data: [{ id: "ucall_1", correlationId: "c1", operation: "create", endOrgId: "11111111-aaaa", status: 201 }] } } : base(url, init));
    const c = client(m).customer("acme-1");
    await c.disconnect(hsConn.id);
    await c.renameAccount(hsConn.id, "Front desk");
    await c.update({ name: "Acme Dental Ltd", status: "suspended" });
    const log = await c.callLog("c1");
    expect(log).toEqual([{ id: "ucall_1", correlationId: "c1", operation: "create", status: 201 }]);   // no internal customer id
    const calls = m.calls.filter((x) => !x.url.endsWith("/v1/me") && !x.url.includes("/v1/orgs?")).map((x) => `${x.init.method} ${x.url.replace("https://api.fastn.dev", "")} ${JSON.stringify(x.json ?? null)}`);
    expect(calls).toEqual([
      `DELETE /v1/connections/${encodeURIComponent(hsConn.id)} null`,
      `PUT /v1/connections/${encodeURIComponent(hsConn.id)} {"name":"Front desk"}`,
      `PUT /v1/orgs/11111111-aaaa {"name":"Acme Dental Ltd","status":"suspended"}`,
      `GET /v1/unified/calls?correlation_id=c1 null`,
    ]);
    await expect(c.disconnect("")).rejects.toThrow(TypeError);
    await expect(c.callLog("")).rejects.toThrow(TypeError);
  });
  it("fastn.webhooks wraps the subscription routes and answers the data", async () => {
    const m = mockFetch((url, init) => url.includes("/event-subscriptions") && init.method === "POST" && !/\/test$|\/rotate/.test(url) ? { status: 201, body: { data: { id: "esub_1", secret: "whsec_x" } } } : url.includes("/deliveries") ? { body: { data: [{ id: "evd_1", status: "delivered" }] } } : url.endsWith("/event-subscriptions") ? { body: { data: [{ id: "esub_1" }] } } : { body: { data: { id: "esub_1", ok: true } } });
    const fastn = client(m);
    const made = await fastn.webhooks.create({ url: "https://hooks.example.com/f", eventTypes: ["connection.connected"] });
    expect(made.secret).toBe("whsec_x");
    expect((await fastn.webhooks.list()).map((s: any) => s.id)).toEqual(["esub_1"]);
    await fastn.webhooks.get("esub_1"); await fastn.webhooks.update("esub_1", { description: "d" }); await fastn.webhooks.test("esub_1"); await fastn.webhooks.rotateSecret("esub_1");
    expect((await fastn.webhooks.deliveries("esub_1", { limit: 5, status: "delivered" }))[0].id).toBe("evd_1");
    await fastn.webhooks.replay("evd_1"); await fastn.webhooks.delete("esub_1");
    expect(m.calls.map((x) => `${x.init.method} ${x.url.replace("https://api.fastn.dev", "")}`)).toEqual([
      "POST /v1/event-subscriptions", "GET /v1/event-subscriptions", "GET /v1/event-subscriptions/esub_1", "PATCH /v1/event-subscriptions/esub_1",
      "POST /v1/event-subscriptions/esub_1/test", "POST /v1/event-subscriptions/esub_1/rotate-secret", "GET /v1/event-subscriptions/esub_1/deliveries?status=delivered&limit=5",
      "POST /v1/event-subscriptions/deliveries/evd_1/replay", "DELETE /v1/event-subscriptions/esub_1",
    ]);
  });
});
