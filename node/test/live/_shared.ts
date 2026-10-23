// Shared by every live suite: the target environment and its production guard, the LIVE switches, and the evidence
// writer (one place for `mask`, so a new secret prefix is redacted in every suite at once).
import fs from "node:fs";

/** Target: FASTN_BASE_URL, default https://api.fastn-test.dev (the development environment). */
export const BASE_URL = process.env.FASTN_BASE_URL ?? "https://api.fastn-test.dev";
/** https://api.fastn.dev only with LIVE_PROD=1: the suites create and delete real customers, bookings and CRM records. */
export function guardProduction(baseUrl = BASE_URL): void {
  if (/api\.fastn\.dev/.test(baseUrl) && process.env.LIVE_PROD !== "1") throw new Error("FASTN_BASE_URL points at production; set LIVE_PROD=1 to run the live suite there");
}
/** The partner API suites need LIVE=1, FASTN_API_KEY and FASTN_TEST_CUSTOMER. */
export const LIVE_API = process.env.LIVE === "1" && !!process.env.FASTN_API_KEY && !!process.env.FASTN_TEST_CUSTOMER;
/** The tools suite needs LIVE=1, FASTN_TOOLS_KEY, FASTN_TOOLS_URL and FASTN_TEST_CUSTOMER. */
export const LIVE_TOOLS = process.env.LIVE === "1" && !!process.env.FASTN_TOOLS_KEY && !!process.env.FASTN_TOOLS_URL && !!process.env.FASTN_TEST_CUSTOMER;
/** The ref of a customer org that has Google Calendar and HubSpot connected. */
export const E2E = process.env.FASTN_TEST_CUSTOMER ?? "";
/** A per-run suffix for everything a suite creates. */
export const run = new Date().toISOString().slice(11, 19).replace(/:/g, "");

export const EVIDENCE_FILE = new URL("./evidence.jsonl", import.meta.url).pathname;
/** Redacts keys and long tokens before anything is written to the evidence file. */
export const mask = (s: string) => s.replace(/(emb_|ucl_|fsk_[a-z]+_|whsec_|stp_tok_|sk_)[A-Za-z0-9_\-]{6,}/g, "$1***").replace(/[A-Za-z0-9_-]{48,}/g, "<tok>");
/** An evidence writer for one suite: `ev("step", data)` appends one masked line. */
export const evidence = (suite?: string) => (step: string, data: unknown) =>
  fs.appendFileSync(EVIDENCE_FILE, mask(JSON.stringify({ at: new Date().toISOString(), step: suite ? `${suite} ${step}` : step, data })).slice(0, 2500) + "\n");

export const dataOf = (r: any) => r?.data ?? r;
/** YYYY-MM-DD, n days from now. */
export const dayFromNow = (n: number) => new Date(Date.now() + n * 86400e3).toISOString().slice(0, 10);
/** HH:MM (UTC) of a record's start_time, or undefined when it has none. */
export const utc = (rec: any) => { try { return new Date(dataOf(rec).start_time).toISOString().slice(11, 16); } catch { return undefined; } };
