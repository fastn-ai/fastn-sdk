// @fastn-ai/sdk/codegen - turns a workspace's tool list (MCP tools/list) into one TypeScript module of typed,
// per-connector methods: tools.googleCalendar.listEvents({...}), tools.customer("acme-1").hubspot.createContact({...}).
//
// The generated code is per workspace, so it never ships inside the package: partners run `npx fastn-sdk-tools`
// (src/cli/fastn-sdk-tools.ts) or call generateToolsModule() from a build script. Output is deterministic for the
// same list (sorted by tool name, no timestamps) so it can be committed and checked for drift.
//
// Input types come from each tool's inputSchema through json-schema-to-typescript, after a pre-pass that inlines
// local $refs, drops nested titles (the library would hoist them as shared interfaces that collide across tools)
// and refuses non-local $refs (a listing is vendor data; nothing is ever read from a file or URL for it).
import { compile, type JSONSchema } from "json-schema-to-typescript";
import type { Tool } from "../tools.js";

export interface GenerateToolsOptions {
  /** The workspace endpoint, for the header comment only (never the key). */
  url?: string;
  /** The customer the listing was fetched for (--customer), for the header comment. */
  customer?: string;
  /** Where the generated module imports the SDK types from. Default "@fastn-ai/sdk". */
  importFrom?: string;
}

/** One generated method and where it came from, for reports and tests. */
export interface GeneratedMethod {
  tool: string;
  connector: string | undefined;
  /** The property on the Tools object (connector group), or undefined for a prefix-less tool on the root. */
  group: string | undefined;
  method: string;
  inputType: string;
  outputType: string;
  /** True when the input schema has no properties at all (the method takes an optional empty object). */
  emptyInput: boolean;
  /** True when every top-level property is optional (the args parameter is optional). */
  optionalArgs: boolean;
}

export interface GeneratedToolsModule {
  source: string;
  methods: GeneratedMethod[];
  /** Connector groups on the Tools object, sorted. */
  groups: string[];
}

const DEFAULT_IMPORT = "@fastn-ai/sdk";
const ROOT_PLACEHOLDER = "GeneratedRoot";
/** Names on the Tools object that a prefix-less tool or a connector cannot take. */
const ROOT_RESERVED = new Set(["client", "customer"]);
const IDENT = /^[A-Za-z_$][A-Za-z0-9_$]*$/;
/** Identifiers the generated module declares or imports itself. */
const MODULE_NAMES = ["run", "Tools", "ToolName", "TOOL_NAMES", "WorkspaceTools", "ClientLike", "createTools", "toolsClientOf", "ToolsClient", "ToolCallOptions", "ToolResult"];
/** ES reserved words: not usable as a type name or property on the Tools object (method names on a class are fine). */
const RESERVED = new Set("break case catch class const continue debugger default delete do else enum export extends false finally for function if import in instanceof new null return super switch this throw true try typeof var void while with yield let static implements interface package private protected public await".split(" "));

export function readToolList(json: unknown): Tool[] {
  const list = Array.isArray(json) ? json
    : json && typeof json === "object" && Array.isArray((json as any).tools) ? (json as any).tools
    : json && typeof json === "object" && Array.isArray((json as any).result?.tools) ? (json as any).result.tools
    : undefined;
  if (!list) throw new TypeError("tool list: expected an array of tools, { tools: [...] } or a tools/list result");
  const tools = (list as unknown[]).filter((t): t is Tool => !!t && typeof t === "object" && typeof (t as Tool).name === "string" && (t as Tool).name.length > 0);
  if (tools.length === 0) throw new TypeError("tool list: empty (no tool with a name)");
  return tools;
}

