# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased] — Canonical Terminology Refactor

(See below for details — this will ship in a future version.)

## [0.4.0] - 2026-10-28

### Added

- **`fastn.platform`**: a client for the fastn platform REST API with the same surface as the Node SDK `@fastn-ai/sdk` 0.4.0. `from fastn.platform import FastnClient`.
  - 461 operations in 19 areas (`orgs`, `embed`, `connections`, `unified`, `events`, `workflows`, ...), generated from fastn's OpenAPI spec (`node/spec/openapi-v1.8.2.json`) by `scripts/generate_platform.py`; one method per operation in snake_case (`create_setup_link`) with the operationId as an alias (`createSetupLink`), typed inputs and outputs as `TypedDict`s under `fastn.platform.types`. Platform-administration routes are left out, as in Node.
  - Customer context: `fastn.customer(ref)` with `register`, `remove`, `connect(app)` (setup link by connector slug; widgets looked up once, inherited and inactive rows left out), `connect({...})` (direct OAuth), `connect_with_credentials`, `auth_fields`, `run_action`, `get`, `connections`, `setup_link`, `embed_token`, `records(category, entity)`, `links.get / cancel`, `customer.api.<area>` (fills `externalRef` / `endOrgId` where a route takes the customer in the body). Setup-link and event answers leave fastn's internal customer id out.
  - Typed calendar and CRM on a customer: `customer.calendar.free_slots / book / get / find / list / reschedule / cancel` and `customer.crm.contacts / notes / tasks / deals` (`create / get / find / list / update / delete`, `notes.add`, `tasks.add`, `deals.move_stage`, `deals.stages`). The provider is resolved from the customer's connected providers (404 `NO_CONNECTED_PROVIDER`, 404 `OPERATION_NOT_SUPPORTED`, 409 `PROVIDER_AMBIGUOUS`; `provider=` overrides), cached 60 s and forgotten on a provider or connection error. `datetime` / `date` values are sent as ISO strings; `notes.add` defaults `created_at` to now; an empty record id raises `TypeError` before any request. `free_intervals` and `slots_of` are exported.
  - The unified catalog: `fastn.catalog.categories / category / entity / fields / providers / refresh`; `customer.catalog.providers` reports the customer's own connections.
  - Transport: `x-api-key`, `x-end-org-ref` / `x-end-org-id`, `Idempotency-Key`, `X-Fastn-Correlation-Id`, `x-installation-id`, `x-fastn-target-org`, extra headers; user agent `fastn-python-sdk/<version>`; 60 s timeout; retries (default 2) for GET and for idempotent operations that carry an `idempotency_key`, on 429 (honouring `Retry-After`), 502, 503, 504 and network errors with backoff; `extra_body` / `extra_query`; `on_request` hook. Non-2xx raises `FastnApiError` (`status`, `code`, `details`, `method`, `path`, `request_id`, `body`, `is_not_found` / `is_conflict` / `is_rate_limited` / `is_auth` / `is_validation`); transport failures raise `FastnNetworkError`.
  - Events: `verify_event_signature`, `sign_event_body`, `parse_event` (drops `endOrgId` / `end_org_id` unless `internal_ids=True`), `read_event_headers`; `paginate` for `limit`/`offset` and cursor lists.
  - Tests: `tests/platform` (unit, with pytest-httpx) and `tests/platform/live` (run with `LIVE=1 FASTN_API_KEY=... FASTN_TEST_CUSTOMER=...`; production only with `LIVE_PROD=1`).
  - `customer.watch("hubspot", ["contact.created", "deal.stageChanged"], account_id=...)` turns on an app's change events for a customer (a `connector.event` and a `unified.event` per change on your webhook). Events are named in plain words (`EVENT_ALIASES`) or as the app names them; an unknown name raises 400 `EVENT_NOT_FOUND` with the valid list (`customer.watchable_events(app)`). The connector is found by slug and the customer's account on it by their connections (none: 404 `CONNECTION_NOT_FOUND`; several: 409 `CONNECTION_AMBIGUOUS`, pass `connection_id=`). `customer.watches(app=None)` lists (every page), `customer.unwatch(app_or_watch_id)` removes and answers the ids removed; a watch id that is not this customer's raises 404 `WATCH_NOT_FOUND`. Two plain names that map to one app event are sent once; a `connection_id` of another app raises 400 `CONNECTION_MISMATCH`. Answers carry the app's event ids and no internal customer id (the API's nested `appTrigger` part is flattened). HubSpot has no stage-only event: `deal.stageChanged` maps to `deal.propertyChange`, filter on `propertyName == "dealstage"` in the event.
  - `customer.disconnect(account_id)` and `customer.rename_account(account_id, name)` (the id must be one of this customer's accounts: 404 `CONNECTION_NOT_FOUND` otherwise, so one key serving every customer can never touch another customer by mistake), `customer.update({"name": ..., "status": ...})` and `customer.call_log(correlation_id)` (one entry per app call, no internal customer id), in place of the raw `delete_connections`, `update_connection`, `update_tenant` and `list_unified_calls` calls.
  - `fastn.webhooks`: `create`, `list`, `get`, `update`, `delete`, `test`, `rotate_secret`, `deliveries`, `replay`, answering the data directly.
- `find(filters, page_size=)` answers one page: the search route has no cursor, so a `cursor=` raises `TypeError` instead of being dropped (page with `list`). A naive `datetime` is read as the machine's local time, as Python does, and a date-time string with no zone the same way; a bare date is UTC midnight, as JavaScript reads it. `customer.remove()` puts the org back to active when the check after a failed delete hits a network error.
- No new runtime dependency (`httpx` only); Python 3.8+.

## [0.3.1] - 2026-02-26

### Added

- **Bundled type stubs**: 255 connector `.pyi` stubs ship in the wheel — `pip install fastn-ai` gives full IDE autocomplete with zero extra setup
- **Concurrent tool-schema fetching**: `fastn connector sync` fetches tool schemas for all connectors in parallel (10 workers)
- **`__getattr__` fallback stubs**: Connectors without tool schemas get a fallback stub so `fastn.<connector>.<anything>()` still works at runtime
- **`.gitattributes`**: Generated stubs collapse in GitHub PR diffs

### Changed

- `fastn connector sync` is now the single command that does everything: fetch registry, fetch tool schemas, save snapshot, generate stubs
- `fastn connector add` now described as "fetch full tool schemas" (stubs already bundled)
- Removed `_install_stubs_to_package()` — stubs ship in the wheel, no runtime copy needed
- Removed `generator/fetch_and_generate.py` — merged into `fastn connector sync`
- Updated all docs and templates to use canonical `fastn connector` commands

### Breaking Changes — Terminology

The SDK now uses the canonical Fastn architecture terminology:

**Connectors provide tools. Flows compose tools. Agents run flows and tools with reasoning.**

| Concept | Old term (v0.3.0) | New term (canonical) |
|---------|-------------------|---------------------|
| Service integration (Slack, Jira) | Tool | **Connector** |
| Callable function (send_message) | Action | **Tool** |

#### Renamed Classes
- `DynamicTool` → `DynamicConnector`
- `AsyncDynamicTool` → `AsyncDynamicConnector`
- `ToolNotFoundError` → `ConnectorNotFoundError` (connector not in registry)
- `ActionNotFoundError` → `ToolNotFoundError` (tool not found in connector)

#### Renamed Methods
- `fastn.tools.list()` → `fastn.connectors.list()`
- `fastn.tools.get(name)` → `fastn.connectors.get(name)`
- `fastn.get_actions(name)` → `fastn.get_tools(name)`
- `fastn.get_action(connector, tool)` → `fastn.get_tool(connector, tool)`
- `fastn.execute(action_id=...)` → `fastn.execute(tool=...)`
- `get_tools_for(..., tool=)` → `get_tools_for(..., connector=)`

#### Renamed CLI Flags
- `--tool` → `--connector` (scope to a connector)
- `--action` → `--tool` (scope to a tool)

#### Renamed Files
- `fastn/tool.py` → `fastn/connector.py`
- `tests/sdk/test_tool.py` → `tests/sdk/test_connector.py`

#### Renamed Config Functions
- `add_tool_to_manifest()` → `add_connector_to_manifest()`
- `remove_tool_from_manifest()` → `remove_connector_from_manifest()`
- `get_installed_tools()` → `get_installed_connectors()`

#### Migration Guide

```python
# Before (v0.3.0)
from fastn import ToolNotFoundError, ActionNotFoundError
tools = client.tools.list()
actions = client.get_actions("slack")
result = client.execute(action_id="send_message", params={...})
tools = client.get_tools_for("message", tool="slack", format="openai")

# After (canonical)
from fastn import ConnectorNotFoundError, ToolNotFoundError
connectors = client.connectors.list()
tools = client.get_tools("slack")
result = client.execute(tool="send_message", params={...})
tools = client.get_tools_for("message", connector="slack", format="openai")
```

## [0.3.0] - 2026-02-21

### Breaking Changes

- **Terminology refactor**: "Connector" is now "Tool", "Tool" (action) is now "Action" throughout the SDK
- **Namespace restructure**:
  - `fastn.admin.connectors.list()` → `fastn.tools.list()`
  - `fastn.admin.connectors.get(name)` → `fastn.tools.get(name)`
  - `fastn.get_tools(connector_name)` → `fastn.get_actions(tool_name)`
  - `fastn.get_tool(connector_name, tool_name)` → `fastn.get_action(tool_name, action_name)`
  - `fastn.connections.initiate()` → `fastn.auth.connect()`
  - `fastn.connections.status()` → `fastn.auth.status()`
  - `fastn.configure_custom_auth()` → `fastn.auth.configure_custom()`
  - `get_tools_for(..., connector="slack")` → `get_tools_for(..., tool="slack")`
- **Exception renames**:
  - `ConnectorNotFoundError` → `ToolNotFoundError` (with `.tool_name` attribute)
  - `ToolNotFoundError` → `ActionNotFoundError` (with `.tool_name` and `.action_name` attributes)
- **File rename**: `fastn/connector.py` → `fastn/tool.py`
  - `DynamicConnector` → `DynamicTool`
  - `AsyncDynamicConnector` → `AsyncDynamicTool`
- **CLI option rename**: `fastn agent --connector` → `fastn agent --tool`

### Added

- `fastn.auth.configure_custom(userinfo_url)` — register custom auth provider via GraphQL `updateResolverStep` mutation
- Comprehensive documentation with terminology glossary, full feature examples (flows, auth, multi-tenant)
- Platform benefits documentation (performance, governance, security, observability)

### Changed

- `auth.configure_custom()` now uses GraphQL `updateResolverStep` mutation instead of REST endpoint
- `_ToolsAdmin.get()` returns `"actions"` key instead of `"tools"` for consistency
- All user-facing CLI strings updated to use "tool" and "action" terminology
- All examples and documentation updated to match new API surface

## [0.2.3] - 2026-02-20

### Added

- `get_tools_for()` is now prompt-first: describe what you need in plain English and Fastn discovers the right tools
- `get_tools_for()` accepts `connector=` for direct registry lookup (single or list of connectors)
- `get_tools_for()` has a `limit` parameter (default 5) to control how many tools are returned
- "Platform Benefits" section in Python README documenting centralized gateway, monitoring, auth management

### Changed

- Root README LLM section now shows complete working code with all variables defined
- Python README LLM section rewritten with prompt-first examples for all 4 LLM providers
- LLM agent example updated to use prompt-first tool discovery

## [0.2.2] - 2026-02-20

### Fixed

- Default `tenant_id` changed from `"organization"` to `""` (empty) — backend handles defaults
- Updated tagline from "Pre-built tools" to accurate description of the integration platform

## [0.2.1] - 2026-02-20

### Changed

- Smart stub generation: only generates stubs for detected SDK languages (Python and/or TypeScript)
- Reorganized tests into `tests/sdk/` and `tests/cli/` for selective test runs
- Reorganized examples into `examples/sdk/` and `examples/cli/`
- Added pytest markers (`sdk`, `cli`) and Makefile for development workflow
- Updated documentation with AI-friendly API reference and LLM provider examples

## [0.2.0] - 2026-02-19

### Added

- `fastn agent` command: AI-powered agentic tool execution with native function calling
  - OpenAI function-calling integration with automatic tool discovery
  - Prompt-based tool routing via `getTools(prompt, limit)` — sends only top-N tools to LLM
  - Configurable tool limit (`--max-tools`, default 5) to reduce hallucination
  - Benchmark summary table with token counts, cost estimation ($), and timing
  - Error recovery with consecutive error tracking (`--max-errors`, default 2)
  - Evaluation mode (`--eval`) — LLM judge assesses if agent called correct tools
  - Confirmation gates for tool calls (default on, `-y` to skip)
  - LLM diagnosis on persistent failures with debug context dump
  - Schema unwrapping for LLM consumption, re-wrapping for API execution
- `fastn connector run` command for direct tool execution from CLI
  - Interactive parameter prompting when no args provided
  - Inline parameters via `--key value`
  - Tenant ID as positional argument: `fastn connector run slack send_message <tenant_id>`
- `--tenant` option on `fastn connector run` and `fastn agent` for multi-tenant testing
- `fastn connector ls --active` to show only enabled tools in project and org
- Generic error detection (`_detect_api_error`) for diverse API response formats
  - Handles Slack, GitHub, Stripe, GraphQL, generic REST, HTTP status codes in body
  - Preserves original error messages for LLM diagnosis
- Interactive LLM provider setup (OpenAI, Anthropic, Gemini) on first `fastn agent` run
- Project selection during `fastn login`
- CLI split into `cli/` package for maintainability

### Changed

- Registry sync fetches from three scopes: project, organization, community
- `fastn connector ls` groups connectors by source category
- Tenant header corrected to `x-fastn-space-tenantid`
- Tool schemas unwrapped for LLM (flat params) and re-wrapped for API execution

### Fixed

- Version alignment between pyproject.toml and __init__.py
- Error value preservation in API responses (Slack `channel_not_found` no longer overwritten)
- Agent summary table totals now include the final LLM response turn

## [0.1.0] - 2025-02-19

### Added

- `FastnClient` and `AsyncFastnClient` for sync and async workflows
- Dynamic connector proxy with attribute-based tool access (`fastn.slack.send_message()`)
- Multi-connection support via `connect()` and per-call `connection_id`
- LLM agent integration:
  - `get_tools_for(connector, format)` — returns tools in OpenAI, Anthropic, Gemini, Bedrock, or raw format
  - `execute(action_id, params)` — execute tools by action ID with LLM-generated parameters
- AI-powered mode via `run(prompt)` for natural language tool discovery
- Control plane: `admin.connectors.list()`, `admin.connectors.get()`, `get_tools()`, `get_tool()`
- Schema-aware migrations with deprecation warnings for smooth upgrades
- OAuth device authorization flow (`fastn login`) with automatic token refresh
- CLI commands: `init`, `login`, `logout`, `whoami`, `sync`, `add`, `remove`, `list`, `schema`, `version`
- IDE autocomplete via generated `.pyi` type stubs
- Automatic retry with exponential backoff for transient failures
- Config file security (owner-only permissions)
- PEP 561 `py.typed` marker for type checker support
- 9 typed exceptions for granular error handling
