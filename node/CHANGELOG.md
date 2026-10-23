# Changelog

All notable changes to `@fastn-ai/sdk` are documented here.

## [Unreleased]

## [0.1.0] - 2026-10-22

- First working client. Platform API client generated from the fastn OpenAPI spec v1.8.2 (461 partner-facing operations in 19 areas, typed inputs; platform-administration and backend-only routes are left out).
- `fastn.customer(ref)`: register, setup links, embed tokens, connections, unified records, with one customer id.
- `ToolsClient` / `fastn.tools`: list and run every tool a fastn Connect workspace has turned on (MCP tools/list, tools/call), typed `ToolError`.
- Event signature verification (`parseEvent`, `verifyEventSignature`), `paginate`, retries with Retry-After, `FastnApiError` / `FastnNetworkError`.
- Tests: 39 unit; live suites for prod (`test/live/prod.test.ts`) and a Connect workspace (`test/live/tools.test.ts`), run with `LIVE=1`.

## [0.0.1] - 2026-10-22

- Initial package scaffold. No client yet.
