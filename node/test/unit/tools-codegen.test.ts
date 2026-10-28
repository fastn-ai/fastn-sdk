// The typed-tools generator (src/codegen/tools.ts) and its CLI (src/cli/fastn-sdk-tools.ts).
// Generated modules are written under test/.generated/ (gitignored), type-checked with tsc --strict, and imported
// at runtime against a mocked fetch to prove the generated methods send exactly what ToolsClient.call sends.
import { describe, it, expect, vi, afterEach } from "vitest";
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";
import { pathToFileURL } from "node:url";
import { generateToolsModule, prepareSchema, identifier, splitName, readToolList } from "../../src/codegen/tools.js";
import { main, parseArgs } from "../../src/cli/fastn-sdk-tools.js";
import { FastnClient, ToolsClient, ToolError, type Tool } from "../../src/index.js";
import { mockFetch as sharedMock, type Reply } from "../helpers.js";

const ROOT = path.resolve(import.meta.dirname, "../..");
const OUT_DIR = path.join(ROOT, "test/.generated");
const FIXTURE = path.join(ROOT, "test/fixtures/tools-list.trillet.json");
const IMPORT = "../../src/index.js";
fs.mkdirSync(OUT_DIR, { recursive: true });

const fixture = (): Tool[] => readToolList(JSON.parse(fs.readFileSync(FIXTURE, "utf8")));
const gen = (tools: Tool[], opts = {}) => generateToolsModule(tools, { importFrom: IMPORT, url: "https://mcp.fastn.dev/acme", ...opts });
const tool = (name: string, inputSchema?: Record<string, any>, extra: Partial<Tool> = {}): Tool => ({ name, ...(inputSchema ? { inputSchema } : {}), ...extra });
function write(name: string, source: string): string { const f = path.join(OUT_DIR, `${name}.ts`); fs.writeFileSync(f, source); return f; }
/** tsc --strict on a generated file; throws with the diagnostics when it fails. */
function tsc(file: string): void {
  execFileSync(path.join(ROOT, "node_modules/.bin/tsc"), ["--strict", "--noEmit", "--skipLibCheck", "--target", "es2022", "--module", "esnext", "--moduleResolution", "bundler", file], { cwd: ROOT, stdio: ["ignore", "pipe", "pipe"], encoding: "utf8" });
}
async function load(name: string, source: string): Promise<any> { const f = write(name, source); return import(`${pathToFileURL(f).href}?t=${Date.now()}`); }

const rpcOk = (id: number, result: unknown) => ({ jsonrpc: "2.0", id, result });
const toolOk = (id: number, text: string, isError = false) => rpcOk(id, { content: [{ type: "text", text }], isError });
const mockFetch = (replies: Reply[] | ((url: string, init: any) => Reply)) => sharedMock(replies, { body: rpcOk(0, { content: [{ type: "text", text: "{}" }], isError: false }) });
/** A fetch that answers tools/list with `list` (in `pages` pages) and tools/call with "{}" or the given reply. */
const workspace = (list: Tool[], pages = 1, onCall?: (name: string, args: any) => Reply) => mockFetch((_url, init) => {
  const req = JSON.parse(init.body);
  if (req.method === "tools/list") {
    const size = Math.ceil(list.length / pages);
    const page = req.params?.cursor ? Number(req.params.cursor) : 0;
    const tools = list.slice(page * size, (page + 1) * size);
    return { body: rpcOk(req.id, { tools, ...(page + 1 < pages ? { nextCursor: String(page + 1) } : {}) }) };
  }
  const r = onCall?.(req.params.name, req.params.arguments);
  return r ?? { body: rpcOk(req.id, { content: [{ type: "text", text: JSON.stringify({ ok: true, name: req.params.name }) }], isError: false }) };
});

afterEach(() => { vi.unstubAllGlobals(); });

describe("names", () => {
  it("identifier() makes camelCase identifiers; splitName() takes the part after the first __", () => {
    expect(identifier("createContact")).toBe("createContact");
    expect(identifier("create-contact")).toBe("createContact");
    expect(identifier("google-calendar")).toBe("googleCalendar");
    expect(identifier("a.b.c")).toBe("aBC");
    expect(identifier("365dynamics")).toBe("_365dynamics");
    expect(identifier("---")).toBe("tool");
    expect(identifier("ünïcode-name")).toBe("unicodeName");
    expect(splitName("googleCalendar__listEvents")).toEqual({ connector: "googleCalendar", action: "listEvents" });
    expect(splitName("a__b__c")).toEqual({ connector: "a", action: "b__c" });
    expect(splitName("skill")).toEqual({ connector: undefined, action: "skill" });
    expect(splitName("__x")).toEqual({ connector: undefined, action: "__x" });
    expect(splitName("x__")).toEqual({ connector: undefined, action: "x__" });
  });
  it("readToolList() accepts an array, { tools }, a JSON-RPC result, and rejects the rest", () => {
    expect(readToolList([{ name: "a" }]).map((t) => t.name)).toEqual(["a"]);
    expect(readToolList({ tools: [{ name: "a" }, { nope: 1 }] }).map((t) => t.name)).toEqual(["a"]);
    expect(readToolList({ result: { tools: [{ name: "a" }] } }).map((t) => t.name)).toEqual(["a"]);
    expect(() => readToolList([])).toThrow(/empty/);
    expect(() => readToolList([{ name: "" }])).toThrow(/empty/);
    expect(() => readToolList({ foo: 1 })).toThrow(/expected an array/);
    expect(() => readToolList("x")).toThrow(/expected an array/);
  });
});

