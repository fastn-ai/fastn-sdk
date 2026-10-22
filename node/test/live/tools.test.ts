// Live run against the Trillet fastn Connect workspace (mcp.fastn.dev/trillet). Skipped unless LIVE=1 and FASTN_TOOLS_KEY are set.
// Creates one Google Calendar event (sdk-live-<run>) on the workspace's shared account and deletes it at the end.
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import fs from "node:fs";
import { FastnClient, ToolsClient, ToolError } from "../../src/index.js";

const LIVE = process.env.LIVE === "1" && !!process.env.FASTN_TOOLS_KEY;
const d = describe.skipIf(!LIVE);
const URL_ = process.env.FASTN_TOOLS_URL ?? "https://mcp.fastn.dev/trillet";
const EV = new URL("./evidence.jsonl", import.meta.url).pathname;
const mask = (s: string) => s.replace(/(emb_|ucl_|fsk_[a-z]+_|whsec_|stp_tok_|sk_)[A-Za-z0-9_\-]{6,}/g, "$1***").replace(/[A-Za-z0-9_-]{48,}/g, "<tok>");
const ev = (step: string, data: unknown) => fs.appendFileSync(EV, mask(JSON.stringify({ at: new Date().toISOString(), step: `tools ${step}`, data })).slice(0, 2500) + "\n");
const run = new Date().toISOString().slice(11, 19).replace(/:/g, "");
const E2E = "trillet_ws_prod_e2e";
const day = new Date(Date.now() + 10 * 86400e3).toISOString().slice(0, 10);

let ucl: ToolsClient; let eventId: string | undefined;
// The Trillet key is a delegated key: the gateway requires X-Org-Id on every call, so the client defaults to the e2e customer.
beforeAll(() => { ucl = new ToolsClient({ key: process.env.FASTN_TOOLS_KEY!, url: URL_, defaults: { customer: { ref: E2E } } }); });
afterAll(async () => {
  if (eventId) {
    const r = await ucl.call("googleCalendar__deleteEvent", { calendarId: "primary", eventId, sendUpdates: "none" }).catch((e) => ({ data: `delete failed: ${e.message}` }));
    const after = await ucl.call("googleCalendar__getEvent", { calendarId: "primary", eventId }).then((g) => g.data?.status).catch((e) => `getEvent: ${e.message}`);
    ev("deleteEvent", { answer: r.data || "deleted", statusAfter: after });
    if (after !== "cancelled") throw new Error(`event ${eventId} still ${after} after delete`);
  }
});

d("tools: the workspace's tools", () => {
  it("tools() lists every connector turned on; Google Calendar and Fastn Workspace are there", async () => {
    const tools = await ucl.tools();
    const names = tools.map((t) => t.name);
    const connectors = [...new Set(names.map((n) => n.split("__")[0]))];
    ev("tools", { count: tools.length, connectors, calendar: (await ucl.toolsOf("googleCalendar")).length });
    expect(tools.length).toBeGreaterThan(100);
    expect(names).toContain("googleCalendar__listCalendars");
    expect(names.some((n) => n.startsWith("fastnPlatform__"))).toBe(true);
    expect((await ucl.toolsOf("googleCalendar")).length).toBeGreaterThanOrEqual(20);
  }, 60_000);
  it("googleCalendar listCalendars and listEvents (read-only)", async () => {
    const cals = await ucl.call("googleCalendar__listCalendars", { maxResults: 5 });
    ev("listCalendars", { keys: Object.keys(cals.data ?? {}), count: cals.data?.items?.length, first: cals.data?.items?.[0]?.id });
    expect(typeof cals.data).toBe("object");
    const evs = await ucl.call("googleCalendar__listEvents", { calendarId: "primary", timeMin: new Date().toISOString(), maxResults: 5, singleEvents: true, orderBy: "startTime" });
    ev("listEvents", { keys: Object.keys(evs.data ?? {}), count: evs.data?.items?.length });
    expect(typeof evs.data).toBe("object");
  }, 60_000);
  it("create -> get -> patch -> get an event on the shared account (deleted in afterAll)", async () => {
    const created = await ucl.call("googleCalendar__createEvent", { calendarId: "primary", summary: `sdk-live-${run}`, description: "@fastn-ai/sdk ucl live test, auto-deleted", startDateTime: `${day}T10:00:00`, endDateTime: `${day}T10:30:00`, timeZone: "Europe/London" });
    ev("createEvent", { id: created.data?.id, summary: created.data?.summary, start: created.data?.start, status: created.data?.status, link: created.data?.htmlLink });
    eventId = created.data?.id; expect(eventId).toBeTruthy();
    const got = await ucl.call("googleCalendar__getEvent", { calendarId: "primary", eventId });
    expect(got.data?.summary).toBe(`sdk-live-${run}`);
    const patched = await ucl.call("googleCalendar__patchEvent", { calendarId: "primary", eventId, summary: `sdk-live-${run} moved` });
    ev("patchEvent", { summary: patched.data?.summary, updated: patched.data?.updated });
    const again = await ucl.call("googleCalendar__getEvent", { calendarId: "primary", eventId });
    expect(again.data?.summary).toBe(`sdk-live-${run} moved`);
  }, 120_000);
  it("the same client runs a Fastn Workspace tool, scoped to a customer with X-Org-Id", async () => {
    const who = await ucl.customer(E2E).call("fastnPlatform__whoami", {});
    const noOrg = await new ToolsClient({ key: process.env.FASTN_TOOLS_KEY!, url: URL_ }).call("fastnPlatform__whoami", {}).catch((e) => e);
    ev("whoami without X-Org-Id", { kind: noOrg?.kind, status: noOrg?.status, message: noOrg?.message });
    expect(noOrg).toBeInstanceOf(ToolError); expect(noOrg.status).toBe(400);
    ev("whoami", who.data);
    expect(typeof who.data).toBe("object");
    if (process.env.FASTN_API_KEY) {
      const fastn = new FastnClient({ apiKey: process.env.FASTN_API_KEY, tools: { key: process.env.FASTN_TOOLS_KEY!, url: URL_ } });
      const viaClient = await fastn.customer(E2E).tools.call("fastnPlatform__whoami", {});
      expect(JSON.stringify(viaClient.data)).toBe(JSON.stringify(who.data));
    }
  }, 60_000);
  it("a wrong tool name is a typed ToolError", async () => {
    const e = await ucl.call("googleCalendar__noSuchTool", {}).catch((x) => x);
    ev("badTool", { kind: e?.kind, code: e?.code, message: e?.message });
    expect(e).toBeInstanceOf(ToolError);
    expect(["rpc", "tool", "http"]).toContain(e.kind);
  }, 60_000);
});
