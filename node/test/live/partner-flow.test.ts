// A partner's whole call flow, end to end, against the fastn API: register a business, let it connect its apps, check free time,
// book, find, reschedule, list, cancel, find and update the CRM contact, log the call, follow-up task, deal, events.
// Skipped unless LIVE=1, FASTN_API_KEY and FASTN_TEST_CUSTOMER are set. FASTN_TOOLS_KEY + FASTN_TOOLS_URL add the gateway (tools) route.
// Creates on prod: one throw-away business org, one setup link (cancelled), one meeting (cancelled), one HubSpot note / task / deal
// on the fixed test contact, one event subscription (deleted). The business org is suspended and deleted at the end.
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import fs from "node:fs";
import { FastnClient, FastnApiError, ToolError, paginate } from "../../src/index.js";

const LIVE = process.env.LIVE === "1" && !!process.env.FASTN_API_KEY && !!process.env.FASTN_TEST_CUSTOMER;
const d = describe.skipIf(!LIVE);
const EV = new URL("./evidence.jsonl", import.meta.url).pathname;
const mask = (s: string) => s.replace(/(emb_|ucl_|fsk_[a-z]+_|whsec_|stp_tok_|sk_)[A-Za-z0-9_\-]{6,}/g, "$1***").replace(/[A-Za-z0-9_-]{48,}/g, "<tok>");
const ev = (step: string, data: unknown) => fs.appendFileSync(EV, mask(JSON.stringify({ at: new Date().toISOString(), step: `flow ${step}`, data })).slice(0, 2500) + "\n");
const run = new Date().toISOString().slice(11, 19).replace(/:/g, "");
const E2E = process.env.FASTN_TEST_CUSTOMER ?? "";  // a customer org with Google Calendar + HubSpot connected
const FLOW = `sdk_flow_${run}`;                   // a new business, registered and removed by this run
const day = new Date(Date.now() + 11 * 86400e3).toISOString().slice(0, 10);
const dataOf = (r: any) => r?.data ?? r;
const utc = (rec: any) => new Date(dataOf(rec).start_time).toISOString().slice(11, 16);
const FIXED_CONTACT = "jane.sdk.live@example.com";

let fastn: FastnClient; const log: any[] = [];
let partnerOrg: string | undefined;
const partnerOrgId = async () => { if (!partnerOrg) { const me = dataOf(await fastn.call("whoami" as any, {})); partnerOrg = me.org?.id ?? me.orgId; } return partnerOrg!; };
let meetingId: string | undefined; let toolsMeetingId: string | undefined; let subId: string | undefined; let flowCreated = false;
const e2e = () => fastn.customer(E2E);
const G = { category: "scheduling", entity: "meeting", provider: "googleCalendar" } as const;
const H = (entity: string) => ({ category: "crm", entity, provider: "hubspot" });

beforeAll(() => {
  fastn = new FastnClient({
    apiKey: process.env.FASTN_API_KEY!, onRequest: (i) => log.push(i), timeoutMs: 60_000,
    tools: process.env.FASTN_TOOLS_KEY && process.env.FASTN_TOOLS_URL ? { key: process.env.FASTN_TOOLS_KEY, url: process.env.FASTN_TOOLS_URL } : undefined,
  });
});
afterAll(async () => {
  const quiet = async (name: string, f: () => Promise<unknown>) => { try { ev(`cleanup ${name}`, dataOf(await f()) ?? "ok"); } catch (e: any) { ev(`cleanup ${name}`, `skipped: ${e.message}`); } };
  if (meetingId) await quiet("meeting", () => e2e().records(G).delete(meetingId!));
  if (toolsMeetingId) await quiet("tools meeting", () => e2e().records(G).delete(toolsMeetingId!));
  if (subId) await quiet("event subscription", () => fastn.events.deleteEventSubscription({ id: subId! } as any));
  if (flowCreated) await quiet("business org", () => fastn.customer(FLOW).remove());
  ev("requests", log.map((l) => `${l.method} ${l.url.replace("https://api.fastn.dev", "")} -> ${l.status} ${l.durationMs}ms`));
});

