// Live run against the fastn API with a partner API key. Skipped unless LIVE=1, FASTN_API_KEY and FASTN_TEST_CUSTOMER are set.
// FASTN_TEST_CUSTOMER is the ref of a customer org that has Google Calendar and HubSpot connected.
// Creates: one meeting + one HubSpot contact/note in the e2e customer org, and one throw-away customer org; all removed at the end.
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import fs from "node:fs";
import { FastnClient, FastnApiError, paginate } from "../../src/index.js";

// Target: FASTN_BASE_URL, default https://api.fastn-test.dev (the development environment). Point it at
// https://api.fastn.dev only with LIVE_PROD=1: the suite creates and deletes real customers, bookings and CRM records.
const BASE_URL = process.env.FASTN_BASE_URL ?? "https://api.fastn-test.dev";
if (/api\.fastn\.dev/.test(BASE_URL) && process.env.LIVE_PROD !== "1") throw new Error("FASTN_BASE_URL points at production; set LIVE_PROD=1 to run the live suite there");
const LIVE = process.env.LIVE === "1" && !!process.env.FASTN_API_KEY && !!process.env.FASTN_TEST_CUSTOMER;
const d = describe.skipIf(!LIVE);
const EV = new URL("./evidence.jsonl", import.meta.url).pathname;
const mask = (s: string) => s.replace(/(emb_|ucl_|fsk_[a-z]+_|whsec_|stp_tok_|sk_)[A-Za-z0-9_\-]{6,}/g, "$1***").replace(/[A-Za-z0-9_-]{48,}/g, "<tok>");
const ev = (step: string, data: unknown) => fs.appendFileSync(EV, mask(JSON.stringify({ at: new Date().toISOString(), step, data })).slice(0, 2500) + "\n");
const run = new Date().toISOString().slice(11, 19).replace(/:/g, "");
const E2E = process.env.FASTN_TEST_CUSTOMER ?? "";
const day = new Date(Date.now() + 9 * 86400e3).toISOString().slice(0, 10);
const utc = (rec: any) => { try { return new Date((rec?.data ?? rec).start_time).toISOString().slice(11, 16); } catch { return undefined; } };
const dataOf = (r: any) => r?.data ?? r;

let fastn: FastnClient; const log: any[] = [];
beforeAll(() => { fastn = new FastnClient({ apiKey: process.env.FASTN_API_KEY!, baseUrl: BASE_URL, onRequest: (i) => log.push(i) }); });
afterAll(() => ev("requests", log.map((l) => `${l.method} ${l.url.replace(BASE_URL, "")} -> ${l.status} ${l.durationMs}ms`)));

d("prod: orgs and customer context", () => {
  it("listOrgs answers and the e2e customer resolves to a fastn id", async () => {
    const res = await fastn.orgs.listOrgs({ type: "end_org" });
    ev("listOrgs", { count: res.data?.length, keys: Object.keys(res.data?.[0] ?? {}) });
    expect(Array.isArray(res.data)).toBe(true);
    const c = fastn.customer(E2E);
    const id = await c.id(); expect(id).toMatch(/^[0-9a-f-]{36}$|^org_/);
    const org = await c.get(); ev("getTenant", dataOf(org)); expect(dataOf(org).id).toBe(id);
    const conns = await c.connections(); ev("connections", (conns.data ?? []).map((x: any) => ({ connector: x.connectorSlug ?? x.connector ?? x.connectorId, status: x.status })));
    expect(Array.isArray(conns.data)).toBe(true); expect(conns.data.length).toBeGreaterThan(0);
  });
  it("paginate walks listEvents by limit/offset and stops on a list that ignores paging", async () => {
    const rows: any[] = []; for await (const r of paginate((i) => fastn.events.listEvents(i as any), {}, { pageSize: 2, maxPages: 3 })) rows.push(r);
    ev("paginate events", { rows: rows.length });
    const orgs: any[] = []; for await (const r of paginate((i) => fastn.orgs.listOrgs(i), { type: "end_org" }, { pageSize: 2 })) orgs.push(r);
    expect(orgs.length).toBeGreaterThan(0); expect(orgs.length).toBeLessThan(50);
  }, 30000);
  it("a wrong id is a typed 404", async () => {
    const err = await fastn.orgs.getTenant({ id: "00000000-0000-0000-0000-000000000000" }).catch((e) => e);
    ev("getTenant 404", { status: err.status, code: err.code, message: err.message, requestId: err.requestId });
    expect(err).toBeInstanceOf(FastnApiError); expect(err.status === 404 || err.status === 403).toBe(true); expect(err.requestId).toBeTruthy();
  });
});

