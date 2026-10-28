import { defineConfig } from "tsup";

// One build: the client (index), the generator (codegen) and its CLI (bin "fastn-sdk-tools"; the shebang in the
// source is kept by esbuild). Declarations only for the two importable entries. One config, so `clean` can never
// race the CLI's output.
export default defineConfig({
  entry: { index: "src/index.ts", codegen: "src/codegen/tools.ts", "cli/fastn-sdk-tools": "src/cli/fastn-sdk-tools.ts" },
  format: ["esm", "cjs"],
  dts: { entry: { index: "src/index.ts", codegen: "src/codegen/tools.ts" } },
  sourcemap: true,
  clean: true,
  treeshake: true,
  target: "es2022",
});
