# @fastn-ai/sdk

The fastn platform REST API for Node and TypeScript. Every endpoint, generated from fastn's OpenAPI spec, plus a
small hand-written layer that makes the common partner flow easy.

- Node 20+ (built-in fetch), no runtime dependencies, ESM and CommonJS, full types.
- 461 operations in 19 areas (`orgs`, `embed`, `connections`, `unified`, `events`, `workflows`, ...), one method per
  operation, named exactly like the operation in the API docs and the Fastn Workspace tools. Platform-administration
  routes, which a partner key cannot call, are left out on purpose.
- Customer context that hides fastn's internal org ids: you only ever use the id you gave fastn.
- Event signature verification, retries, typed errors, pagination.

## Install

```bash
npm install @fastn-ai/sdk
```

## 60-second tour

```ts
import { FastnClient } from "@fastn-ai/sdk";

const fastn = new FastnClient({ apiKey: process.env.FASTN_API_KEY! });   // https://api.fastn.dev

// 1. Register a customer under your account, using YOUR id for them.
const customer = fastn.customer("acme-42");
await customer.register({ name: "Acme Dental" });              // idempotent: returns the existing org on repeat

// 2. Give them a link to connect their tools (Google Calendar, HubSpot, ...).
const link = await customer.setupLink({ widgetId: "wgt_...", connectionName: "Google Calendar" });
console.log(link.data.setupUrl);                               // send this to the customer

// 3. Read and write through the unified API, same field names as the catalog.
const meetings = customer.records({ category: "scheduling", entity: "meeting", provider: "googleCalendar" });
const booked = await meetings.create(
  { title: "Intro call", start_time: "2026-11-03T15:00:00Z", end_time: "2026-11-03T15:30:00Z", timezone: "Europe/London", attendee_email: "jane@example.com" },
  { idempotencyKey: "booking-123", correlationId: "req-abc" },  // safe to retry; traceable later
);
console.log(booked.id, booked.provider, booked.data.web_url);

await meetings.update(booked.id, { start_time: "2026-11-03T16:00:00Z", end_time: "2026-11-03T16:30:00Z" });
await meetings.search({ start_time: "2026-11-03T00:00:00Z", query: "Intro call" });
await meetings.delete(booked.id, { idempotencyKey: "cancel-123" });

const contacts = customer.records({ category: "crm", entity: "contact", provider: "hubspot" });
await contacts.create({ first_name: "Jane", last_name: "Doe", email: "jane@example.com" });

// 4. What did fastn do for my request id?
await fastn.unified.listUnifiedCalls({ correlation_id: "req-abc" });
```

Every area is on the client directly, with typed inputs. The partner flow lives in `orgs`, `embed`, `connections`, `unified`, `events` and `workflows`. Platform-administration areas (admin, platform config, support) and backend-only routes (OAuth callbacks, credential reads, staff approvals) are not generated: a partner key cannot call them, and leaving them out keeps the surface the SDK promises to keep stable small. The generator's `HIDDEN_TAGS` / `PUBLIC_INTERNAL` lists in `scripts/generate.ts` are the single place that rule lives.

```ts
await fastn.orgs.listOrgs({ type: "end_org" });
await fastn.connections.listConnections({ endOrgId: await customer.id() });
await fastn.events.listEventSubscriptions();
await fastn.embed.getSetupLink({ id: "stp_..." });
await fastn.call("getTenant", { id: "..." });                   // any operation by operationId
await fastn.me();                                               // who this key is: actor, role, org, parentOrg
```

## Customer ids, explained once

Use `fastn.customer(ref)` (or the `customer` option) and nothing else. The raw API names the same customer
differently per operation; those generated input fields still exist, but they are the raw API and will be
renamed on the platform side. Scoping calls to a customer needs a multi-tenant partner API key; the platform
rejects the customer headers on a single-tenant key (not exercised by the tests here).