describe("schema shapes", () => {
  it("empty input schema: Record<string, never> and an optional argument", async () => {
    const g = await gen([tool("cal__getColors", { type: "object", properties: {} }), tool("cal__bare", { type: "object" }), tool("cal__none"), tool("cal__reqEmpty", { type: "object", required: [], properties: {} })]);
    for (const m of g.methods) { expect(m.emptyInput).toBe(true); expect(m.optionalArgs).toBe(true); }
    expect(g.source).toContain("export type CalGetColorsInput = Record<string, never>;");
    expect(g.source).toContain("export type CalBareInput = Record<string, never>;");
    expect(g.source).toContain("export type CalNoneInput = Record<string, never>;");
    expect(g.source).toContain("getColors(args?: CalGetColorsInput, opts?: ToolCallOptions): Promise<ToolResult<unknown>>");
  });
  it("no properties but additionalProperties: an open map, optional argument", async () => {
    const g = await gen([tool("w__run", { type: "object", additionalProperties: true }), tool("w__env", { type: "object", additionalProperties: { type: "string" } }), tool("w__anyMap", { type: "object", additionalProperties: {} })]);
    expect(g.source).toMatch(/export interface WRunInput \{\n\[k: string\]: unknown\n\}/);
    expect(g.source).toMatch(/export interface WEnvInput \{\n\[k: string\]: string\n\}/);
    expect(g.source).toMatch(/export interface WAnyMapInput \{\n\[k: string\]: unknown\n\}/);
    expect(g.methods.map((m) => [m.emptyInput, m.optionalArgs])).toEqual([[false, true], [false, true], [false, true]]);
    expect(g.source).toContain("run(args?: WRunInput, opts?: ToolCallOptions)");
  });
  it("required vs optional properties decide `?` on the property and on the argument", async () => {
    const g = await gen([
      tool("crm__createContact", { type: "object", required: ["email"], properties: { email: { type: "string" }, name: { type: "string" } } }),
      tool("crm__listContacts", { type: "object", properties: { limit: { type: "integer" }, cursor: { type: "string" } } }),
      tool("crm__ghostRequired", { type: "object", required: ["missing"], properties: { a: { type: "string" } } }),
    ]);
    expect(g.source).toMatch(/export interface CrmCreateContactInput \{\nemail: string\nname\?: string\n\}/);
    expect(g.source).toContain("createContact(args: CrmCreateContactInput, opts?: ToolCallOptions)");
    expect(g.source).toMatch(/export interface CrmListContactsInput \{\nlimit\?: number\ncursor\?: string\n\}/);
    expect(g.source).toContain("listContacts(args?: CrmListContactsInput, opts?: ToolCallOptions)");
    // a required name that is not a property does not make the argument required
    expect(g.source).toContain("ghostRequired(args?: CrmGhostRequiredInput, opts?: ToolCallOptions)");
  });
  it("enums and const become literal unions; nullable and type lists add null", async () => {
    const g = await gen([tool("c__set", { type: "object", properties: { role: { type: "string", enum: ["reader", "writer"] }, n: { enum: [1, "two", null, true] }, k: { const: "fixed" }, maybe: { type: "string", nullable: true }, alt: { type: ["number", "null"] } } })]);
    expect(g.source).toContain('role?: ("reader" | "writer")');
    expect(g.source).toContain('n?: (1 | "two" | null | true)');
    expect(g.source).toContain('k?: "fixed"');
    expect(g.source).toContain("maybe?: (string | null)");
    expect(g.source).toContain("alt?: (number | null)");
  });
  it("nested objects and arrays, tuples, and a nested bare object as an open map", async () => {
    const g = await gen([tool("cal__createEvent", { type: "object", required: ["attendees"], properties: {
      attendees: { type: "array", items: { type: "object", required: ["email"], properties: { email: { type: "string" }, optional: { type: "boolean" } } } },
      pair: { type: "array", items: [{ type: "string" }, { type: "number" }] },
      tags: { type: "array", items: { type: "string" } },
      meta: { type: "object" },
      anything: { description: "no type at all" },
      blank: {},
      where: { type: "object", properties: { room: { type: "object", properties: { id: { type: "string" } } } } },
    } })]);
    expect(g.source).toMatch(/attendees: \{\nemail: string\noptional\?: boolean\n\}\[\]/);
    expect(g.source).toContain("pair?: []|[string]|[string, number]");
    expect(g.source).toContain("tags?: string[]");
    expect(g.source).toMatch(/meta\?: \{\n\[k: string\]: unknown\n\}/);
    expect(g.source).toMatch(/no type at all\n \*\/\nanything\?: unknown\nblank\?: unknown\n/);
    expect(g.source).toMatch(/where\?: \{\nroom\?: \{\nid\?: string\n\}\n\}/);
  });
  it("$ref to definitions / $defs / a property is inlined; cycles and non-local refs become unknown; nothing is read from disk", async () => {
    const g = await gen([tool("x__refs", {
      type: "object",
      properties: { addr: { $ref: "#/definitions/Address" }, alt: { $ref: "#/$defs/Alt" }, again: { $ref: "#/properties/alt" }, self: { $ref: "#" }, loop: { $ref: "#/definitions/Node" }, ext: { $ref: "file:///etc/hosts" }, http: { $ref: "https://example.com/s.json#/x" }, missing: { $ref: "#/definitions/Nope" }, described: { $ref: "#/definitions/Address", description: "with its own text" } },
      definitions: { Address: { type: "object", required: ["city"], properties: { city: { type: "string" } } }, Node: { type: "object", properties: { next: { $ref: "#/definitions/Node" } } } },
      $defs: { Alt: { type: "string", enum: ["x", "y"] } },
    })]);
    expect(g.source).toMatch(/addr\?: \{\ncity: string\n\}/);
    expect(g.source).toContain('alt?: ("x" | "y")');
    expect(g.source).toContain('again?: ("x" | "y")');
    expect(g.source).toMatch(/self\?: unknown/);                       // the root referencing itself
    expect(g.source).toMatch(/loop\?: \{\n\/\*\*\n \* recursive schema\n \*\/\nnext\?: unknown\n\}/);   // one level, then the cycle
    expect(g.source).toMatch(/ext\?: unknown/); expect(g.source).toMatch(/http\?: unknown/); expect(g.source).toMatch(/missing\?: unknown/);
    expect(g.source).not.toContain("localhost");                        // nothing from /etc/hosts
    expect(g.source).toMatch(/with its own text\n \*\/\ndescribed\?: \{\ncity: string\n\}/);
    expect(g.source).not.toContain("export interface Address");       // no hoisted shared interfaces
    expect(prepareSchema({ $ref: "#/definitions/A", definitions: { A: { type: "string" } } })).toEqual({ type: "string" });
  });
  it("oneOf / anyOf become unions, allOf an intersection; a top-level oneOf makes the argument required", async () => {
    const g = await gen([tool("x__u", { type: "object", properties: {
      a: { oneOf: [{ type: "string" }, { type: "number" }] },
      b: { anyOf: [{ type: "boolean" }, { type: "object", properties: { z: { type: "string" } } }] },
      c: { allOf: [{ type: "object", properties: { p: { type: "string" } } }, { type: "object", properties: { q: { type: "number" } } }] },
    } }), tool("x__top", { oneOf: [{ type: "object", required: ["id"], properties: { id: { type: "string" } } }, { type: "object", required: ["email"], properties: { email: { type: "string" } } }] })]);
    expect(g.source).toContain("a?: (string | number)");
    expect(g.source).toMatch(/b\?: \(boolean \| \{\nz\?: string\n\}\)/);
    expect(g.source).toMatch(/c\?: \(\{\np\?: string\n\} & \{\nq\?: number\n\}\)/);
    expect(g.source).toMatch(/export type XTopInput = \(?\{\nid: string\n\} \| \{\nemail: string\n\}\)?/);
    expect(g.source).toContain("top(args: XTopInput, opts?: ToolCallOptions)");
  });
  it("property names that are not identifiers stay as quoted keys; reserved words are plain keys", async () => {
    const g = await gen([tool("x__k", { type: "object", required: ["first-name", "class"], properties: { "first-name": { type: "string" }, "a.b": { type: "number" }, "123x": { type: "boolean" }, class: { type: "string" }, default: { type: "string" }, "x y": { type: "string" }, "ünï": { type: "string" } } })]);
    expect(g.source).toContain('"first-name": string'); expect(g.source).toContain('"a.b"?: number'); expect(g.source).toContain('"123x"?: boolean');
    expect(g.source).toContain("\nclass: string"); expect(g.source).toContain("\ndefault?: string"); expect(g.source).toContain('"x y"?: string'); expect(g.source).toContain('"ünï"?: string');
  });
  it("outputSchema becomes the ToolResult type parameter; without it the answer is unknown", async () => {
    const g = await gen([tool("c__get", { type: "object", properties: { id: { type: "string" } } }, { outputSchema: { type: "object", required: ["id"], properties: { id: { type: "string" }, tags: { type: "array", items: { type: "string" } } } } }), tool("c__plain", { type: "object", properties: {} })]);
    expect(g.source).toMatch(/export interface CGetOutput \{\nid: string\ntags\?: string\[\]\n\}/);
    expect(g.source).toContain("get(args?: CGetInput, opts?: ToolCallOptions): Promise<ToolResult<CGetOutput>>");
    expect(g.source).toContain("return run<CGetOutput>(this.client, \"c__get\", args, opts);");
    expect(g.source).toContain("plain(args?: CPlainInput, opts?: ToolCallOptions): Promise<ToolResult<unknown>>");
    expect(g.methods.find((m) => m.tool === "c__get")?.outputType).toBe("CGetOutput");
  });
});

