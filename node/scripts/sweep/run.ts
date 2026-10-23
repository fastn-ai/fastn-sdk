// Live sweep: calls every published operation once (reads, writes and deletes) against one environment and writes a
// per-operation report. Run with:
//   FASTN_BASE_URL=https://api.fastn-test.dev FASTN_API_KEY=... FASTN_TEST_CUSTOMER=<ref> npx tsx scripts/sweep/run.ts [--only=Area,Area] [--report=path]
// Everything the sweep creates is named sdk_sweep_<run> and deleted by the sweep itself (the delete calls are part of
// the sweep). The report lists, per operation: HTTP status, outcome class, and a short note.
import fs from "node:fs";
import path from "node:path";
import { FastnClient, FastnApiError, FastnNetworkError, unstable } from "../../src/index.js";
import type { OperationId } from "../../src/generated/ops.js";
import { buildPlan, type Step, type Ctx } from "./plan.js";

const { OPS } = unstable;
const env = (k: string, d?: string) => process.env[k] ?? d;
const BASE = env("FASTN_BASE_URL", "https://api.fastn-test.dev")!;
// Same guard as the live suites: this sweep creates and deletes real objects on whatever FASTN_BASE_URL names.
if (/api\.fastn\.dev/.test(BASE) && process.env.LIVE_PROD !== "1") { console.error("FASTN_BASE_URL points at production; set LIVE_PROD=1 to sweep there"); process.exit(2); }
const KEY = env("FASTN_API_KEY");
if (!KEY) { console.error("FASTN_API_KEY is required"); process.exit(2); }
const args = Object.fromEntries(process.argv.slice(2).filter((a) => a.startsWith("--")).map((a) => { const [k, v] = a.slice(2).split("="); return [k, v ?? "1"]; }));
const only = args.only ? new Set(String(args.only).split(",")) : undefined;
const run = new Date().toISOString().slice(11, 19).replace(/:/g, "");
const reportPath = args.report ?? path.resolve(process.cwd(), `test/live/sweep-${new URL(BASE).hostname}-${new Date().toISOString().slice(0, 10)}.csv`);

export type Outcome = "ok" | "ok-expected-4xx" | "forbidden" | "user-token-only" | "route-missing" | "not-found" | "input-rejected" | "BUG-5xx" | "network" | "sdk-error" | "skipped";
interface Row { area: string; op: string; method: string; path: string; status: number | ""; outcome: Outcome; ms: number; note: string }

const fastn = new FastnClient({ apiKey: KEY, baseUrl: BASE, retries: 1, timeoutMs: 60_000 });
const ctx: Ctx = { fastn, run, customerRef: env("FASTN_TEST_CUSTOMER", "") ?? "", ids: {}, notes: [] };
const rows: Row[] = [];
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const short = (s: unknown, n = 160) => String(s ?? "").replace(/\s+/g, " ").slice(0, n);

function classify(err: unknown, step: Step): { status: number | ""; outcome: Outcome; note: string } {
  if (err instanceof FastnApiError) {
    const { status, code } = err;
    const body: any = err.body;
    if (step.expect?.includes(status)) return { status, outcome: "ok-expected-4xx", note: `${code ?? ""} ${short(err.message, 120)}` };
    if (status >= 500) return { status, outcome: "BUG-5xx", note: short(err.message) };
    if (status === 403) return { status, outcome: "forbidden", note: short(err.message, 120) };
    if (status === 401) return { status, outcome: "user-token-only", note: short(err.message, 120) };
    if (status === 405) return { status, outcome: "route-missing", note: `method not served: ${short(err.message, 100)}` };
    if (status === 404) {
      const routeMissing = body && typeof body === "object" && body.error === "Not found" && typeof body.path === "string" && !body.message;
      return { status, outcome: routeMissing ? "route-missing" : "not-found", note: short(err.message, 120) };
    }
    if (status === 400 || status === 422 || status === 409) return { status, outcome: "input-rejected", note: short(err.message) };
    return { status, outcome: "input-rejected", note: short(err.message) };
  }
  if (err instanceof FastnNetworkError) return { status: "", outcome: "network", note: short(err.message) };
  if (err instanceof TypeError) return { status: "", outcome: "sdk-error", note: short(err.message) };
  return { status: "", outcome: "sdk-error", note: short((err as Error)?.message ?? err) };
}