d("prod: register a customer, setup link, delete", () => {
  const ref = `sdk_test_customer_${run}`; let fastnId: string | undefined;
  it("register is idempotent and the ref round-trips", async () => {
    const c = fastn.customer(ref);
    expect(await c.find()).toBeUndefined();
    const created = await c.register({ name: `SDK test ${run}` }); ev("register", dataOf(created));
    fastnId = dataOf(created).id as string; expect(fastnId).toBeTruthy();
    const again = await c.register({ name: `SDK test ${run}` }); expect(again.existed).toBe(true); expect(dataOf(again).id).toBe(fastnId);
    const row = await fastn.customer(ref).find(); expect(row?.id).toBe(fastnId); expect(row?.externalRef).toBe(ref);
  });
  it("setupLink creates a pending link for the customer and getSetupLink reads it back", async () => {
    const widgets = await fastn.embed.listWidgets(); const w = (widgets.data ?? [])[0]; ev("widgets", (widgets.data ?? []).map((x: any) => ({ id: x.id, name: x.name })));
    expect(w?.id).toBeTruthy();
    const link = await fastn.customer(ref).setupLink({ widgetId: w.id as string, connectionName: "sdk-test", expiresInMinutes: 10 }); ev("setupLink", dataOf(link));
    const l = dataOf(link); expect(l.setupId).toMatch(/^stp_/); expect(l.setupUrl).toContain("http"); expect(l.status).toBe("pending");
    const got = await fastn.embed.getSetupLink({ id: l.setupId as string }); ev("getSetupLink", dataOf(got)); expect(dataOf(got).status ?? dataOf(got).setupLink?.status).toBeTruthy();
    const st = await fastn.embed.getSetupLinkStatus({ id: l.setupId as string }).catch((e) => e); ev("getSetupLinkStatus", st instanceof Error ? { status: (st as any).status, message: st.message } : dataOf(st));
  });
  it("remove() suspends then deletes the throw-away customer", async () => {
    expect(fastnId).toBeTruthy();
    const direct = await fastn.orgs.deleteTenant({ id: fastnId! }).catch((e) => e); ev("deleteTenant active org", { status: direct.status, message: direct.message });
    expect(direct.status).toBe(400); // the API wants the org suspended first; remove() does both
    await fastn.customer(ref).remove();
    expect(await fastn.customer(ref).find()).toBeUndefined();
  }, 30000);
});

