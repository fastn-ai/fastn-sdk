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

// 2. Give them a link to connect their tools (Google Calendar, HubSpot, ...), by connector slug.
const link = await customer.connect("googleCalendar");
console.log(link.url);                                         // send this to the customer

// 3. Typed methods on whatever the customer connected: the provider is picked from their connections.
const booked = await customer.calendar.book(
  { title: "Intro call", start_time: "2026-11-03T15:00:00Z", end_time: "2026-11-03T15:30:00Z", timezone: "Europe/London", attendee_email: "jane@example.com" },
  { idempotencyKey: "booking-123", correlationId: "req-abc" },  // safe to retry; traceable later
);
console.log(booked.id, booked.provider, booked.data.web_url);

await customer.calendar.reschedule(booked.id, { start_time: "2026-11-03T16:00:00Z", end_time: "2026-11-03T16:30:00Z" });
await customer.calendar.cancel(booked.id, { idempotencyKey: "cancel-123" });

const { records } = await customer.crm.contacts.find({ email: "jane@example.com" }); // one page (the search route has no cursor); list() pages
const contact = records[0] ?? await customer.crm.contacts.create({ first_name: "Jane", last_name: "Doe", email: "jane@example.com" });
await customer.crm.notes.add({ body: "Booked an intro call", parent_id: contact.id, parent_type: "contact" });

// 4. What did fastn do for my request id?
await fastn.unified.listUnifiedCalls({ correlation_id: "req-abc" });
```

## Calendar and CRM, typed

`customer.calendar` and `customer.crm` are the unified API with the fields named: each method takes a TypeScript
interface (the catalog's own field names, `start_time`, `first_name`, ...; `Date` values are sent as ISO strings) and
answers `{ id, provider, data, warnings? }` or a page `{ records, nextCursor, hasMore }`. The provider is the one the
customer has connected for that entity: no connected provider answers 404 `NO_CONNECTED_PROVIDER` (send them a setup
link), several answer 409 `PROVIDER_AMBIGUOUS` (pass `{ provider }`). `warnings` lists fields the provider does not
map and therefore dropped. Every method takes `{ provider?, connectionId?, idempotencyKey?, correlationId?, ... }` last.

| Method | Underneath |
| --- | --- |
| `calendar.freeSlots({ start_time, end_time, timezone?, slot_minutes? })` | scheduling/availability; answers `busy`, `free`, and `slots` of that length |
| `calendar.book(meeting)`, `get(id)`, `find({ start_time, end_time })`, `list({ page_size, cursor })`, `reschedule(id, { start_time, end_time })`, `cancel(id)` | scheduling/meeting |
| `crm.contacts.create / get / find({ email, phone, first_name, last_name }) / list / update / delete` | crm/contact |
| `crm.notes.add({ body, parent_id, parent_type })`, `update`, `delete` | crm/note (`created_at` defaults to now) |
| `crm.tasks.add({ subject, due_date, status, ... })`, `get`, `list`, `update`, `delete` | crm/task |
| `crm.deals.create({ name, amount, stage, ... })`, `get`, `list`, `update`, `moveStage(id, stage)`, `delete`, `stages()` | crm/opportunity, crm/stage |

What they do not cover is still one call away: `customer.records({ category, entity, provider })` takes any entity
in the catalog with untyped input, and `customer.runAction(...)` runs a connector's own action.

```ts
// The catalog: which categories and entities exist, the fields each takes, which providers a customer connected.
const categories = await fastn.catalog.categories();                 // [{ slug: "crm", entities: [{ slug: "contact", operations, createFields }] }]
const fields = await fastn.catalog.fields("crm", "contact");         // [{ field: "email", type: "string", required: false }, ...]
const providers = await customer.catalog.providers("crm", "contact"); // [{ connectorSlug: "hubspot", connected: true, operations: [...] }]
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

`customer.register()`, `connect(app)`, `links`, `watch()`, `disconnect()`, `renameAccount()`, `update()`, `callLog()`,
`setupLink()`, `embedToken()`, `connectWithCredentials()`, `connections()`, `get()`, `remove()`, `calendar`, `crm` and
`records(...)` all take the ref and resolve fastn's id only where the API insists on it. The lookup is
limited to orgs under your own org, so a key that can see more than your account can still never resolve someone
else's customer; the resolved id is cached per client.

`customer.api.<area>.<operation>()` runs any operation for that customer. It sends x-end-org-ref and, on routes that
take the customer in the body instead (`endOrgId` or `externalRef`: OAuth initiation, stored connections, event
subscriptions, secrets, setup links, ...), fills that field in too. The platform only reads the header on unified record
and workflow execute routes; without the body field those calls would silently run as your own org.

