# JavaScript stack rules (including TypeScript · React · Next · Node)

> When to read: when the target has a `package.json`. Shared by audit, refactor and init.

## Layer map

| Layer | Location (React/Next) | What goes in |
|---|---|---|
| Presentation | `app/`, `pages/`, `components/` | Screens, components, screen state |
| Application | `hooks/`, `services/`, `store/` | Flows outside screens, server state |
| Domain | `types/`, `models/`, `domain/` | Types, pure rules |
| Infrastructure | `api/`, `clients/`, `lib/http` | fetch and axios clients, auth headers |
| Common | `styles/tokens`, `tailwind.config`, `components/ui` | Tokens, common components |

Treat a Node CLI or library as one-way `src/cli` (entry point, arguments) → `src/core` (logic). Defaults or logic reappearing in the entry point is a violation.

## Common AI smells

- Server API types copied by hand (`types/api/*` mimicking server classes) — switch to OpenAPI generation
- Server enums and error codes compared as string literals
- Hard-coded production base URL; auth headers attached in two places, an interceptor and a util
- Color values like `#4F46E5`, Tailwind arbitrary values `[#hex]`, inline `style={{` (bypassing tokens)
- Same name, different implementations (2–3 kinds of search bar or pagination), copies nobody imports
- `loading`, `open`, `disabled` state (no prefix), papering over with the `any` type
- `/* eslint-disable */` at the file head, no lint config

## First rule candidates

```
# no-hex-color-in-components.rule
description=No color literals in components (use tokens or the Tailwind theme)
paths=src/components/,src/app/
extensions=.tsx,.jsx
pattern=["'`]#[0-9a-fA-F]{6}\b|-\[#[0-9a-fA-F]{3,8}\]

# components-must-not-import-api-client.rule
description=Components must not import the HTTP client directly (go through hooks or services)
paths=src/components/
extensions=.ts,.tsx,.js,.jsx
pattern=from\s+['"](?:@/|\.\.?/)[^'"]*\bapis?/[^'"]*['"]
```

Adjust the pattern to this repo's real client folder (the infrastructure edges in `deps`, the `wrappers` in `bypassed_components`). If the `ledger` verdict finds 0 hits, the path is wrong.

dependency-cruiser and eslint-plugin-boundaries are more precise for layer imports — they are new dependencies, so **only propose** them.

## Rule tests

`install-tests PATH --stack javascript --module <package folder>` → `test/architecture/architecture.rules.test.mjs`.
Run with `node --test test/architecture` (Node 18+, no extra dependencies). In a vitest or jest project, append this command to the `npm test` script.

## Choosing model files

1 component (uses only tokens), 1 hook (server state in one place), 1 API module (uses generated types).
