// Generates src/generated/{ops,types,api}.ts from spec/openapi-*.json.
// Rules mirror fastn-platform/scripts/ucl-sync-platform-tools.ts (opsFromSpec, headerInputKey, claim order
// path > query > body > header) so an SDK input is named exactly like the Fastn Workspace MCP tool input.
import fs from "node:fs";
import path from "node:path";
import type { ParamDef, BodyDef } from "../src/transport.js";
import { isHidden, lockInputs, breakingChanges, type LockEntry } from "./surface.js";

type Json = Record<string, any>;
const SPEC_DIR = path.resolve(import.meta.dirname, "../spec");
const OUT_DIR = path.resolve(import.meta.dirname, "../src/generated");
// --check: report what a spec would change against spec/surface.lock.json and write nothing (exit 1 on a break).
// --spec=<file>: use that spec instead of the newest spec/openapi-v*.json (with --check: try a spec before taking it).
const checkOnly = process.argv.includes("--check");
const specArg = process.argv.find((a) => a.startsWith("--spec="))?.slice("--spec=".length);
const specPath = specArg ? path.resolve(specArg) : path.join(SPEC_DIR, fs.readdirSync(SPEC_DIR).filter((f) => /^openapi-v.*\.json$/.test(f)).sort().at(-1)!);
const specFile = path.basename(specPath);
const spec: Json = JSON.parse(fs.readFileSync(specPath, "utf8"));
const METHODS = ["get", "put", "post", "delete", "patch", "head", "options", "trace"];
const isObj = (v: unknown): v is Json => typeof v === "object" && v !== null && !Array.isArray(v);

function pointer(ref: string): Json {
  let node: any = spec;
  for (const raw of ref.slice(2).split("/")) node = node?.[raw.replace(/~1/g, "/").replace(/~0/g, "~")];
  if (node === undefined) throw new Error(`unresolvable $ref ${ref}`);
  return node;
}
function resolveParam(p: Json): Json { return typeof p.$ref === "string" ? { ...pointer(p.$ref), ...stripRef(p) } : p; }
function stripRef(p: Json): Json { const { $ref: _, ...rest } = p; return rest; }

function headerInputKey(header: string): string {
  return header.replace(/^x-/i, "").replace(/^(.)/, (c) => c.toLowerCase()).replace(/-([a-zA-Z0-9])/g, (_, c: string) => c.toUpperCase());
}
/**
 * Operations the platform de-duplicates by Idempotency-Key, so the SDK may retry them after a lost answer. Taken from
 * the spec (an Idempotency-Key header parameter) plus the ones verified live that the spec does not declare yet.
 */