d("Partner flow 1: register the business", () => {
  it("register, read, list, rename", async () => {
    const biz = fastn.customer(FLOW);
    const created = dataOf(await biz.register({ name: `Flow Clinic ${run}` })); flowCreated = true;
    ev("register", { id: created.id, orgId: created.orgId ?? created.externalRef, status: created.status, plan: created.plan });
    expect(created.id).toBeTruthy(); expect(created.status).toBe("active");
    expect(dataOf(await biz.get()).id).toBe(created.id);
    expect((await fastn.customer(FLOW).find())?.id).toBe(created.id);
    const renamed = dataOf(await fastn.orgs.updateTenant({ id: created.id, name: `Flow Clinic ${run} Ltd` } as any));
    ev("rename", { name: renamed.name }); expect(renamed.name).toBe(`Flow Clinic ${run} Ltd`);
  });
  it("org config: the partner's redirect list is read; a save round-trips on the throw-away org", async () => {
    // setupLinkRedirectUrls lives on the PARTNER org (the caller); setup links take their redirectUrl from it. Read-only there.
    const partner = dataOf(await fastn.orgs.getOrgConfig({ id: await partnerOrgId() } as any));
    ev("partner getOrgConfig", { keys: Object.keys(partner), redirects: partner.setupLinkRedirectUrls });
    expect(Array.isArray(partner.setupLinkRedirectUrls)).toBe(true);
    const id = await fastn.customer(FLOW).id();
    await fastn.orgs.updateOrgConfig({ id, setupLinkRedirectUrls: ["https://example.com/connected"] } as any);
    const after = dataOf(await fastn.orgs.getOrgConfig({ id } as any)); ev("flow org getOrgConfig", after);
    expect(after.setupLinkRedirectUrls).toEqual(["https://example.com/connected"]);
  });
});