```ts
// A setup link by app: the account's widget for that connector is found for you (several: pass widgetId).
const link = await customer.connect("hubspot", { connectionName: "Main CRM", redirectUrl: "https://app.acme.com/connected" });
redirect(link.url);                                                   // then customer.links.get(link.setupId) / links.cancel(...)

// Or start OAuth directly, without a widget:
const { data } = await customer.connect({ connectorId: "googleCalendar", returnUrl: "https://app.acme.com/connected" });
redirect(data.authorizationUrl);                                      // the connection lands on the customer org

// Typed-in credentials (API key, basic auth): the fields come from the connector's auth method. The platform checks
// them; an incomplete set answers 400 CREDENTIALS_INCOMPLETE with the missing names (err.body.missing).
const fields = await customer.authFields("acme-crm");                 // { names, required, schema, authMethodId }
await customer.connectWithCredentials({ connectorId: "acme-crm", credentials: { apiKey: "..." }, name: "Acme CRM" });
```

```ts
// Changes at an app, sent to your webhook as connector.event / unified.event: watch them per customer.
const w = await customer.watch("hubspot", ["contact.created", "deal.stageChanged"], { accountId: hubspotPortalId });
await customer.watches("hubspot");                                    // [{ id, app, events, status }]
await customer.unwatch("hubspot");                                    // or unwatch(w.id)

await customer.disconnect(accountId);                                 // the customer gets connection.revoked
await customer.renameAccount(accountId, "Front desk calendar");
await customer.update({ name: "Acme Dental Ltd" });                   // or { status: "suspended" }
await customer.callLog("req-abc");                                    // what fastn did for your request id

// Your webhook, once for the whole account.
const hook = await fastn.webhooks.create({ url: "https://app.acme.com/fastn", eventTypes: ["connection.connected", "setup_link.completed", "connector.event", "unified.event"] });
hook.secret                                                           // shown once: the signing secret for parseEvent
await fastn.webhooks.test(hook.id); await fastn.webhooks.deliveries(hook.id); await fastn.webhooks.rotateSecret(hook.id);
```

```ts
// Anything the unified API does not cover: run the connector's own action with the customer's connection.
const r = await customer.runAction({ connector: "hubspot", action: "updateDeal", input: { dealId, properties: { dealstage: "qualifiedtobuy" } } });
r.data.response                                                       // the provider's answer
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
`GET` calls are retried on 429/502/503/504 (default 2 retries, honouring `Retry-After`). A write is retried only when
it carries an `idempotencyKey` **and** the platform de-duplicates that operation by it (unified record create, update
and delete, workflow execute; each such method says so in its doc). Every other write is never retried, so a lost
answer cannot make it act twice.

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
- Failures throw `ToolError` with `kind` "http" (gateway), "rpc" (JSON-RPC, e.g. unknown tool), "tool" (the tool ran
  and answered an error) or "auth" (the app is not connected for this customer yet), plus `status`, `code` and the
  gateway's message. For "auth", `e.isConnectionRequired` is true and `e.authorizeUrl` is where to send the customer,
  so an agent can ask the user to connect at runtime instead of failing.
- In "one shared account" mode every call runs as that one account, whatever customer you name. Per-customer accounts
  need the "each customer org" mode in the workspace.
- The customer is named once. Fastn Workspace tools that act for a customer (unified records) take it as the
  `endOrgRef` argument, and `customer(ref)` fills that in for every tool whose input schema has it, from one
  tools/list per workspace (shared by every `customer()` clone, kept for 10 minutes). An `endOrgRef` or `endOrgId`
  you pass yourself wins; `customerArg: false` on the client turns the fill off. Tools of other connectors are left
  alone: the customer reaches them through X-Org-Id. Call `await connect.tools()` once at startup if the first call
  must not pay for the listing.
- One name for the customer: write `orgId` in the arguments of any Fastn Workspace tool. Where the tool spells it
  `endOrgId` or `end_org_id` (and has no `orgId` of its own), the SDK passes the value under that spelling, so your
  code never carries the older names; a value you pass under the old name is left as it is.
- Answers of Fastn Workspace tools and parsed events come back without fastn's internal customer id keys
  (`endOrgId`, `end_org_id`): the only customer id you see is the one you chose (`orgId` / `tenantRef`). `r.text` keeps
  the raw answer; `parseEvent(..., { internalIds: true })` keeps the id in an event.

### Typed methods for your workspace: `npx fastn-sdk-tools`

Tool names as strings work, but your editor cannot check them. The generator turns your workspace's tool list into one
TypeScript module with a class per connector and a method per tool, each input typed from the tool's schema:

```sh
# once, and again whenever the workspace changes (commit the file)
export FASTN_TOOLS_KEY=...                                        # the workspace key; it never ends up in the file
npx fastn-sdk-tools --url https://mcp.fastn.dev/<workspace> --out src/fastn-tools.ts
npx fastn-sdk-tools --url https://mcp.fastn.dev/<workspace> --out src/fastn-tools.ts --check   # CI: exit 1 on drift
```

```ts
import { ToolsClient } from "@fastn-ai/sdk";
import { createTools } from "./fastn-tools.js";

