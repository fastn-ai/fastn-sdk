import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { OPS } from "../../src/generated/ops.js";
import { buildApis } from "../../src/generated/api.js";

const specDir = path.resolve(__dirname, "../../spec");
const specFile = fs.readdirSync(specDir).filter((f) => /^openapi-v.*\.json$/.test(f)).sort().at(-1)!;
const spec = JSON.parse(fs.readFileSync(path.join(specDir, specFile), "utf8"));
const METHODS = ["get", "put", "post", "delete", "patch", "head", "options", "trace"];

// Same rule as scripts/generate.ts: platform-admin areas and backend-only routes are left out of the SDK.
const HIDDEN_TAGS = new Set(["Admin", "Platform Config", "Platform", "Support"]);
const PUBLIC_INTERNAL = new Set(["createEmbedToken", "getSetupLinkStatus"]);
const isHidden = (op: any) => HIDDEN_TAGS.has(op.tags?.[0]) || (op["x-mcp"] === false && !PUBLIC_INTERNAL.has(op.operationId));

describe("every partner-facing spec operation is in the SDK, nothing else", () => {
  const specOps: { id: string; method: string; path: string; tag: string }[] = [];
  const hiddenOps: string[] = [];
  for (const [p, item] of Object.entries<any>(spec.paths)) for (const m of METHODS) if (item[m]?.operationId) {
    if (isHidden(item[m])) hiddenOps.push(item[m].operationId);
    else specOps.push({ id: item[m].operationId, method: m.toUpperCase(), path: p, tag: item[m].tags?.[0] });
  }
  it("has the same count", () => { expect(Object.keys(OPS).length).toBe(specOps.length); expect(specOps.length).toBeGreaterThan(400); });
  it("leaves platform-admin and backend-only routes out", () => {
    expect(hiddenOps.length).toBeGreaterThan(150);
    for (const id of hiddenOps) expect((OPS as any)[id], id).toBeUndefined();
    for (const id of ["listPlatformConfig", "getAuthProviderCredentials", "oauthCallback", "listTeams"]) expect(hiddenOps).toContain(id);
    expect((OPS as any).createEmbedToken).toBeDefined(); expect((OPS as any).getSetupLinkStatus).toBeDefined();
  });
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
  it("matches spec/surface.lock.json (the compatibility record a spec refresh is checked against)", () => {
    const lock = JSON.parse(fs.readFileSync(path.join(specDir, "surface.lock.json"), "utf8"));
    expect(lock.spec).toBe(specFile);
    expect(Object.keys(lock.operations).sort()).toEqual(Object.keys(OPS).sort());
    for (const [id, entry] of Object.entries<any>(lock.operations)) {
      const o = (OPS as any)[id];
      expect(`${o.method} ${o.path}`).toBe(`${entry.method} ${entry.path}`);
      const inputs: Record<string, string> = {};
      for (const p of o.params) inputs[p.key] = `${p.in}:${p.name}`;
      if (o.body?.kind === "fields") for (const [k, n] of Object.entries(o.body.keys ?? {})) inputs[k] = `body:${n}`;
      else if (o.body?.kind === "whole") inputs[o.body.key] = "body:*";
      expect(inputs, id).toEqual(entry.inputs);
    }
  });
  it("every path parameter has an input", () => {
    for (const o of Object.values(OPS)) for (const m of o.path.matchAll(/\{([^}]+)\}/g)) expect(o.params.some((p) => p.in === "path" && p.name === m[1]), `${o.id} ${m[1]}`).toBe(true);
  });
});
