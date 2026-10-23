// The SDK's published surface, in one side-effect-free place: which spec operations are left out, and what
// spec/surface.lock.json records per operation. Used by scripts/generate.ts and by test/unit/coverage.test.ts.
import { createHash } from "node:crypto";
import type { OpDef } from "../src/transport.js";

/**
 * What the SDK leaves out. Partners cannot call these with a partner API key (403), so they only widen the surface
 * the SDK has to keep compatible.
 * - HIDDEN_TAGS: whole areas that are platform administration. Billing stays: its quota and plan reads are how a
 *   partner finds out why a call answered 403 quota_exceeded.
 * - Routes marked `x-mcp: false` in the spec (callbacks, credentials, staff-only admin) in any other area, except
 *   the few in PUBLIC_INTERNAL that a partner backend does use.
 */
export const HIDDEN_TAGS = new Set(["Admin", "Platform Config", "Platform", "Support"]);
export const PUBLIC_INTERNAL = new Set(["createEmbedToken", "getSetupLinkStatus"]);
export const isHidden = (op: { tags?: string[]; operationId?: string; "x-mcp"?: unknown }): boolean =>
  HIDDEN_TAGS.has(op.tags?.[0] ?? "") || (op["x-mcp"] === false && !PUBLIC_INTERNAL.has(op.operationId ?? ""));

/**
 * One operation in the lock: method, path, every input key with where it goes on the wire ("path:id", "query:limit",
 * "header:x-end-org-ref", "body:name", "body:*" for a whole-body input) and a "!" suffix when it is required, plus
 * the output's field paths with their structural type ("data.org.id": "string!", "data.items[].name": "string"),
 * no descriptions. A spec refresh may add operations, optional inputs and output fields; it may not remove an
 * operation, rename or move an input, make an optional input required, add a required input, remove an output
 * field, change its type, or make a required output field optional, without `--accept-breaking`.
 */
export interface LockEntry { method: string; path: string; inputs: Record<string, string>; output?: Record<string, string> | string }

export function lockInputs(op: OpDef): Record<string, string> {
  const inputs: Record<string, string> = {};
  for (const p of op.params) inputs[p.key] = `${p.in}:${p.name}${p.required ? "!" : ""}`;
  if (op.body?.kind === "fields") {
    const req = new Set(op.body.requiredKeys ?? []);
    for (const [k, n] of Object.entries(op.body.keys ?? {})) inputs[k] = `body:${n}${req.has(k) ? "!" : ""}`;
  } else if (op.body?.kind === "whole") inputs[op.body.key!] = `body:*${op.body.required ? "!" : ""}`;
  return inputs;
}

/** Kept for locks written before outputs were recorded as fields; no longer used by the generator. */
export const typeHash = (ts: string): string => createHash("sha256").update(ts).digest("hex").slice(0, 12);

/** What changed between two locks that a partner's code could feel. */
export function breakingChanges(prev: Record<string, LockEntry>, next: Record<string, LockEntry>): { inputs: string[]; outputs: string[] } {
  const inputs: string[] = [], outputs: string[] = [];
  for (const [id, was] of Object.entries(prev)) {
    const now = next[id];
    if (!now) { inputs.push(`${id}: operation removed`); continue; }
    if (now.method !== was.method || now.path !== was.path) inputs.push(`${id}: ${was.method} ${was.path} -> ${now.method} ${now.path}`);
    for (const [k, where] of Object.entries(was.inputs)) {
      const nowWhere = now.inputs[k];
      if (nowWhere === undefined) inputs.push(`${id}: input "${k}" (${where}) removed or renamed`);
      else if (nowWhere.replace(/!$/, "") !== where.replace(/!$/, "")) inputs.push(`${id}: input "${k}" moved ${where} -> ${nowWhere}`);
      else if (nowWhere.endsWith("!") && !where.endsWith("!")) inputs.push(`${id}: input "${k}" became required`);
    }
    for (const [k, where] of Object.entries(now.inputs)) if (!(k in was.inputs) && where.endsWith("!")) inputs.push(`${id}: new required input "${k}" (${where})`);
    // Outputs: a field a partner reads may not disappear, change type, or stop being guaranteed. New fields are free.
    // (A lock written before outputs were recorded as fields holds a hash string there; nothing to compare.)
    if (typeof was.output === "object" && typeof now.output === "object") {
      for (const [field, type] of Object.entries(was.output)) {
        const nowType = now.output[field];
        if (nowType === undefined) outputs.push(`${id}: output field "${field}" removed`);
        else if (nowType.replace(/!$/, "") !== type.replace(/!$/, "")) outputs.push(`${id}: output field "${field}" type changed ${type} -> ${nowType}`);
        else if (type.endsWith("!") && !nowType.endsWith("!")) outputs.push(`${id}: output field "${field}" is no longer always present`);
      }
    }
  }
  return { inputs, outputs };
}
