import { describe, it, expect, vi } from "vitest";
import { FastnClient, FastnApiError, freeIntervals, slotsOf, PROVIDER_TTL_MS } from "../../src/index.js";
import { mockFetch, type Reply } from "../helpers.js";

// whoami answers the partner org; the providers route answers what each test says; everything else echoes.
const providers = (rows: any[]) => ({ body: { data: rows } });
const hubspot = (ops = ["get", "list", "create", "delete", "search", "update"]) => ({ connectorSlug: "hubspot", connectorName: "HubSpot", operations: ops, connected: true, healthy: false, connectionCount: 1 });
const gcal = { connectorSlug: "googleCalendar", connectorName: "Google Calendar", operations: ["get", "list", "create", "delete", "search", "update"], connected: true, healthy: false, connectionCount: 1 };
const notConnected = { connectorSlug: "pipedrive", connectorName: "Pipedrive", operations: ["get", "list", "create"], connected: false, connectionCount: 0 };
const fx = (handler: (url: string, init: any) => Reply) => mockFetch((url, init) => url.endsWith("/v1/me") ? { body: { data: { actor: "api_key", org: { id: "partner-1" } } } } : handler(url, init));
const client = (m: ReturnType<typeof mockFetch>) => new FastnClient({ apiKey: "k", fetch: m.fetch });

describe("provider resolution", () => {
  it("find() answers one page: a cursor is refused before any request, page_size still goes on the query", async () => {
    const m = fx((url) => url.includes("/providers") ? providers([hubspot()]) : { body: { records: [], hasMore: false, provider: "hubspot" } });
    const c = client(m).customer("acme-1");
    await c.crm.contacts.find({ email: "a@b.co" }, { page_size: 5 });
    await c.crm.contacts.find({ email: "a@b.co" }, { page_size: 5, cursor: undefined } as any);   // a paging helper's first page: not a cursor
    await expect(c.crm.contacts.find({ email: "a@b.co" }, { cursor: "abc" } as any)).rejects.toThrow(/find\(\) has no cursor/);
    expect(m.urls().filter((u) => u.includes("/search")).length).toBe(2);
    expect(m.urls().at(-1)).toBe("/v1/unified/crm/contact/search?provider=hubspot&page_size=5");
  });

  it("pins the one connected provider on the call, reads the providers list once per entity, and sends the customer header", async () => {
    const m = fx((url) => url.includes("/providers") ? providers([hubspot(), notConnected]) : { body: { records: [], hasMore: false, provider: "hubspot" } });
    const fastn = client(m);
    const c = fastn.customer("acme-1");
    await c.crm.contacts.find({ email: "a@b.co" });
    await c.crm.contacts.list({ page_size: 5 });
    await fastn.customer("acme-1").crm.contacts.list();                             // another object for the same ref: no new lookup
    expect(m.urls()).toEqual([
      "/v1/unified/crm/contact/providers",
      "/v1/unified/crm/contact/search?provider=hubspot",
      "/v1/unified/crm/contact?provider=hubspot&page_size=5",
      "/v1/unified/crm/contact?provider=hubspot",
    ]);
    for (const x of m.calls) expect(x.init.headers["x-end-org-ref"]).toBe("acme-1");
    expect(m.calls[1].json).toEqual({ email: "a@b.co" });                            // the filters are the body
  });
  it("opts.provider skips the lookup; connectionId goes on the query", async () => {
    const m = fx(() => ({ body: { id: "1", provider: "pipedrive", data: {} } }));
    await client(m).customer("acme-1").crm.contacts.get("1", { provider: "pipedrive", connectionId: "conn_9" });
    expect(m.urls()).toEqual(["/v1/unified/crm/contact/1?provider=pipedrive&connection_id=conn_9"]);
  });
  it("no connected provider -> 404 NO_CONNECTED_PROVIDER; two -> 409 PROVIDER_AMBIGUOUS; none able -> OPERATION_NOT_SUPPORTED", async () => {
    const m0 = fx(() => providers([notConnected]));
    await expect(client(m0).customer("acme-1").crm.contacts.list()).rejects.toMatchObject({ code: "NO_CONNECTED_PROVIDER", status: 404 });
    const m2 = fx(() => providers([hubspot(), { ...hubspot(), connectorSlug: "salesforce" }]));
    await expect(client(m2).customer("acme-1").crm.contacts.list()).rejects.toMatchObject({ code: "PROVIDER_AMBIGUOUS", status: 409 });
    const m3 = fx(() => providers([hubspot(["get", "list"])]));
    await expect(client(m3).customer("acme-1").crm.contacts.create({ email: "x@y.z" })).rejects.toMatchObject({ code: "OPERATION_NOT_SUPPORTED" });
    const c = client(fx(() => providers([hubspot(["get", "list"]), { ...gcal, connectorSlug: "zohoCrm", operations: ["create"] }]))).customer("acme-1");
    await expect(c.crm.contacts.list()).resolves.toBeDefined();                     // only hubspot lists: not ambiguous
  });
  it("a provider/connection error forgets the cached answer, so the next call looks providers up again", async () => {
    let n = 0;
    const m = fx((url) => url.includes("/providers") ? providers([hubspot()]) : (++n === 1 ? { status: 404, body: { error: { code: "UNIFIED_CONNECTION_NOT_FOUND", message: "gone" } } } : { body: { records: [] } }));
    const c = client(m).customer("acme-1");
    await expect(c.crm.contacts.list()).rejects.toBeInstanceOf(FastnApiError);
    await c.crm.contacts.list();
    expect(m.urls().filter((u) => u.endsWith("/providers")).length).toBe(2);
  });
  it("request options still reach the wire: idempotency key, correlation id, Date inputs as ISO strings", async () => {
    const m = fx((url) => url.includes("/providers") ? providers([gcal]) : { status: 201, body: { id: "evt1", provider: "googleCalendar", data: {} } });
    const r = await client(m).customer("acme-1").calendar.book({ title: "Intro", start_time: new Date("2026-11-02T10:00:00Z"), duration_minutes: 30 }, { idempotencyKey: "call-7", correlationId: "corr-7" });
    expect(r.id).toBe("evt1");
    const post = m.calls[1];
    expect(post.init.headers["idempotency-key"]).toBe("call-7"); expect(post.init.headers["x-fastn-correlation-id"]).toBe("corr-7");
    expect(post.json).toEqual({ title: "Intro", start_time: "2026-11-02T10:00:00.000Z", duration_minutes: 30 });   // the record is the body
  });
});

