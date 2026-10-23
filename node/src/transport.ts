import { FastnApiError, FastnNetworkError } from "./errors.js";

export interface ParamDef { key: string; name: string; in: "path" | "query" | "header"; required?: boolean }
export interface BodyDef {
  /** `fields`: the input's named keys form the JSON body; `whole`: one input key is the entire body. */
  kind: "fields" | "whole";
  /** fields: input key -> wire name. */
  keys?: Record<string, string>;
  /** whole: the input key that carries the body. */
  key?: string;
  required?: boolean;
  /** fields: the spec allows extra body fields (additionalProperties); unknown input keys are sent as given. */
  open?: boolean;
  contentType: string;
}
export interface OpDef { id: string; method: string; path: string; params: ParamDef[]; body?: BodyDef }

/** Per-call options. Everything here is optional and applies to any operation. */
export interface RequestOptions {
  /** Sent as Idempotency-Key: a retry with the same key returns the first answer instead of acting twice. */
  idempotencyKey?: string;
  /** Sent as X-Fastn-Correlation-Id: your own id for the request; look it up later with unified.listUnifiedCalls. */
  correlationId?: string;
  /**
   * The customer the call is for. `{ ref }` is the id you chose for the customer (sent as x-end-org-ref);
   * `{ id }` is fastn's own id of that customer org (sent as x-end-org-id). `fastn.customer(ref)` sets this for you.
   */
  customer?: { ref: string } | { id: string };
  /** Sent as x-installation-id. */
  installationId?: string;
  /** Sent as x-fastn-target-org: run as another org you are a member of (user tokens only). */
  targetOrg?: string;
  /** Extra headers, sent as given. */
  headers?: Record<string, string>;
  /** Overrides the client's timeout for this call. */
  timeoutMs?: number;
  /** Overrides the client's retry count for this call (0 = never retry). */
  retries?: number;
  signal?: AbortSignal;
}

export interface Transport {
  call(op: OpDef, input: Record<string, unknown>, opts?: RequestOptions): Promise<any>;
}

export interface FetchTransportConfig {
  apiKey: string;
  baseUrl: string;
  timeoutMs: number;
  /** Retries for GET and for calls that carry an Idempotency-Key, on 429, 502, 503, 504 and network errors. */
  retries: number;
  fetch?: typeof fetch;
  userAgent?: string;
  /** Called after every attempt; use it for logging. Never receives the api key. */
  onRequest?: (info: RequestLog) => void;
  /** Headers added to every call (e.g. from a customer context). */
  defaultOptions?: RequestOptions;
}

export interface RequestLog {
  opId: string; method: string; url: string; status: number; durationMs: number; attempt: number; requestId?: string; correlationId?: string;
}

