import { describe, it, expect, vi } from "vitest";
import { FastnClient, FastnApiError, FastnNetworkError, unstable } from "../../src/index.js";
const { OPS } = unstable;

function mockFetch(responses: Array<{ status?: number; body?: unknown; headers?: Record<string, string> } | Error>) {
  const calls: { url: string; init: any }[] = [];
  const fetch = vi.fn(async (url: string, init: any) => {
    calls.push({ url, init });
    const r = responses.shift() ?? { status: 200, body: { data: {} } };
    if (r instanceof Error) throw r;
    const text = r.body === undefined ? "" : typeof r.body === "string" ? r.body : JSON.stringify(r.body);
    return new Response(r.status === 204 ? null : text, { status: r.status ?? 200, headers: { "content-type": "application/json", "x-request-id": "req_1", ...r.headers } });
  });
  return { fetch: fetch as unknown as typeof globalThis.fetch, calls };
}
const client = (m: ReturnType<typeof mockFetch>, extra = {}) => new FastnClient({ apiKey: "k_test", fetch: m.fetch, retries: 2, ...extra });

describe("request shape", () => {
  it("path + query + api key header", async () => {
    const m = mockFetch([{ body: { data: [] } }]);
    await client(m).orgs.listOrgs({ type: "end_org", include_usage: "true" });
    expect(m.calls[0].url).toBe("https://api.fastn.dev/v1/orgs?type=end_org&include_usage=true");
    expect(m.calls[0].init.method).toBe("GET");
    expect(m.calls[0].init.headers["x-api-key"]).toBe("k_test");
    expect(m.calls[0].init.body).toBeUndefined();
  });
  it("path params are encoded and required", async () => {
    const m = mockFetch([{ body: {} }]);
    await client(m).orgs.getTenant({ id: "a/b c" });
    expect(m.calls[0].url).toBe("https://api.fastn.dev/v1/orgs/a%2Fb%20c");
    await expect(client(m).orgs.getTenant({} as any)).rejects.toThrow(/"id" is required/);
  });
  it("body fields are mapped to wire names and undefined is dropped", async () => {
    const m = mockFetch([{ status: 201, body: { data: { id: "org_1" } } }]);
    const res = await client(m).orgs.createTenant({ name: "Acme", orgId: "acme-1", slug: undefined });
    expect(res).toEqual({ data: { id: "org_1" } });
    expect(JSON.parse(m.calls[0].init.body)).toEqual({ name: "Acme", orgId: "acme-1" });
    expect(m.calls[0].init.headers["content-type"]).toBe("application/json");
  });
  it("open bodies pass extra fields through, closed bodies drop them", async () => {
    const m = mockFetch([{ body: {} }, { body: {} }]);
    const c = client(m);
    expect(OPS.updateOrgConfig.body?.open).toBe(true);
    await c.orgs.updateOrgConfig({ id: "org_1", orgName: "Acme", setupLinkRedirectUrls: ["https://app.acme.com/connected"] } as any);
    expect(JSON.parse(m.calls[0].init.body)).toEqual({ orgName: "Acme", setupLinkRedirectUrls: ["https://app.acme.com/connected"] });
    expect(OPS.createTenant.body?.open).toBeFalsy();
    await c.orgs.createTenant({ name: "Acme", orgId: "acme-1", plan: "free", surprise: 1 } as any);
    expect(JSON.parse(m.calls[1].init.body)).not.toHaveProperty("surprise");
  });
  it("free-form body uses the spec's input name (record / filters)", async () => {
    const m = mockFetch([{ body: {} }, { body: {} }]);
    const c = client(m);
    await c.unified.createUnifiedRecord({ category: "crm", entity: "contact", provider: "hubspot", record: { email: "a@b.c" } });
    expect(m.calls[0].url).toBe("https://api.fastn.dev/v1/unified/crm/contact?provider=hubspot");
    expect(JSON.parse(m.calls[0].init.body)).toEqual({ email: "a@b.c" });
    await c.unified.searchUnifiedRecords({ category: "crm", entity: "contact", filters: { email: "a@b.c" } });
    expect(JSON.parse(m.calls[1].init.body)).toEqual({ email: "a@b.c" });
  });
  it("header params from the spec and cross-cutting options become headers", async () => {
    const m = mockFetch([{ body: {} }, { body: {} }]);
    const c = client(m);
    await c.unified.createUnifiedRecord({ category: "scheduling", entity: "meeting", endOrgRef: "cust-1", record: {} }, { idempotencyKey: "k1", correlationId: "c1" });
    const h = m.calls[0].init.headers;
    expect(h["x-end-org-ref"]).toBe("cust-1"); expect(h["idempotency-key"]).toBe("k1"); expect(h["x-fastn-correlation-id"]).toBe("c1");
    await c.unified.updateUnifiedRecord({ category: "scheduling", entity: "meeting", id: "m1", record: {} }, { customer: { ref: "cust-1" }, installationId: "inst_1" });
    expect(m.calls[1].init.headers["x-end-org-ref"]).toBe("cust-1"); expect(m.calls[1].init.headers["x-installation-id"]).toBe("inst_1");
    expect(m.calls[1].init.method).toBe("PATCH");
  });
  it("renamed collisions keep the path value and send the body value", async () => {
    const op = OPS.updateConfigEntry;
    expect(op.params.find((p) => p.in === "path" && p.name === "id")?.key).toBe("id");
    expect(op.body?.keys?.bodyId).toBe("id");
    expect(op.body?.keys?.bodyConnectorId).toBe("connectorId");
  });
  it("defaults from the client apply to every call", async () => {
    const m = mockFetch([{ body: {} }]);
    await client(m, { defaults: { customer: { ref: "cust-9" }, headers: { "x-custom": "1" } } }).unified.listUnifiedRecords({ category: "crm", entity: "contact" });
    expect(m.calls[0].init.headers["x-end-org-ref"]).toBe("cust-9"); expect(m.calls[0].init.headers["x-custom"]).toBe("1");
  });
  it("customer { id } sends x-end-org-id, a per-call customer overrides the default", async () => {
    const m = mockFetch([{ body: {} }, { body: {} }]);
    const c = client(m, { defaults: { customer: { ref: "cust-9" } } });
    await c.unified.listUnifiedRecords({ category: "crm", entity: "contact" }, { customer: { id: "0b3241c4-fastn" } });
    expect(m.calls[0].init.headers["x-end-org-id"]).toBe("0b3241c4-fastn"); expect(m.calls[0].init.headers["x-end-org-ref"]).toBeUndefined();
    await c.unified.listUnifiedRecords({ category: "crm", entity: "contact" });
    expect(m.calls[1].init.headers["x-end-org-ref"]).toBe("cust-9"); expect(m.calls[1].init.headers["x-end-org-id"]).toBeUndefined();
  });
  it("extraBody and extraQuery send fields the SDK does not know", async () => {
    const m = mockFetch([{ body: {} }, { body: {} }, { body: {} }]);
    const c = client(m);
    await c.orgs.createTenant({ name: "Acme", orgId: "acme-1" }, { extraBody: { brandNewField: true } });
    expect(JSON.parse(m.calls[0].init.body)).toEqual({ name: "Acme", orgId: "acme-1", brandNewField: true });
    await c.orgs.listOrgs({ type: "end_org" }, { extraQuery: { brand_new: "1", tags: ["a", "b"] } });
    expect(m.calls[1].url).toBe("https://api.fastn.dev/v1/orgs?type=end_org&brand_new=1&tags=a&tags=b");
    await c.unified.createUnifiedRecord({ category: "crm", entity: "contact", record: { email: "a@b.c" } }, { extraBody: { custom_field: 1 } });
    expect(JSON.parse(m.calls[2].init.body)).toEqual({ email: "a@b.c", custom_field: 1 });
    await expect(c.orgs.listOrgs({}, { extraBody: { x: 1 } })).rejects.toThrow(/takes no request body/);
  });
  it("call() by operationId", async () => {
    const m = mockFetch([{ body: { data: 1 } }]);
    expect(await client(m).call("listOrgs")).toEqual({ data: 1 });
    expect(m.calls[0].url).toBe("https://api.fastn.dev/v1/orgs");
  });
});