describe("calendar", () => {
  it("freeSlots posts an availability record and returns busy, free and slots", async () => {
    const m = fx((url) => url.includes("/providers") ? providers([gcal]) : { body: { id: "x", provider: "googleCalendar", data: { start_time: "2026-11-02T09:00:00.000Z", end_time: "2026-11-02T12:00:00.000Z", busy: [{ start_time: "2026-11-02T10:00:00.000Z", end_time: "2026-11-02T10:30:00.000Z" }] } } });
    const r = await client(m).customer("acme-1").calendar.freeSlots({ start_time: "2026-11-02T09:00:00Z", end_time: "2026-11-02T12:00:00Z", timezone: "UTC", slot_minutes: 60 });
    expect(m.urls()).toEqual(["/v1/unified/scheduling/availability/providers", "/v1/unified/scheduling/availability?provider=googleCalendar"]);
    expect(m.calls[1].json).toEqual({ start_time: "2026-11-02T09:00:00Z", end_time: "2026-11-02T12:00:00Z", timezone: "UTC" });
    expect(r.busy).toEqual([{ start_time: "2026-11-02T10:00:00.000Z", end_time: "2026-11-02T10:30:00.000Z" }]);
    expect(r.free).toEqual([{ start_time: "2026-11-02T09:00:00.000Z", end_time: "2026-11-02T10:00:00.000Z" }, { start_time: "2026-11-02T10:30:00.000Z", end_time: "2026-11-02T12:00:00.000Z" }]);
    expect(r.slots).toEqual([{ start_time: "2026-11-02T09:00:00.000Z", end_time: "2026-11-02T10:00:00.000Z" }, { start_time: "2026-11-02T10:30:00.000Z", end_time: "2026-11-02T11:30:00.000Z" }]);
    expect(r.provider).toBe("googleCalendar");
  });
  it("find, reschedule and cancel map to search, PATCH and DELETE on scheduling/meeting", async () => {
    const m = fx((url) => url.includes("/providers") ? providers([gcal]) : { body: { records: [], id: "m1", provider: "googleCalendar", data: {} } });
    const c = client(m).customer("acme-1");
    await c.calendar.find({ start_time: "2026-11-01T00:00:00Z", end_time: "2026-11-08T00:00:00Z", query: "Jane" }, { page_size: 50 });
    await c.calendar.reschedule("m1", { start_time: "2026-11-03T10:00:00Z", end_time: "2026-11-03T10:30:00Z" });
    await c.calendar.cancel("m1", { idempotencyKey: "c1" });
    const calls = m.calls.slice(1);
    expect(calls.map((x) => `${x.init.method} ${x.url.replace("https://api.fastn.dev", "")}`)).toEqual([
      "POST /v1/unified/scheduling/meeting/search?provider=googleCalendar&page_size=50",
      "PATCH /v1/unified/scheduling/meeting/m1?provider=googleCalendar",
      "DELETE /v1/unified/scheduling/meeting/m1?provider=googleCalendar",
    ]);
    expect(calls[0].json).toEqual({ start_time: "2026-11-01T00:00:00Z", end_time: "2026-11-08T00:00:00Z", query: "Jane" });
    expect(calls[1].json).toEqual({ start_time: "2026-11-03T10:00:00Z", end_time: "2026-11-03T10:30:00Z" });
    expect(calls[2].init.headers["idempotency-key"]).toBe("c1");
  });
});