const tools = createTools(new ToolsClient({ key: process.env.FASTN_TOOLS_KEY!, url: "https://mcp.fastn.dev/<workspace>" }));
// or createTools(fastn) with a FastnClient created with tools: { key, url }

const acme = tools.customer("acme-42");                                       // X-Org-Id on every call, endOrgRef filled where a tool takes it
const cals = await acme.googleCalendar.listCalendars({});                     // tools.<connector>.<tool>(args, opts?)
const created = await acme.hubspot.createContact({ email: "jane@example.com", firstname: "Jane" });   // args typed from the schema
const cats = await tools.fastnPlatform.listUnifiedCategories();               // a tool with no inputs takes no argument
created.data                                                                  // ToolResult, as from call(); ToolError on failure
```

- `--url` + `--key` (or `FASTN_TOOLS_URL` / `FASTN_TOOLS_KEY`) fetch the listing; `--from tools-list.json` generates
  offline from a saved tools/list (the same list gives the same file). `--customer <ref>` fetches the listing as that
  customer. The header records the url, customer and tool count, never the key.
- The module exports `createTools`, `Tools`, one class per connector (`GoogleCalendarTools`), one input interface per
  tool (`GoogleCalendarListEventsInput`), an output type where the tool publishes an `outputSchema` (else the answer is
  `unknown`), and `TOOL_NAMES`. Tools without a connector prefix (`skill`, `feedback`) are methods on the root.
- Names are made identifiers (`google-calendar` -> `googleCalendar`, `create-contact` -> `createContact`); a clash after
  that gets a name-derived variant (`create_contact`, `createContactTool`). Property names stay as the schema spells
  them (quoted when needed). A tool whose schema says nothing about a field types it `unknown`; an object with no
  declared properties is `Record<string, unknown>`.
- `tools.client` is the `ToolsClient` under the methods, for a tool the file does not know yet.
- Programmatic use: `import { generateToolsModule } from "@fastn-ai/sdk/codegen"`. The schema-to-type step is
  `json-schema-to-typescript`, the package's one runtime dependency (the CLI runs from the installed package, so it
  cannot be a devDependency); it is loaded by the generator only, never by the client.

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
npm test             # unit tests with a mocked fetch
LIVE=1 FASTN_API_KEY=... FASTN_TEST_CUSTOMER=... npm run test:live   # live run on api.fastn-test.dev (creates and removes test data)
# FASTN_BASE_URL=https://api.fastn.dev LIVE_PROD=1 ... runs the same suite on production
# FASTN_API_KEY=... npx tsx scripts/sweep/run.ts   # calls every published operation once on dev and writes a per-operation report
npm run build        # dist/ (esm + cjs + d.ts)
npm run spec:refresh -- /path/to/fastn-platform   # pull a newer spec from a platform checkout
```

`spec/SOURCE.md` records which platform commit the spec came from.

### What stays compatible

- The hand-written layer (`FastnClient`, `customer(...)`, `records(...)`, `ToolsClient`, `parseEvent`, `paginate`,
  the error classes) follows semver: breaking changes only in a major version. Until 1.0 they can still land in a
  minor and are listed under Changed in the CHANGELOG.
- The generated methods mirror the REST API 1:1. `spec/surface.lock.json` records every operation with its input
  keys (where each goes on the wire and whether it is required) and its output fields (path, structural type,
  whether always present; no descriptions). `npm run generate` refuses a spec that removes an operation, renames or
  moves an input, makes an optional input required, adds a required input, removes or retypes an output field, or
  stops guaranteeing one, unless run with `--accept-breaking`, which goes with a major version bump. New operations,
  new optional inputs, new output fields and description edits pass. `npm run generate:check -- --spec=<file>`
  reports what a spec would change without writing anything (exit 1 on a break), for CI and for trying a refresh.
- Everything under `unstable` (the wire manifest `OPS`, `FetchTransport`) has no compatibility promise.

## Releasing

1. Bump `version` in `node/package.json` and update `node/CHANGELOG.md` in a PR.
2. After merge, tag `main` and push the tag:
   ```bash
   git tag node/v0.0.1 && git push origin node/v0.0.1
   ```
3. The `Publish Node SDK` workflow checks the tag matches `package.json`, runs the checks, and runs `npm stage publish`. It uses the `NPM_TOKEN` secret (a stage-only token) from the `npm` GitHub environment.
4. A maintainer opens npmjs.com > Staged Packages, reviews the version and approves it with 2FA. Only then is it installable.

## License

MIT
