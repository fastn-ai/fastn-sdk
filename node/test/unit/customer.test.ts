import { describe, it, expect, vi } from "vitest";
import { FastnClient } from "../../src/index.js";

function fx(handler: (url: string, init: any) => { status?: number; body: unknown }) {
  const calls: { url: string; init: any }[] = [];
  const fetch = vi.fn(async (url: string, init: any) => { calls.push({ url, init }); const r = handler(url, init); return new Response(JSON.stringify(r.body), { status: r.status ?? 200, headers: { "content-type": "application/json" } }); });
  return { fetch: fetch as unknown as typeof globalThis.fetch, calls };
}
const orgRow = { id: "11111111-aaaa", externalRef: "acme-1", orgId: "acme-1", name: "Acme", type: "end_org" };

describe("customer context", () => {
  it("resolves and caches fastn's org id from listOrgs", async () => {
    const m = fx((url) => url.includes("/v1/orgs?") ? { body: { data: [orgRow] } } : url.includes("/v1/connections") ? { body: { data: [{ id: "conn_1" }] } } : { body: { data: orgRow } });
    const c = new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("acme-1");
    expect(await c.id()).toBe("11111111-aaaa");
    await c.connections(); await c.get();
    expect(m.calls.map((x) => x.url)).toEqual(["https://api.fastn.dev/v1/orgs?type=end_org", "https://api.fastn.dev/v1/connections?endOrgId=11111111-aaaa", "https://api.fastn.dev/v1/orgs/11111111-aaaa"]);
  });
  it("register creates once and returns the existing org afterwards", async () => {
    let created = false;
    const m = fx((url, init) => {
      if (url.endsWith("/v1/orgs?type=end_org")) return { body: { data: created ? [orgRow] : [] } };
      if (init.method === "POST") { created = true; return { status: 201, body: { data: orgRow } }; }
      return { body: {} };
    });
    const c = new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("acme-1");
    const first = await c.register({ name: "Acme" });
    expect(first.data.id).toBe("11111111-aaaa"); expect(JSON.parse(m.calls[1].init.body)).toEqual({ plan: "free", name: "Acme", orgId: "acme-1" });
    const again = await c.register({ name: "Acme" });
    expect(again.existed).toBe(true); expect(m.calls.filter((x) => x.init.method === "POST").length).toBe(1);
    expect(await c.id()).toBe("11111111-aaaa"); expect(m.calls.length).toBe(3);
  });
  it("unknown ref fails clearly", async () => {
    const m = fx(() => ({ body: { data: [] } }));
    await expect(new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("ghost").id()).rejects.toThrow(/not registered/);
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
});