describe("crm", () => {
  it("contacts, notes, tasks and deals name their entities; moveStage patches the stage; stages lists crm/stage", async () => {
    const m = fx((url) => url.includes("/providers") ? providers([hubspot()]) : { body: { records: [], id: "r", provider: "hubspot", data: {} } });
    const c = client(m).customer("acme-1");
    await c.crm.contacts.create({ first_name: "Jane", email: "jane@x.io" }, { idempotencyKey: "k1" });
    await c.crm.contacts.update("c1", { last_name: "Doe" });
    await c.crm.notes.add({ body: "Called", parent_id: "c1", parent_type: "contact" });
    await c.crm.tasks.add({ subject: "Call back", due_date: new Date("2026-11-05T09:00:00Z") });
    await c.crm.tasks.delete("t1");
    await c.crm.deals.create({ name: "Annual plan", amount: 1200 });
    await c.crm.deals.moveStage("d1", "qualifiedtobuy");
    await c.crm.deals.stages();
    const calls = m.calls.filter((x) => !x.url.includes("/providers") && !x.url.endsWith("/v1/me"));
    expect(calls.map((x) => `${x.init.method} ${x.url.replace("https://api.fastn.dev", "")}`)).toEqual([
      "POST /v1/unified/crm/contact?provider=hubspot",
      "PATCH /v1/unified/crm/contact/c1?provider=hubspot",
      "POST /v1/unified/crm/note?provider=hubspot",
      "POST /v1/unified/crm/task?provider=hubspot",
      "DELETE /v1/unified/crm/task/t1?provider=hubspot",
      "POST /v1/unified/crm/opportunity?provider=hubspot",
      "PATCH /v1/unified/crm/opportunity/d1?provider=hubspot",
      "GET /v1/unified/crm/stage?provider=hubspot",
    ]);
    expect(calls[0].json).toEqual({ first_name: "Jane", email: "jane@x.io" }); expect(calls[0].init.headers["idempotency-key"]).toBe("k1");
    expect(calls[2].json).toMatchObject({ body: "Called", parent_id: "c1", parent_type: "contact" }); expect(Date.parse(calls[2].json.created_at)).toBeGreaterThan(Date.now() - 60_000);   // created_at defaults to now
    await expect(c.crm.contacts.get("")).rejects.toThrow(TypeError);
    expect(calls[3].json).toEqual({ subject: "Call back", due_date: "2026-11-05T09:00:00.000Z" });
    expect(calls[6].json).toEqual({ stage: "qualifiedtobuy" });
    // one providers lookup per entity: contact, note, task, opportunity, stage
    expect(m.urls().filter((u) => u.endsWith("/providers")).sort()).toEqual(["/v1/unified/crm/contact/providers", "/v1/unified/crm/note/providers", "/v1/unified/crm/opportunity/providers", "/v1/unified/crm/stage/providers", "/v1/unified/crm/task/providers"]);
  });
});

