// Live run against a fastn Connect workspace. Skipped unless LIVE=1, FASTN_TOOLS_KEY, FASTN_TOOLS_URL and FASTN_TEST_CUSTOMER are set.
// Creates one Google Calendar event (sdk-live-<run>) on the workspace's shared account and deletes it at the end.
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import fs from "node:fs";
import { FastnClient, ToolsClient, ToolError, unstable } from "../../src/index.js";

const LIVE = process.env.LIVE === "1" && !!process.env.FASTN_TOOLS_KEY && !!process.env.FASTN_TOOLS_URL && !!process.env.FASTN_TEST_CUSTOMER;
const d = describe.skipIf(!LIVE);
const URL_ = process.env.FASTN_TOOLS_URL ?? "";
const EV = new URL("./evidence.jsonl", import.meta.url).pathname;
const mask = (s: string) => s.replace(/(emb_|ucl_|fsk_[a-z]+_|whsec_|stp_tok_|sk_)[A-Za-z0-9_\-]{6,}/g, "$1***").replace(/[A-Za-z0-9_-]{48,}/g, "<tok>");
const ev = (step: string, data: unknown) => fs.appendFileSync(EV, mask(JSON.stringify({ at: new Date().toISOString(), step: `tools ${step}`, data })).slice(0, 2500) + "\n");
const run = new Date().toISOString().slice(11, 19).replace(/:/g, "");
const E2E = process.env.FASTN_TEST_CUSTOMER ?? "";
const day = new Date(Date.now() + 10 * 86400e3).toISOString().slice(0, 10);

let ucl: ToolsClient; let eventId: string | undefined;
// A delegated workspace key requires X-Org-Id on every call, so the client defaults to the test customer.
beforeAll(() => { ucl = new ToolsClient({ key: process.env.FASTN_TOOLS_KEY!, url: URL_, defaults: { customer: { ref: E2E } } }); });
afterAll(async () => {
  if (eventId) {
    const r = await ucl.call("googleCalendar__deleteEvent", { calendarId: "primary", eventId, sendUpdates: "none" }).catch((e) => ({ data: `delete failed: ${e.message}` }));
    const after = await ucl.call("googleCalendar__getEvent", { calendarId: "primary", eventId }).then((g) => g.data?.status).catch((e) => `getEvent: ${e.message}`);
    ev("deleteEvent", { answer: r.data || "deleted", statusAfter: after });
    if (after !== "cancelled") throw new Error(`event ${eventId} still ${after} after delete`);
  }
});

