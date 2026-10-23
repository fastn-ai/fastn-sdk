import { describe, it, expect, vi } from "vitest";
import { FastnClient, ToolsClient, ToolError, FastnNetworkError, parseMessages } from "../../src/index.js";

type Reply = { status?: number; body?: unknown; sse?: boolean } | Error;
function mockFetch(replies: Reply[]) {
  const calls: { url: string; init: any; json: any }[] = [];
  const fetch = vi.fn(async (url: string, init: any) => {
    calls.push({ url, init, json: JSON.parse(init.body) });
    const r = replies.shift() ?? { body: { jsonrpc: "2.0", id: 1, result: {} } };
    if (r instanceof Error) throw r;
    const text = r.sse ? `event: message\ndata: ${JSON.stringify(r.body)}\n\n` : typeof r.body === "string" ? r.body : JSON.stringify(r.body);
    return new Response(text, { status: r.status ?? 200, headers: { "content-type": r.sse ? "text/event-stream" : "application/json" } });
  });
  return { fetch: fetch as unknown as typeof globalThis.fetch, calls };
}
const rpcOk = (id: number, result: unknown) => ({ jsonrpc: "2.0", id, result });
const toolOk = (id: number, text: string, isError = false) => rpcOk(id, { content: [{ type: "text", text }], isError });
const ucl = (m: ReturnType<typeof mockFetch>, extra = {}) => new ToolsClient({ key: "ucl_test", url: "https://mcp.fastn.dev/acme", fetch: m.fetch, ...extra });

