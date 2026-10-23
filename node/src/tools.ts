// @fastn-ai/sdk (tools) - run the tools a fastn Connect workspace exposes (connect.fastn.dev > Tools), over MCP.
//
//   import { ToolsClient } from "@fastn-ai/sdk";
//   const connect = new ToolsClient({ key: process.env.FASTN_TOOLS_KEY!, url: "https://mcp.fastn.dev/<workspace>" });
//   const tools = await connect.tools();                                     // every tool turned on in the workspace
//   const r = await connect.customer("acme-42").call("googleCalendar__listEvents", { calendarId: "primary" });
//   r.data                                                               // the tool's answer, JSON-decoded
//
// Which tools exist is decided in the workspace, not here: turn a connector on in the workspace and it shows up in tools().
import { FastnNetworkError } from "./errors.js";
import { RETRY_STATUS, backoff, defaultUserAgent, errorInfo, mergeOptions, parseLoose, requestSignal, sleep } from "./http.js";

export interface ToolsClientConfig {
  /** The workspace's key (connect.fastn.dev > Settings > API keys). Sent as Authorization: Bearer. */
  key: string;
  /** The workspace endpoint, e.g. https://mcp.fastn.dev/<workspace> */
  url: string;
  /** A fetch implementation, default globalThis.fetch (Node 20+). */
  fetch?: typeof fetch;
  /** Per-call timeout, default 120000 (tools can be slow). */
  timeoutMs?: number;
  userAgent?: string;
  /** Options applied to every call, e.g. { customer: { ref: "acme-42" } }. */
  defaults?: ToolCallOptions;
}

export interface ToolCallOptions {
  /** The customer the call is for: the id you use for them, sent as X-Org-Id. */
  customer?: { ref: string };
  /** The end user the call is for, sent as X-User-Id (needed when the workspace runs calls as each person). */
  userId?: string;
  /** Extra headers, sent as given. */
  headers?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
  /**
   * Retries for a gateway hiccup (HTTP 429/502/503/504, or a tool answer that is only "error code: 50x"), with the
   * same backoff as the REST client. Default 0: the SDK cannot know whether a tool is safe to repeat, so turn this on
   * for reads.
   */
  retries?: number;
}

/** One tool as the workspace lists it (MCP tools/list). */
export interface Tool {
  name: string;
  title?: string;
  description?: string;
  inputSchema?: Record<string, any>;
  annotations?: Record<string, any>;
  [k: string]: any;
}

/** A tool's answer. `data` is the text content JSON-decoded when it parses, otherwise the raw text. */
export interface ToolResult<T = any> {
  data: T;
  text: string;
  /** MCP content blocks as returned. */
  content: any[];
  structuredContent?: any;
  isError: boolean;
}

/** Thrown when the gateway, the JSON-RPC layer or the tool itself reports a failure. */
export class ToolError extends Error {
  readonly name = "ToolError";
  constructor(
    message: string,
    /**
     * "http": non-2xx from the gateway; "rpc": JSON-RPC error; "tool": the tool ran and answered isError;
     * "auth": the app behind the tool is not connected for this customer yet (see authorizeUrl).
     */
    readonly kind: "http" | "rpc" | "tool" | "auth",
    /** HTTP status of the call. */
    readonly status: number,
    /** JSON-RPC error code, or the gateway's error code when it sent one. */
    readonly code: number | string | undefined,
    /** The tool name, for tools/call failures. */
    readonly tool: string | undefined,
    /** The raw body or message the failure came with. */
    readonly body: unknown,
  ) {
    super(message);
  }
  get isAuth() { return this.status === 401 || this.status === 403; }
  /** True when the customer has to connect the app first; send them to authorizeUrl. */
  get isConnectionRequired() { return this.kind === "auth"; }
  /** Where the customer connects the app (kind "auth" only). */
  get authorizeUrl(): string | undefined { const b: any = this.body; return this.kind === "auth" && typeof b?.authorizeUrl === "string" ? b.authorizeUrl : undefined; }
  /** The app that needs connecting (kind "auth" only). */
  get connector(): string | undefined { const b: any = this.body; return this.kind === "auth" && typeof b?.connector === "string" ? b.connector : undefined; }
  get isUnknownTool() { return (this.kind === "rpc" && this.code === -32601) || ((this.kind === "rpc" || this.kind === "tool") && /unknown tool|is not a tool/i.test(this.message)); }
}

