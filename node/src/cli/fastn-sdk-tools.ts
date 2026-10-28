#!/usr/bin/env node
// fastn-sdk-tools - generate typed per-connector methods from a fastn Connect workspace's tool list.
//
//   npx fastn-sdk-tools --url https://mcp.fastn.dev/<workspace> --key $FASTN_TOOLS_KEY --out src/fastn-tools.ts
//   npx fastn-sdk-tools --from tools-list.json --out src/fastn-tools.ts        # offline, from a saved tools/list
//   npx fastn-sdk-tools --url ... --out src/fastn-tools.ts --check             # exit 1 when the file would change
//
// The key is read from --key or FASTN_TOOLS_KEY and is never written anywhere (the header has the url only).
import fs from "node:fs";
import path from "node:path";
import { ToolsClient } from "../tools.js";
import { generateToolsModule, readToolList } from "../codegen/tools.js";

const USAGE = `usage: fastn-sdk-tools --out <file.ts> (--url <workspace endpoint> [--key <key>] | --from <tools-list.json>) [--customer <ref>] [--check]

  --url <url>        the workspace endpoint, e.g. https://mcp.fastn.dev/<workspace> (or FASTN_TOOLS_URL)
  --key <key>        the workspace key (or FASTN_TOOLS_KEY); needed with --url
  --from <file>      a saved tools/list (an array of tools, { tools: [...] } or the JSON-RPC result) instead of fetching
  --customer <ref>   fetch the listing as this customer (X-Org-Id); noted in the header
  --out <file.ts>    where to write the module (required)
  --check            write nothing; exit 1 when --out is missing or would change, 0 when it is up to date
  --import <module>  what the module imports the SDK types from (default "@fastn-ai/sdk")
`;

interface Args { url?: string; key?: string; from?: string; customer?: string; out?: string; check: boolean; import?: string; help: boolean }

export function parseArgs(argv: string[], env: NodeJS.ProcessEnv = {}): Args {
  const a: Args = { check: false, help: false, url: env.FASTN_TOOLS_URL || undefined, key: env.FASTN_TOOLS_KEY || undefined };
  for (let i = 0; i < argv.length; i++) {
    const x = argv[i];
    const take = (name: keyof Args) => { const v = argv[++i]; if (v === undefined || v.startsWith("--")) throw new TypeError(`${x} needs a value`); (a as any)[name] = v; };
    if (x === "--check") a.check = true;
    else if (x === "--help" || x === "-h") a.help = true;
    else if (x === "--url") take("url");
    else if (x === "--key") take("key");
    else if (x === "--from") take("from");
    else if (x === "--customer") take("customer");
    else if (x === "--out") take("out");
    else if (x === "--import") take("import");
    else if (x.startsWith("--") && x.includes("=")) { const [k, v] = x.slice(2).split(/=(.*)/s); argv.splice(i + 1, 0, v ?? ""); argv[i] = `--${k}`; i--; }
    else throw new TypeError(x.startsWith("--") ? `unknown argument ${x}` : "unexpected value on the command line (a key goes after --key, or in FASTN_TOOLS_KEY)");
  }
  return a;
}

export async function main(argv = process.argv.slice(2), env = process.env, io = { out: (s: string) => process.stdout.write(s), err: (s: string) => process.stderr.write(s) }): Promise<number> {
  let a: Args;
  try { a = parseArgs(argv, env); } catch (e) { io.err(`fastn-sdk-tools: ${(e as Error).message}\n${USAGE}`); return 2; }
  if (a.help) { io.out(USAGE); return 0; }
  if (!a.out) { io.err(`fastn-sdk-tools: --out <file.ts> is required\n${USAGE}`); return 2; }
  if (!a.from && !a.url) { io.err(`fastn-sdk-tools: give --url <workspace endpoint> (or FASTN_TOOLS_URL) or --from <tools-list.json>\n${USAGE}`); return 2; }

  let tools;
  try {
    if (a.from) {
      tools = readToolList(JSON.parse(fs.readFileSync(path.resolve(a.from), "utf8")));
    } else {
      if (!a.key) { io.err("fastn-sdk-tools: --key <key> (or FASTN_TOOLS_KEY) is required with --url\n"); return 2; }
      const client = new ToolsClient({ key: a.key, url: a.url! });
      tools = await client.tools(a.customer ? { customer: { ref: a.customer } } : {});
      tools = readToolList(tools);
    }
  } catch (e) {
    io.err(`fastn-sdk-tools: could not read the tool list: ${(e as Error).message}\n`);
    return 1;
  }

  let source: string;
  let groups: string[];
  try {
    const g = await generateToolsModule(tools, { url: a.url, customer: a.customer, importFrom: a.import });
    source = g.source; groups = g.groups;
  } catch (e) {
    io.err(`fastn-sdk-tools: generation failed: ${(e as Error).message}\n`);
    return 1;
  }

  const outPath = path.resolve(a.out);
  if (a.check) {
    const current = fs.existsSync(outPath) ? fs.readFileSync(outPath, "utf8") : undefined;
    if (current === source) { io.out(`fastn-sdk-tools: ${a.out} is up to date (${tools.length} tools)\n`); return 0; }
    io.err(current === undefined ? `fastn-sdk-tools: ${a.out} does not exist; run without --check to create it\n` : `fastn-sdk-tools: ${a.out} would change (${firstDiff(current, source)}); run without --check to update it\n`);
    return 1;
  }
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, source);
  io.out(`fastn-sdk-tools: wrote ${a.out}: ${tools.length} tools, ${groups.length} connectors (${groups.join(", ")})\n`);
  return 0;
}

function firstDiff(a: string, b: string): string {
  const la = a.split("\n"), lb = b.split("\n");
  for (let i = 0; i < Math.max(la.length, lb.length); i++) if (la[i] !== lb[i]) return `first difference at line ${i + 1}: ${JSON.stringify((la[i] ?? "<end>").slice(0, 80))} -> ${JSON.stringify((lb[i] ?? "<end>").slice(0, 80))}`;
  return "same lines, different bytes";
}

// Run when executed as a program (not when imported by the unit tests).
const invoked = process.argv[1] && /fastn-sdk-tools(\.[cm]?[jt]s)?$/.test(process.argv[1]);
if (invoked) main().then((code) => { process.exitCode = code; }, (e) => { process.stderr.write(`fastn-sdk-tools: ${(e as Error)?.message ?? e}\n`); process.exitCode = 1; });