describe("connect(app) and links", () => {
  const widgets = [
    { id: "wgt_cal", name: "Google Calendar", slug: "google-calendar", connectorRefs: [{ slug: "googleCalendar", connectorId: "867f" }] },
    { id: "wgt_hs", name: "HubSpot", slug: "hubspot", connectorRefs: [{ slug: "hubspot", connectorId: "9036" }] },
  ];
  const wfx = (extra: any[] = []) => fx((url, init) => url.includes("/v1/widgets") ? { body: { data: [...widgets, ...extra] } } : init.method === "POST" ? { status: 201, body: { data: { setupId: "stp_1", setupUrl: "https://connect.fastn.dev/s/stp_1", status: "pending", expiresAt: "2026-11-04T00:00:00Z", endOrgId: "11111111-aaaa" } } } : { body: { data: { setupId: "stp_1", status: "revoked", endOrgId: "11111111-aaaa" } } });
  it("finds the widget by connector slug once per client and creates the setup link for the customer", async () => {
    const m = wfx();
    const fastn = client(m);
    const link = await fastn.customer("acme-1").connect("googleCalendar");
    const again = await fastn.customer("acme-2").connect("hubspot", { connectionName: "Main CRM", redirectUrl: "https://app.acme.com/done", expiresInMinutes: 60 });
    expect(link).toMatchObject({ setupId: "stp_1", url: "https://connect.fastn.dev/s/stp_1", status: "pending", widgetId: "wgt_cal", expiresAt: "2026-11-04T00:00:00Z" });
    expect(again.widgetId).toBe("wgt_hs");
    expect(link).not.toHaveProperty("endOrgId"); expect(link).not.toHaveProperty("setupUrl");   // fastn's internal customer id never reaches the partner
    const posts = m.calls.filter((x) => x.init.method === "POST");
    expect(posts[0].json).toEqual({ createIfMissing: true, widgetId: "wgt_cal", externalRef: "acme-1", connectionName: "Google Calendar" });
    expect(posts[1].json).toEqual({ createIfMissing: true, widgetId: "wgt_hs", externalRef: "acme-2", connectionName: "Main CRM", redirectUrl: "https://app.acme.com/done", expiresInMinutes: 60 });
    expect(m.urls().filter((u) => u.startsWith("/v1/widgets")).length).toBe(1);
  });
  it("no widget -> 404 WIDGET_NOT_FOUND; two widgets -> 409 WIDGET_AMBIGUOUS unless widgetId is given", async () => {
    await expect(client(wfx()).customer("acme-1").connect("salesforce")).rejects.toMatchObject({ code: "WIDGET_NOT_FOUND", status: 404 });
    const m = wfx([{ id: "wgt_cal2", name: "Calendar (EU)", connectorRefs: [{ slug: "googleCalendar" }] }]);
    const fastn = client(m);
    await expect(fastn.customer("acme-1").connect("googleCalendar")).rejects.toMatchObject({ code: "WIDGET_AMBIGUOUS", status: 409 });
    const link = await fastn.customer("acme-1").connect("googleCalendar", { widgetId: "wgt_cal2" });
    expect(link.widgetId).toBe("wgt_cal2");
    expect(m.calls.filter((x) => x.init.method === "POST")[0].json).toMatchObject({ widgetId: "wgt_cal2", connectionName: "Calendar (EU)" });
  });
  it("the object form still starts an OAuth connection on the customer org", async () => {
    const m = fx((url, init) => url.includes("/v1/orgs?") ? { body: { data: [{ id: "11111111-aaaa", externalRef: "acme-1", parentId: "partner-1" }] } } : { body: { data: { url: "https://oauth" } } });
    const r: any = await client(m).customer("acme-1").connect({ connectorId: "googleCalendar", connectionName: "work" } as any);
    expect(r.data.url).toBe("https://oauth");
    const call = m.calls.find((x) => x.init.method === "POST")!;
    expect(call.url).toContain("/v1/oauth/"); expect(call.json).toMatchObject({ connectorId: "googleCalendar", endOrgId: "11111111-aaaa" });
  });
  it("links.get and links.cancel answer the link's data", async () => {
    const m = wfx();
    const c = client(m).customer("acme-1");
    expect((await c.links.get("stp_1")).status).toBe("revoked");
    expect((await c.links.cancel("stp_1")).setupId).toBe("stp_1");
    expect(m.calls.map((x) => `${x.init.method} ${x.url.replace("https://api.fastn.dev", "")}`)).toEqual(["GET /v1/setup-links/stp_1", "DELETE /v1/setup-links/stp_1"]);
    expect(await c.links.get("stp_1")).not.toHaveProperty("endOrgId");                    // fastn's internal customer id is left out
  });
});

