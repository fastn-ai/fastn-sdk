// Copies the current OpenAPI spec (public /v1 spelling) out of a fastn-platform checkout.
// Usage: npm run spec:refresh -- /path/to/fastn-platform [version]
// The platform's openapi.ts imports workspace packages; they are resolved from source via a temporary tsconfig,
// so the checkout needs node_modules but no build.
import fs from "node:fs";
import path from "node:path";
import { execFileSync } from "node:child_process";

const [checkout, versionArg] = process.argv.slice(2);
if (!checkout) { console.error("usage: refresh-spec <fastn-platform checkout> [version]"); process.exit(2); }
const root = path.resolve(checkout);
const specDir = path.resolve(import.meta.dirname, "../spec");
const tsconfig = path.join(root, "tsconfig.sdk-dump.json");
fs.writeFileSync(tsconfig, JSON.stringify({ compilerOptions: { module: "ESNext", moduleResolution: "Bundler", target: "ES2022", baseUrl: root, paths: { "@fastn/*/contracts": ["packages/*/src/contracts/index.ts"], "@fastn/*": ["packages/*/src/index.ts", "services/*/src/index.ts"] } } }));
const dump = path.join(root, "sdk-dump-spec.mts");
fs.writeFileSync(dump, `import { publicSpec } from "./services/api/src/openapi.ts"; process.stdout.write(JSON.stringify(publicSpec, null, 1));`);
try {
  const json = execFileSync("npx", ["tsx", "--tsconfig", tsconfig, dump], { cwd: root, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 });
  const spec = JSON.parse(json);
  const commit = execFileSync("git", ["rev-parse", "--short", "HEAD"], { cwd: root, encoding: "utf8" }).trim();
  const version = versionArg ?? (() => { try { return execFileSync("git", ["describe", "--tags", "--abbrev=0"], { cwd: root, encoding: "utf8" }).trim().replace(/^v/, ""); } catch { return spec.info?.version ?? "0.0.0"; } })();
  for (const f of fs.readdirSync(specDir)) if (/^openapi-v.*\.json$/.test(f)) fs.unlinkSync(path.join(specDir, f));
  const out = path.join(specDir, `openapi-v${version}.json`);
  fs.writeFileSync(out, JSON.stringify(spec, null, 1));
  const ops = Object.values<any>(spec.paths).reduce((n, item) => n + Object.values(item).filter((o: any) => o?.operationId).length, 0);
  fs.writeFileSync(path.join(specDir, "SOURCE.md"), `# Spec source\n- File: openapi-v${version}.json = \`publicSpec\` of fastn-platform services/api/src/openapi.ts (public /v1 spelling).\n- Taken from fastn-platform @ ${commit} on ${new Date().toISOString().slice(0, 10)}; ${ops} operations.\n- Refresh: \`npm run spec:refresh -- /path/to/fastn-platform [version]\`, then \`npm run generate\` and \`npm test\`.\n`);
  console.log(`wrote ${out} (${ops} operations) from ${commit}`);
} finally { fs.rmSync(tsconfig, { force: true }); fs.rmSync(dump, { force: true }); }