| You see in the API docs        | What it is                                        | In this SDK                       |
| ------------------------------ | ------------------------------------------------- | --------------------------------- |
| `orgId` (createTenant body)    | the id YOU choose for the customer                | `fastn.customer(ref)`             |
| `externalRef`, `endOrgRef`, `x-end-org-ref` | the same id, under other names       | filled in for you                 |
| `endOrgId`, `id` (createTenant answer), `x-end-org-id` | fastn's own id of that customer org | `await customer.id()` (cached) |

`customer.register()`, `setupLink()`, `embedToken()`, `connect()`, `connectWithCredentials()`, `connections()`, `get()`,
`remove()` and `records(...)` all take the ref and resolve fastn's id only where the API insists on it. The lookup is
limited to orgs under your own org, so a key that can see more than your account can still never resolve someone
else's customer; the resolved id is cached per client.

`customer.api.<area>.<operation>()` runs any operation for that customer. It sends x-end-org-ref and, on routes that
take the customer in the body instead (`endOrgId` or `externalRef`: OAuth initiation, stored connections, event
subscriptions, secrets, setup links, ...), fills that field in too. The platform only reads the header on unified record
and workflow execute routes; without the body field those calls would silently run as your own org.

```ts
const { data } = await customer.connect({ connectorId: "googleCalendar", returnUrl: "https://app.acme.com/connected" });
redirect(data.authorizationUrl);                                      // the connection lands on the customer org

// Typed-in credentials (API key, basic auth): the fields come from the connector's auth method.
const fields = await customer.authFields("acme-crm");                 // { names, required, schema, authMethodId }
await customer.connectWithCredentials({ connectorId: "acme-crm", credentials: { apiKey: "..." }, name: "Acme CRM" });
```

Prefer `setupLink()` for credentials: fastn's hosted page collects them, so they never pass through your backend. For
auth types other than custom-input forms the platform may store the credential under a fixed field name that differs
from the auth method's contract; that is a platform limitation being tracked, not something the SDK can see.

## Responses and errors

Answers are returned exactly as the REST API sends them (usually `{ data: ... }`; unified records are
`{ id, provider, data }`), so the SDK agrees 1:1 with the REST docs and Postman collection. Typed where the spec
describes the answer, `Record<string, any>` otherwise.

Non-2xx answers throw `FastnApiError` with `status`, `code` (e.g. `NOT_FOUND`, `VALIDATION_ERROR`), `message`,
`details` and `requestId` (quote it when asking fastn for help). Network failures throw `FastnNetworkError`.
`GET` calls and calls that carry an `idempotencyKey` are retried on 429/502/503/504 (default 2 retries, honouring
`Retry-After`); other writes are never retried.

```ts
try { await fastn.orgs.getTenant({ id }); }
catch (e) { if (e instanceof FastnApiError && e.isNotFound) ... }
```

## Per-call options

Every method takes an optional second argument:

```ts
{ idempotencyKey, correlationId, customer, installationId, targetOrg, headers, extraBody, extraQuery, timeoutMs, retries, signal }
```

`extraBody` / `extraQuery` send fields the SDK does not know yet (a new API field before the SDK catches up); they are
passed as given and not validated.

`customer` is `{ ref: "acme-42" }` (your id) or `{ id: "<fastn org id>" }`. `new FastnClient({ defaults: { customer: { ref: "acme-42" } } })` applies options to every call.

## Workspace tools: run anything your workspace has turned on

The platform API above is one door. The other is your fastn Connect workspace (connect.fastn.dev > Tools): every connector you
switch on there, Google Calendar, HubSpot, Slack, the Fastn Workspace itself, becomes a tool the SDK can list and run.
Nothing in the SDK is tied to a connector; turn one on in the workspace and it shows up.

