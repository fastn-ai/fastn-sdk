// Internal HTTP helpers shared by the REST transport (transport.ts) and the tools client (tools.ts), so both time out,
// retry, parse and report errors the same way. Not exported from the package.
import { VERSION } from "./version.js";

/** Answers worth one more try: rate limit and gateway errors. */
export const RETRY_STATUS = new Set([429, 502, 503, 504]);

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Exponential backoff with a cap and a little jitter: 0.5s, 1s, 2s, 4s, 8s (+ up to 200ms). */
export function backoff(attempt: number): number {
  return Math.min(500 * 2 ** attempt, 8000) + Math.floor(Math.random() * 200);
}

/** The wait before the next attempt: Retry-After when the answer carries one (capped at 30s), else backoff(). */
export function retryDelay(res: Pick<Response, "headers">, attempt: number): number {
  const ra = Number(res.headers.get("retry-after"));
  return Number.isFinite(ra) && ra > 0 ? Math.min(ra * 1000, 30_000) : backoff(attempt);
}

/** The user-agent both clients send unless the caller sets one. */
export function defaultUserAgent(): string {
  return `fastn-ai-sdk/${VERSION} node/${typeof process !== "undefined" ? process.versions?.node ?? "" : ""}`;
}

/** Per-call options over client defaults; `headers` merged, everything else overridden. */
export function mergeOptions<O extends { headers?: Record<string, string> }>(defaults: O | undefined, opts: O | undefined): O & { headers: Record<string, string> } {
  return { ...(defaults as O), ...(opts as O), headers: { ...defaults?.headers, ...opts?.headers } };
}

/**
 * A signal that aborts on the per-call timeout or when the caller's own signal aborts. With AbortSignal.any
 * (Node 20.3+) nothing is left attached to the caller's signal; on older runtimes `release()` removes the listener,
 * so a long-lived signal reused across many calls does not collect one listener per call.
 */
export function requestSignal(timeoutMs: number, signal?: AbortSignal): { signal: AbortSignal; release(): void } {
  const t = AbortSignal.timeout(timeoutMs);
  if (!signal) return { signal: t, release() {} };
  const any = (AbortSignal as unknown as { any?: (s: AbortSignal[]) => AbortSignal }).any;
  if (typeof any === "function") return { signal: any([t, signal]), release() {} };
  const ac = new AbortController();
  const onAbort = () => ac.abort(signal.reason);
  const onTimeout = () => ac.abort(t.reason);
  if (signal.aborted) onAbort(); else signal.addEventListener("abort", onAbort, { once: true });
  t.addEventListener("abort", onTimeout, { once: true });
  return { signal: ac.signal, release() { signal.removeEventListener("abort", onAbort); t.removeEventListener("abort", onTimeout); } };
}

/** JSON when the body is JSON (by content type or by its first character), otherwise the text as is. */
export function parseLoose(text: string, contentType = ""): unknown {
  const s = text.trim();
  if (!s) return text;
  if (contentType.includes("json") || /^[\[{]/.test(s)) { try { return JSON.parse(s); } catch { /* keep the text */ } }
  return text;
}

/** The message, code and details out of an error body, whichever of the API's shapes it has. */
export function errorInfo(body: unknown, fallback = ""): { message: string; code?: string | number; details?: unknown } {
  const b = body as Record<string, any> | null | undefined;
  if (b && typeof b === "object") {
    const e = b.error;
    const nested = e && typeof e === "object" ? e : undefined;
    const message = typeof e === "string" ? e : nested?.message ?? b.message ?? b.detail;
    const code = nested?.code ?? b.code;
    return { message: typeof message === "string" ? message : fallback || JSON.stringify(b).slice(0, 300), ...(code !== undefined ? { code } : {}), ...(nested?.details !== undefined ? { details: nested.details } : {}) };
  }
  return { message: String(fallback || body || "").slice(0, 300) };
}
