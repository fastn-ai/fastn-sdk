# fastn SDKs

Official SDKs for [fastn](https://fastn.ai), the embedded integration platform for SaaS products and AI agents.

| Language | Package | What it is | Guide |
|----------|---------|------------|-------|
| **Python** | [`fastn-ai`](https://pypi.org/project/fastn-ai/) | Tool discovery and execution for AI agents across 250+ connectors, flows, the `fastn` CLI, and the platform API client (`fastn.platform`) | [python/README.md](python/README.md) / [changelog](python/CHANGELOG.md) |
| **Node.js / TypeScript** | [`@fastn-ai/sdk`](https://www.npmjs.com/package/@fastn-ai/sdk) | The platform API client (customers, setup links, unified CRM and calendar, webhooks, events) and workspace tool calls | [node/README.md](node/README.md) / [changelog](node/CHANGELOG.md) |

The platform API client is the same in both languages: `fastn.platform.FastnClient` in Python and `FastnClient` from
`@fastn-ai/sdk` in Node, with a platform API key from the [fastn dashboard](https://app.fastn.dev) against
`https://api.fastn.dev`. The agent tooling (`get_tools_for`, connector calls, flows, CLI) is Python only.

## Quick start: platform API

```bash
pip install fastn-ai          # or: npm install @fastn-ai/sdk
```

```python
import os
from fastn.platform import FastnClient

fastn = FastnClient(api_key=os.environ["FASTN_API_KEY"])
customer = fastn.customer("acme-42")                 # your id for the customer
customer.register({"name": "Acme Dental"})
print(customer.connect("googleCalendar")["url"])     # send this link to the customer
```

```ts
import { FastnClient } from "@fastn-ai/sdk";

const fastn = new FastnClient({ apiKey: process.env.FASTN_API_KEY! });
const customer = fastn.customer("acme-42");
await customer.register({ name: "Acme Dental" });
console.log((await customer.connect("googleCalendar")).url);   // send this link to the customer
```

## Quick start: tools for AI agents (Python)

```bash
pip install "fastn-ai[cli]"
fastn login
```

```python
from fastn import FastnClient

fastn = FastnClient()
tools = fastn.get_tools_for("Send a Slack message", format="openai")   # only the relevant tools reach the LLM
# ...send `tools` to your LLM, then run its tool call:
# fastn.execute(tool=call.function.name, params=json.loads(call.function.arguments))
```

See the [Python guide](python/README.md) for connectors, flows, auth, the CLI, and the other LLM providers.

## Repo structure

```
fastn-sdk/
├── python/          # fastn-ai on PyPI
│   ├── fastn/       # SDK: client, connectors, flows, auth, cli/, platform/
│   ├── scripts/     # generate_platform.py, generate_client_stub.py
│   ├── tests/       # sdk/, cli/, platform/
│   └── examples/
├── node/            # @fastn-ai/sdk on npm
│   ├── src/         # client, customer, domain, events, tools, generated/
│   ├── spec/        # the platform OpenAPI spec the clients are generated from
│   └── test/
└── generator/       # Python connector stub generator (used by `fastn connector sync`)
```

## Development and releases

```bash
cd python && pip install -e ".[dev]" && make test
cd node && npm ci && npm test
```

Pushing a tag publishes from CI: `python/vX.Y.Z` to PyPI (trusted publishing) and `node/vX.Y.Z` to npm. The tag must
match the package version.

## License

MIT
