// The typed calendar and CRM methods, the catalog and connect(app), end to end on a customer that has Google
// Calendar and HubSpot connected. Everything created here is removed at the end.
// Env: LIVE=1, FASTN_API_KEY, FASTN_TEST_CUSTOMER; FASTN_BASE_URL (default https://api.fastn-test.dev).
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import { FastnClient, FastnApiError, type Customer } from "../../src/index.js";
import { BASE_URL, guardProduction, LIVE_API, E2E, run, evidence } from "./_shared.js";

guardProduction();
const d = describe.skipIf(!LIVE_API);
const ev = evidence("domain");
const D = (h: number) => new Date(Date.now() + h * 3600e3).toISOString();

let fastn: FastnClient, customer: Customer;
let meetingId = "", contactId = "", noteId = "", taskId = "", dealId = "";
beforeAll(() => { fastn = new FastnClient({ apiKey: process.env.FASTN_API_KEY!, baseUrl: BASE_URL }); customer = fastn.customer(E2E); });
afterAll(async () => {
  const drop = async (what: string, f: () => Promise<unknown>) => { try { ev(`cleanup ${what}`, await f()); } catch (e: any) { ev(`cleanup ${what} failed`, e.message); } };
  if (meetingId) await drop("meeting", () => customer.calendar.cancel(meetingId));
  if (dealId) await drop("deal", () => customer.crm.deals.delete(dealId));
  if (taskId) await drop("task", () => customer.crm.tasks.delete(taskId));
  if (noteId) await drop("note", () => customer.crm.notes.delete(noteId));
  if (contactId) await drop("contact", () => customer.crm.contacts.delete(contactId));
});

d("catalog", () => {
  it("lists categories, entities and fields, and the customer's providers", async () => {
    const cats = await fastn.catalog.categories();
    expect(cats.map((c) => c.slug)).toEqual(expect.arrayContaining(["crm", "scheduling"]));
    const contact = await fastn.catalog.entity("crm", "contact");
    expect(contact.operations).toEqual(expect.arrayContaining(["create", "search"]));
    expect((await fastn.catalog.fields("scheduling", "meeting")).filter((f) => f.required).map((f) => f.field).sort()).toEqual(["start_time", "title"]);
    const providers = await customer.catalog.providers("crm", "contact");
    expect(providers.find((p) => p.connectorSlug === "hubspot")?.connected).toBe(true);
    await expect(fastn.catalog.entity("crm", "unicorn")).rejects.toMatchObject({ code: "NOT_FOUND" });
    ev("catalog", { categories: cats.map((c) => `${c.slug}(${c.entities.length})`), providers: providers.filter((p) => p.connected).map((p) => p.connectorSlug) });
  });
});

d("connect(app) and links", () => {
  it("makes a setup link by connector slug, reads it and cancels it", async () => {
    const link = await customer.connect("googleCalendar", { expiresInMinutes: 30 });
    expect(link.url).toMatch(/^https:/); expect(link.status).toBe("pending"); expect(link.widgetId).toMatch(/^wgt_/);
    expect((await customer.links.get(link.setupId)).status).toBe("pending");
    expect((await customer.links.cancel(link.setupId)).status).toBe("revoked");
    await expect(customer.connect("no-such-connector")).rejects.toMatchObject({ code: "WIDGET_NOT_FOUND" });
    ev("connect", { setupId: link.setupId, widgetId: link.widgetId });
  });
});

