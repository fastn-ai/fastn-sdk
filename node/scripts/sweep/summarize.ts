// Turns a sweep report CSV into a short Markdown summary: counts per outcome and area, and every row that needs a
// look (5xx, route mismatches, rejected inputs, SDK errors). Usage: npx tsx scripts/sweep/summarize.ts <report.csv>
import fs from "node:fs";

const file = process.argv[2];
if (!file) { console.error("usage: summarize.ts <report.csv>"); process.exit(2); }
const lines = fs.readFileSync(file, "utf8").split("\n").filter(Boolean);
const parse = (line: string) => { const out: string[] = []; let cur = "", q = false; for (let i = 0; i < line.length; i++) { const ch = line[i]; if (q) { if (ch === '"' && line[i + 1] === '"') { cur += '"'; i++; } else if (ch === '"') q = false; else cur += ch; } else if (ch === '"') q = true; else if (ch === ",") { out.push(cur); cur = ""; } else cur += ch; } out.push(cur); return out; };
const header = parse(lines[0]);
const rows = lines.slice(1).map((l) => Object.fromEntries(parse(l).map((v, i) => [header[i], v])) as Record<string, string>);
const by = (key: string) => { const m: Record<string, number> = {}; for (const r of rows) m[r[key]] = (m[r[key]] ?? 0) + 1; return m; };
const ops = new Set(rows.map((r) => r.operation));
const out: string[] = [];
out.push(`# API sweep summary`, ``, `Source: ${file}`, `Steps: ${rows.length}; operations covered: ${ops.size}`, ``, `## Outcomes`, ``, `| outcome | steps |`, `|---|---|`);
for (const [k, v] of Object.entries(by("outcome")).sort((a, b) => b[1] - a[1])) out.push(`| ${k} | ${v} |`);
out.push(``, `## Per area`, ``, `| area | ok | expected 4xx | forbidden / user-token | skipped | needs a look |`, `|---|---|---|---|---|---|`);
const areas = [...new Set(rows.map((r) => r.area))].sort();
for (const a of areas) {
  const rs = rows.filter((r) => r.area === a);
  const n = (f: (r: Record<string, string>) => boolean) => rs.filter(f).length;
  out.push(`| ${a} | ${n((r) => r.outcome === "ok")} | ${n((r) => r.outcome === "ok-expected-4xx")} | ${n((r) => r.outcome === "forbidden" || r.outcome === "user-token-only")} | ${n((r) => r.outcome === "skipped")} | ${n((r) => ["BUG-5xx", "route-missing", "input-rejected", "sdk-error", "network", "not-found"].includes(r.outcome))} |`);
}
out.push(``, `## Needs a look`, ``, `| outcome | operation | status | note |`, `|---|---|---|---|`);
for (const r of rows.filter((r) => ["BUG-5xx", "route-missing", "input-rejected", "sdk-error", "network", "not-found"].includes(r.outcome))) out.push(`| ${r.outcome} | ${r.operation} | ${r.status} | ${r.note.replace(/\|/g, "/").slice(0, 140)} |`);
out.push(``, `## Not callable with a partner API key`, ``, `| outcome | operation | note |`, `|---|---|---|`);
for (const r of rows.filter((r) => r.outcome === "forbidden" || r.outcome === "user-token-only")) out.push(`| ${r.outcome} | ${r.operation} | ${r.note.replace(/\|/g, "/").slice(0, 120)} |`);
out.push(``, `## Skipped`, ``, `| operation | why |`, `|---|---|`);
for (const r of rows.filter((r) => r.outcome === "skipped")) out.push(`| ${r.operation} | ${r.note.replace(/\|/g, "/").slice(0, 120)} |`);
console.log(out.join("\n"));
