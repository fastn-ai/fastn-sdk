import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { OPS } from "../../src/generated/ops.js";
import { buildApis } from "../../src/generated/api.js";

const specDir = path.resolve(__dirname, "../../spec");
const specFile = fs.readdirSync(specDir).filter((f) => /^openapi-v.*\.json$/.test(f)).sort().at(-1)!;
const spec = JSON.parse(fs.readFileSync(path.join(specDir, specFile), "utf8"));
const METHODS = ["get", "put", "post", "delete", "patch", "head", "options", "trace"];

describe("every spec operation is in the SDK", () => {
  const specOps: { id: string; method: string; path: string; tag: string }[] = [];
  for (const [p, item] of Object.entries<any>(spec.paths)) for (const m of METHODS) if (item[m]?.operationId) specOps.push({ id: item[m].operationId, method: m.toUpperCase(), path: p, tag: item[m].tags?.[0] });
  it("has the same count", () => { expect(Object.keys(OPS).length).toBe(specOps.length); expect(specOps.length).toBeGreaterThan(600); });
  it("matches method + path for each operationId", () => {
    for (const s of specOps) { const o = (OPS as any)[s.id]; expect(o, s.id).toBeDefined(); expect(`${o.method} ${o.path}`).toBe(`${s.method} ${s.path}`); }
  });
  it("exposes each operation as a method on its area", () => {
    const calls: string[] = [];
    const apis = buildApis({ call: async (op) => { calls.push(op.id); return {}; } });
    const methods = new Set<string>();
    for (const area of Object.values(apis)) for (const name of Object.getOwnPropertyNames(Object.getPrototypeOf(area))) if (name !== "constructor") methods.add(name);
    for (const s of specOps) expect(methods.has(s.id), s.id).toBe(true);
    expect(methods.size).toBe(specOps.length);
  });
  it("every path parameter has an input", () => {
    for (const o of Object.values(OPS)) for (const m of o.path.matchAll(/\{([^}]+)\}/g)) expect(o.params.some((p) => p.in === "path" && p.name === m[1]), `${o.id} ${m[1]}`).toBe(true);
  });
});