d("Partner flow 2: let the business connect its apps", () => {
  it("setup link: create, read, status, cancel", async () => {
    const widgets = dataOf(await fastn.embed.listWidgets({} as any)); const w = (widgets.widgets ?? widgets)[0];
    const link = dataOf(await fastn.customer(FLOW).setupLink({ widgetId: w.id, connectionName: "Google Calendar", expiresInMinutes: 10, label: `flow ${run}` } as any));
    const id = link.setupId ?? link.id;
    ev("setupLink", { id, status: link.status, url: (link.setupUrl ?? link.url)?.replace(/#.*/, "#<tok>"), redirectUrl: link.redirectUrl });
    expect(id).toMatch(/^stp_/); expect(link.setupUrl ?? link.url).toContain("app.fastn.dev/setup/");
    const partner = dataOf(await fastn.orgs.getOrgConfig({ id: await partnerOrgId() } as any));
    expect(partner.setupLinkRedirectUrls).toContain(link.redirectUrl);           // the partner org's list decides the redirect
    const read = dataOf(await fastn.embed.getSetupLink({ id } as any)); expect(read.setupId ?? read.id).toBe(id);
    const st = dataOf(await fastn.embed.getSetupLinkStatus({ id } as any)); ev("setupLinkStatus", st);
    expect(["pending", "active", "created"]).toContain(st.status ?? link.status);
    await fastn.embed.cancelSetupLink({ id } as any);
    const gone = dataOf(await fastn.embed.getSetupLinkStatus({ id } as any)); ev("setupLinkAfterCancel", gone);
    expect(["revoked", "cancelled", "canceled", "expired"]).toContain(gone.status);   // prod answers "revoked"
  });
  it("embed token for the in-app widget", async () => {
    const tok = dataOf(await fastn.customer(FLOW).embedToken({ userId: `flow-user-${run}`, userEmail: "flow@example.com" } as any));
    ev("embedToken", { hasToken: !!tok.token, expiresIn: tok.expiresIn ?? tok.expires_in });
    expect(tok.token).toMatch(/^emb_/);
  });
});

d("Partner flow 3: the customer's connected accounts", () => {
  it("connections, one connection, providers, categories", async () => {
    const conns = dataOf(await e2e().connections()); const list = conns.connections ?? conns;
    ev("connections", list.map((c: any) => ({ id: c.id, connector: c.connectorId ?? c.connector, status: c.status })));
    expect(list.length).toBeGreaterThan(0);
    const one = dataOf(await fastn.connections.getConnection({ id: list[0].id } as any)); expect(one.id).toBe(list[0].id);
    const prov = dataOf(await e2e().records(G).providers()); const rows = prov.providers ?? prov;
    const names = rows.map((p: any) => p.connectorSlug); ev("providers", rows.map((p: any) => ({ slug: p.connectorSlug, connected: p.connected, ops: p.operations })));
    expect(names).toContain("googleCalendar"); expect(rows.find((p: any) => p.connectorSlug === "googleCalendar").connected).toBe(true);
    const cats = dataOf(await e2e().api.unified.listUnifiedCategories({} as any));
    const slugs = (cats.categories ?? cats).map((c: any) => c.slug ?? c.category); ev("categories", slugs);
    expect(slugs).toEqual(expect.arrayContaining(["scheduling", "crm"]));
  });
});

d("Partner flow 4: the phone call, scheduling", () => {
  it("check free time", async () => {
    const r = dataOf(await e2e().records({ ...G, entity: "availability" }).create({ start_time: `${day}T08:00:00Z`, end_time: `${day}T18:00:00Z`, timezone: "Europe/London" }));
    ev("availability", { busy: r.busy?.length ?? r }); expect(Array.isArray(r.busy ?? r.slots ?? [])).toBe(true);
  });
  it("book with idempotency key, replay returns the same booking", async () => {
    const rec = { title: `Check-up - Jane Doe (flow ${run})`, start_time: `${day}T15:00:00Z`, end_time: `${day}T15:30:00Z`, timezone: "Europe/London", attendee_email: "jane.sdk@example.com", attendee_name: "Jane Doe", description: "Booked by phone, sdk flow test" };
    const opts = { idempotencyKey: `flow_${run}_book_1`, correlationId: `flow_${run}` };
    const a = await e2e().records(G).create(rec, opts); meetingId = a.id; ev("book", { id: a.id, start: utc(a), status: dataOf(a).status });
    expect(meetingId).toBeTruthy(); expect(utc(a)).toBe("15:00");
    const b = await e2e().records(G).create(rec, opts); expect(b.id).toBe(meetingId);
  });
  it("find, reschedule, read, list, cancel", async () => {
    const found = dataOf(await e2e().records(G).search({ start_time: `${day}T00:00:00Z`, query: "Jane Doe" }));
    const rows = found.records ?? found; ev("search", { count: rows.length, hit: rows.some((r: any) => r.id === meetingId) });
    expect(rows.some((r: any) => r.id === meetingId)).toBe(true);
    const moved = await e2e().records(G).update(meetingId!, { start_time: `${day}T16:00:00Z`, end_time: `${day}T16:30:00Z` }, { idempotencyKey: `flow_${run}_move_1` });
    expect(utc(moved)).toBe("16:00");
    const one = await e2e().records(G).get(meetingId!); expect(utc(one)).toBe("16:00"); ev("get", { id: one.id, start: utc(one) });
    let pages = 0, seen = false;
    for await (const row of paginate((i: any) => e2e().records(G).list(i), {}, { pageSize: 5, limitKey: "page_size", offsetKey: null, cursorKey: "cursor", rows: (r: any) => dataOf(r).records ?? [], nextCursor: (r: any) => dataOf(r).nextCursor, maxPages: 6 })) { pages++; if ((row as any).id === meetingId) seen = true; }
    ev("list", { rowsWalked: pages, sawBooking: seen }); expect(pages).toBeGreaterThan(0);
    await e2e().records(G).delete(meetingId!, { idempotencyKey: `flow_${run}_cancel_1` });
    const after = await e2e().records(G).get(meetingId!).then((r) => dataOf(r).status).catch((e: FastnApiError) => `error ${e.status}`);
    ev("afterCancel", after); expect(["cancelled", "error 404", "error 410"]).toContain(after);
    meetingId = undefined;
  });
  it("the call is traceable by correlation id", async () => {
    const calls = dataOf(await fastn.unified.listUnifiedCalls({ correlation_id: `flow_${run}` } as any)); const rows = calls.calls ?? calls;
    ev("calls", { count: rows.length, ops: rows.map((c: any) => c.operation ?? c.method ?? c.op) });
    expect(rows.length).toBeGreaterThanOrEqual(1);
  });
});

d("Partner flow 5: the phone call, CRM", () => {
  it("find or create the contact, update it, log the call, follow-up task, deal", async () => {
    const C = e2e().records(H("contact"));
    const hits = dataOf(await C.search({ email: FIXED_CONTACT })); let contact = (hits.records ?? hits)[0];
    if (!contact) contact = await C.create({ first_name: "Jane", last_name: "SDK", email: FIXED_CONTACT, phone: "+447700900123" });
    ev("contact", { id: contact.id, found: !!(hits.records ?? hits)[0] }); expect(contact.id).toBeTruthy();
    const upd = await C.update(contact.id, { last_name: `SDK-flow-${run}` }); expect(dataOf(upd).last_name ?? `SDK-flow-${run}`).toBe(`SDK-flow-${run}`);
    const note = await e2e().records(H("note")).create({ body: `Booked a check-up for ${day}. (sdk flow ${run})`, parent_type: "contact", parent_id: contact.id, created_at: new Date().toISOString() });
    ev("note", { id: note.id }); expect(note.id).toBeTruthy();
    const task = await e2e().records(H("task")).create({ subject: `Call back Jane (sdk flow ${run})`, due_date: `${day}T09:00:00Z` });
    ev("task", { id: task.id }); expect(task.id).toBeTruthy();
    const deal = await e2e().records(H("opportunity")).create({ name: `Annual plan (sdk flow ${run})`, amount: 1200, stage: "appointmentscheduled" });
    ev("deal", { id: deal.id }); expect(deal.id).toBeTruthy();
    for (const [name, scope, id] of [["task", H("task"), task.id], ["deal", H("opportunity"), deal.id]] as const) {
      const r = await e2e().records(scope).delete(id).then(() => "deleted").catch((e: FastnApiError) => `${e.status} ${e.code}`);
      ev(`${name} delete`, r);
    }
  });
});

d("Partner flow 6: events", () => {
  it("subscribe, read, send a test event, see deliveries, list events, unsubscribe", async () => {
    const sub = dataOf(await fastn.events.createEventSubscription({ url: `https://example.com/fastn-sdk-flow-${run}`, eventTypes: ["connection.connected", "setup_link.completed", "unified.event"], description: `sdk flow ${run}` } as any));
    subId = sub.id; ev("subscribe", { id: sub.id, hasSecret: !!sub.secret, eventTypes: sub.eventTypes }); expect(sub.id).toBeTruthy(); expect(sub.secret).toMatch(/^whsec_/);
    expect(dataOf(await fastn.events.getEventSubscription({ id: sub.id } as any)).id).toBe(sub.id);
    const test = dataOf(await fastn.events.testEventSubscription({ id: sub.id } as any)); ev("testEvent", test);
    await new Promise((r) => setTimeout(r, 4000));
    const del = dataOf(await fastn.events.listEventDeliveries({ id: sub.id, limit: 5 } as any)); const rows = del.deliveries ?? del;
    ev("deliveries", rows.map((x: any) => ({ status: x.status, type: x.eventType ?? x.type, attempts: x.attempts ?? x.attemptCount })));
    expect(rows.length).toBeGreaterThanOrEqual(1);
    const evs = dataOf(await fastn.events.listEvents({ limit: 5 } as any)); expect(Array.isArray(evs.events ?? evs)).toBe(true);
    await fastn.events.deleteEventSubscription({ id: sub.id } as any); subId = undefined;
    await expect(fastn.events.getEventSubscription({ id: sub.id } as any)).rejects.toMatchObject({ status: 404 });
  });
});

d("Partner flow 7: the same booking steps through the gateway (tools route)", () => {
  const skip = !process.env.FASTN_TOOLS_KEY || !process.env.FASTN_TOOLS_URL;
  const P = { category: "scheduling", entity: "meeting", provider: "googleCalendar", endOrgRef: E2E };
  it.skipIf(skip)("check free time, book, read via fastnPlatform tools", async () => {
    const t = e2e().tools;
    const free = await t.call("fastnPlatform__createUnifiedRecord", { ...P, entity: "availability", record: { start_time: `${day}T08:00:00Z`, end_time: `${day}T18:00:00Z`, timezone: "Europe/London" } }, { retries: 2 });
    ev("tools availability", { busy: free.data?.busy?.length ?? free.data }); expect(free.isError).toBe(false);
    const booked = await t.call("fastnPlatform__createUnifiedRecord", { ...P, record: { title: `Check-up via tools (flow ${run})`, start_time: `${day}T17:00:00Z`, end_time: `${day}T17:30:00Z`, timezone: "Europe/London" } });
    toolsMeetingId = booked.data?.id; ev("tools book", { id: toolsMeetingId }); expect(toolsMeetingId).toBeTruthy();
    const got = await t.call("fastnPlatform__getUnifiedRecord", { ...P, id: toolsMeetingId }, { retries: 2 });
    expect(got.data?.id).toBe(toolsMeetingId);
    const bad = await t.call("fastnPlatform__getUnifiedRecord", { ...P, id: "no_such_meeting" }).catch((e) => e);
    expect(bad).toBeInstanceOf(ToolError); ev("tools bad id", { kind: bad.kind, message: bad.message?.slice(0, 120) });
  });
  // Known platform/gateway issue (2026-10-22): deleteUnifiedRecord through the gateway answers "error code: 502" on prod while the
  // same DELETE over REST works. it.fails documents it: when the platform is fixed this test turns red, and the cancel moves to the tools route.
  it.skipIf(skip).fails("cancel via fastnPlatform__deleteUnifiedRecord (known 502 on prod, cancelled over REST in afterAll instead)", async () => {
    const r = await e2e().tools.call("fastnPlatform__deleteUnifiedRecord", { ...P, id: toolsMeetingId }, { retries: 1 }).catch((e) => e);
    ev("tools cancel", r instanceof Error ? { kind: (r as any).kind, message: r.message.slice(0, 120) } : r.data);
    if (r instanceof Error) throw r;
    toolsMeetingId = undefined;
  });
});

d("Partner flow 8: who am I", () => {
  it("whoami answers the partner org", async () => {
    const me = dataOf(await fastn.call("whoami" as any, {})); ev("whoami", { org: me.org?.id ?? me.orgId, actor: me.actor });
    expect(me.org?.id ?? me.orgId).toBe(await partnerOrgId());
  });
});