/** Identifier-safe camelCase of any string: "create-contact" -> createContact, "2fa.check" -> _2faCheck, "" -> fallback. */
export function identifier(raw: string, fallback = "tool"): string {
  if (IDENT.test(raw)) return raw;
  const parts = raw.normalize("NFD").replace(/[\u0300-\u036f]/g, "").split(/[^A-Za-z0-9_$]+/).filter(Boolean);
  let out = parts.map((p, i) => (i === 0 ? p : p.charAt(0).toUpperCase() + p.slice(1))).join("");
  if (!out) out = fallback;
  if (/^[0-9]/.test(out)) out = `_${out}`;
  return out;
}
const pascal = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/**
 * A unique name for `raw` among `taken`: the identifier form first, then the raw string with every other character
 * as `_` (so "create-contact" next to "createContact" becomes create_contact, which survives new tools being added),
 * then a numeric suffix as the last resort.
 */
function unique(raw: string, taken: Set<string>, reserved: Set<string> = new Set(), fallback = "tool"): string {
  const first = identifier(raw, fallback);
  const candidates = [first, identifier(raw.replace(/[^A-Za-z0-9_$]/g, "_"), fallback), `${first}Tool`];
  for (const c of candidates) if (!taken.has(c) && !reserved.has(c)) { taken.add(c); return c; }
  for (let i = 2; ; i++) { const c = `${first}${i}`; if (!taken.has(c) && !reserved.has(c)) { taken.add(c); return c; } }
}
/** A unique type-level name: `base`, then base2, base3, ... */
function uniqueType(base: string, taken: Set<string>): string {
  for (let i = 1; ; i++) { const c = i === 1 ? base : `${base}${i}`; if (!taken.has(c) && !RESERVED.has(c)) { taken.add(c); return c; } }
}

