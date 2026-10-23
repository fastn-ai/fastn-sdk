# Changelog

All notable changes to `@fastn-ai/sdk` are documented here.

## [Unreleased]

- Fixed: `customer.api.*` now fills `endOrgId` / `externalRef` in the body on routes that take the customer there (OAuth initiation, stored connections, event subscriptions, secrets, setup links, ...). The platform reads the x-end-org-ref header only on unified record and workflow execute routes, so those calls used to run as the partner org.
- Fixed: `customer.find()` / `id()` only look under the caller's own org (listOrgs with `parent_id`, parentId checked), so a key that sees every org can never resolve another partner's customer. The ref -> id cache is now per client, not per `Customer` object.
- Fixed: `customer.remove()` sets the org back to active when the delete fails and says so in the error.
- Added: `customer.connect()` (OAuth, returns `authorizationUrl`), `customer.authFields()` and `customer.connectWithCredentials()` (typed-in credentials, required fields checked first), `fastn.me()` (whoami, cached).
- Added: `spec/surface.lock.json`, a record of every generated operation and input key; `npm run generate` fails on a spec that removes or renames one unless `--accept-breaking` is given.
- Added: `extraBody` / `extraQuery` per-call options for API fields the SDK does not know yet.
- Changed: `OPS`, `FetchTransport` and their types moved under the `unstable` export (no compatibility promise). The generator refuses an API area whose name would shadow a client member.
- Added: `ToolError` kind "auth" with `isConnectionRequired`, `authorizeUrl` and `connector`, from the gateway's authRequired answer.
- Added: `scripts/sweep`, a live run that calls every published operation once (reads, writes, deletes) and writes a per-operation report; live suites run on the development environment by default (`FASTN_BASE_URL`, `LIVE_PROD=1` for production) and one file at a time.
- Changed: `Records` methods are typed with the generated unified input/output types (no more `as any`).

## [0.1.0] - 2026-10-22

- First working client. Platform API client generated from the fastn OpenAPI spec v1.8.2 (461 partner-facing operations in 19 areas, typed inputs; platform-administration and backend-only routes are left out).
- `fastn.customer(ref)`: register, setup links, embed tokens, connections, unified records, with one customer id.
- `ToolsClient` / `fastn.tools`: list and run every tool a fastn Connect workspace has turned on (MCP tools/list, tools/call), typed `ToolError`.
- Event signature verification (`parseEvent`, `verifyEventSignature`), `paginate`, retries with Retry-After, `FastnApiError` / `FastnNetworkError`.
- Tests: 39 unit; live suites for prod (`test/live/prod.test.ts`) and a Connect workspace (`test/live/tools.test.ts`), run with `LIVE=1`.

## [0.0.1] - 2026-10-22

- Initial package scaffold. No client yet.