// The calendar tests need a workspace with Google Calendar turned on (the e2e workspace on prod). Elsewhere they are
// skipped with a note, so a run on another workspace still reports honestly.
let hasCalendar = false;
const calendarOnly = (t: { skip: () => void }) => { if (!hasCalendar) { ev("skip", "googleCalendar is not turned on in this workspace"); t.skip(); } };
d("tools: the workspace's tools", () => {
  it("tools() lists every connector turned on; the Fastn Workspace is there", async () => {
    const tools = await ucl.tools();
    const names = tools.map((t) => t.name);
    const connectors = [...new Set(names.map((n) => n.split("__")[0]))];
    hasCalendar = names.includes("googleCalendar__listCalendars");
    ev("tools", { count: tools.length, connectors, calendar: (await ucl.toolsOf("googleCalendar")).length });
    expect(tools.length).toBeGreaterThan(50);
    expect(names.some((n) => n.startsWith("fastnPlatform__"))).toBe(true);
    if (hasCalendar) expect((await ucl.toolsOf("googleCalendar")).length).toBeGreaterThanOrEqual(20);
  }, 60_000);
  it("googleCalendar listCalendars and listEvents (read-only)", async (t) => {
    calendarOnly(t);
    const cals = await ucl.call("googleCalendar__listCalendars", { maxResults: 5 });
    ev("listCalendars", { keys: Object.keys(cals.data ?? {}), count: cals.data?.items?.length, first: cals.data?.items?.[0]?.id });
    expect(typeof cals.data).toBe("object");
    const evs = await ucl.call("googleCalendar__listEvents", { calendarId: "primary", timeMin: new Date().toISOString(), maxResults: 5, singleEvents: true, orderBy: "startTime" });
    ev("listEvents", { keys: Object.keys(evs.data ?? {}), count: evs.data?.items?.length });
    expect(typeof evs.data).toBe("object");
  }, 60_000);
  it("create -> get -> patch -> get an event on the shared account (deleted in afterAll)", async (t) => {
    calendarOnly(t);
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
  it("the same client runs a Fastn Workspace tool, scoped to a customer with X-Org-Id", async (t) => {
    const who = await ucl.customer(E2E).call("fastnPlatform__whoami", {})
      .catch((e) => { if (e instanceof ToolError && e.isConnectionRequired) { ev("skip", `Fastn Workspace not connected for ${E2E} in this workspace: ${e.authorizeUrl}`); t.skip(); } throw e; });
    const noOrg = await new ToolsClient({ key: process.env.FASTN_TOOLS_KEY!, url: URL_ }).call("fastnPlatform__whoami", {}).catch((e) => e);
    ev("whoami without X-Org-Id", { kind: noOrg?.kind, status: noOrg?.status, message: noOrg?.message, delegatedKey: noOrg instanceof ToolError });
    // A delegated workspace key answers 400 without X-Org-Id; an org-level key simply runs as the workspace.
    if (noOrg instanceof ToolError) expect(noOrg.status).toBe(400);
    ev("whoami", who.data);
    expect(typeof who.data).toBe("object");
    if (process.env.FASTN_API_KEY) {
      const fastn = new FastnClient({ apiKey: process.env.FASTN_API_KEY, baseUrl: process.env.FASTN_BASE_URL, tools: { key: process.env.FASTN_TOOLS_KEY!, url: URL_ } });
      const viaClient = await fastn.customer(E2E).tools.call("fastnPlatform__whoami", {});
      expect(JSON.stringify(viaClient.data)).toBe(JSON.stringify(who.data));
    }
  }, 60_000);
  it("Fastn Workspace tool inputs use the same names as the SDK's generated inputs (no naming drift)", async () => {
    // The gateway derives tool input names from the same spec with its own copy of the naming rules; this catches
    // the two drifting apart. Headers map differently on purpose (x-end-org-ref -> endOrgRef) and are left out.
    const tools = await ucl.toolsOf("fastnPlatform");
    const drift: string[] = []; let compared = 0;
    for (const t of tools) {
      const op = (unstable.OPS as any)[t.name.replace(/^fastnPlatform__/, "")];
      if (!op) continue;
      const sdkKeys = new Set<string>([...op.params.filter((p: any) => p.in !== "header").map((p: any) => p.key), ...Object.keys(op.body?.keys ?? {}), ...(op.body?.kind === "whole" ? [op.body.key] : [])]);
      // The gateway exposes the cross-cutting headers as tool inputs; the SDK takes them as per-call options.
      const toolKeys = Object.keys((t as any).inputSchema?.properties ?? {}).filter((k) => !/^(endOrgRef|endOrgId|_task|installationId|idempotencyKey|fastnCorrelationId|fastnEnv|fastnTargetOrg)$/.test(k));
      compared++;
      for (const k of toolKeys) if (!sdkKeys.has(k)) drift.push(`${t.name}: tool input "${k}" has no SDK input (sdk has ${[...sdkKeys].join(",")})`);
    }
    ev("naming drift", { toolsCompared: compared, drift: drift.slice(0, 20) });
    expect(compared).toBeGreaterThan(20);
    expect(drift).toEqual([]);
  }, 60_000);
  it("a wrong tool name is a typed ToolError", async () => {
    const e = await ucl.call("googleCalendar__noSuchTool", {}).catch((x) => x);
    ev("badTool", { kind: e?.kind, code: e?.code, message: e?.message });
    expect(e).toBeInstanceOf(ToolError);
    expect(["rpc", "tool", "http"]).toContain(e.kind);
  }, 60_000);
});