/** JSDoc-safe text: `*\/` would end the comment early, so it is broken up. */
function jsdoc(lines: (string | undefined)[], indent = ""): string {
  const text = lines.filter((l): l is string => typeof l === "string" && l.trim() !== "").join("\n");
  if (!text) return "";
  const body = text.replace(/\*\//g, "*\\/").split(/\r?\n/).map((l) => `${indent} * ${l}`.replace(/\s+$/, ""));
  return `${indent}/**\n${body.join("\n")}\n${indent} */\n`;
}

const isObj = (v: unknown): v is Record<string, any> => typeof v === "object" && v !== null && !Array.isArray(v);
/** Keywords whose value is a schema or a map/list of schemas: the pre-pass walks these and nothing else. */
const SCHEMA_KEYS = ["additionalProperties", "items", "additionalItems", "contains", "not", "if", "then", "else", "propertyNames", "unevaluatedProperties", "unevaluatedItems"];
const SCHEMA_LIST_KEYS = ["oneOf", "anyOf", "allOf", "prefixItems"];
const SCHEMA_MAP_KEYS = ["properties", "patternProperties", "dependentSchemas"];

function pointerGet(root: any, ref: string): any {
  if (ref === "#" || ref === "#/") return root;
  if (!ref.startsWith("#/")) return undefined;
  let node = root;
  for (const raw of ref.slice(2).split("/")) {
    const key = raw.replace(/~1/g, "/").replace(/~0/g, "~");
    if (!isObj(node) && !Array.isArray(node)) return undefined;
    node = (node as any)[key];
    if (node === undefined) return undefined;
  }
  return node;
}

/**
 * The schema as json-schema-to-typescript should see it: local $refs inlined (a cycle or a $ref that is not a local
 * JSON pointer becomes `unknown`), `title`/`$id` dropped below the root (they would become hoisted shared interfaces),
 * `definitions`/`$defs` removed, and an object with no `properties` and no `additionalProperties` made an open map.
 */
export function prepareSchema(schema: Record<string, any>): JSONSchema {
  const root = schema;
  const visit = (node: any, stack: Set<any>, top: boolean): any => {
    if (Array.isArray(node)) return node.map((n) => visit(n, stack, false));
    if (!isObj(node)) return node;
    if (typeof node.$ref === "string") {
      const target = pointerGet(root, node.$ref);
      if (!isObj(target) && !Array.isArray(target)) return { tsType: "unknown", description: `$ref ${node.$ref} could not be resolved locally` };
      if (stack.has(target)) return { tsType: "unknown", description: "recursive schema" };
      const next = new Set(stack); next.add(target);
      const { $ref, ...rest } = node;   // keys next to $ref (a description) win over the target's
      return visit(isObj(target) ? { ...target, ...rest } : target, next, false);
    }
    const out: Record<string, any> = {};
    for (const [k, v] of Object.entries(node)) {
      if (k === "definitions" || k === "$defs" || k === "$schema") continue;
      if (!top && (k === "title" || k === "$id" || k === "id")) continue;
      if (SCHEMA_KEYS.includes(k)) out[k] = isObj(v) ? visit(v, stack, false) : v;
      else if (SCHEMA_LIST_KEYS.includes(k)) out[k] = Array.isArray(v) ? v.map((s) => visit(s, stack, false)) : v;
      else if (SCHEMA_MAP_KEYS.includes(k)) out[k] = isObj(v) ? Object.fromEntries(Object.entries(v).map(([pk, pv]) => [pk, visit(pv, stack, false)])) : v;
      else if (k === "items" && Array.isArray(v)) out[k] = v.map((s) => visit(s, stack, false));
      else out[k] = v;
    }
    // { type: "object" } with nothing else is "any object": an open map rather than the empty `{}` type.
    const objectLike = out.type === "object" || (Array.isArray(out.type) && out.type.includes("object"));
    const shaped = isObj(out.properties) && Object.keys(out.properties).length > 0 || out.additionalProperties !== undefined || out.patternProperties !== undefined || out.oneOf || out.anyOf || out.allOf || out.tsType;
    if (objectLike && !shaped && !top) out.additionalProperties = {};
    // A schema that says nothing about the shape (a description alone, or {}) is `unknown`, not an object.
    const typed = out.type !== undefined || shaped || out.items !== undefined || out.enum !== undefined || out.const !== undefined || out.not !== undefined;
    if (!typed && !top) out.tsType = "unknown";
    return out;
  };
  return visit(root, new Set([root]), true) as JSONSchema;
}

/** What the top-level input schema says about the argument: no properties at all / every property optional. */
function argShape(schema: Record<string, any> | undefined): { empty: boolean; optional: boolean; open: boolean } {
  if (!isObj(schema)) return { empty: true, optional: true, open: false };
  const props = isObj(schema.properties) ? Object.keys(schema.properties) : [];
  const composed = Array.isArray(schema.oneOf) || Array.isArray(schema.anyOf) || Array.isArray(schema.allOf) || typeof schema.$ref === "string";
  const open = schema.additionalProperties === true || isObj(schema.additionalProperties) || isObj(schema.patternProperties);
  const required = Array.isArray(schema.required) ? schema.required.filter((r: unknown) => typeof r === "string") : [];
  if (props.length === 0 && !composed) return { empty: !open, optional: true, open };
  return { empty: false, optional: !composed && !required.some((r: string) => props.includes(r)), open };
}

async function compileType(name: string, schema: Record<string, any> | undefined, empty: boolean): Promise<string> {
  if (empty) return `export type ${name} = Record<string, never>;\n`;
  const prepared = prepareSchema({ ...schema });
  delete (prepared as any).title; delete (prepared as any).$id; delete (prepared as any).id;
  // The library normalises the name it is given (underscores and digits change case), so it compiles under a
  // placeholder and the one root declaration is renamed to the exact name the methods reference.
  const ts = await compile(prepared, ROOT_PLACEHOLDER, { format: false, additionalProperties: false, bannerComment: "", $refOptions: { resolve: { external: false } } });
  const renamed = ts.replace(new RegExp(`^export (interface|type) ${ROOT_PLACEHOLDER}\\b`, "m"), `export $1 ${name}`);
  if (renamed === ts || renamed.includes(ROOT_PLACEHOLDER)) throw new Error(`${name}: unexpected generator output (root declaration not found)`);
  return renamed.replace(/\n{3,}/g, "\n\n").trim() + "\n";
}

export async function generateToolsModule(toolsIn: Tool[], opts: GenerateToolsOptions = {}): Promise<GeneratedToolsModule> {
  if (!Array.isArray(toolsIn) || toolsIn.length === 0) throw new TypeError("generateToolsModule: the tool list is empty");
  const importFrom = opts.importFrom ?? DEFAULT_IMPORT;
  // One entry per distinct tool name, sorted: the output is a function of the list, not its order.
  const byName = new Map<string, Tool>();
  for (const t of toolsIn) if (t && typeof t.name === "string" && t.name && !byName.has(t.name)) byName.set(t.name, t);
  const tools = [...byName.values()].sort((a, b) => (a.name < b.name ? -1 : a.name > b.name ? 1 : 0));

  // Groups: connector prefix -> property name on Tools (identifier, unique, not a reserved root name).
  const prefixes = [...new Set(tools.map((t) => splitName(t.name).connector).filter((c): c is string => c !== undefined))].sort();
  const groupNames = new Set<string>();
  const groupOf = new Map<string, string>();
  for (const p of prefixes) groupOf.set(p, unique(p, groupNames, ROOT_RESERVED, "connector"));
  // Type-level names: the module's own come first so a connector called "workspace" or a tool called "tools" cannot shadow them.
  const typeNames = new Set<string>(MODULE_NAMES);
  const classOf = new Map<string, string>();
  for (const [, group] of [...groupOf.entries()].sort(([a], [b]) => (a < b ? -1 : 1))) classOf.set(group, uniqueType(`${pascal(group)}Tools`, typeNames));
  const rootTaken = new Set<string>(groupNames);
  const methodTaken = new Map<string, Set<string>>();

  const methods: GeneratedMethod[] = [];
  const typeBlocks: string[] = [];
  const classMethods = new Map<string, string[]>();
  const rootMethods: string[] = [];
  for (const t of tools) {
    const { connector, action } = splitName(t.name);
    const group = connector === undefined ? undefined : groupOf.get(connector)!;
    const taken = group === undefined ? rootTaken : (methodTaken.get(group) ?? methodTaken.set(group, new Set()).get(group)!);
    const method = group === undefined ? unique(action, taken, ROOT_RESERVED) : unique(action, taken);
    const base = `${group === undefined ? "" : pascal(group)}${pascal(method)}`;
    const inputType = uniqueType(`${base}Input`, typeNames);
    const shape = argShape(t.inputSchema);
    typeBlocks.push(await compileType(inputType, t.inputSchema, shape.empty));
    let outputType = "unknown";
    if (isObj(t.outputSchema)) {
      outputType = uniqueType(`${base}Output`, typeNames);
      typeBlocks.push(await compileType(outputType, t.outputSchema, argShape(t.outputSchema).empty));
    }
    const readOnly = t.annotations?.readOnlyHint === true ? "Read-only." : undefined;
    const doc = jsdoc([t.description, readOnly, `Tool: ${t.name}`], "  ");
    const sig = `${method}(args${shape.optional ? "?" : ""}: ${inputType}, opts?: ToolCallOptions): Promise<ToolResult<${outputType}>>`;
    const body = `return run<${outputType}>(this.client, ${JSON.stringify(t.name)}, args, opts);`;
    const code = `${doc}  ${sig} {\n    ${body}\n  }\n`;
    if (group === undefined) rootMethods.push(code); else (classMethods.get(group) ?? classMethods.set(group, []).get(group)!).push(code);
    methods.push({ tool: t.name, connector, group, method, inputType, outputType, emptyInput: shape.empty, optionalArgs: shape.optional });
  }

  const groups = [...groupOf.entries()].sort(([a], [b]) => (a < b ? -1 : 1));
  const header = [
    `// GENERATED by fastn-sdk-tools (@fastn-ai/sdk) from ${opts.url ?? "a saved tools/list"}${opts.customer ? ` for customer ${JSON.stringify(opts.customer)}` : ""}: ${tools.length} tools, ${groups.length} connectors. Do not edit.`,
    `// Regenerate when the workspace changes (npx fastn-sdk-tools --url <workspace> --out <this file>); --check reports drift.`,
    `/* eslint-disable */`,
    `import type { ToolsClient, ToolCallOptions, ToolResult } from ${JSON.stringify(importFrom)};`,
    ``,
    `/** Every tool in the listing, sorted. */`,
    `export const TOOL_NAMES = [\n${tools.map((t) => `  ${JSON.stringify(t.name)},`).join("\n")}\n] as const;`,
    `export type ToolName = (typeof TOOL_NAMES)[number];`,
    ``,
    `function run<T>(client: ToolsClient, name: string, args: unknown, opts?: ToolCallOptions): Promise<ToolResult<T>> {`,
    `  return client.call<T>(name, (args ?? {}) as Record<string, unknown>, opts);`,
    `}`,
    ``,
  ];
  const out: string[] = [header.join("\n")];
  out.push(typeBlocks.join("\n"));
  for (const [prefix, group] of groups) {
    out.push(`/** The ${prefix} tools of the workspace. */\nexport class ${classOf.get(group)} {\n  constructor(readonly client: ToolsClient) {}\n${(classMethods.get(group) ?? []).join("")}}\n`);
  }
  const groupProps = groups.map(([prefix, group]) => `  /** ${prefix} */\n  readonly ${group}: ${classOf.get(group)};`);
  out.push([
    `/** The workspace's tools, typed. tools.customer(ref) is the same set scoped to one customer. */`,
    `export interface Tools {`,
    `  /** The client under the methods: client.call("<tool>", args) runs a tool the module does not know. */`,
    `  readonly client: ToolsClient;`,
    ...groupProps,
    ...rootMethods.map((m) => m.replace(/ \{\n    return [^\n]*\n  \}\n$/, ";\n")),
    `  /** The same tools for one customer: X-Org-Id = ref on every call, and \`endOrgRef\` filled where a tool takes it. */`,
    `  customer(ref: string): Tools;`,
    `}`,
    ``,
    `class WorkspaceTools implements Tools {`,
    ...groups.map(([, group]) => `  readonly ${group}: ${classOf.get(group)};`),
    `  constructor(readonly client: ToolsClient) {`,
    ...groups.map(([, group]) => `    this.${group} = new ${classOf.get(group)}(client);`),
    `  }`,
    ...rootMethods.map((m) => m.replace(/^\s*\/\*\*[\s\S]*?\*\/\n/, "")),
    `  customer(ref: string): Tools { return new WorkspaceTools(this.client.customer(ref)); }`,
    `}`,
    ``,
    `/** A ToolsClient-like: FastnClient.tools, or any object with call() and customer(). */`,
    `type ClientLike = ToolsClient | { tools?: ToolsClient };`,
    `function toolsClientOf(client: ClientLike): ToolsClient {`,
    `  const c: any = client;`,
    `  if (c && typeof c.call === "function" && typeof c.customer === "function" && typeof c.rpc === "function") return c as ToolsClient;`,
    `  const t = c?.tools;`,
    `  if (t && typeof t.call === "function" && typeof t.customer === "function") return t as ToolsClient;`,
    `  throw new TypeError("createTools(client): pass a ToolsClient, or a FastnClient created with tools: { key, url }");`,
    `}`,
    ``,
    `/**`,
    ` * The typed tools of this workspace on a ToolsClient (or a FastnClient created with \`tools: { key, url }\`).`,
    ` * Every method is \`client.call("<connector>__<tool>", args, opts)\` with the tool's input schema as its type.`,
    ` */`,
    `export function createTools(client: ClientLike): Tools { return new WorkspaceTools(toolsClientOf(client)); }`,
    ``,
  ].join("\n"));
  return { source: out.join("\n"), methods, groups: groups.map(([, g]) => g) };
}

/** "googleCalendar__listEvents" -> { connector: "googleCalendar", action: "listEvents" }; "skill" -> { action: "skill" }. */
export function splitName(name: string): { connector: string | undefined; action: string } {
  const i = name.indexOf("__");
  if (i <= 0) return { connector: undefined, action: name };
  const action = name.slice(i + 2);
  return action ? { connector: name.slice(0, i), action } : { connector: undefined, action: name };
}
