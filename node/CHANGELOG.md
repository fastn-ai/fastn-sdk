# Changelog

All notable changes to `@fastn-ai/sdk` are documented here.

## [Unreleased]

## [0.3.0] - 2026-10-28

- Added: typed calendar and CRM methods on a customer. `customer.calendar.freeSlots / book / get / find / list / reschedule / cancel` (scheduling/availability and scheduling/meeting) and `customer.crm.contacts`, `crm.notes`, `crm.tasks`, `crm.deals` (`create / get / find / list / update / delete`, plus `notes.add`, `tasks.add`, `deals.moveStage`, `deals.stages`). Inputs are TypeScript interfaces with the catalog's field names (`Date` values are sent as ISO strings); answers are `{ id, provider, data, warnings? }` records or `{ records, nextCursor, hasMore }` pages. The provider is resolved from the customer's connected providers for that entity, once per client: none answers 404 `NO_CONNECTED_PROVIDER`, several 409 `PROVIDER_AMBIGUOUS`, and `{ provider }` on the call overrides. A provider or connection error forgets the cached answer. `notes.add` defaults `created_at` to now (HubSpot requires it). An empty record id throws before any request.
- Added: `customer.connect("googleCalendar")` makes a setup link by connector slug: the account's widget for that connector is looked up once per client (`listWidgets`, matched on `connectorRefs`), `connectionName` defaults to the widget's name, and the answer is `{ setupId, url, status, expiresAt, widgetId }`. No widget: 404 `WIDGET_NOT_FOUND`; several: 409 `WIDGET_AMBIGUOUS` (pass `widgetId`). The object form `connect({ connectorId, ... })` (direct OAuth) is unchanged. `customer.links.get(setupId)` and `links.cancel(setupId)` read and revoke a link.
- Added: the unified catalog. `fastn.catalog.categories()`, `.category(slug)`, `.entity(category, entity)`, `.fields(category, entity)` (create fields with `required`), and `.providers(category, entity)`; `customer.catalog.providers(...)` reports the customer's own connections.
- Added: `freeIntervals(start, end, busy)` and `slotsOf(free, minutes)`, the arithmetic behind `freeSlots`.


## [0.2.0] - 2026-10-27

- Changed: answers of Fastn Workspace tools (`ToolResult.data` / `structuredContent`) and events parsed with `parseEvent` no longer carry fastn's internal customer id keys (`endOrgId`, `end_org_id`); the partner's own id (`orgId`, `externalRef`, `tenantRef`) is what remains. `r.text` keeps the raw answer; `parseEvent(..., { internalIds: true })` keeps the id; `customerArg: false` keeps answers untouched.
- Added: `orgId` is the one name for the customer on workspace tools: a Fastn Workspace tool that spells it `endOrgId` or `end_org_id` (with no `orgId` of its own) receives the value under its own spelling, so partner code never carries the older names.
- Added: the customer is named once on workspace tools. `ToolsClient.customer(ref)` (and the `customer` call option) fills `endOrgRef: ref` into every Fastn Workspace tool whose input schema takes it (the unified record tools), from one tools/list per workspace shared by every `customer()` clone and kept for 10 minutes. An `endOrgRef` / `endOrgId` passed by the caller wins; `customerArg: false` turns the fill off; tools of other connectors are untouched. Before this, a call scoped with `customer(ref)` still had to repeat the customer in its arguments or the platform answered "No connected provider".

## [0.1.0] - 2026-10-24

First working client.