describe("naming edge cases", () => {
  it("a tool without __ becomes a root method; names taken by the module or a connector get a Tool suffix", async () => {
    const g = await gen([tool("skill", { type: "object", properties: { slug: { type: "string" } } }), tool("customer", { type: "object", properties: {} }), tool("client"), tool("hubspot"), tool("hubspot__createContact", { type: "object", properties: {} })]);
    expect(g.methods.map((m) => [m.tool, m.group, m.method])).toEqual([
      ["client", undefined, "clientTool"], ["customer", undefined, "customerTool"], ["hubspot", undefined, "hubspotTool"], ["hubspot__createContact", "hubspot", "createContact"], ["skill", undefined, "skill"],
    ]);
    expect(g.source).toContain("  skill(args?: SkillInput, opts?: ToolCallOptions): Promise<ToolResult<unknown>>;");
    expect(g.source).toContain("  customerTool(args?: CustomerToolInput, opts?: ToolCallOptions): Promise<ToolResult<unknown>>;");
    expect(g.source).toContain("  customer(ref: string): Tools;");
    expect(g.source).toContain('return run<unknown>(this.client, "customer", args, opts);');
    expect(g.source).toContain("readonly hubspot: HubspotTools;");
  });
  it("two tools that sanitise to the same method get distinct, name-derived methods, in the same way whatever the input order", async () => {
    const list = [tool("hubspot__create-contact"), tool("hubspot__createContact"), tool("hubspot__create.contact"), tool("hubspot__create_contact"), tool("hubspot__Create-Contact")];
    const g = await gen(list);
    expect(g.methods.map((m) => [m.tool, m.method, m.inputType])).toEqual([
      ["hubspot__Create-Contact", "CreateContact", "HubspotCreateContactInput"],
      ["hubspot__create-contact", "createContact", "HubspotCreateContactInput2"],
      ["hubspot__create.contact", "create_contact", "HubspotCreate_contactInput"],
      ["hubspot__createContact", "createContactTool", "HubspotCreateContactToolInput"],
      ["hubspot__create_contact", "create_contactTool", "HubspotCreate_contactToolInput"],
    ]);
    expect(g.source).toContain('createContact(args?: HubspotCreateContactInput2, opts?: ToolCallOptions): Promise<ToolResult<unknown>> {\n    return run<unknown>(this.client, "hubspot__create-contact", args, opts);');
    const reversed = await gen([...list].reverse());
    expect(reversed.source).toBe(g.source);
    const duplicated = await gen([...list, ...list]);
    expect(duplicated.source).toBe(g.source);
    tsc(write("clash", g.source));
  });
  it("a connector name that is not an identifier becomes one; the class and the Tools property follow it", async () => {
    const g = await gen([tool("google-calendar__listEvents"), tool("365dynamics__get"), tool("x.y__z"), tool("default__run"), tool("workspace__tools"), tool("tools__run")]);
    expect(g.groups).toEqual(["_365dynamics", "default", "googleCalendar", "tools", "workspace", "xY"]);
    expect(g.source).toContain("export class GoogleCalendarTools {"); expect(g.source).toContain("readonly googleCalendar: GoogleCalendarTools;");
    expect(g.source).toContain("export class _365dynamicsTools {"); expect(g.source).toContain("readonly _365dynamics: _365dynamicsTools;");
    expect(g.source).toContain("readonly default: DefaultTools;");
    expect(g.source).toContain("export class WorkspaceTools2 {");                 // the module's own WorkspaceTools keeps its name
    expect(g.source).toContain("class WorkspaceTools implements Tools {");
    expect(g.source).toContain("export class ToolsTools {"); expect(g.source).toContain("export interface Tools {");
    tsc(write("connectors", g.source));
  });
  it("descriptions with */, backticks, newlines and unicode keep the JSDoc valid", async () => {
    const d = "Ends a comment */ early? `code` and 日本語 ✓\nsecond line";
    const g = await gen([tool("x__d", { type: "object", description: d, properties: { a: { type: "string", description: d } } }, { description: d, annotations: { readOnlyHint: true } })]);
    expect(g.source).not.toMatch(/\*\/ early/);
    expect(g.source).toContain("Ends a comment *\\/ early? `code` and 日本語 ✓\n   * second line\n   * Read-only.\n   * Tool: x__d");
    expect(g.source).toContain("Ends a comment * / early? `code` and 日本語 ✓\n * second line");
    tsc(write("jsdoc", g.source));
  });
  it("the header names the url, customer and counts, never a key, and the output has no timestamp", async () => {
    const list = [tool("a__b")];
    const g1 = await gen(list, { customer: "acme-1" });
    expect(g1.source.split("\n")[0]).toBe('// GENERATED by fastn-sdk-tools (@fastn-ai/sdk) from https://mcp.fastn.dev/acme for customer "acme-1": 1 tools, 1 connectors. Do not edit.');
    expect((await gen(list, { url: undefined })).source.split("\n")[0]).toContain("from a saved tools/list: 1 tools");
    await new Promise((r) => setTimeout(r, 5));
    expect((await gen(list, { customer: "acme-1" })).source).toBe(g1.source);
    expect(g1.source).toContain('from "../../src/index.js"');
    expect((await generateToolsModule(list)).source).toContain('from "@fastn-ai/sdk"');
    await expect(generateToolsModule([])).rejects.toThrow(/empty/);
  });
});

