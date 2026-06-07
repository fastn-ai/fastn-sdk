# Fastn SDK

**Give your AI agents and apps instant, secure access to 250+ enterprise systems.**

Part of Fastn, the embedded integration platform for SaaS products and AI agents.

Production-ready SDK with fully managed OAuth 2.1, SOC 2 certified platform, governed access, and sub-second execution. One SDK for OpenAI, Anthropic, Gemini, and Bedrock function calling.

## Why Fastn?

| Problem | Fastn Solution |
|---------|---------------|
| Agents receive all tool schemas, burning tokens and increasing hallucination | `get_tools_for(prompt, limit=5)` semantically matches and returns only the most relevant tools |
| API schemas are deeply nested, wasting context on structural wrappers | SDK auto-unwraps schemas for LLMs and re-wraps for execution, flat params in, correct API structure out |
| Each SaaS API has its own OAuth flow, token refresh, and credential storage | Fully managed OAuth 2.1 vault, acquisition, auto-refresh, tenant isolation. No token management code. |
| Security and compliance are afterthoughts in most agent tooling | SOC 2 certified platform, role-based access control, audit trails, PII filtering |
| LLM agents need tool schemas in provider-specific formats | `get_tools_for("Send a Slack message", format="openai")` returns ready-to-use schemas for OpenAI, Anthropic, Gemini, Bedrock |
| Building automation workflows requires stitching APIs together | `fastn.flows.create("When a PR is opened, post to Slack")` handles orchestration |
| No type safety when calling integrations dynamically | Generated `.pyi` stubs give full IDE autocomplete with parameter names and types |

## SDKs