- Fixed: `customer.connectWithCredentials()` no longer checks credential fields on the client. The platform checks them for INPUT auth methods only (400 CREDENTIALS_INCOMPLETE, `body.missing`); the other auth types store one fixed key per type that the method's contract does not always name, so the client-side check refused connections the platform accepts.
- Fixed: `customer.api.*` leaves `externalRef` alone on `createTenant` / `updateTenant` (there it names the org being edited, not the customer), and sends the ref itself as `endOrgId` on `createEmbedToken`, so `createIfMissing` works through `customer.api` for a customer that is not registered yet.
- Fixed: `customer.runAction()` lists only the customer's installations (`end_org_id`) and runs from the customer's connection alone when it has no installation (a connection made with `connect()` / `connectWithCredentials()`).
- Fixed: `customer.remove()` checks the org after a failed delete: gone (a lost answer) counts as removed; otherwise it is set back to active as before.
- Changed: `spec/surface.lock.json` now records whether each input is required (`!` suffix) and each operation's output fields (path, structural type, always present or not; no descriptions); `npm run generate` also refuses an optional input turned required, a new required input, a removed or retyped output field, or a required output field turned optional, without `--accept-breaking`. New output fields and description edits pass. The lock logic lives in `scripts/surface.ts`, shared with the unit test. `npm run generate:check -- --spec=<file>` reports a spec's changes against the lock without writing anything.
- Changed: `FastnApiError` takes `(message, { status, code, details, method, path, requestId, body })` instead of eight positional arguments.
- Changed: `ToolsClient` and the REST transport share one HTTP helper (`src/http.ts`): the same timeout/abort handling (no listener left on a reused `AbortSignal`), backoff with cap and jitter, retry set (429/502/503/504), loose JSON parsing and error-message extraction. `toolsOf()` reuses one tools listing per client for 60s (or takes `from`).
- Changed: `src/version.ts` is generated from `package.json`; `SPEC_FILE` is exported next to `SPEC_VERSION` (the `FastnClient.specVersion` / `specFile` statics are gone); the `Customer` id cache is filled from every org row seen and concurrent lookups share one request; `customer.api` and `customer.tools` are built once per object.
- Changed: `scripts/sweep` refuses production without `LIVE_PROD=1`, like the live suites; the live suites share their helpers (`test/live/_shared.ts`), so secret masking is in one place.
- Fixed: `customer.api.*` now fills `endOrgId` / `externalRef` in the body on routes that take the customer there (OAuth initiation, stored connections, event subscriptions, secrets, setup links, ...). The platform reads the x-end-org-ref header only on unified record and workflow execute routes, so those calls used to run as the partner org.
- Fixed: `customer.find()` / `id()` only look under the caller's own org (listOrgs with `parent_id`, parentId checked), so a key that sees every org can never resolve another partner's customer. The ref -> id cache is now per client, not per `Customer` object.
- Fixed: `customer.remove()` sets the org back to active when the delete fails and says so in the error.
- Added: `customer.connect()` (OAuth, returns `authorizationUrl`), `customer.authFields()` and `customer.connectWithCredentials()` (typed-in credentials, required fields checked first), `fastn.me()` (whoami, cached).
- Added: `spec/surface.lock.json`, a record of every generated operation and input key; `npm run generate` fails on a spec that removes or renames one unless `--accept-breaking` is given.
- Added: `extraBody` / `extraQuery` per-call options for API fields the SDK does not know yet.
- Changed: `OPS`, `FetchTransport` and their types moved under the `unstable` export (no compatibility promise). The generator refuses an API area whose name would shadow a client member.
- Added: `customer.runAction({ connector, action, input })` runs a raw connector action with the customer's own connection and installation pinned, for what the unified catalog does not map (e.g. HubSpot deal stage, call logging).
- Added: `ToolError` kind "auth" with `isConnectionRequired`, `authorizeUrl` and `connector`, from the gateway's authRequired answer.
- Added: `scripts/sweep`, a live run that calls every published operation once (reads, writes, deletes) and writes a per-operation report; live suites run on the development environment by default (`FASTN_BASE_URL`, `LIVE_PROD=1` for production) and one file at a time.
- Changed: `Records` methods are typed with the generated unified input/output types (no more `as any`).

From the first cut (never published):
- Platform API client generated from the fastn OpenAPI spec v1.8.2 (461 partner-facing operations in 19 areas, typed inputs; platform-administration and backend-only routes are left out).
- `fastn.customer(ref)`: register, setup links, embed tokens, connections, unified records, with one customer id.
- `ToolsClient` / `fastn.tools`: list and run every tool a fastn Connect workspace has turned on (MCP tools/list, tools/call), typed `ToolError`.
- Event signature verification (`parseEvent`, `verifyEventSignature`), `paginate`, retries with Retry-After, `FastnApiError` / `FastnNetworkError`.
- Tests: 39 unit; live suites for prod (`test/live/prod.test.ts`) and a Connect workspace (`test/live/tools.test.ts`), run with `LIVE=1`.

## [0.0.1] - 2026-10-22

- Initial package scaffold. No client yet.
