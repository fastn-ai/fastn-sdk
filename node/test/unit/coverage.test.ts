import { describe, it, expect } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { OPS } from "../../src/generated/ops.js";
import { buildApis } from "../../src/generated/api.js";
import { isHidden, lockInputs, breakingChanges, type LockEntry } from "../../scripts/surface.js";

const specDir = path.resolve(__dirname, "../../spec");
const specFile = fs.readdirSync(specDir).filter((f) => /^openapi-v.*\.json$/.test(f)).sort().at(-1)!;
const spec = JSON.parse(fs.readFileSync(path.join(specDir, specFile), "utf8"));
const METHODS = ["get", "put", "post", "delete", "patch", "head", "options", "trace"];

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
    for (const [id, entry] of Object.entries<LockEntry>(lock.operations)) {
      const o = (OPS as any)[id];
      expect(`${o.method} ${o.path}`).toBe(`${entry.method} ${entry.path}`);
      expect(lockInputs(o), id).toEqual(entry.inputs);
      expect(entry.output, id).toMatch(/^[0-9a-f]{12}$/);
    }
    // required-ness is recorded: a path parameter is always required, a required body field carries "!"
    expect(lock.operations.getTenant.inputs.id).toBe("path:id!");
    expect(lock.operations.createTenant.inputs.name).toBe("body:name!");
    expect(lock.operations.createTenant.inputs.plan).toBe("body:plan");
  });
  it("the lock check catches removed, renamed, moved and newly required inputs and changed Output types", () => {
    const was: Record<string, LockEntry> = {
      a: { method: "GET", path: "/a", inputs: { id: "path:id!", q: "query:q", opt: "body:opt" }, output: "aaaaaaaaaaaa" },
      gone: { method: "GET", path: "/gone", inputs: {}, output: "bbbbbbbbbbbb" },
    };
    const now: Record<string, LockEntry> = {
      a: { method: "GET", path: "/a", inputs: { id: "path:id!", q: "header:q", opt: "body:opt!", extra: "query:extra", must: "body:must!" }, output: "cccccccccccc" },
      added: { method: "POST", path: "/new", inputs: { x: "body:x!" }, output: "dddddddddddd" },
    };
    const b = breakingChanges(was, now);
    expect(b.inputs).toEqual(['a: input "q" moved query:q -> header:q', 'a: input "opt" became required', 'a: new required input "must" (body:must!)', "gone: operation removed"]);
    expect(b.outputs).toEqual(["a: Output type changed (aaaaaaaaaaaa -> cccccccccccc)"]);
    // additive: a new optional input, a new operation, required -> optional
    expect(breakingChanges({ a: { method: "GET", path: "/a", inputs: { id: "path:id!" }, output: "aaaaaaaaaaaa" } }, { a: { method: "GET", path: "/a", inputs: { id: "path:id", n: "query:n" }, output: "aaaaaaaaaaaa" }, b: now.added })).toEqual({ inputs: [], outputs: [] });
  });
  it("every path parameter has an input", () => {
    for (const o of Object.values(OPS)) for (const m of o.path.matchAll(/\{([^}]+)\}/g)) expect(o.params.some((p) => p.in === "path" && p.name === m[1]), `${o.id} ${m[1]}`).toBe(true);
  });
});