const RETRY_STATUS = new Set([429, 502, 503, 504]);
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export class FetchTransport implements Transport {
  constructor(private readonly cfg: FetchTransportConfig) {}

  /** Builds the request without sending it. Exposed for tests and for debugging what the SDK sends. */
  prepare(op: OpDef, input: Record<string, unknown>, opts: RequestOptions = {}): { url: string; init: RequestInit & { headers: Record<string, string> } } {
    const o = { ...this.cfg.defaultOptions, ...opts, headers: { ...this.cfg.defaultOptions?.headers, ...opts.headers } };
    let path = op.path;
    const query = new URLSearchParams();
    const headers: Record<string, string> = { accept: "application/json", "x-api-key": this.cfg.apiKey };
    if (this.cfg.userAgent) headers["user-agent"] = this.cfg.userAgent;
    for (const p of op.params) {
      const v = input[p.key];
      if (v === undefined || v === null) {
        if (p.required) throw new TypeError(`${op.id}: "${p.key}" is required (${p.in} ${p.name})`);
        continue;
      }
      if (p.in === "path") path = path.replace(`{${p.name}}`, encodeURIComponent(String(v)));
      else if (p.in === "query") {
        if (Array.isArray(v)) for (const x of v) query.append(p.name, String(x));
        else query.set(p.name, typeof v === "object" ? JSON.stringify(v) : String(v));
      } else headers[p.name.toLowerCase()] = String(v);
    }
    const missing = path.match(/\{[^}]+\}/g);
    if (missing) throw new TypeError(`${op.id}: path parameter ${missing.join(", ")} not filled`);
    const cross: [keyof RequestOptions, string][] = [["idempotencyKey", "idempotency-key"], ["correlationId", "x-fastn-correlation-id"], ["installationId", "x-installation-id"], ["targetOrg", "x-fastn-target-org"]];
    for (const [k, h] of cross) if (typeof o[k] === "string" && o[k] && headers[h] === undefined) headers[h] = o[k] as string;
    if (o.customer) {
      if ("ref" in o.customer && o.customer.ref) headers["x-end-org-ref"] ??= o.customer.ref;
      else if ("id" in o.customer && o.customer.id) headers["x-end-org-id"] ??= o.customer.id;
    }
    for (const [k, v] of Object.entries(o.headers)) if (typeof v === "string") headers[k.toLowerCase()] = v;
    let body: string | undefined;
    if (op.body) {
      let payload: unknown;
      if (op.body.kind === "fields") {
        const obj: Record<string, unknown> = {};
        for (const [key, name] of Object.entries(op.body.keys ?? {})) if (input[key] !== undefined) obj[name] = input[key];
        if (op.body.open) {
          const taken = new Set([...Object.keys(op.body.keys ?? {}), ...op.params.map((p) => p.key)]);
          for (const [key, v] of Object.entries(input)) if (!taken.has(key) && v !== undefined) obj[key] = v;
        }
        payload = obj;
      } else {
        payload = input[op.body.key!];
        if (payload === undefined && op.body.required) throw new TypeError(`${op.id}: "${op.body.key}" (request body) is required`);
      }
      if (payload !== undefined) {
        if (op.body.contentType === "application/x-www-form-urlencoded") {
          body = typeof payload === "string" ? payload : new URLSearchParams(Object.entries(payload as Record<string, string>).map(([k, v]) => [k, String(v)])).toString();
        } else body = typeof payload === "string" ? payload : JSON.stringify(payload);
        headers["content-type"] = op.body.contentType;
      }
    }
    const qs = query.toString();
    const url = `${this.cfg.baseUrl}${path}${qs ? `?${qs}` : ""}`;
    return { url, init: { method: op.method, headers, body } };
  }

  async call(op: OpDef, input: Record<string, unknown>, opts: RequestOptions = {}): Promise<any> {
    const { url, init } = this.prepare(op, input, opts);
    const f = this.cfg.fetch ?? globalThis.fetch;
    if (typeof f !== "function") throw new FastnNetworkError("No fetch available: use Node 20+ or pass { fetch } to the client", op.method, op.path);
    const retryable = op.method === "GET" || init.headers["idempotency-key"] !== undefined;
    const maxRetries = retryable ? (opts.retries ?? this.cfg.retries) : 0;
    const timeoutMs = opts.timeoutMs ?? this.cfg.timeoutMs;
    for (let attempt = 0; ; attempt++) {
      const t0 = Date.now();
      let res: Response;
      try {
        const signals = [AbortSignal.timeout(timeoutMs), ...(opts.signal ? [opts.signal] : [])];
        res = await f(url, { ...init, signal: signals.length > 1 && "any" in AbortSignal ? (AbortSignal as any).any(signals) : signals[0] });
      } catch (err) {
        this.cfg.onRequest?.({ opId: op.id, method: op.method, url, status: 0, durationMs: Date.now() - t0, attempt, correlationId: init.headers["x-fastn-correlation-id"] });
        if (attempt < maxRetries && !opts.signal?.aborted) { await sleep(backoff(attempt)); continue; }
        throw new FastnNetworkError(`${op.method} ${op.path}: ${(err as Error)?.message ?? String(err)}`, op.method, op.path, err);
      }
      const requestId = res.headers.get("x-request-id") ?? undefined;
      this.cfg.onRequest?.({ opId: op.id, method: op.method, url, status: res.status, durationMs: Date.now() - t0, attempt, requestId, correlationId: init.headers["x-fastn-correlation-id"] });
      const text = await res.text();
      let parsed: unknown = text;
      const ct = res.headers.get("content-type") ?? "";
      if (text && (ct.includes("json") || /^[\[{]/.test(text.trim()))) { try { parsed = JSON.parse(text); } catch { /* keep text */ } }
      if (res.ok) return text === "" ? undefined : parsed;
      if (attempt < maxRetries && RETRY_STATUS.has(res.status)) {
        const ra = Number(res.headers.get("retry-after"));
        await sleep(Number.isFinite(ra) && ra > 0 ? Math.min(ra * 1000, 30_000) : backoff(attempt));
        continue;
      }
      const e = (parsed as any)?.error;
      const message = typeof e === "string" ? e : e?.message ?? (parsed as any)?.message ?? `HTTP ${res.status}`;
      const code = typeof e === "object" && e ? e.code : (parsed as any)?.code;
      throw new FastnApiError(`${op.method} ${op.path} -> ${res.status}${code ? ` ${code}` : ""}: ${message}`, res.status, code, e?.details, op.method, op.path, requestId, parsed);
    }
  }
}

function backoff(attempt: number): number {
  return Math.min(500 * 2 ** attempt, 8000) + Math.floor(Math.random() * 200);
}