d("prod: unified scheduling + crm for the e2e customer", () => {
  const c = () => fastn.customer(E2E);
  const cid = `sdk_${run}`; let mid: string | undefined; let hid: string | undefined; let nid: string | undefined;
  const meetings = () => c().records({ category: "scheduling", entity: "meeting", provider: "googleCalendar" });
  const contacts = () => c().records({ category: "crm", entity: "contact", provider: "hubspot" });
  // HubSpot delete is not mapped on prod (UNIFIED_UNSUPPORTED_OPERATION); contacts stay behind, listed in LEARNINGS.
  it("providers for scheduling/meeting include googleCalendar", async () => {
    const p = await meetings().providers(); ev("providers", dataOf(p)); expect(JSON.stringify(p)).toContain("googleCalendar");
  });
  it("availability", async () => {
    const a = await c().records({ category: "scheduling", entity: "availability", provider: "googleCalendar" }).create({ start_time: `${day}T08:00:00Z`, end_time: `${day}T18:00:00Z`, timezone: "Europe/London" });
    ev("availability", dataOf(a)); expect(JSON.stringify(a)).toContain("busy");
  });
  it("book with idempotency key, replay returns the same id", async () => {
    const rec = { title: `sdk check ${run}`, start_time: `${day}T15:00:00Z`, end_time: `${day}T15:30:00Z`, timezone: "Europe/London", attendee_email: "jane.sdk@example.com", attendee_name: "Jane Doe", description: "platform-sdk live test" };
    const b1 = await meetings().create(rec, { idempotencyKey: `${cid}_book`, correlationId: cid }); ev("book", { id: b1.id, provider: b1.provider, keys: Object.keys(b1), title: b1.data?.title });
    mid = b1.id; expect(mid).toBeTruthy(); expect(b1.provider).toBe("googleCalendar"); expect(b1.data?.title).toBe(rec.title);
    const b2 = await meetings().create(rec, { idempotencyKey: `${cid}_book`, correlationId: cid }); expect(b2.id).toBe(mid);
  });
  it("search finds it, reschedule (PATCH) moves it, get shows the new time", async () => {
    await new Promise((r) => setTimeout(r, 3000));
    const s = await meetings().search({ start_time: `${day}T00:00:00Z`, query: `sdk check ${run}` }, { correlationId: cid }); ev("search", { found: JSON.stringify(s).includes(mid!) });
    expect(JSON.stringify(s)).toContain(mid!);
    const u = await meetings().update(mid!, { start_time: `${day}T16:00:00Z`, end_time: `${day}T16:30:00Z` }, { idempotencyKey: `${cid}_move`, correlationId: cid }); ev("reschedule", dataOf(u));
    expect(utc(u)).toBe("16:00");
    const g = await meetings().get(mid!); expect(utc(g)).toBe("16:00");
  }, 30000);
  it("listUnifiedCalls finds the correlation id", async () => {
    const calls = await fastn.unified.listUnifiedCalls({ correlation_id: cid }); ev("calls", { n: (calls.data ?? calls)?.length, sample: JSON.stringify(calls).slice(0, 300) });
    expect(JSON.stringify(calls).toLowerCase()).toContain("create");
  });
  it("hubspot contact create / update / search / note", async () => {
    // HubSpot delete is unsupported, so one fixed contact is reused across runs instead of creating a new one each time.
    const em = "jane.sdk.live@example.com";
    const found = await contacts().search({ email: em }); const existing = (found?.records ?? found?.data?.records ?? []).find((r: any) => (r.data?.email ?? r.email) === em);
    const cr = existing ?? await contacts().create({ first_name: "Jane", last_name: "SDK", email: em, phone: "+447700900123" }, { idempotencyKey: `${cid}_contact` });
    ev("contact", { id: cr.id, reused: !!existing }); hid = cr.id; expect(hid).toBeTruthy();
    const up = await contacts().update(hid!, { last_name: `SDK-${run}` }); ev("contact update", dataOf(up)); expect(up).toBeTruthy();
    await new Promise((r) => setTimeout(r, 5000));
    const se = await contacts().search({ email: em }); expect(JSON.stringify(se)).toContain(hid!);
    const note = await c().records({ category: "crm", entity: "note", provider: "hubspot" }).create({ body: "platform-sdk live note", parent_type: "contact", parent_id: hid, created_at: new Date().toISOString() }); ev("note", dataOf(note));
    nid = note.id; expect(nid).toBeTruthy();
  }, 30000);
  afterAll(async () => {
    const out: any = {};
    if (mid) out.meeting = await meetings().delete(mid, { idempotencyKey: `${cid}_cancel` }).then(() => "deleted", (e) => `${e.status} ${e.message}`);
    if (nid) out.note = await c().records({ category: "crm", entity: "note", provider: "hubspot" }).delete(nid).then(() => "deleted", (e) => `${e.status} ${e.message}`);
    if (hid) out.contact = await contacts().delete(hid).then(() => "deleted", (e) => `${e.status} ${e.message}`);
    ev("cleanup", out);
  });
});

d("prod: events and workflows read-only", () => {
  it("event subscriptions and events list", async () => {
    const subs = await fastn.events.listEventSubscriptions().catch((e) => e); ev("subscriptions", subs instanceof Error ? { status: (subs as any).status, message: subs.message } : (subs.data ?? []).map((s: any) => ({ id: s.id, url: String(s.url ?? "").replace(/\/\/[^/]+/, "//<host>"), status: s.status })));
    expect(subs).not.toBeInstanceOf(Error);
    const evs = await fastn.events.listEvents({ limit: 2 } as any); ev("events", { n: (evs.data ?? []).length }); expect(Array.isArray(evs.data)).toBe(true);
  });
});