describe("catalog", () => {
  const cats = [{ id: "ucat_1", slug: "crm", name: "CRM", entities: [{ id: "ue_1", slug: "contact", name: "Contact", connectorSlugs: ["hubspot"], operations: ["create", "get"], createFields: [{ field: "first_name", type: "string", required: false }, { field: "email", type: "string", required: true }] }] }];
  it("categories are read once; entity and fields come from them; providers hit the entity route", async () => {
    const m = fx((url) => url.includes("/providers") ? providers([hubspot(), notConnected]) : { body: { data: cats } });
    const fastn = client(m);
    expect((await fastn.catalog.categories()).map((c) => c.slug)).toEqual(["crm"]);
    expect((await fastn.catalog.entity("crm", "contact")).operations).toEqual(["create", "get"]);
    expect((await fastn.catalog.fields("crm", "contact")).map((f) => `${f.field}${f.required ? "*" : ""}`)).toEqual(["first_name", "email*"]);
    await expect(fastn.catalog.entity("crm", "nope")).rejects.toMatchObject({ code: "NOT_FOUND" });
    await expect(fastn.catalog.category("hr")).rejects.toMatchObject({ code: "NOT_FOUND" });
    expect((await fastn.customer("acme-1").catalog.providers("crm", "contact")).map((p) => `${p.connectorSlug}:${p.connected}`)).toEqual(["hubspot:true", "pipedrive:false"]);
    expect(m.urls()).toEqual(["/v1/unified/categories", "/v1/unified/crm/contact/providers"]);
    expect(m.calls[1].init.headers["x-end-org-ref"]).toBe("acme-1");
  });
});

