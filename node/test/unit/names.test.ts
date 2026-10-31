import { describe, it, expect } from "vitest";
import { Apps, Categories, Entities, HubSpotEvents, EventTypes, UnifiedActions, EVENT_ALIASES, FastnClient, parseEvent, signEventBody } from "../../src/index.js";
import { readFileSync } from "node:fs";
import { requireName } from "../../src/names.js";
import { mockFetch } from "../helpers.js";

describe("named apps, categories, entities and events", () => {
  it("each name is the exact string the API takes, so the string form and the named form send the same request", () => {
    expect(Apps.googleCalendar).toBe("googleCalendar");
    expect(Apps.hubspot).toBe("hubspot");
    expect(Categories.knowledgeBase).toBe("knowledge_base");
    expect(Entities.engagementType).toBe("engagement_type");
    for (const [k, v] of Object.entries(Apps)) expect(k).toBe(v);
  });

  it("HubSpotEvents lists exactly the plain names the SDK maps to HubSpot's event ids", () => {
    expect(new Set(Object.values(HubSpotEvents))).toEqual(new Set(Object.keys(EVENT_ALIASES.hubspot!)));
  });

  it("catalog.fields(Categories.crm, Entities.contact) calls the same route as the strings", async () => {
    const entity = { slug: "contact", operations: [], createFields: [{ field: "email", label: "Email", type: "string", required: false }] };
    const m = mockFetch((url) => url.includes("/unified/categories") ? { body: { data: [{ slug: "crm", entities: [entity] }] } } : { status: 404, body: {} });
    const fastn = new FastnClient({ apiKey: "k", fetch: m.fetch, retries: 0 });
    const named = await fastn.catalog.fields(Categories.crm, Entities.contact);
    const plain = await fastn.catalog.fields("crm", "contact");
    expect(named).toEqual(plain);
    expect(named[0]!.field).toBe("email");
  });

  it("a missing name (a misspelt member in plain JavaScript is undefined) throws a clear TypeError before any request", async () => {
    const m = mockFetch(() => ({ body: { data: [] } }));
    const c = new FastnClient({ apiKey: "k", fetch: m.fetch, retries: 0 }).customer("acme-1");
    const missing = (Apps as any).googleCalender;   // undefined
    await expect(c.connect(missing)).rejects.toThrow(/connect\(app\): got undefined/);
    await expect(c.watch(missing, ["contact.created"])).rejects.toThrow(/watch\(app, events\): got undefined/);
    await expect(c.unwatch(missing)).rejects.toThrow(/unwatch\(appOrWatchId\): got undefined/);
    await expect(c.unwatch("")).rejects.toThrow(/got an empty string/);     // never "every app"
    await expect(c.watchableEvents(missing)).rejects.toThrow(TypeError);
    await expect(c.catalog.fields((Categories as any).crmm, Entities.contact)).rejects.toThrow(/catalog.fields/);
    expect(m.calls.length).toBe(0);
    expect(requireName("googleCalendar", "x")).toBe("googleCalendar");
  });

  it("EventTypes are exactly the event types the API spec lists for webhooks, plus endpoint.test", () => {
    const spec = JSON.parse(readFileSync(new URL("../../spec/openapi-v1.8.2.json", import.meta.url), "utf8"));
    let fromSpec: string[] = [];
    const walk = (o: any): void => { if (o && typeof o === "object") { if (Array.isArray(o.enum) && o.enum.includes("connection.connected")) fromSpec = o.enum; Object.values(o).forEach(walk); } };
    walk(spec);
    expect(new Set(Object.values(EventTypes))).toEqual(new Set([...fromSpec, "endpoint.test"]));
    expect(Object.values(UnifiedActions)).toEqual(["created", "updated", "deleted"]);
  });

  it("a parsed event compares equal to the named values", () => {
    const body = JSON.stringify({ id: "evt_1", type: "connection.connected", app: "hubspot", tenantRef: "acme-1" });
    const ts = Math.floor(Date.now() / 1000);
    const ev = parseEvent("whsec_t", { "x-fastn-timestamp": String(ts), "x-fastn-signature": signEventBody("whsec_t", ts, body) }, body);
    expect(ev.type).toBe(EventTypes.connectionConnected);
    expect(ev.app).toBe(Apps.hubspot);
  });
});
