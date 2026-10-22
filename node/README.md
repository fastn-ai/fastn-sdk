# @fastn-ai/sdk

Official fastn SDK for Node.js and TypeScript.

> Status: early scaffold. The client API is not implemented yet.

## Install

```bash
npm install @fastn-ai/sdk
```

Requires Node.js 20 or later. Ships ESM and CommonJS with TypeScript types.

## Development

```bash
cd node
npm install
npm run build          # tsup -> dist/ (ESM + CJS + .d.ts)
npm run typecheck
npm test               # vitest, tests in test/
npm run lint:package   # publint + are-the-types-wrong on the packed tarball
```

```
node/
  src/
    index.ts      public entry point (everything exported from @fastn-ai/sdk)
    core/         config, errors
  test/           *.test.ts
```

## Releasing

1. Bump `version` in `node/package.json` and update `node/CHANGELOG.md` in a PR.
2. After merge, tag `main` and push the tag:
   ```bash
   git tag node/v0.0.1 && git push origin node/v0.0.1
   ```
3. The `Publish Node SDK` workflow checks the tag matches `package.json`, runs the checks, and publishes to npm with provenance. It uses the `NPM_TOKEN` secret from the `npm` GitHub environment.

## License

MIT
