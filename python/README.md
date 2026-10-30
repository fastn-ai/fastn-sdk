# fastn SDK for Python

**Embedded integrations for your product and your AI agents.**

[![PyPI version](https://img.shields.io/pypi/v/fastn-ai.svg)](https://pypi.org/project/fastn-ai/)
[![Python](https://img.shields.io/pypi/pyversions/fastn-ai.svg)](https://pypi.org/project/fastn-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

[fastn](https://fastn.ai) is the embedded integration platform for B2B SaaS. `fastn-ai` is its official Python SDK:
add customer-facing integrations (CRM, calendar, Slack, and 1,000+ more apps) to your product through one API, and give
your AI agents the same integrations as tools.

Your customers connect their own apps inside your product. Your backend uses those connections through the fastn
platform API (`fastn.platform`), and your AI agents use them as tools with OpenAI, Anthropic, Gemini, or Bedrock
function calling.

**Built for multi-tenant SaaS:**

- **One key, every customer.** Address each customer by your own id (`fastn.customer("acme-42")`); fastn's internal
  org ids never reach your code. Every call is scoped to that customer, and an account or watch id that belongs to
  another customer is refused, so one customer's data never leaks into another's.
- **Each customer brings their own accounts.** Send a setup link and the customer connects their HubSpot, Google
  Calendar, Slack, and so on. Credentials stay in fastn's vault, isolated per customer, and refresh automatically.
- **Several accounts per app.** A customer can connect two Slack workspaces or two calendars; pick one per call with
  `connection_id`.
- **One API across providers.** `customer.crm` and `customer.calendar` work the same whichever CRM or calendar the
  customer connected; the provider is picked from their connections.
- **Safe retries and traceability.** `idempotency_key` makes writes safe to retry, and `correlation_id` lets you ask
  later what fastn did for a request (`customer.call_log(...)`).
- **Governed.** Role-based access control, audit logs, and per-customer isolation on a SOC 2 Type II platform.

**Use fastn when:**

- your customers ask for integrations your team cannot build and maintain one by one;
- every customer needs the same integration connected to their own account and configured to their own fields;
- you want one integration to serve your product, your customers, and your AI agents;
- you need per-customer isolation, audit logs, and SOC 2 for a security review.

## Which client do I need?

The package ships two clients. They use different keys and endpoints, so pick by what you are building:

| You want to... | Use | Key |
|---|---|---|
| Give an LLM agent tools from 250+ connectors, call connector tools, run flows, use the `fastn` CLI | `from fastn import FastnClient` (this page, from [Installation](#installation) on) | Project API key or `fastn login` |
| Embed integrations for your own customers: register customers, send setup links, read and write their CRM / calendar through the unified API, receive webhooks | `from fastn.platform import FastnClient` (see [Platform API client](#platform-api-client-fastnplatform)) | Platform API key, `https://api.fastn.dev` |

## Embed fastn in your product (guide for Claude and other AI coding assistants)

The steps to add customer-facing integrations to a SaaS app with fastn. Use the exact names below; do not invent
props or endpoints.

1. **Install and get a key.** `pip install fastn-ai`, then create a platform API key in the
   [fastn dashboard](https://app.fastn.dev) and set it as `FASTN_API_KEY`.
2. **Register each of your customers by your own id** (backend):

   ```python
   import os
   from fastn.platform import FastnClient

   fastn = FastnClient(api_key=os.environ["FASTN_API_KEY"])
   customer = fastn.customer(account.id)          # your id for this customer
   customer.register({"name": account.name})      # idempotent
   ```

3. **Let the customer connect their apps.** Either send a hosted setup link, or show the embedded widget in your UI:

   ```python
   link = customer.connect("hubspot")             # hosted page: redirect the customer to link["url"]
   token = customer.embed_token()                 # or: a short-lived token for the in-app widget
   ```

   On the frontend, the widget is the [`@fastn-ai/embed`](https://www.npmjs.com/package/@fastn-ai/embed) package
   (`FastnProvider` with `FastnHub` or `FastnConnectCard` from `@fastn-ai/embed/react`, or the hosted script tag).
   Copy the exact snippet from the dashboard's Embed tab. See the [embedding docs](https://docs.fastn.ai/embed/embedding).
4. **Use the customer's connections** from your backend: `customer.crm.contacts.find(...)`,
   `customer.calendar.book(...)`, or `customer.run_action(app, action, input)` for any app action.
5. **React to changes**: `fastn.webhooks.create(...)` once for your account, `customer.watch(app, events)` per
   customer, and verify deliveries with `parse_event(secret, headers, body)`.
6. **Give your AI agents the same integrations**: use `get_tools_for()` below, or connect Claude, Cursor, or any MCP
   client to the [fastn MCP gateway](https://docs.fastn.ai/build/mcp-gateway).

Pricing is per customer connection, with a free plan to start: see [fastn.ai/pricing](https://fastn.ai/pricing).
A machine-readable summary of fastn for LLMs is at [fastn.ai/llms.txt](https://fastn.ai/llms.txt).

## Why fastn?

| Problem | fastn Solution |
|---------|---------------|
| Agents receive all tool schemas, burning tokens and increasing hallucination | `get_tools_for(prompt, limit=5)` returns only the most relevant tools: 250+ connectors, but only 5 reach the LLM |
| API schemas are deeply nested, wasting context on structure | SDK auto-unwraps schemas for LLMs and re-wraps for execution: flat params in, correct API structure out |
| Each SaaS API has its own OAuth flow, token refresh, and credential storage | Fully managed OAuth vault: acquisition, auto-refresh, tenant isolation. No token management code. |
| Security and compliance are afterthoughts in most agent tooling | SOC 2 Type II platform, role-based access control, audit trails |
| LLM agents need tool schemas in provider-specific formats | `get_tools_for("Send a Slack message", format="openai")` returns ready-to-use schemas for OpenAI, Anthropic, Gemini, Bedrock |
| Managing connections per customer in multi-tenant apps is complex | First-class `tenant_id` and `connection_id` support at every level |
| Building automation workflows requires stitching APIs together | `fastn.flows.generate("When a PR is opened, post to Slack")` builds the flow for you |

## Installation

```bash
pip install "fastn-ai[cli]"   # SDK + the fastn CLI (recommended)
pip install fastn-ai          # SDK only, no CLI
```

Requires Python 3.8+. The package includes type stubs for 250+ connectors, so IDE autocomplete works out of the box. The `fastn` command needs the `[cli]` extra.

## Quick Start

Log in once and add the connectors you want to call. This writes your credentials and the connector tool schemas to `.fastn/` in the current directory:

```bash
fastn login                  # opens the browser, then pick a project
fastn connector sync         # fetch the connector registry
fastn connector add slack    # fetch Slack's tool schemas
```

Then call the connector from Python:

```python
from fastn import FastnClient

fastn = FastnClient()        # reads .fastn/config.json
fastn.slack.send_message(channel="general", text="Hello from fastn!")
```

Calling a connector that has not been added raises `ConnectorNotFoundError`. On a server, pass `api_key=` and `project_id=` (or set `FASTN_API_KEY` and `FASTN_PROJECT_ID`) instead of `fastn login`. [`get_tools_for()`](#llm-agent-integration) needs no local registry.

Async:

```python
from fastn import AsyncFastnClient

async with AsyncFastnClient() as fastn:
    await fastn.slack.send_message(channel="general", text="Hello!")
```

## How It Works

fastn sits between your AI agent and the apps your customers connect. The SDK handles client-side concerns (tool discovery, schema transformation, parameter routing). The platform handles server-side concerns (credential injection, access control, batch optimization, prompt safety, observability).

> **One-liner:** Connectors provide tools. Flows compose tools. Agents run tools and flows with reasoning.

### Core Capabilities

| Capability | What It Does | Where It Runs |
|-----------|-------------|---------------|
| **Dynamic tool filtering** | Returns only tools that match the current prompt or intent | Platform |
| **Context optimization** | Composes tools/skills and filters schema I/O to minimize tokens and hallucination | Platform + SDK |
| **Schema transformer** | Flattens nested API schemas for LLMs, re-wraps for execution | SDK |
| **Intent routing** | Determines which tool to use based on agent request | Platform + SDK |
| **Managed OAuth** | Full token lifecycle: acquisition, refresh, revocation, tenant isolation | Platform |
| **Governed access** | RBAC, audit trails, and enterprise compliance controls (SOC 2 Type II) | Platform |
| **Batch optimizer** | Groups similar calls to reduce cost and time | Platform |
| **Prompt safety** | Blocks unsafe or injected tool commands | Platform |
| **Observability layer** | Tracks cost, latency, and errors per tool call | Platform + SDK CLI |

### Dynamic Tool Filtering

`get_tools_for(prompt)` sends a semantic search to the platform, which matches the prompt against the full connector registry and returns only the top N tools (default: 5). Sending a handful of tools instead of hundreds keeps the tool context small, and fewer tools also means fewer hallucinated tool calls.

```python
# Semantic discovery: only the most relevant tools reach the LLM
tools = fastn.get_tools_for("Send a Slack message", format="openai", limit=5)

# Direct lookup: bypass semantic search when you know the connector name
tools = fastn.get_tools_for("slack tools", connector="slack", format="openai")
```

### Context Optimization

fastn minimizes what reaches the LLM: fewer tokens, less hallucination, better compliance.

- **Tool and skill composition**: the platform composes tools and skills into efficient chains, so agents receive focused context instead of raw API surface area
- **Schema I/O filtering**: strips unnecessary fields from tool input and output schemas before they reach the LLM, reducing token cost
- **Schema transformation**: the SDK flattens nested API wrappers (`body`, `param`) for the LLM and re-wraps them for execution:

```
What the API expects:   {"body": {"channel": "#general", "text": "hello"}}
What the LLM sees:      {"channel": "#general", "text": "hello"}
```

Combined with [Dynamic Tool Filtering](#dynamic-tool-filtering), the agent gets a focused payload instead of the full API surface.

### Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Your Agent                                                             │
│                                                                         │
│  1. Discovery                                                           │
│     get_tools_for(prompt) ──→ SDK ──→ POST /getTools ──→ Platform       │
│     Platform: dynamic tool filtering, intent routing                    │
│                              ←── top N tools (unwrapped schemas) ←──    │
│                                                                         │
│  2. LLM Call                                                            │
│     SDK: format schemas for provider (OpenAI / Claude / Gemini / etc.)  │
│     Send prompt + N tool schemas to LLM                                 │
│     LLM returns tool_call with flat params                              │
│                                                                         │
│  3. Execution                                                           │
│     execute(tool, params) ──→ SDK (re-wrap params) ──→ Platform         │
│     Platform: credential injection, RBAC, prompt safety, batch opt.     │
│                               ←── result ←──                            │
│                                                                         │
│  4. Observability                                                       │
│     Platform: audit trail, cost/latency/error tracking per tool         │
│     SDK CLI: per-call cost, latency, and token summary table            │
└─────────────────────────────────────────────────────────────────────────┘
```

## Terminology

| Term | Definition | Example |
|------|-----------|---------|
| **Connector** | An adapter to an external service. Provides tools. | Slack, Jira, GitHub, Salesforce |
| **Tool** | A callable action within a connector, exposed to agents/LLMs. The callable unit in MCP. | `slack.send_message`, `jira.create_issue` |
| **Flow** | Orchestration of multiple tools with logic, branching, retries, scheduling. | "When a Jira ticket is created, post to Slack" |
| **Connection** | An authenticated link between a connector and a specific account. | OAuth connection to a Slack workspace |
| **Tenant** | One of your customers (an organization or team) in a multi-tenant app. The platform API calls this a *customer*. | `tenant_id: "acme-corp"` |
| **Skill** | A reusable agent configuration stored in a project. | `fastn.skills.list()` |
| **Agent** | A goal-driven executor that calls tools/flows with reasoning. | `fastn agent "Send hello to Slack"` |
| **Project** | A container that groups connectors, flows, and tenants. | `project_id: "proj_xyz"` |
| **Stage** | An environment for isolating dev/staging/production data. | `"LIVE"`, `"STAGING"`, `"DEV"` |

## SDKs

| Package | What It Does | Language | Status |
|---------|-------------|----------|--------|
| [`fastn-ai`](https://pypi.org/project/fastn-ai/) | Backend SDK: tool discovery and execution for agents, flows, CLI, and the platform API client (`fastn.platform`) | Python | Available |
| [`@fastn-ai/sdk`](https://www.npmjs.com/package/@fastn-ai/sdk) | Backend SDK: the platform API client (same surface as `fastn.platform`) and workspace tool calls. No CLI, flows, or `get_tools_for` | TypeScript | Available |
| [`@fastn-ai/embed`](https://www.npmjs.com/package/@fastn-ai/embed) | Frontend widget: lets your end users connect their apps (OAuth and connector config) inside your product | JavaScript / React | Available |

## Configuration

Credentials are loaded from three sources (highest priority first):

1. **Constructor parameters**: `FastnClient(api_key="...", project_id="...")`
2. **Environment variables**: `FASTN_API_KEY`, `FASTN_PROJECT_ID`
3. **Config file**: `.fastn/config.json` (created by `fastn login`)

```python
# Explicit credentials (no config file needed)
fastn = FastnClient(api_key="your-api-key", project_id="your-project-id")
```

| Variable | Description |
|----------|-------------|
| `FASTN_API_KEY` | API key |
| `FASTN_PROJECT_ID` | Project ID |
| `FASTN_AUTH_TOKEN` | JWT from `fastn login` |
| `FASTN_TENANT_ID` | Default tenant ID |
| `FASTN_STAGE` | Environment: `LIVE`, `STAGING`, or `DEV` |

## LLM Agent Integration

fastn handles the three hardest parts of giving LLMs access to tools:

1. **Discovery**: `get_tools_for(prompt)` semantically matches tools from 250+ connectors. Only the top N reach the LLM, keeping context small and hallucination low.
2. **Schema translation**: schemas are flattened for LLM consumption and formatted for your provider (OpenAI, Anthropic, Gemini, Bedrock).
3. **Execution**: `execute(tool, params)` routes through the platform, which handles credential injection, parameter re-wrapping, retries, and logging.

```python
import json
import openai
from fastn import FastnClient

fastn = FastnClient()

# 1. Describe what you need and fastn discovers the right tools
tools = fastn.get_tools_for(
    "Send a message on Slack and create a Jira ticket",
    format="openai",   # also: anthropic, gemini, bedrock, raw
)

# 2. Send tools + user prompt to the LLM
response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Send hello to #general on Slack"}],
    tools=tools,
)

# 3. The LLM returns a tool_call when it wants to use a tool
tool_call = response.choices[0].message.tool_calls[0]

# 4. Execute the tool call through fastn
result = fastn.execute(
    tool=tool_call.function.name,                      # e.g. "send_message"
    params=json.loads(tool_call.function.arguments),    # e.g. {"channel": "general", "text": "hello"}
)
print(result)
```

### Supported LLM Providers

| Format | Provider | Example |
|--------|----------|---------|
| `"openai"` | OpenAI, Azure OpenAI | `get_tools_for("Send a Slack message", format="openai")` |
| `"anthropic"` | Anthropic Claude | `get_tools_for("Create a Jira issue", format="anthropic")` |
| `"gemini"` | Google Gemini / Vertex AI | `get_tools_for("List GitHub repos", format="gemini")` |
| `"bedrock"` | AWS Bedrock Converse API | `get_tools_for("Send an email", format="bedrock")` |
| `"raw"` | Any (raw fastn schemas) | `get_tools_for("Notify team", format="raw")` |

### Anthropic Claude Example

```python
import anthropic
from fastn import FastnClient

fastn = FastnClient()
tools = fastn.get_tools_for("Send a message on Slack", format="anthropic")

client = anthropic.Anthropic()
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    messages=[{"role": "user", "content": "Send 'Build passed' to #ci"}],
    tools=tools,
)

for block in response.content:
    if block.type == "tool_use":
        result = fastn.execute(tool=block.name, params=block.input)
        print(result)
```

### Google Gemini Example

```python
from google import genai
from fastn import FastnClient

fastn = FastnClient()
tools = fastn.get_tools_for("Send a Slack message", format="gemini", limit=10)

client = genai.Client()
response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="Send a greeting to #general on Slack",
    # format="gemini" returns function declarations; wrap them in a Tool
    config=genai.types.GenerateContentConfig(
        tools=[genai.types.Tool(function_declarations=tools)],
    ),
)

for part in response.candidates[0].content.parts:
    if fn := part.function_call:
        result = fastn.execute(tool=fn.name, params=dict(fn.args))
        print(result)
```

### AWS Bedrock Example

```python
import boto3
from fastn import FastnClient

fastn = FastnClient()
tools = fastn.get_tools_for("Notify the team on Slack", format="bedrock")

bedrock = boto3.client("bedrock-runtime")
response = bedrock.converse(
    modelId="anthropic.claude-sonnet-4-20250514-v1:0",
    messages=[{"role": "user", "content": [{"text": "Notify #ops that deploy is done"}]}],
    toolConfig={"tools": tools},
)

for block in response["output"]["message"]["content"]:
    if "toolUse" in block:
        tool_use = block["toolUse"]
        result = fastn.execute(tool=tool_use["name"], params=tool_use["input"])
        print(result)
```

### Using Connector Names Directly

For local registry lookup without an API call, pass connector names:

```python
# Single connector
tools = fastn.get_tools_for("slack tools", connector="slack", format="openai")

# Multiple connectors: limit applies to the total across all
tools = fastn.get_tools_for(
    "project tools",
    connector=["slack", "jira", "github"],
    format="openai",
    limit=10,
)
```

## Connector Catalog

Inspect the connector registry programmatically:

```python
# List all connectors in the registry
connectors = fastn.connectors.list()
for c in connectors:
    print(f"{c['name']}: {c['tool_count']} tools")

# Get details for a specific connector
slack = fastn.connectors.get("slack")
print(slack["tools"])

# List all tools in a connector with full schemas
tools = fastn.get_tools("slack")
for t in tools:
    print(f"  {t['name']}: {t['description']}")

# Get a single tool's schema
tool = fastn.get_tool("slack", "send_message")
print(tool["inputSchema"])
```

## Flows

Flows (called *workflows* in the fastn dashboard) chain tools across connectors. Describe one in plain English and the flow builder agent generates it; then deploy it and run it by name.

```python
import uuid

# Generate a flow with the flow builder agent. It is a conversation: reuse the
# session id to answer its follow-up questions.
session = str(uuid.uuid4())
reply = fastn.flows.generate(
    "When a Jira ticket is created, post a summary to #engineering on Slack",
    session_id=session,
)
print(reply)  # the agent's answer: the flow it built, or questions for you
fastn.flows.generate("Use the ENG project and the #engineering channel", session_id=session)

# List flows (status filter is case-insensitive: "DEPLOYED", "DRAFT", ...)
flows = fastn.flows.list()
deployed = fastn.flows.list(status="DEPLOYED")

# Inspect a flow and the input it expects
flow = fastn.flows.get("jira_to_slack")
schema = fastn.flows.schema("jira_to_slack")   # {"fields": [...], "schema": {...}}

# Deploy, then run by flow name
fastn.flows.deploy("jira_to_slack", stage="LIVE", comment="first release")
result = fastn.flows.run("jira_to_slack", input_data={"ticket": "ENG-42"}, stage="LIVE")

# Update the schedule or enable/disable (by flow id), and delete
flow_id = flows[0]["flow_id"]
fastn.flows.update(flow_id, schedule="0 9 * * MON-FRI", enabled=True)
fastn.flows.delete(flow_id)          # also accepts a flow name
```

## Authentication

fastn supports three authentication types at different levels. The SDK triggers connectors and flows; the platform manages OAuth token refresh and credential injection.

| Auth Type | Who Authenticates | To What | How | Expiry |
|-----------|------------------|---------|-----|--------|
| **API Key** | Your app | fastn platform | `x-fastn-api-key` header | Never |
| **OAuth Token** | You (developer) | fastn platform | `Authorization: Bearer` JWT | Auto-refreshed |
| **Connection** | Your end-users | External services (Slack, Jira...) | OAuth vault + `connection_id` | Platform-managed |

### 1. API Key: App-to-Platform

Static credential that authenticates your application to the fastn platform. Create it in the [fastn dashboard](https://app.fastn.dev); it does not expire.

```
Your App                          fastn Platform
  │                                     │
  │  POST /executeTool                  │
  │  x-fastn-api-key: sk_live_xxx      │
  │  x-fastn-space-id: proj_abc        │
  │ ──────────────────────────────────→ │
  │                                     │  Validate API key
  │                                     │  Resolve project
  │              200 OK + result        │
  │ ←────────────────────────────────── │
```

```python
fastn = FastnClient(api_key="sk_live_xxx", project_id="proj_abc")
# or: export FASTN_API_KEY=sk_live_xxx
```

### 2. OAuth Token: Developer-to-Platform

JWT obtained via browser-based login (RFC 8628 Device Authorization Grant). Used by the CLI and dashboard. Auto-refreshed with a 30-second expiry buffer.

```
Developer          Browser            fastn (Keycloak)
  │                   │                      │
  │  fastn login      │                      │
  │ ──────────────────────────────────────→  │
  │                   │    device_code +      │
  │  ←───────────────────  user_code         │
  │                   │                      │
  │  "Visit URL,      │                      │
  │   enter code"     │                      │
  │ ────────────────→ │                      │
  │                   │  User logs in +      │
  │                   │  enters code         │
  │                   │ ──────────────────→  │
  │                   │      authorized      │
  │                   │ ←──────────────────  │
  │                   │                      │
  │  Poll for token   │                      │
  │ ──────────────────────────────────────→  │
  │       access_token + refresh_token       │
  │ ←──────────────────────────────────────  │
  │                                          │
  │  (saved to .fastn/config.json)           │
  │                                          │
  │  POST /executeTool                       │
  │  Authorization: Bearer <jwt>             │
  │ ──────────────────────────────────────→  │
  │                                          │
  │  (on expiry: auto-refresh with 30s       │
  │   buffer using refresh_token)            │
```

```python
# CLI handles this automatically:
# $ fastn login
# Tokens stored in .fastn/config.json (0o600 permissions)
fastn = FastnClient()  # Picks up auth_token from config
```

### 3. Connection: End-User-to-External-Service

OAuth connections that link your end-users to external services (Slack, GitHub, etc.) through the fastn OAuth vault. Tokens are stored server-side, auto-refreshed by the platform, and isolated per tenant. Your code never sees raw credentials.

The [`@fastn-ai/embed`](https://www.npmjs.com/package/@fastn-ai/embed) widget captures auth and connector config on the frontend. This SDK triggers connectors and flows on the backend; pass `connection_id` to route to the right account.

```
Your App (backend)       Frontend (embed widget)      fastn Platform         External Service
  │                           │                         │                       │
  │  auth.connect(            │                         │                       │
  │    connector="slack"      │                         │                       │
  │    tenant="acme")         │                         │                       │
  │ ───────────────────────────────────────────────→    │                       │
  │                           │                         │                       │
  │  { connection_id,         │                         │                       │
  │    auth_url }             │                         │                       │
  │ ←───────────────────────────────────────────────    │                       │
  │                           │                         │                       │
  │  Pass auth_url to         │                         │                       │
  │  frontend ──────────────→ │                         │                       │
  │                           │  Render login /         │                       │
  │                           │  redirect user          │                       │
  │                           │ ────────────────────────────────────────────→   │
  │                           │                         │    User authorizes    │
  │                           │                         │ ←─────────────────    │
  │                           │  Callback received      │  Store tokens in      │
  │                           │ ←───────────────────    │  OAuth vault          │
  │                           │                         │                       │
  │  auth.status(             │                         │                       │
  │    connection_id)         │                         │                       │
  │ ───────────────────────────────────────────────→    │                       │
  │  { status: "authorized" } │                         │                       │
  │ ←───────────────────────────────────────────────    │                       │
  │                           │                         │                       │
  │  execute(tool,            │                         │                       │
  │    connection_id)         │                         │                       │
  │ ───────────────────────────────────────────────→    │                       │
  │                           │                         │  Inject credentials   │
  │                           │                         │ ──────────────────→   │
  │                           │                         │       result          │
  │                           │                         │ ←──────────────────   │
  │       result              │                         │                       │
  │ ←───────────────────────────────────────────────    │                       │
  │                           │                         │                       │
  │  (on token expiry: platform auto-refreshes)         │                       │
```

```python
# 1. Start an OAuth connection for your end-user
result = fastn.auth.connect(
    connector="slack",
    tenant_id="customer_acme",
    redirect_url="https://myapp.com/callback",
)
# Send the user to result["auth_url"] (or let the embed widget handle it)

# 2. Check connection status (after user completes auth)
status = fastn.auth.status(connection_id=result["connection_id"])
print(status["status"])  # "pending", "authorized", "expired"

# Or look up by connector + tenant
status = fastn.auth.status(connector="github", tenant_id="customer_acme")

# 3. Use the connection: the platform injects the credentials
fastn.slack.send_message(
    connection_id=result["connection_id"],
    channel="general", text="Hello!",
)
```

### Custom Auth Provider

For apps with their own identity provider, configure fastn to validate end-user tokens via your userinfo endpoint.

```python
fastn.auth.configure_custom(
    userinfo_url="https://myapp.auth0.com/userinfo",
)
```

## Multi-Connection Support

When you have multiple connections for the same connector (e.g. two Slack workspaces):

```python
# Per-call
fastn.slack.send_message(connection_id="conn_workspace_a", channel="general", text="Hi!")

# Or bind once
slack_a = fastn.connect("conn_workspace_a")
slack_a.send_message(channel="general", text="Hello!")
```

## Multi-Tenant Support

Route requests to the correct tenant (customer, organization, or team):

```python
# Per-call override
fastn.slack.send_message(tenant_id="acme", channel="general", text="Hello!")

# Constructor-level default
fastn = FastnClient(tenant_id="acme")

# Environment variable
# export FASTN_TENANT_ID=acme

# CLI flag
# fastn connector run slack send_message --tenant acme --channel general --text "Hello!"
```

**Priority:** per-call `tenant_id` > CLI `--tenant` flag > constructor param > `FASTN_TENANT_ID` env var > config file

## Environments

Switch between `LIVE`, `STAGING`, and `DEV`:

```python
dev = FastnClient(stage="DEV")
staging = FastnClient(stage="STAGING")
prod = FastnClient()  # defaults to LIVE
```

Or: `export FASTN_STAGE=DEV`

## AI-Powered Mode

For quick prototyping, use natural language:

```python
result = fastn.run("Send hello to #general on Slack")
```

## Projects

List available projects for the authenticated user:

```python
projects = fastn.projects.list()
for p in projects:
    print(f"{p['name']} ({p['id']})")
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `fastn login` | Authenticate with Fastn and select a project |
| `fastn logout` | Log out and clear saved credentials |
| `fastn whoami` | Show the current logged-in user |
| `fastn connector ls` | List all available connectors (`--active`, `--installed` to filter) |
| `fastn connector ls <name>` | Show tools for a specific connector |
| `fastn connector sync` | Refresh connector registry, fetch tool schemas, regenerate type stubs |
| `fastn connector add <name> [...]` | Fetch full tool schemas for specific connectors |
| `fastn connector remove <name>` | Remove connector stubs |
| `fastn connector run <name> <tool>` | Execute a connector tool |
| `fastn connector schema <name> <tool>` | Print a tool's input/output schema |
| `fastn flow ls [--status deployed]` | List flows |
| `fastn flow generate` | Generate a flow from a plain-English prompt (interactive) |
| `fastn flow run <flow_name>` | Run a flow |
| `fastn flow deploy <flow_name>` | Deploy a flow to `DRAFT` or `LIVE` |
| `fastn flow schema <flow_name>` | Show a flow's input/output schema |
| `fastn flow update <flow_id>` / `fastn flow delete <flow_id>` | Update or delete a flow |
| `fastn kit ls` / `fastn kit get <name>` / `fastn kit config` | Connect Kit connectors and settings |
| `fastn skill` | List available agent skills |
| `fastn agent "<prompt>"` | Describe a task in plain English; the agent calls the right tools |
| `fastn version` | Show SDK and registry versions |

### `fastn agent`

Agentic CLI: describe what you want in natural language and the agent discovers tools, sends them to your LLM via native function calling, and executes tool calls in a loop until the task is complete.

```bash
fastn agent "Send hello to #general on Slack"
fastn agent --connector slack "List all channels"
fastn agent --eval "Create a Jira ticket for the login bug"
```

The first run asks you to pick an LLM provider and enter its API key (saved to `.fastn/config.json`).

| Option | Default | Description |
|--------|---------|-------------|
| `--connector` | -- | Scope tool discovery to a specific connector |
| `--tool` | -- | Scope discovery to a specific tool |
| `--max-turns` | `10` | Maximum agentic loop iterations |
| `--max-tools` | `5` | Maximum number of tools passed to the LLM |
| `--max-errors` | `2` | Stop after this many consecutive tool errors |
| `-y` / `--yes` | off | Skip confirmation prompts before each tool call |
| `--eval` | off | Run LLM-based evaluation after the agent finishes |
| `--connection-id` | -- | Connection ID for multi-connection connectors |
| `--tenant` | -- | Tenant ID override |
| `--model` | -- | Override the LLM model (e.g. `gpt-4o-mini`) |
| `--setup` | off | Re-run the LLM provider/model setup |

### `fastn connector run`

Execute connector tools directly from the command line:

```bash
# List available tools
fastn connector run slack

# Interactive mode (prompts for each parameter)
fastn connector run slack send_message

# Inline parameters
fastn connector run slack send_message --channel general --text "Hello!"

# With tenant override (or pass the tenant as a third positional argument)
fastn connector run slack send_message --tenant acme --channel general --text "Hello!"
```

## API Reference

### `FastnClient`

```python
FastnClient(
    api_key: str = None,        # fastn API key (or FASTN_API_KEY)
    project_id: str = None,     # Project ID (or FASTN_PROJECT_ID)
    auth_token: str = None,     # JWT from fastn login (or FASTN_AUTH_TOKEN)
    tenant_id: str = None,      # Tenant ID (or FASTN_TENANT_ID)
    stage: str = None,          # "LIVE", "STAGING", "DEV" (or FASTN_STAGE)
    agent_id: str = None,       # Agent ID, for agent-scoped calls
    config_path: str = None,    # Path to config.json
    timeout: float = None,      # HTTP timeout in seconds (default from config, else 30)
    max_retries: int = 3,       # Retry count for transient failures
    verbose: bool = False,      # Debug logging
)
```

**Data Plane (tool execution):**

| Method | Description |
|--------|-------------|
| `fastn.<connector>.<tool>(**params)` | Execute a tool on a connector |
| `fastn.connect(connection_id)` | Bind a connection, return a proxy |
| `fastn.execute(tool, params, ...)` | Execute by tool name (for LLM agents) |
| `fastn.run(prompt)` | AI-powered tool discovery and execution |

**Control Plane (discovery):**

| Method | Description |
|--------|-------------|
| `fastn.connectors.list()` | List all connectors in the registry |
| `fastn.connectors.get(connector_name)` | Get connector details (name, category, tools) |
| `fastn.get_tools(connector_name)` | List all tools for a connector with schemas |
| `fastn.get_tool(connector_name, tool_name)` | Get one tool's schema |
| `fastn.get_tools_for(prompt, format, limit, connector)` | Discover tools by prompt or connector name in LLM format |

**Flows:**

| Method | Description |
|--------|-------------|
| `fastn.flows.generate(prompt, session_id=None)` | Generate a flow with the flow builder agent (`create` is an alias) |
| `fastn.flows.list(status=None)` | List flows (optional, case-insensitive status filter) |
| `fastn.flows.get(flow_name)` | Full flow definition |
| `fastn.flows.schema(flow_name)` | Input fields the flow expects |
| `fastn.flows.deploy(flow_name, stage="LIVE", comment="")` | Deploy to `DRAFT` or `LIVE` |
| `fastn.flows.run(flow_name, input_data=None, stage=None)` | Run a flow |
| `fastn.flows.get_run(run_id)` | Check run status and results |
| `fastn.flows.update(flow_id, prompt=, schedule=, enabled=, answers=)` | Update schedule, enable/disable |
| `fastn.flows.delete(flow_id)` | Delete a flow |

**Auth:**

| Method | Description |
|--------|-------------|
| `fastn.auth.connect(connector, tenant_id, redirect_url)` | Start OAuth connection flow |
| `fastn.auth.status(connection_id=None, connector=None, tenant_id=None)` | Check connection status |
| `fastn.auth.configure_custom(userinfo_url)` | Register custom auth provider |

**Skills:**

| Method | Description |
|--------|-------------|
| `fastn.skills.list()` | List agent skills in the current project |

**Projects:**

| Method | Description |
|--------|-------------|
| `fastn.projects.list()` | List available projects |

**Connect Kit:**

| Method | Description |
|--------|-------------|
| `fastn.kit.get()` | Connect Kit configuration for the project |
| `fastn.kit.update(settings)` | Update the configuration |
| `fastn.kit.list(query="", limit=8, offset=0)` | List Connect Kit connectors |
| `fastn.kit.get_connector(connector_id)` | One connector's details |

Requests are retried on transient failures (`max_retries`, default 3, with exponential backoff).

### `AsyncFastnClient`

Same API as `FastnClient`, but all methods are `async`/`await`:

```python
async with AsyncFastnClient() as fastn:
    result = await fastn.slack.send_message(channel="general", text="Hi")
    flows = await fastn.flows.list()
    skills = await fastn.skills.list()
    status = await fastn.auth.status(connection_id="conn_abc")
```

## Error Handling

All exceptions inherit from `FastnError`:

```python
from fastn import (
    FastnClient, FastnError, AuthError, ConfigError, APIError,
    ConnectorNotFoundError, ToolNotFoundError, ConnectionNotFoundError,
    OAuthError, RegistryError, FlowNotFoundError, RunNotFoundError,
)

try:
    fastn.slack.send_message(channel="general", text="Hello!")
except AuthError:
    print("Invalid credentials: check your API key")
except ConnectorNotFoundError as e:
    print(f"Connector '{e.connector_name}' not found: run fastn connector add {e.connector_name}")
except ToolNotFoundError as e:
    print(f"Tool '{e.tool_name}' not found in '{e.connector_name}'")
except APIError as e:
    print(f"HTTP {e.status_code}: {e}")
except ConfigError:
    print("Run: fastn login")
```

| Exception | When | Key Attributes |
|-----------|------|----------------|
| `FastnError` | Base class for all SDK errors | `.message`, `.details` |
| `AuthError` | Invalid or expired credentials | -- |
| `ConfigError` | Missing API key or project ID | -- |
| `APIError` | HTTP error from the Fastn API | `.status_code`, `.response_body` |
| `ConnectorNotFoundError` | Connector not in registry | `.connector_name` |
| `ToolNotFoundError` | Tool not found in connector | `.connector_name`, `.tool_name` |
| `ConnectionNotFoundError` | Connection ID not recognized | -- |
| `FlowNotFoundError` | Flow not found | `.flow_id` |
| `RunNotFoundError` | Run not found | `.run_id` |
| `OAuthError` | OAuth flow failed | `.error_code` |
| `RegistryError` | Registry sync or parse failure | -- |

## IDE Autocomplete

Type stubs for the client and 250+ connectors ship in the package, so autocomplete works after `pip install fastn-ai`:

- **PyCharm / IntelliJ**: Works automatically
- **VS Code (Pylance)**: Works automatically
- **mypy**: Works automatically (PEP 561 `py.typed` marker included)

To refresh stubs with the latest connector schemas, run `fastn connector sync`.

## Examples

Runnable scripts are in the [repository](https://github.com/fastn-ai/fastn-sdk/tree/main/python/examples):

| File | Contents |
|------|----------|
| [`examples/sdk/connectors.py`](https://github.com/fastn-ai/fastn-sdk/blob/main/python/examples/sdk/connectors.py) | Calling connector tools, catalog, multi-connection, multi-tenant |
| [`examples/sdk/agents.py`](https://github.com/fastn-ai/fastn-sdk/blob/main/python/examples/sdk/agents.py) | LLM agents with `get_tools_for` and `execute` |
| [`examples/sdk/flows.py`](https://github.com/fastn-ai/fastn-sdk/blob/main/python/examples/sdk/flows.py) | Generating, listing, and running flows |
| [`examples/cli/cli_commands.sh`](https://github.com/fastn-ai/fastn-sdk/blob/main/python/examples/cli/cli_commands.sh) | Every CLI command with examples |

## Platform API client (`fastn.platform`)

The fastn platform REST API for Python: every endpoint, generated from fastn's OpenAPI spec, plus a small hand-written
layer that makes the common partner flow easy. It mirrors the platform client in the Node SDK (`@fastn-ai/sdk`):
every operation is a snake_case method on its area (`fastn.embed.create_setup_link`) with the operationId as an alias
(`createSetupLink`); per-call options are keyword arguments. The Node SDK's workspace tool calls (`ToolsClient`,
`fastn-sdk-tools`) are Node-only.

This is a different `FastnClient` from `fastn.FastnClient` above: it takes a platform API key from the
[fastn dashboard](https://app.fastn.dev) and talks to `https://api.fastn.dev`. It is synchronous.

```python
import os
from fastn.platform import FastnClient

fastn = FastnClient(
    api_key=os.environ["FASTN_API_KEY"],
    # base_url="https://api.fastn.dev", timeout=60.0, retries=2,
    # on_request=lambda log: print(log), defaults={...}
)

# 1. Register a customer under your account, using YOUR id for them.
customer = fastn.customer("acme-42")
customer.register({"name": "Acme Dental"})                        # idempotent: returns the existing org on repeat

# 2. Give them a link to connect their tools (Google Calendar, HubSpot, ...), by connector slug.
link = customer.connect("googleCalendar")
print(link["url"])                                                # send this to the customer

# 3. Typed methods on whatever the customer connected: the provider is picked from their connections.
booked = customer.calendar.book(
    {"title": "Intro call", "start_time": "2026-11-03T15:00:00Z", "end_time": "2026-11-03T15:30:00Z", "timezone": "Europe/London", "attendee_email": "jane@example.com"},
    idempotency_key="booking-123", correlation_id="req-abc",      # safe to retry; traceable later
)
print(booked["id"], booked["provider"], booked["data"].get("web_url"))

customer.calendar.reschedule(booked["id"], {"start_time": "2026-11-03T16:00:00Z", "end_time": "2026-11-03T16:30:00Z"})
customer.calendar.cancel(booked["id"], idempotency_key="cancel-123")

page = customer.crm.contacts.find({"email": "jane@example.com"})  # one page (the search route has no cursor); list() pages
contact = page["records"][0] if page["records"] else customer.crm.contacts.create({"first_name": "Jane", "last_name": "Doe", "email": "jane@example.com"})
customer.crm.notes.add({"body": "Booked an intro call", "parent_id": contact["id"], "parent_type": "contact"})

# 4. What did fastn do for my request id?
customer.call_log("req-abc")

# Changes at an app, sent to your webhook as connector.event / unified.event: watch them per customer.
account_id = "..."                                                # one of the customer's accounts, from customer.connections()
w = customer.watch("hubspot", ["contact.created", "deal.stageChanged"], account_id=account_id)
customer.watches("hubspot")                                       # [{"id", "app", "events", "status", ...}]
customer.unwatch("hubspot")                                       # or unwatch(w["id"])

customer.disconnect(account_id)                                   # the customer gets connection.revoked
customer.rename_account(account_id, "Front desk calendar")
customer.update({"name": "Acme Dental Ltd"})                      # or {"status": "suspended"}

# Your webhook, once for the whole account.
hook = fastn.webhooks.create({"url": "https://app.acme.com/fastn", "eventTypes": ["connection.connected", "setup_link.completed", "connector.event", "unified.event"]})
hook["secret"]                                                    # shown once: the signing secret for parse_event
fastn.webhooks.test(hook["id"]); fastn.webhooks.deliveries(hook["id"]); fastn.webhooks.rotate_secret(hook["id"])
```

### Calendar and CRM, typed

`customer.calendar` and `customer.crm` are the unified API with the fields named (the catalog's own names,
`start_time`, `first_name`, ...; `datetime` values are sent as ISO strings). Answers are `{"id", "provider", "data",
"warnings"?}` records or `{"records", "nextCursor", "hasMore"}` pages. The provider is the one the customer has
connected for that entity: no connected provider raises 404 `NO_CONNECTED_PROVIDER` (send them a setup link), several
raise 409 `PROVIDER_AMBIGUOUS` (pass `provider=`). `warnings` lists fields the provider does not map and therefore
dropped. Every method also takes `provider=`, `connection_id=`, `idempotency_key=`, `correlation_id=`, ...

| Method | Underneath |
| --- | --- |
| `calendar.free_slots({"start_time", "end_time", "timezone"?, "slot_minutes"?})` | scheduling/availability; answers `busy`, `free`, and `slots` of that length |
| `calendar.book(meeting)`, `get(id)`, `find(filters)`, `list(page_size=, cursor=)`, `reschedule(id, {"start_time", "end_time"})`, `cancel(id)` | scheduling/meeting |
| `crm.contacts.create / get / find({"email", "phone", "first_name", "last_name"}) / list / update / delete` | crm/contact |
| `crm.notes.add({"body", "parent_id", "parent_type"})`, `create`, `get`, `find`, `list`, `update`, `delete` | crm/note (`created_at` defaults to now) |
| `crm.tasks.add({"subject", "due_date", "status", ...})`, `create`, `get`, `find`, `list`, `update`, `delete` | crm/task |
| `crm.deals.create({"name", "amount", "stage", ...})`, `get`, `find`, `list`, `update`, `move_stage(id, stage)`, `delete`, `stages()` | crm/opportunity, crm/stage |

`find(filters, page_size=)` answers one page (the search route has no cursor); `list(page_size=, cursor=)` pages.
What the typed methods do not cover is still one call away: `customer.records("crm", "contact", provider="hubspot")`
takes any entity in the catalog with untyped input (`create`, `get`, `list`, `update`, `delete`, plus `search(filters)`
and `providers()`), and `customer.run_action(connector, action, input)` runs a connector's own action.

```python
# The catalog: which categories and entities exist, the fields each takes, which providers a customer connected.
categories = fastn.catalog.categories()                 # [{"slug": "crm", "entities": [...]}]
fields = fastn.catalog.fields("crm", "contact")         # [{"field": "email", "type": "string", "required": False}, ...]
providers = customer.catalog.providers("crm", "contact")  # [{"connectorSlug": "hubspot", "connected": True, ...}]

# Anything the unified API does not cover: the connector's own action with the customer's connection.
r = customer.run_action("hubspot", "updateDeal", {"dealId": deal_id, "properties": {"dealstage": "qualifiedtobuy"}})
```

Every area is on the client directly, with typed inputs. The partner flow lives in `orgs`, `embed`, `connections`,
`unified`, `events` and `workflows`; platform-administration and backend-only routes are not generated, because a
partner key cannot call them.

```python
fastn.orgs.list_orgs({"type": "end_org"})
fastn.connections.list_connections({"endOrgId": customer.id()})
fastn.embed.get_setup_link({"id": "stp_..."})
fastn.call("getTenant", {"id": "..."})                  # any operation by operationId
fastn.me()                                              # who this key is: actor, role, org, parentOrg
```

### Customer ids, explained once

Use `fastn.customer(ref)` (or the `customer=` option) and nothing else. The raw API names the same customer
differently per operation; those generated input fields still exist, but they are the raw API. Scoping calls to a
customer needs a multi-tenant partner API key.

| You see in the API docs | What it is | In this SDK |
| --- | --- | --- |
| `orgId` (createTenant body) | the id YOU choose for the customer | `fastn.customer(ref)` |
| `externalRef`, `endOrgRef`, `x-end-org-ref` | the same id, under other names | filled in for you |
| `endOrgId`, `id` (createTenant answer), `x-end-org-id` | fastn's own id of that customer org | `customer.id()` (cached) |

`customer.find()` returns the customer's org row (or `None` when fastn does not know the ref). `register`, `connect`,
`links`, `watch`, `disconnect`, `rename_account`, `update`, `call_log`, `setup_link`, `embed_token`,
`connect_with_credentials`, `connections`, `get`, `remove`, `calendar`, `crm` and `records` all take the ref and resolve
fastn's id only where the API insists on it. The lookup is limited to orgs under your own org, so a key that can see
more than your account can still never resolve someone else's customer.

`customer.api.<area>.<operation>()` runs any operation for that customer: it sends x-end-org-ref and, on routes that
take the customer in the body instead (OAuth initiation, stored connections, event subscriptions, secrets, setup
links, ...), fills that field in too.

### Connecting a customer's apps

```python
# A setup link by app: the account's widget for that connector is found for you (several: pass widget_id=).
link = customer.connect("hubspot", connection_name="Main CRM", redirect_url="https://app.acme.com/connected")
link["url"]                                             # then customer.links.get(link["setupId"]) / links.cancel(...)

# Or start OAuth directly, without a widget:
answer = customer.connect({"connectorId": "googleCalendar", "connectionName": "Google Calendar", "returnUrl": "https://app.acme.com/connected"})

# Typed-in credentials (API key, basic auth): the fields come from the connector's auth method. The platform checks
# them; an incomplete set raises 400 CREDENTIALS_INCOMPLETE with the missing names (err.body["missing"]).
fields = customer.auth_fields("acme-crm")              # {"names", "required", "schema", "authMethodId", ...}
customer.connect_with_credentials({"connectorId": "acme-crm", "credentials": {"apiKey": "..."}, "name": "Acme CRM"})
```

Prefer setup links for credentials: fastn's hosted page collects them, so they never pass through your backend.

### Watching changes

`customer.watch(app, events, account_id=, connection_id=, name=)` turns on an app's change events for a customer; each
change reaches your webhook as `connector.event` and `unified.event`. Name events in plain words (`EVENT_ALIASES`:
`contact.created`, `deal.stageChanged`, ...) or as the app names them; an unknown name raises 400 `EVENT_NOT_FOUND`
with the valid list (`customer.watchable_events(app)`). No account on the app raises 404 `CONNECTION_NOT_FOUND`,
several raise 409 `CONNECTION_AMBIGUOUS` (pass `connection_id=`; one of another app is 400 `CONNECTION_MISMATCH`).
`watches(app=None)` lists every page, and `unwatch(app | id)` removes (an id that is not this customer's is 404
`WATCH_NOT_FOUND`). `disconnect` and `rename_account` refuse an account id that is not the customer's. HubSpot has no
stage-only event: `deal.stageChanged` is `deal.propertyChange`, so check `propertyName == "dealstage"` in the event.

### Responses and errors

Answers are returned as the REST API sends them (usually `{"data": ...}`; unified records are `{"id", "provider",
"data"}`), so the SDK agrees 1:1 with the REST docs, typed as `TypedDict`s under `fastn.platform.types`.

Non-2xx answers raise `FastnApiError` with `status`, `code` (e.g. `NOT_FOUND`, `VALIDATION_ERROR`,
`NO_CONNECTED_PROVIDER`, `OPERATION_NOT_SUPPORTED`, `PROVIDER_AMBIGUOUS`), `message`, `details`, `body` and
`request_id` (quote it when asking fastn for help), plus `is_not_found`, `is_conflict`, `is_rate_limited`, `is_auth`
and `is_validation`. Network failures raise `FastnNetworkError`. GET calls are retried on 429/502/503/504 (default 2
retries, honouring `Retry-After`). A write is retried only when it carries an `idempotency_key` **and** the platform
de-duplicates that operation by it (unified record writes, workflow execute); every other write is never retried, so a
lost answer cannot make it act twice.

```python
from fastn.platform import FastnApiError

try:
    fastn.orgs.get_tenant({"id": tenant_id})
except FastnApiError as e:
    if e.is_not_found:
        ...
```

### Per-call options

Every method takes keyword options: `idempotency_key`, `correlation_id`, `customer={"ref": ...}` or `{"id": ...}`,
`installation_id`, `target_org`, `headers`, `extra_body`, `extra_query`, `timeout`, `retries`. `extra_body` and
`extra_query` send fields the SDK does not know yet; they are passed as given. `FastnClient(defaults={...})` applies
options to every call, e.g. `defaults={"customer": {"ref": "acme-42"}}` to scope a whole client to one customer.

### Events (webhooks)

```python
from fastn.platform import parse_event

# Flask: event = parse_event(os.environ["FASTN_EVENT_SECRET"], request.headers, request.get_data())
event = parse_event(secret, headers, raw_body)          # raises ValueError on a bad signature
# event["id"] is stable across retries: drop repeats by id.
```

The signature is `sha256=HMAC-SHA256(secret, "<X-Fastn-Timestamp>.<raw body>")`; deliveries older than 5 minutes are
rejected (`tolerance_seconds=`, 0 disables the check). Always pass the raw body, never a re-serialised object.
`verify_event_signature` answers a bool instead, `read_event_headers` reads the fastn headers, `sign_event_body` signs a
body the same way (for tests), and `internal_ids=True` keeps fastn's internal customer id in a parsed event.

### Pagination and helpers

```python
from fastn.platform import paginate

for ev in paginate(fastn.events.list_events, {"outcome": "sent_to_dlq"}, page_size=100):
    ...
```

Works for `limit`/`offset` lists and cursor lists. Also exported: `free_intervals` and `slots_of` (the slot maths
behind `calendar.free_slots`).

## FAQ

**What is fastn?**
The embedded integration platform for B2B SaaS. Your customers connect their own apps (HubSpot, Google Calendar,
Slack, and 1,000+ more) inside your product, and your code and AI agents use those connections through one API.

**How do I add customer-facing integrations to my SaaS app in Python?**
Install `fastn-ai`, register each customer with `fastn.customer(your_id).register(...)`, let them connect apps with a
setup link (`customer.connect(app)`) or the `@fastn-ai/embed` widget, then call `customer.crm`, `customer.calendar`, or
`customer.run_action(...)`. See [Embed fastn in your product](#embed-fastn-in-your-product-guide-for-claude-and-other-ai-coding-assistants).

**Does fastn support multi-tenant apps?**
Yes. Every call is scoped to one customer, addressed by your own id; credentials are stored and refreshed per
customer; a customer can connect several accounts of one app.

**Can AI agents like Claude use fastn integrations?**
Yes: as function-calling tools from this SDK (`get_tools_for`, `execute`) for OpenAI, Anthropic, Gemini, and Bedrock,
or through the [fastn MCP gateway](https://docs.fastn.ai/build/mcp-gateway) from Claude, Cursor, or any MCP client.

**Is there a Node.js / TypeScript SDK?**
Yes: [`@fastn-ai/sdk`](https://www.npmjs.com/package/@fastn-ai/sdk), with the same platform API client as
`fastn.platform`.

## Development

Working on the SDK itself (from a clone of the repository):

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run all tests
make test

# Run only SDK tests
make test-sdk

# Run only CLI tests
make test-cli

# Run a single test file
make test-file F=tests/cli/test_cli_commands.py

# Or use pytest directly
python3 -m pytest tests/sdk/ -q       # SDK only
python3 -m pytest tests/cli/ -q       # CLI only
python3 -m pytest tests/ -q           # All
```

Generated code is checked in CI: `python3 scripts/generate_platform.py --check` (platform client) and
`python3 scripts/generate_client_stub.py --check` (the `fastn/__init__.pyi` type stub). The platform live suite runs with
`LIVE=1 FASTN_API_KEY=... FASTN_TEST_CUSTOMER=... pytest tests/platform/live` against api.fastn-test.dev.

### Test Structure

```
tests/
├── sdk/                           # SDK core tests
│   ├── test_client.py             # FastnClient, AsyncFastnClient
│   ├── test_connector.py          # DynamicConnector proxy
│   ├── test_config.py             # Config loading, env vars, validation
│   ├── test_exceptions.py         # Exception hierarchy
│   ├── test_auth.py               # Auth helpers
│   ├── test_oauth.py              # OAuth device flow, token refresh
│   ├── test_projects.py           # Projects namespace
│   └── test_skills.py             # Skills namespace
├── platform/                      # fastn.platform tests (live/ runs against the API)
└── cli/                           # CLI command tests
    ├── test_cli_commands.py        # All CLI commands (sync, add, remove, list, run, agent, etc.)
    ├── test_cli_helpers.py         # CLI helper functions
    ├── test_agent_command.py       # fastn agent command
    ├── test_agent_helpers.py       # Agent helper functions
    ├── test_helpers_extended.py    # Extended helper tests (token, schema, parsing)
    ├── test_skills_command.py      # fastn skill command
    ├── test_detect_api_error.py    # API error detection across providers
    └── test_detect_languages.py    # SDK language detection for stub generation
```

## License

MIT