describe("errors and retries", () => {
  it("non-2xx becomes FastnApiError with status, code, message and requestId", async () => {
    const m = mockFetch([{ status: 404, body: { error: { code: "NOT_FOUND", message: "Tenant not found", details: { id: "x" } } } }]);
    const err = await client(m).orgs.getTenant({ id: "x" }).catch((e) => e);
    expect(err).toBeInstanceOf(FastnApiError);
    expect(err.status).toBe(404); expect(err.code).toBe("NOT_FOUND"); expect(err.isNotFound).toBe(true);
    expect(err.message).toContain("Tenant not found"); expect(err.requestId).toBe("req_1"); expect(err.details).toEqual({ id: "x" });
  });
  it("string error bodies are kept", async () => {
    const m = mockFetch([{ status: 403, body: { error: "Forbidden" } }]);
    const err = await client(m).orgs.listOrgs().catch((e) => e);
    expect(err.status).toBe(403); expect(err.message).toContain("Forbidden"); expect(err.isAuth).toBe(true);
  });
  it("GET retries on 503 then succeeds", async () => {
    const m = mockFetch([{ status: 503, body: { error: "down" } }, { body: { data: [] } }]);
    expect(await client(m).orgs.listOrgs()).toEqual({ data: [] });
    expect(m.calls.length).toBe(2);
  });
  it("writes are retried only where the platform honours Idempotency-Key", async () => {
    const m1 = mockFetch([{ status: 503, body: { error: "down" } }]);
    await expect(client(m1).orgs.createTenant({ name: "x" })).rejects.toBeInstanceOf(FastnApiError);
    expect(m1.calls.length).toBe(1);
    // createTenant does not honour the key: a key is sent, but a lost answer is never retried
    const m3 = mockFetch([{ status: 503, body: { error: "down" } }]);
    await expect(client(m3).orgs.createTenant({ name: "x" }, { idempotencyKey: "k" })).rejects.toBeInstanceOf(FastnApiError);
    expect(m3.calls.length).toBe(1); expect(m3.calls[0].init.headers["idempotency-key"]).toBe("k");
    expect(OPS.createTenant.idempotent).toBeFalsy(); expect(OPS.createUnifiedRecord.idempotent).toBe(true); expect(OPS.executeWorkflow.idempotent).toBe(true);
    const m2 = mockFetch([{ status: 429, body: { error: "slow" }, headers: { "retry-after": "0" } }, { status: 201, body: { ok: 1 } }]);
    expect(await client(m2).unified.createUnifiedRecord({ category: "crm", entity: "contact", record: {} }, { idempotencyKey: "k" })).toEqual({ ok: 1 });
    expect(m2.calls.length).toBe(2);
  });
  it("retries stop at the limit and 4xx is never retried", async () => {
    const m = mockFetch([{ status: 502, body: "" }, { status: 502, body: "" }, { status: 502, body: "" }, { status: 502, body: "" }]);
    const err = await client(m).orgs.listOrgs().catch((e) => e);
    expect(err.status).toBe(502); expect(m.calls.length).toBe(3);
    const m4 = mockFetch([{ status: 400, body: { error: "bad" } }, { body: {} }]);
    await expect(client(m4).orgs.listOrgs()).rejects.toThrow(/400/); expect(m4.calls.length).toBe(1);
  });
  it("network failure becomes FastnNetworkError after retries", async () => {
    const m = mockFetch([new Error("ECONNRESET"), new Error("ECONNRESET"), new Error("ECONNRESET")]);
    const err = await client(m).orgs.listOrgs().catch((e) => e);
    expect(err).toBeInstanceOf(FastnNetworkError); expect(err.message).toContain("ECONNRESET"); expect(m.calls.length).toBe(3);
  });
  it("empty 204 answers resolve to undefined", async () => {
    const m = mockFetch([{ status: 204, body: undefined }]);
    expect(await client(m).orgs.deleteTenant({ id: "org_1" })).toBeUndefined();
  });
  it("apiKey is required", () => { expect(() => new FastnClient({} as any)).toThrow(/apiKey/); });
});