async function execute(step: Step): Promise<void> {
  const op = OPS[step.op as OperationId];
  const area = step.area;
  if (!op) { rows.push({ area, op: step.op, method: "", path: "", status: "", outcome: "sdk-error", ms: 0, note: "unknown operation" }); return; }
  if (step.skip) { rows.push({ area, op: step.op, method: op.method, path: op.path, status: "", outcome: "skipped", ms: 0, note: step.skip }); return; }
  const t0 = Date.now();
  try {
    const input = typeof step.input === "function" ? await step.input(ctx) : step.input ?? {};
    if (!input) { rows.push({ area, op: step.op, method: op.method, path: op.path, status: "", outcome: "skipped", ms: 0, note: step.note ?? "needs an id that no earlier step produced (nothing to act on, or that step failed)" }); return; }
    const res = step.customer ? await callScoped(step.op, input, step.opts) : await fastn.call(step.op as OperationId, input, step.opts);
    const ms = Date.now() - t0;
    let note = step.note ?? "";
    try { const n = await step.after?.(res, ctx); if (typeof n === "string") note = n; } catch (e) { note = `after() failed: ${short((e as Error).message)}`; }
    rows.push({ area, op: step.op, method: op.method, path: op.path, status: 200, outcome: "ok", ms, note: note || short(JSON.stringify(res), 100) });
  } catch (err) {
    const c = classify(err, step);
    rows.push({ area, op: step.op, method: op.method, path: op.path, ms: Date.now() - t0, ...c });
  }
  await sleep(Number(env("SWEEP_DELAY_MS", "150")));
}

// customer.api has no call(); find the area method by operationId.
async function callScoped(opId: string, input: any, opts: any) {
  const api: any = fastn.customer(ctx.customerRef).api;
  for (const area of Object.values(api)) if (typeof (area as any)[opId] === "function") return (area as any)[opId](input, opts);
  throw new TypeError(`no scoped method ${opId}`);
}

function writeReport() {
  const esc = (v: unknown) => { const s = String(v ?? ""); return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const header = "area,operation,method,path,status,outcome,ms,note";
  fs.writeFileSync(reportPath, [header, ...rows.map((r) => [r.area, r.op, r.method, r.path, r.status, r.outcome, r.ms, r.note].map(esc).join(","))].join("\n") + "\n");
  const counts: Record<string, number> = {};
  for (const r of rows) counts[r.outcome] = (counts[r.outcome] ?? 0) + 1;
  const covered = new Set(rows.map((r) => r.op));
  const missing = Object.keys(OPS).filter((id) => !covered.has(id));
  console.log(`\n${rows.length} steps, ${covered.size}/${Object.keys(OPS).length} operations covered -> ${reportPath}`);
  console.log(counts);
  if (missing.length && !only) console.log(`not covered (${missing.length}): ${missing.join(", ")}`);
  for (const r of rows) if (["BUG-5xx", "route-missing", "input-rejected", "sdk-error", "network"].includes(r.outcome)) console.log(`  ${r.outcome.padEnd(14)} ${r.op.padEnd(36)} ${r.status} ${r.note}`);
  for (const n of ctx.notes) console.log("note:", n);
}

(async () => {
  console.log(`sweep ${run} on ${BASE} as ${(await fastn.me()).org?.id} customer=${ctx.customerRef || "(none)"}`);
  const plan = buildPlan(ctx);
  for (const step of plan) {
    if (only && !only.has(step.area)) continue;
    await execute(step);
    const r = rows.at(-1)!;
    process.stdout.write(`${r.outcome === "ok" ? "." : r.outcome === "ok-expected-4xx" ? "e" : r.outcome === "skipped" ? "s" : "X"}`);
    if (r.outcome !== "ok" && r.outcome !== "ok-expected-4xx" && r.outcome !== "skipped") process.stdout.write(`\n  ${r.outcome} ${r.op} ${r.status} ${r.note}\n`);
  }
  writeReport();
})().catch((e) => { console.error(e); writeReport(); process.exit(1); });