export class ToolsClient {
  readonly url: string;
  private readonly cfg: ToolsClientConfig;
  private nextId = 1;

  constructor(cfg: ToolsClientConfig) {
    if (!cfg?.key || typeof cfg.key !== "string") throw new TypeError("ToolsClient: key is required");
    if (!cfg?.url || !/^https?:\/\//.test(cfg.url)) throw new TypeError("ToolsClient: url must be the workspace endpoint, e.g. https://mcp.fastn.dev/<workspace>");
    this.cfg = cfg;
    this.url = cfg.url.replace(/\/+$/, "");
  }

  /** The same client scoped to one customer: every call carries X-Org-Id = ref. */
  customer(ref: string): ToolsClient {
    if (!ref) throw new TypeError("customer(ref): ref is required");
    return new ToolsClient({ ...this.cfg, defaults: { ...this.cfg.defaults, customer: { ref } } });
  }

  /** Every tool the workspace has turned on, across all connectors (follows paging). */
  async tools(opts: ToolCallOptions = {}): Promise<Tool[]> {
    const out: Tool[] = [];
    let cursor: string | undefined;
    for (let page = 0; page < 100; page++) {
      const res = await this.rpc("tools/list", cursor ? { cursor } : {}, opts);
      out.push(...((res?.tools as Tool[]) ?? []));
      cursor = typeof res?.nextCursor === "string" && res.nextCursor ? res.nextCursor : undefined;
      if (!cursor) break;
    }
    return out;
  }

  /**
   * The tools of one connector, e.g. tools for "googleCalendar". Pass `from` (a list from tools()) to filter without
   * another listing; otherwise the list is fetched once and reused for `cacheMs` (default 60s) on this client.
   */
  async toolsOf(connector: string, opts: ToolCallOptions & { from?: Tool[]; cacheMs?: number } = {}): Promise<Tool[]> {
    const prefix = `${connector}__`;
    const { from, cacheMs = 60_000, ...callOpts } = opts;
    const list = from ?? await this.cachedTools(callOpts, cacheMs);
    return list.filter((t) => t.name.startsWith(prefix));
  }

  private listCache?: { key: string; at: number; list: Promise<Tool[]> };
  private cachedTools(opts: ToolCallOptions, cacheMs: number): Promise<Tool[]> {
    const key = JSON.stringify([opts.customer?.ref ?? this.cfg.defaults?.customer?.ref, opts.userId ?? this.cfg.defaults?.userId]);
    const c = this.listCache;
    if (c && c.key === key && Date.now() - c.at < cacheMs) return c.list;
    const list = this.tools(opts);
    this.listCache = { key, at: Date.now(), list };
    list.catch(() => { if (this.listCache?.list === list) this.listCache = undefined; });
    return list;
  }

  /** Runs one tool by its listed name. Throws ToolError when the tool answers isError. */
  async call<T = any>(name: string, args: Record<string, unknown> = {}, opts: ToolCallOptions = {}): Promise<ToolResult<T>> {
    if (!name) throw new TypeError("call(name): tool name is required");
    const retries = opts.retries ?? this.cfg.defaults?.retries ?? 0;
    for (let attempt = 0; ; attempt++) {
      try {
        return await this.callOnce<T>(name, args, opts);
      } catch (e) {
        if (attempt >= retries || !isGatewayHiccup(e)) throw e;
        await sleep(backoff(attempt));
      }
    }
  }

  private async callOnce<T>(name: string, args: Record<string, unknown>, opts: ToolCallOptions): Promise<ToolResult<T>> {
    const res = await this.rpc("tools/call", { name, arguments: args }, opts, name);
    const content: any[] = Array.isArray(res?.content) ? res.content : [];
    const text = content.filter((c) => c && c.type === "text" && typeof c.text === "string").map((c) => c.text).join("");
    const data = res?.structuredContent !== undefined ? res.structuredContent : parseLoose(text);
    if (res?.isError) {
      if (data && typeof data === "object" && (data as any).authRequired === true && typeof (data as any).authorizeUrl === "string") {
        throw new ToolError(`${name}: ${(data as any).connector ?? "the app"} is not connected for this customer; connect it at ${(data as any).authorizeUrl}`, "auth", 200, "AUTH_REQUIRED", name, data);
      }
      throw new ToolError(errorInfo(data, text).message || `${name} failed`, "tool", 200, undefined, name, data);
    }
    return { data, text, content, structuredContent: res?.structuredContent, isError: false };
  }

  /** A raw JSON-RPC call to the workspace; returns the `result`. Use for methods this class does not wrap. */
  async rpc(method: string, params: Record<string, unknown> = {}, opts: ToolCallOptions = {}, tool?: string): Promise<any> {
    const o = mergeOptions(this.cfg.defaults, opts);
    const id = this.nextId++;
    const headers: Record<string, string> = {
      authorization: `Bearer ${this.cfg.key}`,
      "content-type": "application/json",
      accept: "application/json, text/event-stream",
      "user-agent": this.cfg.userAgent ?? defaultUserAgent(),
    };
    if (o.customer?.ref) headers["x-org-id"] = o.customer.ref;
    if (o.userId) headers["x-user-id"] = o.userId;
    for (const [k, v] of Object.entries(o.headers)) if (typeof v === "string") headers[k.toLowerCase()] = v;

    const { signal, release } = requestSignal(o.timeoutMs ?? this.cfg.timeoutMs ?? 120_000, o.signal);
    let res: Response, raw: string;
    try {
      res = await (this.cfg.fetch ?? globalThis.fetch)(this.url, { method: "POST", headers, body: JSON.stringify({ jsonrpc: "2.0", id, method, params }), signal });
      raw = await res.text();
    } catch (e) {
      throw new FastnNetworkError(`${method}${tool ? ` ${tool}` : ""}: ${(e as Error)?.message ?? String(e)}`, "POST", this.url, e);
    } finally {
      release();
    }
    const msgs = parseMessages(raw);
    const msg = msgs.find((m) => m && m.id === id) ?? msgs.find((m) => m && ("result" in m || "error" in m)) ?? msgs[0];
    if (!res.ok) {
      const body = msg ?? parseLoose(raw);
      const info = errorInfo(body, raw);
      throw new ToolError(`${method}${tool ? ` ${tool}` : ""}: HTTP ${res.status} ${info.message}`.trim(), "http", res.status, info.code, tool, body);
    }
    if (!msg) throw new ToolError(`${method}: the gateway answered without a JSON-RPC message`, "rpc", res.status, undefined, tool, raw);
    if (msg.error) throw new ToolError(`${method}${tool ? ` ${tool}` : ""}: ${msg.error.message ?? "error"}`, "rpc", res.status, msg.error.code, tool, msg.error);
    return msg.result;
  }
}

/**
 * A failure that is the gateway's, not the tool's: worth one more try on a read. HTTP 429/502/503/504, or a tool
 * answer that is only "error code: 50x" (the gateway reports an upstream 5xx inside a successful result today;
 * platform ticket KAT-8586 moves that to a real error, after which this text match can go).
 */
export function isGatewayHiccup(e: unknown): boolean {
  if (!(e instanceof ToolError)) return false;
  if (e.kind === "http") return RETRY_STATUS.has(e.status);
  return /^error code: 50[234]$/i.test(e.message.trim());
}

/** JSON or SSE ("data: {...}" lines) → the JSON-RPC messages inside. */
export function parseMessages(raw: string): any[] {
  const s = raw.trim();
  if (!s) return [];
  if (s.startsWith("{") || s.startsWith("[")) {
    try { const v = JSON.parse(s); return Array.isArray(v) ? v : [v]; } catch { /* fall through */ }
  }
  const out: any[] = [];
  let buf: string[] = [];
  const flush = () => { if (buf.length) { try { out.push(JSON.parse(buf.join("\n"))); } catch { /* ignore */ } buf = []; } };
  for (const line of s.split(/\r?\n/)) {
    if (line.startsWith("data:")) buf.push(line.slice(5).trim());
    else if (line === "") flush();
  }
  flush();
  return out;
}