describe("free interval arithmetic", () => {
  const W = ["2026-11-02T09:00:00.000Z", "2026-11-02T12:00:00.000Z"] as const;
  const iv = (a: string, b: string) => ({ start_time: a, end_time: b });
  it("no busy time = the whole window; busy covering the window = nothing", () => {
    expect(freeIntervals(W[0], W[1], [])).toEqual([iv(W[0], W[1])]);
    expect(freeIntervals(W[0], W[1], [iv("2026-11-02T08:00:00.000Z", "2026-11-02T13:00:00.000Z")])).toEqual([]);
  });
  it("overlapping and unsorted busy intervals are merged; ones outside the window are ignored", () => {
    const busy = [iv("2026-11-02T10:15:00.000Z", "2026-11-02T10:45:00.000Z"), iv("2026-11-02T10:00:00.000Z", "2026-11-02T10:30:00.000Z"), iv("2026-11-02T14:00:00.000Z", "2026-11-02T15:00:00.000Z"), iv("2026-11-02T06:00:00.000Z", "2026-11-02T07:00:00.000Z")];
    expect(freeIntervals(W[0], W[1], busy)).toEqual([iv(W[0], "2026-11-02T10:00:00.000Z"), iv("2026-11-02T10:45:00.000Z", W[1])]);
  });
  it("busy at the edges trims the window; slots drop the short remainder", () => {
    const free = freeIntervals(W[0], W[1], [iv("2026-11-02T09:00:00.000Z", "2026-11-02T09:20:00.000Z"), iv("2026-11-02T11:50:00.000Z", "2026-11-02T12:00:00.000Z")]);
    expect(free).toEqual([iv("2026-11-02T09:20:00.000Z", "2026-11-02T11:50:00.000Z")]);
    expect(slotsOf(free, 60)).toEqual([iv("2026-11-02T09:20:00.000Z", "2026-11-02T10:20:00.000Z"), iv("2026-11-02T10:20:00.000Z", "2026-11-02T11:20:00.000Z")]);
    expect(slotsOf(free, 200)).toEqual([]);
  });
});