describe("the Trillet fixture (265 tools)", () => {
  it("generates 265 methods in 2 connectors plus 2 root tools, and compiles under tsc --strict", async () => {
    const g = await gen(fixture(), { url: "https://mcp.fastn.dev/trillet" });
    expect(g.methods).toHaveLength(265);
    expect(g.groups).toEqual(["fastnPlatform", "googleCalendar"]);
    expect(g.methods.filter((m) => m.group === "fastnPlatform")).toHaveLength(236);
    expect(g.methods.filter((m) => m.group === "googleCalendar")).toHaveLength(27);
    expect(g.methods.filter((m) => m.group === undefined).map((m) => m.method)).toEqual(["feedback", "skill"]);
    expect(g.source).toContain('"googleCalendar__listCalendars",');
    expect(g.source).toContain("listUnifiedCategories(args?: FastnPlatformListUnifiedCategoriesInput, opts?: ToolCallOptions)");
    tsc(write("trillet", g.source));
  }, 120_000);
  it("the loose fastnPlatform schemas: 21 empty inputs, 3 with untyped properties, 2 googleCalendar empty inputs", async () => {
    const g = await gen(fixture());
    const empty = g.methods.filter((m) => m.emptyInput).map((m) => m.tool);
    expect(empty).toEqual([
      "fastnPlatform__claimOnboardingCredits", "fastnPlatform__disconnectGithubIntegration", "fastnPlatform__getGithubIntegrationStatus", "fastnPlatform__getMyOrgDomain", "fastnPlatform__getMySuggestions", "fastnPlatform__getOnboardingProductProfile", "fastnPlatform__getSetupJourney", "fastnPlatform__listEnvironmentConfigs", "fastnPlatform__listEnvironments", "fastnPlatform__listEventSubscriptions", "fastnPlatform__listSaasConnectors", "fastnPlatform__listSyncJobs", "fastnPlatform__listUnifiedCatalogCategories", "fastnPlatform__listUnifiedCategories", "fastnPlatform__listUnifiedCustom", "fastnPlatform__listWorkflowCategories", "fastnPlatform__listWorkflowLabels", "fastnPlatform__syncWorkflowsToGithub", "fastnPlatform__trillet_expiry_check", "fastnPlatform__trillet_redeliver", "fastnPlatform__whoami",
      "googleCalendar__getColors", "googleCalendar__listSettings",
    ]);
    for (const t of empty) expect(g.source).toContain(`export type ${g.methods.find((m) => m.tool === t)!.inputType} = Record<string, never>;`);
    expect(g.source).toMatch(/export interface FastnPlatformCreateWorkflowInput \{[\s\S]*?\ninputExample\?: unknown\noutputExample\?: unknown/);
    expect(g.source).toMatch(/export interface FastnPlatformUpdateWorkflowInput \{[\s\S]*?\ninputExample\?: unknown\noutputExample\?: unknown/);
    expect(g.source).toMatch(/export interface FastnPlatformSendTestAppEventInput \{[\s\S]*?\npayload: unknown\n/);
    expect(g.source).toMatch(/export interface FastnPlatformCreateWorkflowInput \{[\s\S]*?\ninputSchema\?: \{\n\[k: string\]: unknown\n\}/);
    // free-form object params are open maps, not `{}`
    expect(g.source).toMatch(/export interface FastnPlatformExecuteWorkflowInput \{[\s\S]*?\ninput\?: \{\n\[k: string\]: unknown\n\}/);
    expect(g.source).toMatch(/export interface FastnPlatformCreateUnifiedRecordInput \{[\s\S]*?\nrecord: \{\n\[k: string\]: unknown\n\}/);
    expect(g.source).toMatch(/export interface FastnPlatformSearchUnifiedRecordsInput \{[\s\S]*?\nfilters: \{\n\[k: string\]: string \| number \| boolean\n\}/);
    // endOrgRef stays optional, so customer(ref) can fill it
    expect(g.source).toMatch(/export interface FastnPlatformListUnifiedRecordsInput \{[\s\S]*?\nendOrgRef\?: string/);
  });
});

describe("generated methods at runtime", () => {
  const list = [
    tool("googleCalendar__listEvents", { type: "object", required: ["calendarId"], properties: { calendarId: { type: "string" }, maxResults: { type: "integer" } } }),
    tool("googleCalendar__getColors", { type: "object", properties: {} }),
    tool("fastnPlatform__listUnifiedRecords", { type: "object", required: ["category", "entity"], properties: { category: { type: "string" }, entity: { type: "string" }, endOrgRef: { type: "string" }, limit: { type: "integer" } } }),
    tool("fastnPlatform__whoami", { type: "object", properties: {} }),
    tool("skill", { type: "object", properties: { slug: { type: "string" } } }),
  ];
  it("sends exactly the name and arguments ToolsClient.call sends, on a ToolsClient or a FastnClient", async () => {
    const mod = await load("runtime", (await gen(list)).source);
    const m = workspace(list);
    const client = new ToolsClient({ key: "ucl_test", url: "https://mcp.fastn.dev/acme", fetch: m.fetch });
    const tools = mod.createTools(client);
    const r = await tools.googleCalendar.listEvents({ calendarId: "primary", maxResults: 5 });
    await client.call("googleCalendar__listEvents", { calendarId: "primary", maxResults: 5 });
    expect(m.calls).toHaveLength(2);
    expect(m.calls[0].json.params).toEqual(m.calls[1].json.params);
    expect(m.calls[0].json.params).toEqual({ name: "googleCalendar__listEvents", arguments: { calendarId: "primary", maxResults: 5 } });
    expect(m.calls[0].init.headers.authorization).toBe("Bearer ucl_test");
    expect(r.data).toEqual({ ok: true, name: "googleCalendar__listEvents" });
    await tools.googleCalendar.getColors();
    expect(m.calls[2].json.params).toEqual({ name: "googleCalendar__getColors", arguments: {} });
    await tools.skill({ slug: "gateway" }, { userId: "u-1" });
    expect(m.calls[3].json.params).toEqual({ name: "skill", arguments: { slug: "gateway" } });
    expect(m.calls[3].init.headers["x-user-id"]).toBe("u-1");
    expect(mod.TOOL_NAMES).toEqual(["fastnPlatform__listUnifiedRecords", "fastnPlatform__whoami", "googleCalendar__getColors", "googleCalendar__listEvents", "skill"]);
    expect(tools.client).toBe(client);

    const fastn = new FastnClient({ apiKey: "k", fetch: m.fetch, tools: { key: "ucl_test", url: "https://mcp.fastn.dev/acme" } });
    await mod.createTools(fastn).googleCalendar.getColors();
    expect(m.calls[4].url).toBe("https://mcp.fastn.dev/acme");
    expect(() => mod.createTools(new FastnClient({ apiKey: "k" }))).toThrow(/tools: \{ key, url \}/);
    expect(() => mod.createTools({})).toThrow(TypeError);
  });
  it("customer(ref) keeps the scoping: X-Org-Id on every call and endOrgRef filled where the schema takes it", async () => {
    const mod = await load("runtime", (await gen(list)).source);
    const m = workspace(list, 2);
    const client = new ToolsClient({ key: "ucl_test", url: "https://mcp.fastn.dev/acme", fetch: m.fetch });
    const acme = mod.createTools(client).customer("acme-1");
    await acme.fastnPlatform.listUnifiedRecords({ category: "crm", entity: "contact" });
    const call = m.calls.find((c) => c.json.method === "tools/call")!;
    expect(call.init.headers["x-org-id"]).toBe("acme-1");
    expect(call.json.params).toEqual({ name: "fastnPlatform__listUnifiedRecords", arguments: { category: "crm", entity: "contact", endOrgRef: "acme-1" } });
    expect(m.calls.filter((c) => c.json.method === "tools/list")).toHaveLength(2);     // one paged listing for the schema map
    // the same call through the raw client sends the same thing
    await client.customer("acme-1").call("fastnPlatform__listUnifiedRecords", { category: "crm", entity: "contact" });
    expect(m.calls.at(-1)!.json.params).toEqual(call.json.params);
    // non-platform tools get the header only; an explicit endOrgRef wins
    await acme.googleCalendar.listEvents({ calendarId: "primary" });
    expect(m.calls.at(-1)!.json.params.arguments).toEqual({ calendarId: "primary" }); expect(m.calls.at(-1)!.init.headers["x-org-id"]).toBe("acme-1");
    await acme.fastnPlatform.listUnifiedRecords({ category: "crm", entity: "contact", endOrgRef: "other" });
    expect(m.calls.at(-1)!.json.params.arguments.endOrgRef).toBe("other");
    expect(acme.customer("b-2").client.url).toBe("https://mcp.fastn.dev/acme");
  });
  it("surfaces ToolError unchanged", async () => {
    const mod = await load("runtime", (await gen(list)).source);
    const m = workspace(list, 1, (name) => name === "googleCalendar__listEvents" ? { body: toolOk(9, JSON.stringify({ error: { message: "calendar not found" } }), true) } : name === "fastnPlatform__whoami" ? { status: 403, body: { error: "unknown org", code: "IDENTITY_ORG_NOT_FOUND" } } : undefined);
    const tools = mod.createTools(new ToolsClient({ key: "ucl_test", url: "https://mcp.fastn.dev/acme", fetch: m.fetch }));
    const e1 = await tools.googleCalendar.listEvents({ calendarId: "x" }).catch((e: unknown) => e) as ToolError;
    expect(e1).toBeInstanceOf(ToolError); expect(e1.kind).toBe("tool"); expect(e1.message).toBe("calendar not found"); expect(e1.tool).toBe("googleCalendar__listEvents");
    const e2 = await tools.fastnPlatform.whoami().catch((e: unknown) => e) as ToolError;
    expect(e2).toBeInstanceOf(ToolError); expect(e2.kind).toBe("http"); expect(e2.status).toBe(403); expect(e2.code).toBe("IDENTITY_ORG_NOT_FOUND");
  });
});

describe("CLI", () => {
  const run = async (argv: string[], env: NodeJS.ProcessEnv = {}) => { let out = "", err = ""; const code = await main(argv, env, { out: (s) => { out += s; }, err: (s) => { err += s; } }); return { code, out, err }; };
  const outFile = (name: string) => { const f = path.join(OUT_DIR, `cli-${name}.ts`); fs.rmSync(f, { force: true }); return f; };
  it("parses flags, --flag=value and the env; refuses what it cannot use", () => {
    expect(parseArgs(["--url", "https://x", "--key", "k", "--out", "o.ts", "--check", "--customer", "c", "--from", "f", "--import", "m"])).toEqual({ url: "https://x", key: "k", out: "o.ts", check: true, customer: "c", from: "f", import: "m", help: false });
    expect(parseArgs(["--out=o.ts", "--url=https://x/y=z"], { FASTN_TOOLS_KEY: "envkey", FASTN_TOOLS_URL: "https://env" })).toMatchObject({ out: "o.ts", url: "https://x/y=z", key: "envkey" });
    expect(parseArgs([], { FASTN_TOOLS_URL: "https://env" }).url).toBe("https://env");
    expect(() => parseArgs(["--out"])).toThrow(/needs a value/);
    expect(() => parseArgs(["--out", "--check"])).toThrow(/needs a value/);
    expect(() => parseArgs(["--bogus"])).toThrow(/unknown argument --bogus/);
    expect(() => parseArgs(["ucl_secret_value", "--out", "o.ts"])).toThrow(/unexpected value on the command line/);
    try { parseArgs(["ucl_secret_value"]); } catch (e) { expect((e as Error).message).not.toContain("ucl_secret_value"); }
  });
  it("--from writes the module; --check passes when it is current, fails on drift or a missing file, and never writes", async () => {
    const f = outFile("from");
    const r = await run(["--from", FIXTURE, "--url", "https://mcp.fastn.dev/trillet", "--out", f, "--import", IMPORT]);
    expect(r.code).toBe(0); expect(r.out).toContain("wrote"); expect(r.out).toContain("265 tools, 2 connectors (fastnPlatform, googleCalendar)");
    const written = fs.readFileSync(f, "utf8");
    expect(written).toBe((await gen(fixture(), { url: "https://mcp.fastn.dev/trillet" })).source);
    const ok = await run(["--from", FIXTURE, "--url", "https://mcp.fastn.dev/trillet", "--out", f, "--import", IMPORT, "--check"]);
    expect(ok.code).toBe(0); expect(ok.out).toContain("up to date (265 tools)");
    fs.writeFileSync(f, written.replace('"googleCalendar__getColors",\n', ""));
    const drift = await run(["--from", FIXTURE, "--url", "https://mcp.fastn.dev/trillet", "--out", f, "--import", IMPORT, "--check"]);
    expect(drift.code).toBe(1); expect(drift.err).toContain("would change (first difference at line");
    expect(fs.readFileSync(f, "utf8")).not.toBe(written);                      // --check did not repair it
    fs.rmSync(f);
    const missing = await run(["--from", FIXTURE, "--out", f, "--check"]);
    expect(missing.code).toBe(1); expect(missing.err).toContain("does not exist"); expect(fs.existsSync(f)).toBe(false);
  });
  it("a failed or empty tools/list is a clear error and no file is written; the key is never printed", async () => {
    const f = outFile("fail");
    const empty = path.join(OUT_DIR, "empty-list.json"); fs.writeFileSync(empty, "[]");
    const r1 = await run(["--from", empty, "--out", f]);
    expect(r1.code).toBe(1); expect(r1.err).toContain("could not read the tool list: tool list: empty"); expect(fs.existsSync(f)).toBe(false);
    const bad = path.join(OUT_DIR, "bad-list.json"); fs.writeFileSync(bad, "{not json");
    const r2 = await run(["--from", bad, "--out", f]);
    expect(r2.code).toBe(1); expect(r2.err).toContain("could not read the tool list"); expect(fs.existsSync(f)).toBe(false);
    const r3 = await run(["--from", path.join(OUT_DIR, "nope.json"), "--out", f]);
    expect(r3.code).toBe(1); expect(r3.err).toContain("ENOENT"); expect(fs.existsSync(f)).toBe(false);

    vi.stubGlobal("fetch", sharedMock([{ status: 403, body: { error: "unknown org", code: "IDENTITY_ORG_NOT_FOUND" } }]).fetch);
    const r4 = await run(["--url", "https://mcp.fastn.dev/acme", "--out", f], { FASTN_TOOLS_KEY: "ucl_secret_value" });
    expect(r4.code).toBe(1); expect(r4.err).toContain("could not read the tool list: tools/list: HTTP 403 unknown org"); expect(r4.err).not.toContain("ucl_secret_value"); expect(fs.existsSync(f)).toBe(false);
    vi.stubGlobal("fetch", sharedMock([{ body: rpcOk(1, { tools: [] }) }]).fetch);
    const r5 = await run(["--url", "https://mcp.fastn.dev/acme", "--key", "ucl_secret_value", "--out", f]);
    expect(r5.code).toBe(1); expect(r5.err).toContain("tool list: empty"); expect(r5.err).not.toContain("ucl_secret_value"); expect(fs.existsSync(f)).toBe(false);
    vi.stubGlobal("fetch", sharedMock([new TypeError("fetch failed")]).fetch);
    const r6 = await run(["--url", "https://mcp.fastn.dev/acme", "--key", "ucl_secret_value", "--out", f]);
    expect(r6.code).toBe(1); expect(r6.err).toContain("fetch failed"); expect(fs.existsSync(f)).toBe(false);

    expect((await run(["--out", f])).code).toBe(2);
    expect((await run(["--from", FIXTURE])).code).toBe(2);
    expect((await run(["--url", "https://mcp.fastn.dev/acme", "--out", f])).code).toBe(2);   // no key
    expect((await run(["--help"])).out).toContain("usage: fastn-sdk-tools");
    expect(fs.existsSync(f)).toBe(false);
  });
  it("--from and a live fetch (paged, as a customer) produce byte-identical output for the same list", async () => {
    const list = fixture();
    const m = workspace(list, 3);
    vi.stubGlobal("fetch", m.fetch);
    const live = outFile("live"), offline = outFile("offline");
    const r = await run(["--url", "https://mcp.fastn.dev/trillet", "--key", "ucl_secret_value", "--customer", "trillet_ws_prod_e2e", "--out", live, "--import", IMPORT]);
    expect(r.code).toBe(0);
    expect(m.calls.map((c) => c.json.method)).toEqual(["tools/list", "tools/list", "tools/list"]);
    expect(m.calls[0].init.headers["x-org-id"]).toBe("trillet_ws_prod_e2e"); expect(m.calls[0].init.headers.authorization).toBe("Bearer ucl_secret_value");
    const r2 = await run(["--from", FIXTURE, "--url", "https://mcp.fastn.dev/trillet", "--customer", "trillet_ws_prod_e2e", "--out", offline, "--import", IMPORT]);
    expect(r2.code).toBe(0);
    const a = fs.readFileSync(live, "utf8"), b = fs.readFileSync(offline, "utf8");
    expect(a).toBe(b);
    expect(a).not.toContain("ucl_secret_value");
    expect(a.split("\n")[0]).toContain('from https://mcp.fastn.dev/trillet for customer "trillet_ws_prod_e2e": 265 tools, 2 connectors');
  });
});

describe("every Trillet tool, generated and called", () => {
  it("each of the 265 generated methods sends its own tool name with the arguments as given, and no two methods share a tool", async () => {
    const list = fixture();
    const g = await gen(list, { url: "https://mcp.fastn.dev/trillet" });
    const mod = await load("trillet-all", g.source);
    const seen: Array<{ name: string; args: any }> = [];
    const m = workspace(list, 1, (name, args) => { seen.push({ name, args }); return undefined; });
    const tools = mod.createTools(new ToolsClient({ key: "ucl_test", url: "https://mcp.fastn.dev/trillet", fetch: m.fetch }));
    for (const meth of g.methods) {
      const target = meth.group ? tools[meth.group] : tools;
      expect(typeof target[meth.method], `${meth.group ?? "root"}.${meth.method}`).toBe("function");
      const probe = { probe: meth.tool };
      const r = await target[meth.method](probe);
      expect(r.isError).toBe(false);
    }
    expect(seen).toHaveLength(265);
    expect(new Set(seen.map((s) => s.name)).size).toBe(265);
    expect(seen.map((s) => s.name).sort()).toEqual(list.map((t) => t.name).sort());
    for (const s of seen) expect(s.args).toEqual({ probe: s.name });                   // arguments pass through untouched, to the right tool
    const scoped = mod.createTools(new ToolsClient({ key: "ucl_test", url: "https://mcp.fastn.dev/trillet", fetch: m.fetch })).customer("trillet_ws_prod_e2e");
    await scoped.googleCalendar.listCalendars({});
    expect(m.calls.at(-1)!.init.headers["x-org-id"]).toBe("trillet_ws_prod_e2e");
  }, 120_000);
});