d("calendar", () => {
  it("freeSlots, book (idempotent), get, find, list, reschedule, cancel", async () => {
    const free = await customer.calendar.freeSlots({ start_time: D(24), end_time: D(32), timezone: "UTC", slot_minutes: 30 });
    expect(free.provider).toBe("googleCalendar"); expect(free.free.length + free.busy.length).toBeGreaterThan(0); expect(free.slots!.length).toBeGreaterThan(0);
    const meeting = { title: `SDK live ${run}`, start_time: D(26), end_time: D(26.5), timezone: "UTC" };
    const a = await customer.calendar.book(meeting, { idempotencyKey: `${run}_book` });
    const b = await customer.calendar.book(meeting, { idempotencyKey: `${run}_book` });
    meetingId = a.id;
    expect(b.id).toBe(a.id); expect(a.data.title).toBe(meeting.title);
    expect((await customer.calendar.get(a.id)).data.status).toBe("confirmed");
    const found = await customer.calendar.find({ start_time: D(0), end_time: D(48) });
    expect(found.records.some((r) => r.id === a.id)).toBe(true);
    expect((await customer.calendar.list({ page_size: 1 })).records.length).toBe(1);
    const moved = await customer.calendar.reschedule(a.id, { start_time: D(27), end_time: D(27.5) });
    expect(Date.parse(moved.data.start_time!)).toBeGreaterThan(Date.parse(a.data.start_time!));
    const gone = await customer.calendar.cancel(a.id, { idempotencyKey: `${run}_cancel` });
    meetingId = "";
    expect(gone).toMatchObject({ id: a.id, provider: "googleCalendar", deleted: true });
    ev("calendar", { id: a.id, slots: free.slots!.length, moved: moved.data.start_time });
  });
});

d("crm", () => {
  it("contacts: create (idempotent), get, update, find, list; notes, tasks, deals with stages", async () => {
    const email = `sdk.${run}@example.com`;
    const c = await customer.crm.contacts.create({ first_name: "Jane", last_name: "Doe", email }, { idempotencyKey: `${run}_contact` });
    contactId = c.id;
    expect((await customer.crm.contacts.get(c.id)).data.email).toBe(email);
    expect((await customer.crm.contacts.update(c.id, { last_name: "Doe-Smith" })).data.last_name).toBe("Doe-Smith");
    let found = await customer.crm.contacts.find({ email });
    for (let i = 0; i < 3 && !found.records.length; i++) { await new Promise((r) => setTimeout(r, 6000)); found = await customer.crm.contacts.find({ email }); }   // HubSpot indexes a new contact with a lag
    expect(found.records.some((r) => r.id === c.id)).toBe(true);
    expect((await customer.crm.contacts.list({ page_size: 1 })).records.length).toBe(1);

    const note = await customer.crm.notes.add({ body: `SDK live ${run}`, parent_id: c.id, parent_type: "contact" }, { idempotencyKey: `${run}_note` });
    noteId = note.id; expect(note.id).toBeTruthy();
    await customer.crm.notes.update(note.id, { body: `SDK live ${run} (edited)` });

    const task = await customer.crm.tasks.add({ subject: `SDK live ${run}`, due_date: D(33) }, { idempotencyKey: `${run}_task` });
    taskId = task.id; expect(task.data.status).toBe("NOT_STARTED");
    expect((await customer.crm.tasks.update(task.id, { status: "COMPLETED" })).data.status).toBe("COMPLETED");
    const probe = await customer.crm.tasks.add({ subject: `SDK warning probe ${run}`, due_date: D(34), contact_id: c.id });
    await customer.crm.tasks.delete(probe.id);
    expect(probe.warnings?.some((w) => /contact_id/.test(w))).toBe(true);                  // a field the provider does not map is reported, not silently dropped

    const stages = await customer.crm.deals.stages();
    expect(stages.records.length).toBeGreaterThan(1);
    const deal = await customer.crm.deals.create({ name: `SDK live ${run}`, amount: 1200 }, { idempotencyKey: `${run}_deal` });
    dealId = deal.id;
    const target = stages.records[1].id;
    await customer.crm.deals.moveStage(deal.id, target);
    expect((await customer.crm.deals.get(deal.id)).data.stage).toBe(target);
    ev("crm", { contact: c.id, note: note.id, task: task.id, deal: deal.id, stage: target, warnings: probe.warnings });
  });
  it("errors: an unknown customer answers 404; a provider the customer has not connected answers a provider error", async () => {
    await expect(fastn.customer(`no_such_customer_${run}`).crm.contacts.list()).rejects.toMatchObject({ status: 404 });
    const err = await customer.crm.contacts.list({}, { provider: "pipedrive" }).catch((e) => e);
    expect(err).toBeInstanceOf(FastnApiError); expect(err.code).toMatch(/PROVIDER/);
    await expect(customer.calendar.book({ title: "no time" } as any)).rejects.toMatchObject({ code: "UNIFIED_VALIDATION_FAILED" });
  });
});
