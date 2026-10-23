// One fetch mock for every unit suite. `source` is a queue of replies or a handler per request; `fallback` answers
// when the queue is empty or the handler returns undefined.
import { vi } from "vitest";

export type Reply = { status?: number; body?: unknown; headers?: Record<string, string>; sse?: boolean } | Error | undefined;
export function mockFetch(source: Reply[] | ((url: string, init: any) => Reply), fallback: Reply = { status: 200, body: { data: {} } }) {
  const calls: { url: string; init: any; json: any }[] = [];
  const fetch = vi.fn(async (url: string, init: any) => {
    let json: any; try { json = typeof init?.body === "string" ? JSON.parse(init.body) : undefined; } catch { /* not JSON */ }
    calls.push({ url, init, json });
    const r = (Array.isArray(source) ? source.shift() : source(url, init)) ?? fallback;
    if (r instanceof Error) throw r;
    if (!r) return new Response("", { status: 200 });
    const text = r.body === undefined ? "" : r.sse ? `event: message\ndata: ${JSON.stringify(r.body)}\n\n` : typeof r.body === "string" ? r.body : JSON.stringify(r.body);
    return new Response(r.status === 204 ? null : text, { status: r.status ?? 200, headers: { "content-type": r.sse ? "text/event-stream" : "application/json", "x-request-id": "req_1", ...r.headers } });
  });
  return { fetch: fetch as unknown as typeof globalThis.fetch, calls, urls: (base = "https://api.fastn.dev") => calls.map((x) => x.url.replace(base, "")) };
}