| Language | Package | Status |
|----------|---------|--------|
| **Python** | [`fastn-ai`](https://pypi.org/project/fastn-ai/) | Stable (v0.3.1) |
| **Node.js** | `@fastn/sdk` | Planned |

## Quick Start (Python)

```bash
pip install fastn-ai
```

```python
from fastn import FastnClient

fastn = FastnClient(api_key="...", project_id="...")
fastn.slack.send_message(channel="general", text="Hello from Fastn!")
```

IDE autocomplete works immediately, 250+ connector stubs ship in the package.

For CLI usage:

```bash
fastn login
fastn connector sync   # optional, refreshes connector registry and type stubs
```

## Terminology

Connectors provide tools. Flows compose tools. Agents run flows and tools with reasoning.

| Term | Definition | Example |
|------|-----------|---------|
| **Connector** | A service integration | Slack, Jira, GitHub, Salesforce |
| **Tool** | A callable function within a connector | `send_message`, `create_issue` |
| **Flow** | An automated workflow chaining tools across connectors | "When a PR is opened, post to Slack" |
| **Connection** | An authenticated link between a connector and an account | OAuth connection to a Slack workspace |
| **Tenant** | A customer or organization in a multi-tenant app | `tenant_id: "acme-corp"` |

## How It Works

Fastn sits between your AI agent and 250+ SaaS APIs as an embedded integration platform:

- **Dynamic Tool Filtering**, `get_tools_for(prompt)` semantically matches against the full registry and returns only the top N tools (default: 5). This reduces tool context from ~125K tokens to ~2,500 tokens, roughly 98% less context for the LLM.
- **Context Optimization**, composes tools and skills, filters schema inputs/outputs, and strips PII to minimize tokens and reduce hallucination. The SDK also flattens nested API wrappers for the LLM and re-wraps them for execution. Automatic and transparent.
- **Fully Managed Auth**, OAuth 2.1 tokens and API keys are securely vaulted on the SOC 2 certified Fastn platform. The SDK calls the gateway; the gateway injects credentials per tenant. Tokens auto-refresh with a 30-second expiry buffer.

```
Agent → get_tools_for(prompt) → SDK → Platform (semantic match) → top N tools (flat schemas)
Agent → LLM (prompt + N schemas) → tool_call with flat params
Agent → execute(tool, params) → SDK (re-wrap) → Platform (inject credentials) → result
```

## LLM Agent Integration

Fastn handles the three hardest parts of giving LLMs access to tools:

1. **Discovery**, `get_tools_for(prompt)` uses semantic matching to find the right tools from 250+ connectors. Only the top N (default: 5) reach the LLM.
2. **Schema translation**, Schemas are automatically flattened for LLM consumption and formatted for your provider (OpenAI, Anthropic, Gemini, Bedrock).
3. **Execution**, `execute(tool, params)` routes through the gateway, which handles credential injection, parameter re-wrapping, retries, and logging.

```python
import json
from fastn import FastnClient

fastn = FastnClient()

# Step 1: Describe what you need, Fastn finds the right tools
tools = fastn.get_tools_for(
    "Send a message on Slack and create a Jira ticket",
    format="openai",   # also: anthropic, gemini, bedrock, raw
)

# Step 2: Send tools + prompt to the LLM
response = openai.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Send hello to #general on Slack"}],
    tools=tools,
)

# Step 3: Execute the LLM's tool call through Fastn
tool_call = response.choices[0].message.tool_calls[0]
result = fastn.execute(
    tool=tool_call.function.name,
    params=json.loads(tool_call.function.arguments),
)
```

Supported providers: **OpenAI**, **Anthropic Claude**, **Google Gemini**, **AWS Bedrock**, and any provider via `raw` format.

## Flows, Tool Orchestration

```python
# Create a flow from natural language
result = fastn.flows.create(
    prompt="When a Jira ticket is created, post a summary to #engineering on Slack"
)

# Run it
run = fastn.flows.run(flow_id=result["flow_id"])

# Check status
status = fastn.flows.get_run(run_id=run["run_id"])
```

## Auth, Credential Vault

Fastn manages the full OAuth lifecycle, token storage, auto-refresh, and per-tenant isolation, so your application never handles raw credentials.

```python
# Start OAuth for a user
result = fastn.auth.connect(
    connector="slack",
    tenant_id="customer_acme",
    redirect_url="https://myapp.com/callback",
)
# Redirect user to result["auth_url"]

# Configure custom auth provider
fastn.auth.configure_custom(userinfo_url="https://myapp.auth0.com/userinfo")
```

## CLI Agent Mode

Execute tools via natural language from the command line:

```bash
fastn agent "Send hello to #general on Slack"
fastn agent --connector slack "List all channels"
fastn agent --eval "Create a Jira ticket for the login bug"
```

## Platform Capabilities

Every API call goes through the Fastn gateway. The SDK handles client-side concerns (schema transformation, parameter routing, retries). The platform handles server-side concerns (credentials, access control, logging).

| Category | Capabilities |
|----------|-------------|
| **Performance & Context** | Dynamic tool filtering (~98% context reduction), context optimization (tool/skill composition, schema I/O filtering, PII filtering), centralized gateway, connection pooling, automatic retries |
| **Security & Auth Vault** | SOC 2 certified, OAuth 2.1 vault with auto-refresh, credential isolation, tenant isolation, PII filtering, custom auth providers, MCP compatible |
| **Governance & Observability** | Role-based access control, audit trails, enterprise compliance controls, usage analytics, verbose mode, structured error tracking |

## Documentation

- **[Python SDK Guide](python/README.md)**, full API reference, terminology, examples, flows, auth, error handling
- **[Changelog](python/CHANGELOG.md)**, release history
- **[fastn.ai](https://fastn.ai)**, product overview
- **[docs.fastn.ai](https://docs.fastn.ai)**, full documentation

## Repo Structure

```
fastn-sdk/
├── python/                  # Python SDK + CLI (PyPI: fastn-ai)
│   ├── fastn/               # SDK source
│   │   ├── client.py        # FastnClient, AsyncFastnClient
│   │   ├── connector.py     # Dynamic connector proxy (DynamicConnector, AsyncDynamicConnector)
│   │   ├── config.py        # Config management
│   │   ├── exceptions.py    # Typed exception hierarchy
│   │   ├── oauth.py         # OAuth device flow
│   │   ├── auth.py          # Auth helpers
│   │   └── cli/             # CLI commands (login, sync, add, run, agent)
│   ├── tests/
│   │   ├── sdk/             # SDK tests (170+ tests)
│   │   └── cli/             # CLI tests (240+ tests)
│   └── examples/
│       ├── sdk/             # SDK usage examples
│       └── cli/             # CLI usage examples
├── generator/               # Shared stub generation (.pyi / .d.ts)
└── node/                    # Node.js SDK (planned)
```

## Development

```bash
cd python
pip install -e ".[dev]"

# Run all tests (576 tests, ~7s)
make test

# Run only SDK tests
make test-sdk

# Run only CLI tests
make test-cli

# Run a single test file
make test-file F=tests/cli/test_cli_commands.py

# Lint
make lint
```

## License

MIT
