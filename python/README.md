# Fastn SDK for Python

**Give your AI agents and apps secure, governed access to 250+ enterprise systems.**

Production-ready Python SDK for OpenAI, Anthropic, Gemini, and Bedrock function calling. Fully managed OAuth 2.1, SOC 2 certified platform, role-based access control, audit trails, and sub-second execution — so your agent code stays simple and your security team stays happy.

[![PyPI version](https://img.shields.io/pypi/v/fastn-ai.svg)](https://pypi.org/project/fastn-ai/)
[![Python](https://img.shields.io/pypi/pyversions/fastn-ai.svg)](https://pypi.org/project/fastn-ai/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

## Why Fastn?

| Problem | Fastn Solution |
|---------|---------------|
| Agents receive all tool schemas, burning tokens and increasing hallucination | `get_tools_for(prompt, limit=5)` returns only the most relevant tools — 250+ connectors, but only 5 reach the LLM |
| API schemas are deeply nested, wasting context on structure | SDK auto-unwraps schemas for LLMs and re-wraps for execution — flat params in, correct API structure out |
| Each SaaS API has its own OAuth flow, token refresh, and credential storage | Fully managed OAuth 2.1 vault — acquisition, auto-refresh, tenant isolation. No token management code. |
| Security and compliance are afterthoughts in most agent tooling | SOC 2 certified platform, role-based access control, audit trails, PII filtering |
| LLM agents need tool schemas in provider-specific formats | `get_tools_for("Send a Slack message", format="openai")` returns ready-to-use schemas for OpenAI, Anthropic, Gemini, Bedrock |
| Managing connections per customer in multi-tenant apps is complex | First-class `tenant_id` and `connection_id` support at every level |
| Building automation workflows requires stitching APIs together | `fastn.flows.create("When a PR is opened, post to Slack")` handles orchestration |

## Installation

```bash
pip install fastn-ai
```

Installs the SDK, CLI, and type stubs for 250+ connectors. Requires Python 3.8+.
IDE autocomplete works immediately — no extra setup needed.

## Quick Start

```python
from fastn import FastnClient

fastn = FastnClient()
fastn.slack.send_message(channel="general", text="Hello from Fastn!")
```

Async:

```python
from fastn import AsyncFastnClient

async with AsyncFastnClient() as fastn:
    await fastn.slack.send_message(channel="general", text="Hello!")
```

## How It Works

Fastn sits between your AI agent and 250+ SaaS APIs. The SDK handles client-side concerns (tool discovery, schema transformation, parameter routing). The platform handles server-side concerns (credential injection, access control, batch optimization, prompt safety, observability).

> **One-liner:** Connectors provide tools. Flows compose tools. Agents run tools and flows with reasoning.

### Core Capabilities

| Capability | What It Does | Where It Runs |
|-----------|-------------|---------------|
| **Dynamic tool filtering** | Returns only tools that match the current prompt or intent | Platform |
| **Context optimization** | Composes tools/skills, filters schema I/O, strips PII — minimizes tokens and hallucination | Platform + SDK |
| **Schema transformer** | Flattens nested API schemas for LLMs, re-wraps for execution | SDK |
| **Intent routing** | Determines which tool to use based on agent request | Platform + SDK |
| **Managed OAuth 2.1** | Full token lifecycle — acquisition, refresh, revocation, tenant isolation | Platform |
| **Governed access** | RBAC, audit trails, and enterprise compliance controls (SOC 2 certified) | Platform |
| **Batch optimizer** | Groups similar calls to reduce cost and time | Platform |
| **Prompt safety** | Blocks unsafe or injected tool commands | Platform |
| **Observability layer** | Tracks cost, latency, and errors per tool call | Platform + SDK CLI |

### Dynamic Tool Filtering

`get_tools_for(prompt)` sends a semantic search to the platform, which matches the prompt against the full connector registry and returns only the top N tools (default: 5). This reduces tool context from ~125K tokens to ~2,500 tokens — fewer tools also means fewer hallucinated tool calls.

```python
# Semantic discovery — only the most relevant tools reach the LLM
tools = fastn.get_tools_for("Send a Slack message", format="openai", limit=5)

# Direct lookup — bypass semantic search when you know the connector name
tools = fastn.get_tools_for("slack tools", connector="slack", format="openai")
```

### Context Optimization

Fastn minimizes what reaches the LLM — fewer tokens, less hallucination, better compliance:

- **Tool and skill composition** — the platform composes tools and skills into efficient chains, so agents receive focused context instead of raw API surface area
- **Schema I/O filtering** — strips unnecessary fields from tool input and output schemas before they reach the LLM, reducing token cost
- **PII filtering** — removes personally identifiable information from context for security and compliance
- **Schema transformation** — the SDK flattens nested API wrappers (`body`, `param`) for the LLM and re-wraps them for execution:

```
What the API expects:   {"body": {"channel": "#general", "text": "hello"}}
What the LLM sees:      {"channel": "#general", "text": "hello"}
```

Combined with [Dynamic Tool Filtering](#dynamic-tool-filtering), this reduces agent context from ~125K tokens to a focused, compliant payload.

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
| **Tenant** | A customer, organization, or team in a multi-tenant app. | `tenant_id: "acme-corp"` |
| **Skill** | A reusable agent configuration stored in a project. | `fastn.skills.list()` |
| **Agent** | A goal-driven executor that calls tools/flows with reasoning. | `fastn agent "Send hello to Slack"` |
| **Project** | A container that groups connectors, flows, and tenants. | `project_id: "proj_xyz"` |
| **Stage** | An environment for isolating dev/staging/production data. | `"LIVE"`, `"STAGING"`, `"DEV"` |

## SDKs

| Package | What It Does | Language | Status |
|---------|-------------|----------|--------|
| [`fastn-ai`](https://pypi.org/project/fastn-ai/) | Backend SDK — triggers connectors and flows, discovers tools, executes tool calls | Python | Available |
| `@fastn/sdk` | Backend SDK — same capabilities as the Python SDK | TypeScript | Coming soon |
| [`fastn-connect`](https://github.com/fastnai/fastn-connect) | Frontend widget — captures OAuth credentials and connector config for the platform | JavaScript | Available |

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

Fastn handles the three hardest parts of giving LLMs access to tools:

1. **Discovery** — `get_tools_for(prompt)` semantically matches tools from 250+ connectors. Only the top N reach the LLM, keeping context small and hallucination low.
2. **Schema translation** — Schemas are flattened for LLM consumption and formatted for your provider (OpenAI, Anthropic, Gemini, Bedrock).
3. **Execution** — `execute(tool, params)` routes through the platform, which handles credential injection, parameter re-wrapping, retries, and logging.

```python
import json
import openai
from fastn import FastnClient

fastn = FastnClient()

# 1. Describe what you need — Fastn discovers the right tools
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

# 4. Execute the tool call through Fastn
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
| `"raw"` | Any (raw Fastn schemas) | `get_tools_for("Notify team", format="raw")` |

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
    config=genai.types.GenerateContentConfig(tools=tools),
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

# Multiple connectors — limit applies to the total across all
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

Flows chain tools across multiple connectors. Describe the workflow in natural language and Fastn generates, schedules, and executes it.

```python
# Create a flow from a natural language description
result = fastn.flows.create(
    prompt="When a Jira ticket is created, post a summary to #engineering on Slack"
)
print(result["flow_id"])  # "flow_abc123"

# If Fastn needs more info, it returns questions
if "questions" in result:
    result = fastn.flows.create(
        prompt="When a Jira ticket is created, post to Slack",
        answers={"channel": "#engineering", "jira_project": "ENG"},
    )

# List all flows
flows = fastn.flows.list()
active_flows = fastn.flows.list(status="active")

# Run a flow manually
run = fastn.flows.run(flow_id="flow_abc123")
print(run["run_id"])  # "run_xyz"

# Check run status
status = fastn.flows.get_run(run_id="run_xyz")
print(status["status"])  # "completed", "running", "failed"

# Update a flow (schedule, enable/disable)
fastn.flows.update(
    flow_id="flow_abc123",
    schedule="0 9 * * MON-FRI",  # Every weekday at 9am
    enabled=True,
)

# Delete a flow
fastn.flows.delete(flow_id="flow_abc123")
```

## Authentication

Fastn supports three authentication types at different levels. The SDK triggers connectors and flows — the SOC 2 certified platform auto-manages OAuth 2.1 token refresh and credential injection.

| Auth Type | Who Authenticates | To What | How | Expiry |
|-----------|------------------|---------|-----|--------|
| **API Key** | Your app | Fastn platform | `x-fastn-api-key` header | Never |
| **OAuth Token** | You (developer) | Fastn platform | `Authorization: Bearer` JWT | Auto-refreshed |
| **Connection** | Your end-users | External services (Slack, Jira...) | OAuth vault + `connection_id` | Platform-managed |

### 1. API Key — App-to-Platform

Static credential that authenticates your application to the Fastn platform. Created in the [Fastn dashboard](https://fastn.ai), never expires.

```
Your App                          Fastn Platform
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

### 2. OAuth Token — Developer-to-Platform

JWT obtained via browser-based login (RFC 8628 Device Authorization Grant). Used by the CLI and dashboard. Auto-refreshed with a 30-second expiry buffer.

```
Developer          Browser            Fastn (Keycloak)
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

### 3. Connection — End-User-to-External-Service

OAuth connections that link your end-users to external services (Slack, GitHub, etc.) through the Fastn OAuth vault. Tokens are stored server-side, auto-refreshed by the platform, and isolated per tenant. Your code never sees raw credentials.

[fastn-connect](https://github.com/fastnai/fastn-connect) captures auth and connector config on the frontend. This SDK triggers connectors and flows on the backend — pass `connection_id` to route to the right account.

```
Your App (backend)       Frontend (fastn-connect)     Fastn Platform         External Service
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
# Pass result["auth_url"] to your frontend (fastn-connect handles the OAuth flow)

# 2. Check connection status (after user completes auth)
status = fastn.auth.status(connection_id=result["connection_id"])
print(status["status"])  # "pending", "authorized", "expired"

# Or look up by connector + tenant
status = fastn.auth.status(connector="github", tenant_id="customer_acme")

# 3. Use the connection — credentials injected by platform
fastn.slack.send_message(
    connection_id=result["connection_id"],
    channel="general", text="Hello!",
)
```

### Custom Auth Provider

For apps with their own identity provider, configure Fastn to validate end-user tokens via your userinfo endpoint.

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
| `fastn connector ls` | List all available connectors |
| `fastn connector ls <name>` | Show tools for a specific connector |
| `fastn connector sync` | Refresh connector registry, fetch tool schemas, regenerate type stubs |
| `fastn connector add <name> [...]` | Fetch full tool schemas for specific connectors |
| `fastn connector remove <name>` | Remove connector stubs |
| `fastn connector run <name> <tool>` | Execute a connector tool |
| `fastn connector schema <name> <tool>` | Print a tool's input/output schema |
| `fastn flow ls` | List all flows |
| `fastn flow create` | Create a flow from a plain-English prompt |
| `fastn flow run <flow_id>` | Trigger a flow run |
| `fastn skill` | List available agent skills |
| `fastn agent "<prompt>"` | Describe a task in plain English — AI calls the right tools |
| `fastn version` | Show SDK and registry versions |

### `fastn agent`

Agentic CLI — describe what you want in natural language and the agent discovers tools, sends them to your LLM via native function calling, and executes tool calls in a loop until the task is complete.

```bash
fastn agent "Send hello to #general on Slack"
fastn agent --connector slack "List all channels"
fastn agent --eval "Create a Jira ticket for the login bug"
```

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

### `fastn connector run`

Execute connector tools directly from the command line:

```bash
# List available tools
fastn connector run slack

# Interactive mode (prompts for each parameter)
fastn connector run slack send_message

# Inline parameters
fastn connector run slack send_message --channel general --text "Hello!"

# With tenant override
fastn connector run slack send_message --tenant acme --channel general --text "Hello!"
```

## API Reference

### `FastnClient`

```python
FastnClient(
    api_key: str = None,        # Fastn API key (or FASTN_API_KEY)
    project_id: str = None,     # Project ID (or FASTN_PROJECT_ID)
    auth_token: str = None,     # JWT from fastn login (or FASTN_AUTH_TOKEN)
    tenant_id: str = None,      # Tenant ID (or FASTN_TENANT_ID)
    stage: str = None,          # "LIVE", "STAGING", "DEV" (or FASTN_STAGE)
    config_path: str = None,    # Path to config.json
    timeout: float = 30.0,      # HTTP timeout in seconds
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
| `fastn.flows.create(prompt, answers)` | Create a flow from natural language |
| `fastn.flows.list(status)` | List flows (optional status filter) |
| `fastn.flows.run(flow_id, user_id)` | Trigger a flow execution |
| `fastn.flows.get_run(run_id)` | Check run status and results |
| `fastn.flows.update(flow_id, ...)` | Update schedule, enable/disable |
| `fastn.flows.delete(flow_id)` | Delete a flow |

**Auth:**

| Method | Description |
|--------|-------------|
| `fastn.auth.connect(connector, tenant_id, redirect_url)` | Start OAuth connection flow |
| `fastn.auth.status(connection_id)` | Check connection status |
| `fastn.auth.configure_custom(userinfo_url)` | Register custom auth provider |

**Skills:**

| Method | Description |
|--------|-------------|
| `fastn.skills.list()` | List agent skills in the current project |

**Projects:**

| Method | Description |
|--------|-------------|
| `fastn.projects.list()` | List available projects |

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
    print("Invalid credentials — check your API key")
except ConnectorNotFoundError as e:
    print(f"Connector '{e.connector_name}' not found — run: fastn connector sync")
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

Type stubs for 250+ connectors ship in the package — autocomplete works after `pip install fastn-ai`:

- **PyCharm / IntelliJ**: Works automatically
- **VS Code (Pylance)**: Works automatically
- **mypy**: Works automatically (PEP 561 `py.typed` marker included)

To refresh stubs with the latest connector schemas, run `fastn connector sync`.

## Examples

See [`examples/`](examples/) for runnable scripts:

| Directory | Contents |
|-----------|----------|
| [`examples/sdk/`](examples/sdk/) | SDK usage — basic, async, LLM agents (OpenAI/Claude/Gemini/Bedrock), multi-tenant, flows, auth, environments, error handling |
| [`examples/cli/`](examples/cli/) | CLI usage — all commands with examples |

## Platform API client (`fastn.platform`)

The fastn platform REST API for Python: every endpoint, generated from fastn's OpenAPI spec, plus a small hand-written
layer that makes the common partner flow easy. It is the same surface as the Node SDK (`@fastn-ai/sdk`), so the
Node guide maps 1:1: every operation is a snake_case method (`create_setup_link`) and its operationId is an alias
(`createSetupLink`); per-call options are keyword arguments.

```python
from fastn.platform import FastnClient

fastn = FastnClient(api_key=os.environ["FASTN_API_KEY"])          # https://api.fastn.dev

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
w = customer.watch("hubspot", ["contact.created", "deal.stageChanged"], account_id=hubspot_portal_id)
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

- `customer.calendar` and `customer.crm` are the unified API with the fields named (the catalog's own names,
  `start_time`, `first_name`, ...; `datetime` values are sent as ISO strings). Answers are `{"id", "provider", "data",
  "warnings"?}` records or `{"records", "nextCursor", "hasMore"}` pages. No connected provider raises 404
  `NO_CONNECTED_PROVIDER`, several raise 409 `PROVIDER_AMBIGUOUS` (pass `provider=`).
- Every area is on the client directly with typed inputs: `fastn.orgs.list_orgs({"type": "end_org"})`,
  `fastn.embed.get_setup_link({"id": "stp_..."})`, `fastn.call("getTenant", {"id": "..."})`, `fastn.me()`.
  `fastn.catalog.categories()` / `.fields("crm", "contact")` / `customer.catalog.providers("crm", "contact")` read the
  unified catalog. `customer.records("crm", "contact", provider="hubspot")` runs any catalog entity with untyped input;
  `customer.run_action("hubspot", "updateDeal", {...})` runs a connector's own action with the customer's connection.
- `customer.watch(app, events, account_id=, connection_id=, name=)`: events in plain words (`EVENT_ALIASES`:
  `contact.created`, `deal.stageChanged`, ...) or as the app names them; unknown names raise 400 `EVENT_NOT_FOUND`
  with the valid list (`customer.watchable_events(app)`). No account on the app raises 404 `CONNECTION_NOT_FOUND`,
  several raise 409 `CONNECTION_AMBIGUOUS` (pass `connection_id=`; one of another app is 400 `CONNECTION_MISMATCH`).
  `watches(app=None)` lists every page, `unwatch(app | id)` removes (an id that is not this customer's is 404
  `WATCH_NOT_FOUND`); `disconnect` / `rename_account` refuse an account id that is not the customer's. HubSpot has no stage-only event: `deal.stageChanged` is `deal.propertyChange`; check `propertyName ==
  "dealstage"` in the event.
- Per-call options: `idempotency_key`, `correlation_id`, `customer={"ref": ...}` or `{"id": ...}`, `installation_id`,
  `target_org`, `headers`, `extra_body`, `extra_query`, `timeout`, `retries`. `FastnClient(defaults={...})` applies
  options to every call.
- Errors: non-2xx raises `FastnApiError` with `status`, `code`, `message`, `details`, `request_id` and `body`; network
  failures raise `FastnNetworkError`. GET calls are retried on 429/502/503/504 (default 2 retries, honouring
  `Retry-After`); a write is retried only when it carries an `idempotency_key` and the platform de-duplicates that
  operation by it (unified record writes, workflow execute).
- Events: `parse_event(secret, request.headers, raw_body)` verifies `sha256=HMAC-SHA256(secret, "<ts>.<body>")` and
  parses the delivery (5-minute tolerance). `paginate(fastn.events.list_events, {"status": "failed"}, page_size=100)`
  walks `limit`/`offset` and cursor lists.
- Regenerate after a spec refresh with `python3 scripts/generate_platform.py` (`--check` in CI). The live suite runs
  with `LIVE=1 FASTN_API_KEY=... FASTN_TEST_CUSTOMER=... pytest tests/platform/live` against api.fastn-test.dev;
  `FASTN_BASE_URL=https://api.fastn.dev LIVE_PROD=1` runs it on production.

## Development

```bash
# Install in dev mode
pip install -e ".[dev]"

# Run all tests (576 tests, ~7s)
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