describe("tools client", () => {
  it("call() posts JSON-RPC with the key, customer and user headers, and decodes the text answer", async () => {
    const m = mockFetch([{ body: toolOk(1, JSON.stringify({ items: [{ id: "cal_1" }] })) }]);
    const r = await ucl(m).call("googleCalendar__listCalendars", { maxResults: 5 }, { customer: { ref: "acme-42" }, userId: "u-7" });
    expect(m.calls[0].url).toBe("https://mcp.fastn.dev/acme");
    expect(m.calls[0].init.method).toBe("POST");
    const h = m.calls[0].init.headers;
    expect(h.authorization).toBe("Bearer ucl_test"); expect(h["x-org-id"]).toBe("acme-42"); expect(h["x-user-id"]).toBe("u-7");
    expect(h.accept).toContain("text/event-stream"); expect(h["user-agent"]).toMatch(/^fastn-ai-sdk\//);
    expect(m.calls[0].json).toMatchObject({ jsonrpc: "2.0", method: "tools/call", params: { name: "googleCalendar__listCalendars", arguments: { maxResults: 5 } } });
    expect(r.data).toEqual({ items: [{ id: "cal_1" }] }); expect(r.isError).toBe(false); expect(r.text).toContain("cal_1");
  });
  it("reads SSE answers and plain-text answers", async () => {
    const m = mockFetch([{ body: toolOk(1, '{"ok":true}'), sse: true }, { body: toolOk(2, "done, nothing to parse") }]);
    const c = ucl(m);
    expect((await c.call("a")).data).toEqual({ ok: true });
    expect((await c.call("b")).data).toBe("done, nothing to parse");
  });
  it("tools() follows nextCursor and toolsOf() filters by connector", async () => {
    const m = mockFetch([
      { body: rpcOk(1, { tools: [{ name: "googleCalendar__listEvents" }, { name: "fastnPlatform__whoami" }], nextCursor: "p2" }) },
      { body: rpcOk(2, { tools: [{ name: "googleCalendar__createEvent" }] }) },
      { body: rpcOk(3, { tools: [{ name: "googleCalendar__listEvents" }, { name: "hubspot__x" }] }) },
    ]);
    const c = ucl(m);
    expect((await c.tools()).map((t) => t.name)).toEqual(["googleCalendar__listEvents", "fastnPlatform__whoami", "googleCalendar__createEvent"]);
    expect(m.calls[1].json.params).toEqual({ cursor: "p2" });
    expect((await c.toolsOf("googleCalendar")).map((t) => t.name)).toEqual(["googleCalendar__listEvents"]);
  });
  it("three failure shapes become ToolError: HTTP, JSON-RPC error, tool isError", async () => {
    const m = mockFetch([
      { status: 403, body: { error: "unknown org", code: "IDENTITY_ORG_NOT_FOUND" } },
      { body: { jsonrpc: "2.0", id: 2, error: { code: -32601, message: "Unknown tool: nope__x" } } },
      { body: toolOk(3, JSON.stringify({ error: { message: "calendar not found" } }), true) },
      { body: toolOk(4, 'unknown tool "googleCalendar__noSuchTool" - "noSuchTool" is not a tool on this connector', true) },
    ]);
    const c = ucl(m);
    const e1 = await c.call("a").catch((e) => e) as ToolError;
    expect(e1).toBeInstanceOf(ToolError); expect(e1.kind).toBe("http"); expect(e1.status).toBe(403); expect(e1.isAuth).toBe(true); expect(e1.code).toBe("IDENTITY_ORG_NOT_FOUND"); expect(e1.message).toContain("unknown org");
    const e2 = await c.call("nope__x").catch((e) => e) as ToolError;
    expect(e2.kind).toBe("rpc"); expect(e2.code).toBe(-32601); expect(e2.isUnknownTool).toBe(true); expect(e2.tool).toBe("nope__x");
    const e3 = await c.call("googleCalendar__getEvent").catch((e) => e) as ToolError;
    expect(e3.kind).toBe("tool"); expect(e3.message).toBe("calendar not found"); expect(e3.tool).toBe("googleCalendar__getEvent"); expect(e3.isUnknownTool).toBe(false);
    const e4 = await c.call("googleCalendar__noSuchTool").catch((e) => e) as ToolError;   // the real gateway shape: isError text, not a JSON-RPC error
    expect(e4.kind).toBe("tool"); expect(e4.isUnknownTool).toBe(true);
  });
  it("retries a gateway hiccup only when asked", async () => {
    const hiccup = (id: number) => toolOk(id, "error code: 502", true);
    const m = mockFetch([{ body: hiccup(1) }, { body: toolOk(2, "{}") }, { body: hiccup(3) }]);
    const c = ucl(m);
    expect((await c.call("googleCalendar__listCalendars", {}, { retries: 1 })).data).toEqual({});
    const e = await c.call("googleCalendar__listCalendars").catch((x) => x) as ToolError;
    expect(e.kind).toBe("tool"); expect(e.message).toBe("error code: 502"); expect(m.calls).toHaveLength(3);
  });
  it("network failure becomes FastnNetworkError", async () => {
    const m = mockFetch([new TypeError("fetch failed")]);
    await expect(ucl(m).call("a")).rejects.toBeInstanceOf(FastnNetworkError);
  });
  it("customer(ref) scopes every call; FastnClient wires tools and customer(ref).tools", async () => {
    const m = mockFetch([{ body: toolOk(1, "{}") }, { body: toolOk(2, "{}") }]);
    await ucl(m).customer("acme-1").call("x");
    expect(m.calls[0].init.headers["x-org-id"]).toBe("acme-1");
    const fastn = new FastnClient({ apiKey: "k", fetch: m.fetch, tools: { key: "ucl_test", url: "https://mcp.fastn.dev/acme" } });
    await fastn.customer("acme-2").tools.call("y");
    expect(m.calls[1].init.headers["x-org-id"]).toBe("acme-2"); expect(m.calls[1].init.headers.authorization).toBe("Bearer ucl_test");
    expect(() => new FastnClient({ apiKey: "k", fetch: m.fetch }).customer("z").tools).toThrow(/tools/);
    expect(() => new ToolsClient({ key: "k", url: "mcp.fastn.dev/x" } as any)).toThrow(/url/);
  });
  it("parseMessages handles JSON, arrays and multi-event SSE", () => {
    expect(parseMessages('{"id":1}')).toEqual([{ id: 1 }]);
    expect(parseMessages('[{"id":1},{"id":2}]')).toHaveLength(2);
    expect(parseMessages('event: a\ndata: {"id":1}\n\nevent: b\ndata: {"id":2,\ndata: "x":1}\n')).toEqual([{ id: 1 }, { id: 2, x: 1 }]);
    expect(parseMessages("")).toEqual([]);
  });
  it("an authRequired answer becomes a ToolError of kind auth with the connect URL", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ jsonrpc: "2.0", id: 1, result: { isError: true, content: [{ type: "text", text: JSON.stringify({ authRequired: true, connector: "HubSpot", authorizeUrl: "https://connect.example/u/connect?intent=abc", caller: "agent" }) }] } }), { status: 200, headers: { "content-type": "application/json" } }));
    const t = new ToolsClient({ key: "k", url: "https://mcp.example/ws", fetch: fetch as any });
    const e = await t.customer("acme-1").call("hubspot__listContacts", {}).catch((x) => x);
    expect(e).toBeInstanceOf(ToolError);
    expect(e.kind).toBe("auth"); expect(e.isConnectionRequired).toBe(true); expect(e.isUnknownTool).toBe(false);
    expect(e.authorizeUrl).toBe("https://connect.example/u/connect?intent=abc"); expect(e.connector).toBe("HubSpot");
    expect(e.message).toContain("not connected");
  });
});