```ts
import { ToolsClient } from "@fastn-ai/sdk";              // or new FastnClient({ apiKey, tools: { key, url } }).tools

const connect = new ToolsClient({ key: process.env.FASTN_TOOLS_KEY!, url: "https://mcp.fastn.dev/<workspace>" });
const tools = await connect.tools();                           // every tool, e.g. googleCalendar__listEvents
const cal = await connect.toolsOf("googleCalendar");           // one connector's tools, with their input schemas

const r = await connect.customer("acme-42").call("googleCalendar__listEvents", { calendarId: "primary", timeMin: new Date().toISOString() });
r.data                                                     // the tool's answer, JSON-decoded (r.text is the raw text)
```

- The workspace key is a different credential from the platform API key. Read it from Settings > API keys in connect.fastn.dev.
- `customer(ref)` sends `X-Org-Id: ref`. A delegated key requires it on every call (400 otherwise); set it once with
  `defaults: { customer: { ref } }` when one client serves one customer.
- `userId` (sent as X-User-Id) is needed when the workspace runs calls as each person.
- Failures throw `ToolError` with `kind` "http" (gateway), "rpc" (JSON-RPC, e.g. unknown tool) or "tool" (the tool ran
  and answered an error), plus `status`, `code` and the gateway's message.
- In "one shared account" mode every call runs as that one account, whatever customer you name. Per-customer accounts
  need the "each customer org" mode in the workspace.
- The gateway does not yet pass X-Org-Id on to the platform, so Fastn Workspace tools that act for a customer (unified
  records, setup links) still take the customer in their arguments (`endOrgRef`) until that gateway change ships.

## Events (webhooks)

```ts
import { parseEvent, verifyEventSignature } from "@fastn-ai/sdk";

// Express: app.post("/fastn/events", express.raw({ type: "application/json" }), (req, res) => {
const event = parseEvent(process.env.FASTN_EVENT_SECRET!, req.headers, req.body);   // throws on a bad signature
// event.id is stable across retries: drop repeats by id.
```

The signature is `sha256=HMAC-SHA256(secret, "<X-Fastn-Timestamp>.<raw body>")`; deliveries older than 5 minutes
are rejected (configurable). Always pass the raw body, never a re-serialised object.

## Pagination

```ts
import { paginate } from "@fastn-ai/sdk";
for await (const ev of paginate((i) => fastn.events.listEvents(i), { status: "failed" }, { pageSize: 100 })) ...
```

Works for `limit`/`offset` lists and cursor lists; stops on a short page, a missing cursor, or a list that ignores paging.

## Development

```bash
npm run generate     # spec/openapi-*.json -> src/generated (ops, types, api)
npm test             # unit tests with a mocked fetch (42)
LIVE=1 FASTN_API_KEY=... npm run test:live   # live run on api.fastn.dev (creates and removes test data)
npm run build        # dist/ (esm + cjs + d.ts)
npm run spec:refresh -- /path/to/fastn-platform   # pull a newer spec from a platform checkout
```

`spec/SOURCE.md` records which platform commit the spec came from.

### What stays compatible

- The hand-written layer (`FastnClient`, `customer(...)`, `records(...)`, `ToolsClient`, `parseEvent`, `paginate`,
  the error classes) follows semver: breaking changes only in a major version.
- The generated methods mirror the REST API 1:1. `spec/surface.lock.json` records every operation with its input
  keys; `npm run generate` refuses a spec that removes an operation, renames an input or moves it (path, query, body,
  header) unless run with `--accept-breaking`, which goes with a major version bump. Additions pass.
- Everything under `unstable` (the wire manifest `OPS`, `FetchTransport`) has no compatibility promise.

## Releasing

1. Bump `version` in `node/package.json` and update `node/CHANGELOG.md` in a PR.
2. After merge, tag `main` and push the tag:
   ```bash
   git tag node/v0.0.1 && git push origin node/v0.0.1
   ```
3. The `Publish Node SDK` workflow checks the tag matches `package.json`, runs the checks, and publishes to npm with provenance. It uses the `NPM_TOKEN` secret from the `npm` GitHub environment.

## License

MIT