describe("review fixes (PR 5)", () => {
  const gcalRow = { connectorSlug: "googleCalendar", connectorName: "Google Calendar", operations: ["get", "list", "create", "delete", "search", "update"], connected: true };
  it("slot minutes must be a positive number: slotsOf and freeSlots refuse 0, negatives and NaN before any loop", async () => {
    const free = [{ start_time: "2026-11-02T09:00:00.000Z", end_time: "2026-11-02T12:00:00.000Z" }];
    for (const bad of [0, -30, NaN, Infinity, "30" as any]) expect(() => slotsOf(free, bad)).toThrow(TypeError);
    const m = fx(() => ({ body: { data: [gcalRow] } }));
    await expect(client(m).customer("acme-1").calendar.freeSlots({ start_time: "2026-11-02T09:00:00Z", end_time: "2026-11-02T12:00:00Z", slot_minutes: -30 })).rejects.toThrow(TypeError);
    expect(m.calls.length).toBe(0);                                                   // refused before any request
  });
  it("notes: created_at present but undefined still gets the default", async () => {
    const m = fx((url) => url.includes("/providers") ? providers([hubspot()]) : { body: { id: "n1", provider: "hubspot", data: {} } });
    await client(m).customer("acme-1").crm.notes.add({ body: "x", parent_id: "c1", created_at: undefined });
    expect(Date.parse(m.calls[1].json.created_at)).toBeGreaterThan(Date.now() - 60_000);
    await client(m).customer("acme-2").crm.notes.add({ body: "x", parent_id: "c1", created_at: "2026-01-01T00:00:00Z" });
    expect(m.calls[3].json.created_at).toBe("2026-01-01T00:00:00Z");                  // an explicit value wins
  });
  it("provider cache: cleared when no provider fits (so a later connect is seen), and re-read after the TTL", async () => {
    let rows: any[] = [{ ...gcalRow, connected: false }];
    const m = fx((url) => url.includes("/providers") ? providers(rows) : { body: { records: [] } });
    const fastn = client(m);
    await expect(fastn.customer("acme-1").calendar.list()).rejects.toMatchObject({ code: "NO_CONNECTED_PROVIDER" });
    rows = [{ ...gcalRow, operations: ["get"] }];
    await expect(fastn.customer("acme-1").calendar.list()).rejects.toMatchObject({ code: "OPERATION_NOT_SUPPORTED" });
    rows = [gcalRow];
    await fastn.customer("acme-1").calendar.list();                                   // the customer connected: works without a new client
    expect(m.urls().filter((u) => u.endsWith("/providers")).length).toBe(3);
    await fastn.customer("acme-1").calendar.list();                                   // within the TTL: no new lookup
    expect(m.urls().filter((u) => u.endsWith("/providers")).length).toBe(3);
    const spy = vi.spyOn(Date, "now").mockReturnValue(Date.now() + PROVIDER_TTL_MS + 1);
    try { await fastn.customer("acme-1").calendar.list(); } finally { spy.mockRestore(); }
    expect(m.urls().filter((u) => u.endsWith("/providers")).length).toBe(4);          // after the TTL: read again (a second provider connected later is seen)
  });
  it("widgets: a miss re-reads the list once, so a widget made after the first read is found; an explicit widgetId too", async () => {
    let rows: any[] = [{ id: "wgt_cal", name: "Google Calendar", orgId: "partner-1", connectorRefs: [{ slug: "googleCalendar" }] }];
    const m = fx((url, init) => url.includes("/v1/widgets") ? { body: { data: rows } } : init.method === "POST" ? { status: 201, body: { data: { setupId: "stp_1", setupUrl: "https://x/s", status: "pending" } } } : { body: { data: {} } });
    const fastn = client(m);
    await expect(fastn.customer("acme-1").connect("hubspot")).rejects.toMatchObject({ code: "WIDGET_NOT_FOUND" });
    rows = [...rows, { id: "wgt_hs", name: "HubSpot", orgId: "partner-1", connectorRefs: [{ slug: "hubspot" }] }];
    expect((await fastn.customer("acme-1").connect("hubspot")).widgetId).toBe("wgt_hs");
    expect((await fastn.customer("acme-1").connect("hubspot", { widgetId: "wgt_hs" })).widgetId).toBe("wgt_hs");
    const reads = m.urls().filter((u) => u.startsWith("/v1/widgets")).length;
    expect(reads).toBe(3);                                                            // first read, the re-read on the miss, the re-read on the next miss; then cached
  });
  it("widgets: inherited rows, other orgs' rows and the inactive version of a customised integration are never offered", async () => {
    const rows = [
      { id: "wgt_parent_cal", name: "Google Calendar", orgId: "platform", inheritedFrom: { orgId: "platform" }, connectorRefs: [{ slug: "googleCalendar" }] },
      { id: "wgt_cal", name: "Google Calendar", orgId: "partner-1", connectorRefs: [{ slug: "googleCalendar" }] },
      { id: "wgt_hs_orig", name: "HubSpot", orgId: "partner-1", version: { groupId: "g1", kind: "original", active: false, originalAvailable: true }, connectorRefs: [{ slug: "hubspot" }] },
      { id: "wgt_hs_copy", name: "HubSpot (ours)", orgId: "partner-1", version: { groupId: "g1", kind: "custom", active: true }, customisedFrom: { sourceWidgetId: "wgt_hs_orig" }, connectorRefs: [{ slug: "hubspot" }] },
      { id: "wgt_other", name: "Salesforce", orgId: "partner-2", connectorRefs: [{ slug: "salesforce" }] },
    ];
    const m = fx((url, init) => url.includes("/v1/widgets") ? { body: { data: rows } } : init.method === "POST" ? { status: 201, body: { data: { setupId: "stp_1", setupUrl: "https://x/s", status: "pending" } } } : { body: { data: {} } });
    const fastn = client(m);
    expect((await fastn.customer("acme-1").connect("googleCalendar")).widgetId).toBe("wgt_cal");            // not ambiguous with the parent's row
    expect((await fastn.customer("acme-1").connect("hubspot")).widgetId).toBe("wgt_hs_copy");               // the active version only
    await expect(fastn.customer("acme-1").connect("salesforce")).rejects.toMatchObject({ code: "WIDGET_NOT_FOUND" });
    await expect(fastn.customer("acme-1").connect("googleCalendar", { widgetId: "wgt_parent_cal" })).rejects.toMatchObject({ code: "WIDGET_NOT_FOUND" });
  });
});