const IDEMPOTENT_EXTRA = new Set(["createUnifiedRecord"]);
let hidden = 0;
const camel = (s: string) => s.replace(/[^A-Za-z0-9]+(.)?/g, (_, c?: string) => (c ? c.toUpperCase() : "")).replace(/^(.)/, (c) => c.toLowerCase());
const pascal = (s: string) => { const c = camel(s); return c[0]!.toUpperCase() + c.slice(1); };
/** The client member for a tag: a leading acronym is lower-cased ("API Keys" -> apiKeys) and a trailing " API" dropped ("Unified API" -> unified). */
const tagName = (tag: string) => camel(tag.replace(/\s+API$/i, "").replace(/^[A-Z]{2,}(?=\s|$)/, (m) => m.toLowerCase()));
const ident = (s: string) => (/^[A-Za-z_$][\w$]*$/.test(s) ? s : JSON.stringify(s));
const doc = (lines: (string | undefined)[], indent = ""): string => {
  const text = lines.filter((l): l is string => !!l && l.trim().length > 0).map((l) => l.replace(/\*\//g, "* /").trim());
  if (!text.length) return "";
  return `${indent}/**\n${text.map((l) => `${indent} * ${l}`).join("\n")}\n${indent} */\n`;
};

// ── JSON schema -> TypeScript ──
const namedSchemas = new Map<string, string>(); // component name -> TS name
for (const name of Object.keys(spec.components?.schemas ?? {})) namedSchemas.set(name, pascal(name));

function ts(schema: Json | undefined, indent = "  "): string {
  if (!isObj(schema) || Object.keys(schema).length === 0) return "any";
  if (typeof schema.$ref === "string") {
    const name = schema.$ref.split("/").at(-1)!;
    return namedSchemas.get(name) ?? "any";
  }
  if (schema.const !== undefined) return JSON.stringify(schema.const);
  if (Array.isArray(schema.enum)) return schema.enum.map((v: unknown) => JSON.stringify(v)).join(" | ") || "never";
  if (Array.isArray(schema.oneOf)) return schema.oneOf.map((s: Json) => paren(ts(s, indent))).join(" | ");
  if (Array.isArray(schema.anyOf)) return schema.anyOf.map((s: Json) => paren(ts(s, indent))).join(" | ");
  if (Array.isArray(schema.allOf)) return schema.allOf.map((s: Json) => paren(ts(s, indent))).join(" & ");
  const nullable = schema.nullable === true;
  let types: string[] = Array.isArray(schema.type) ? schema.type : schema.type ? [schema.type] : [];
  if (!types.length) types = [schema.properties || schema.additionalProperties !== undefined ? "object" : schema.items ? "array" : "any"];
  const parts = types.map((t) => {
    switch (t) {
      case "string": return "string";
      case "number": case "integer": return "number";
      case "boolean": return "boolean";
      case "null": return "null";
      case "array": return `${paren(ts(schema.items, indent))}[]`;
      case "object": return objectTs(schema, indent);
      default: return "any";
    }
  });
  const out = [...new Set(nullable ? [...parts, "null"] : parts)].join(" | ");
  return out || "any";
}
const paren = (t: string) => (/[|&]/.test(t) ? `(${t})` : t);
function objectTs(schema: Json, indent: string): string {
  const props: Json = isObj(schema.properties) ? schema.properties : {};
  const required = new Set<string>(Array.isArray(schema.required) ? schema.required : []);
  const inner = indent + "  ";
  const lines = Object.entries(props).map(([k, v]) => `${doc([(v as Json).description], inner)}${inner}${ident(k)}${required.has(k) ? "" : "?"}: ${ts(v as Json, inner)};`);
  const ap = schema.additionalProperties;
  if (!lines.length) {
    if (ap === false) return "Record<string, never>";
    return isObj(ap) && Object.keys(ap).length ? `Record<string, ${ts(ap, indent)}>` : "Record<string, any>";
  }
  if (ap === true || (isObj(ap) && !Object.keys(ap).length)) lines.push(`${inner}[key: string]: any;`);
  else if (isObj(ap)) lines.push(`${inner}[key: string]: ${ts(ap, inner)} | undefined;`);
  return `{\n${lines.join("\n")}\n${indent}}`;
}

// ── output shape (for the surface lock) ──
// The fields a partner's code can read from an operation's answer: dotted paths ("data.org.id", "data.items[].name")
// with a structural type and "!" when the field is always present. No descriptions, so a doc edit changes nothing.
const deref = (s: Json | undefined): Json | undefined => (isObj(s) && typeof s.$ref === "string" ? pointer(s.$ref) : s);
function shapeType(s0: Json | undefined, depth: number): string {
  const s = deref(s0);
  if (!isObj(s) || Object.keys(s).length === 0 || depth > 8) return "any";
  if (s.const !== undefined) return JSON.stringify(s.const);
  if (Array.isArray(s.enum)) return s.enum.map((v: unknown) => JSON.stringify(v)).join(" | ") || "never";
  for (const k of ["oneOf", "anyOf"]) if (Array.isArray(s[k])) return s[k].map((x: Json) => paren(shapeType(x, depth + 1))).join(" | ");
  if (Array.isArray(s.allOf)) return s.allOf.map((x: Json) => paren(shapeType(x, depth + 1))).join(" & ");
  let types: string[] = Array.isArray(s.type) ? s.type : s.type ? [s.type] : [];
  if (!types.length) types = [s.properties || s.additionalProperties !== undefined ? "object" : s.items ? "array" : "any"];
  const parts = types.map((t) => {
    switch (t) {
      case "string": case "boolean": case "null": return t;
      case "number": case "integer": return "number";
      case "array": return `${paren(shapeType(s.items, depth + 1))}[]`;
      case "object": {
        if (isObj(s.properties) && Object.keys(s.properties).length) return "object";
        const ap = s.additionalProperties;
        return ap === false ? "Record<string, never>" : isObj(ap) && Object.keys(ap).length ? `Record<string, ${shapeType(ap, depth + 1)}>` : "Record<string, any>";
      }
      default: return "any";
    }
  });
  return [...new Set(s.nullable === true ? [...parts, "null"] : parts)].join(" | ") || "any";
}
function outputShape(schema: Json | undefined): Record<string, string> {
  const out: Record<string, string> = {};
  const walk = (s0: Json | undefined, prefix: string, depth: number) => {
    const s = deref(s0);
    if (!isObj(s) || depth > 8) return;
    if (Array.isArray(s.allOf)) { for (const part of s.allOf) walk(part, prefix, depth + 1); return; }
    const req = new Set<string>(Array.isArray(s.required) ? s.required : []);
    for (const [k, v0] of Object.entries<Json>(isObj(s.properties) ? s.properties : {})) {
      const v = deref(v0);
      const p = prefix ? `${prefix}.${k}` : k;
      out[p] = `${shapeType(v, depth + 1)}${req.has(k) ? "!" : ""}`;
      if (!isObj(v)) continue;
      if (isObj(v.properties) || Array.isArray(v.allOf)) walk(v, p, depth + 1);
      else if (isObj(v.items)) { const it = deref(v.items); if (isObj(it) && (isObj(it.properties) || Array.isArray(it.allOf))) walk(it, `${p}[]`, depth + 1); }
    }
  };
  walk(schema, "", 0);
  return out;
}

// ── operations ──
interface Op { id: string; method: string; path: string; tag: string; summary?: string; description?: string; params: ParamDef[]; body?: BodyDef; inputTs: string; outputTs: string; outputShape: Record<string, string>; inputRequired: boolean; deprecated: boolean; idempotent: boolean }

const ops: Op[] = [];
for (const [p, rawItem] of Object.entries<Json>(spec.paths)) {
  const shared: Json[] = (rawItem.parameters ?? []).map(resolveParam);
  for (const m of METHODS) {
    const op = rawItem[m];
    if (!isObj(op) || typeof op.operationId !== "string") continue;
    if (isHidden(op)) { hidden++; continue; }
    const own: Json[] = (op.parameters ?? []).map(resolveParam);
    const allParams = [...shared.filter((s) => !own.some((o) => o.name === s.name && o.in === s.in)), ...own];
    const idempotent = allParams.some((x) => x.in === "header" && /^idempotency-key$/i.test(String(x.name))) || IDEMPOTENT_EXTRA.has(op.operationId);
    const params = allParams.filter((x) => x.in !== "cookie" && !(x.in === "header" && /^idempotency-key$/i.test(String(x.name))));
    const props: string[] = [];
    const claimed = new Set<string>();
    const defs: ParamDef[] = [];
    let inputRequired = false;
    const claim = (name: string, where: string): string => {
      if (!claimed.has(name)) { claimed.add(name); return name; }
      const alt = `${where}${name[0]!.toUpperCase()}${name.slice(1)}`;
      if (claimed.has(alt)) throw new Error(`${op.operationId}: input ${name} collides twice (${where})`);
      claimed.add(alt); return alt;
    };
    const addParam = (prm: Json) => {
      const where = String(prm.in);
      const key = claim(where === "header" ? headerInputKey(prm.name) : prm.name, where);
      const req = where === "path" || prm.required === true;
      if (req) inputRequired = true;
      const d = [key !== prm.name ? `The ${where} ${where === "header" ? "header" : "parameter"} "${prm.name}".` : undefined, prm.description, prm["x-mcp"] === false && where === "header" ? "Partner-backend attestation header; not an MCP tool input." : undefined];
      props.push(`${doc(d, "  ")}  ${ident(key)}${req ? "" : "?"}: ${ts(prm.schema ?? { type: "string" })};`);
      defs.push({ key, name: prm.name, in: where as ParamDef["in"], ...(req ? { required: true } : {}) });
    };
    // Input order (and claim order on a name collision): path and query, then the body fields, then headers.
    for (const prm of params.filter((x) => x.in !== "header")) addParam(prm);
    let body: BodyDef | undefined;
    const rb: Json | undefined = isObj(op.requestBody) ? op.requestBody : undefined;
    if (rb) {
      const contentType = Object.keys(rb.content ?? {})[0] ?? "application/json";
      const schema: Json | undefined = rb.content?.[contentType]?.schema;
      const bodyProps: Json = isObj(schema?.properties) ? schema!.properties : {};
      const bodyRequired = rb.required !== false;
      if (contentType === "application/json" && Object.keys(bodyProps).length) {
        const keys: Record<string, string> = {};
        const requiredKeys: string[] = [];
        const reqSet = new Set<string>(Array.isArray(schema!.required) ? schema!.required : []);
        for (const [name, sub] of Object.entries<Json>(bodyProps)) {
          const key = claim(name, "body");
          keys[key] = name;
          const req = bodyRequired && reqSet.has(name);
          if (req) { inputRequired = true; requiredKeys.push(key); }
          props.push(`${doc([key !== name ? `The body field "${name}".` : undefined, sub.description], "  ")}  ${ident(key)}${req ? "" : "?"}: ${ts(sub)};`);
        }
        const ap = schema!.additionalProperties;
        const open = ap === true || (isObj(ap) && !Object.keys(ap).length);
        if (open) props.push(`  /** The spec allows fields it does not list; they are sent as given. */
  [key: string]: any;`);
        body = { kind: "fields", keys, ...(open ? { open } : {}), ...(requiredKeys.length ? { requiredKeys } : {}), contentType };
      } else {
        const key = claim(typeof op["x-mcp-body-input"] === "string" ? op["x-mcp-body-input"] : "body", "request");
        if (bodyRequired) inputRequired = true;
        props.push(`${doc([`The whole request body (${contentType}).`, schema?.description], "  ")}  ${ident(key)}${bodyRequired ? "" : "?"}: ${contentType === "application/json" ? ts(schema) : "Record<string, any> | string"};`);
        body = { kind: "whole", key, required: bodyRequired, contentType };
      }
    }
    for (const prm of params.filter((x) => x.in === "header")) addParam(prm);
    const responses: Json = isObj(op.responses) ? op.responses : {};
    const okCode = Object.keys(responses).filter((c) => /^2(\d\d|XX)$/i.test(c)).sort().find((c) => isObj(responses[c]?.content?.["application/json"]?.schema));
    const outSchema = okCode ? responses[okCode].content["application/json"].schema : undefined;
    const outputTs = outSchema ? ts(outSchema) : "JsonObject";
    ops.push({ id: op.operationId, method: m.toUpperCase(), path: p, tag: op.tags?.[0] ?? "Untagged", summary: op.summary, description: op.description, params: defs, body, inputTs: props.length ? `{\n${props.join("\n")}\n}` : "Record<string, never>", outputTs, outputShape: outputShape(outSchema), inputRequired, deprecated: op.deprecated === true, idempotent });
  }
}
const dupes = ops.map((o) => o.id).filter((id, i, a) => a.indexOf(id) !== i);
if (dupes.length) throw new Error(`duplicate operationIds: ${dupes.join(", ")}`);

// ── surface lock ──
// spec/surface.lock.json records every generated operation: its inputs (wire place, required or not) and a hash of
// its Output type (see scripts/surface.ts). A new spec may add operations and optional inputs; anything a partner's
// code could feel needs `npm run generate -- --accept-breaking`, which rewrites the lock. This is what keeps a
// partner's code compiling across spec refreshes (and what a CI diff reviews).
const LOCK_FILE = path.join(SPEC_DIR, "surface.lock.json");
const acceptBreaking = process.argv.includes("--accept-breaking");
const nextLock: Record<string, LockEntry> = Object.fromEntries(ops.map((o) => [o.id, { method: o.method, path: o.path, inputs: lockInputs({ id: o.id, method: o.method, path: o.path, params: o.params, body: o.body }), output: o.outputShape }]));
if (fs.existsSync(LOCK_FILE)) {
  const prevLock = JSON.parse(fs.readFileSync(LOCK_FILE, "utf8"));
  const prev: Record<string, LockEntry> = prevLock.operations;
  const { inputs, outputs } = breakingChanges(prev, nextLock);
  const lines = [...inputs, ...outputs];
  const added = Object.keys(nextLock).filter((id) => !(id in prev));
  if (checkOnly) {
    console.log(`${specFile} against the lock from ${prevLock.spec}: ${added.length} new operation(s)${added.length ? ` (${added.join(", ")})` : ""}; ${lines.length} breaking change(s)${lines.length ? `:\n  ${lines.join("\n  ")}` : "."}`);
    process.exit(lines.length ? 1 : 0);
  }
  if (lines.length && !acceptBreaking) {
    throw new Error(`The new spec changes ${inputs.length} input(s) and ${outputs.length} output field(s) recorded in spec/surface.lock.json:\n  ${lines.join("\n  ")}\nRe-run with --accept-breaking to take them (needs a major version bump).`);
  }
  if (lines.length) console.log(`accepted ${lines.length} breaking change(s):\n  ${lines.join("\n  ")}`);
} else if (checkOnly) { console.log("no spec/surface.lock.json to check against"); process.exit(2); }
fs.writeFileSync(LOCK_FILE, JSON.stringify({ spec: specFile, operations: nextLock }, null, 1) + "\n");

// src/version.ts mirrors package.json, so the user-agent cannot drift from the published version.
const pkgVersion = JSON.parse(fs.readFileSync(path.resolve(import.meta.dirname, "../package.json"), "utf8")).version;
fs.writeFileSync(path.resolve(import.meta.dirname, "../src/version.ts"), `// GENERATED by scripts/generate.ts from package.json - do not edit.\nexport const VERSION = ${JSON.stringify(pkgVersion)};\n`);

// ── emit ──
fs.mkdirSync(OUT_DIR, { recursive: true });
const header = `// GENERATED by scripts/generate.ts from spec/${specFile} - do not edit.\n`;
const info = spec.info ?? {};

// ops.ts: the wire manifest the transport runs on.
const opsOut = [header, `import type { OpDef } from "../transport.js";\n`, `export const SPEC_VERSION = ${JSON.stringify(specFile.match(/^openapi-v(.+)\.json$/)?.[1] ?? info.version ?? "")};`, `export const SPEC_FILE = ${JSON.stringify(specFile)};`, `export const OPS = {`];
for (const o of ops) {
  const def: Json = { id: o.id, method: o.method, path: o.path, params: o.params };
  if (o.body) def.body = o.body;
  if (o.idempotent) def.idempotent = true;
  opsOut.push(`  ${o.id}: ${JSON.stringify(def)} as OpDef,`);
}
opsOut.push(`} as const satisfies Record<string, OpDef>;`, `export type OperationId = keyof typeof OPS;`, "");
fs.writeFileSync(path.join(OUT_DIR, "ops.ts"), opsOut.join("\n"));

// types.ts: component schemas + one Input/Output type per operation.
const typesOut = [header, `/** A JSON answer the spec does not describe in detail; shaped exactly as the REST API returns it (usually { data: ... }). */`, `export type JsonObject = Record<string, any>;`, ""];
for (const [name, schema] of Object.entries<Json>(spec.components?.schemas ?? {})) {
  typesOut.push(`${doc([schema.description])}export type ${namedSchemas.get(name)} = ${ts(schema)};`, "");
}
for (const o of ops) {
  typesOut.push(`${doc([`Input of ${o.id} (${o.method} ${o.path}).`])}export type ${pascal(o.id)}Input = ${o.inputTs};`);
  typesOut.push(`${doc([`Output of ${o.id}.`])}export type ${pascal(o.id)}Output = ${o.outputTs};`, "");
}
fs.writeFileSync(path.join(OUT_DIR, "types.ts"), typesOut.join("\n"));

// api.ts: one class per tag, one method per operation.
const byTag = new Map<string, Op[]>();
for (const o of ops) byTag.set(o.tag, [...(byTag.get(o.tag) ?? []), o]);
const apiOut = [header, `import type { Transport, RequestOptions } from "../transport.js";`, `import { OPS } from "./ops.js";`, `import type * as T from "./types.js";`, ""];
const groups: { prop: string; cls: string; tag: string; count: number }[] = [];
// Members FastnClient defines itself; an area with one of these names would shadow them.
const RESERVED = new Set(["api", "tools", "customer", "customers", "call", "me", "transport", "baseUrl", "constructor", "meCache"]);
for (const [tag, list] of [...byTag.entries()].sort((a, b) => a[0].localeCompare(b[0]))) {
  const prop = tagName(tag), cls = `${pascal(prop)}Api`;
  if (RESERVED.has(prop)) throw new Error(`tag "${tag}" would become client member "${prop}", which FastnClient reserves; rename the tag in the spec`);
  groups.push({ prop, cls, tag, count: list.length });
  const tagDesc = (spec.tags ?? []).find((t: Json) => t.name === tag)?.description;
  apiOut.push(`${doc([`${tag}: ${tagDesc ?? ""}`])}export class ${cls} {`, `  constructor(private readonly _t: Transport) {}`);
  for (const o of list) {
    const lines = [o.summary, o.description, `${o.method} ${o.path}`, o.idempotent ? "Honours Idempotency-Key: pass opts.idempotencyKey and a retry after a lost answer cannot act twice." : undefined, o.deprecated ? "@deprecated" : undefined];
    const inputType = `T.${pascal(o.id)}Input`;
    const arg = o.inputRequired ? `input: ${inputType}` : `input: ${inputType} = {} as ${inputType}`;
    apiOut.push(`${doc(lines, "  ")}  ${o.id}(${arg}, opts?: RequestOptions): Promise<T.${pascal(o.id)}Output> {`, `    return this._t.call(OPS.${o.id}, input, opts);`, `  }`);
  }
  apiOut.push(`}`, "");
}
apiOut.push(`/** Every API area, keyed by its OpenAPI tag. */`, `export interface FastnApis {`);
for (const g of groups) apiOut.push(`  /** ${g.tag} (${g.count} operations) */\n  ${g.prop}: ${g.cls};`);
apiOut.push(`}`, "", `export function buildApis(t: Transport): FastnApis {`, `  return {`);
for (const g of groups) apiOut.push(`    ${g.prop}: new ${g.cls}(t),`);
apiOut.push(`  };`, `}`, "");
fs.writeFileSync(path.join(OUT_DIR, "api.ts"), apiOut.join("\n"));

console.log(`generated ${ops.length} operations in ${groups.length} areas from ${specFile} (${hidden} platform-admin/backend-only routes left out, ${ops.filter((o) => o.outputTs !== "JsonObject").length} with typed output)`);
