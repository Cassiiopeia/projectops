# Repo layout

> When to read: creating a new repo, adding a stack to an existing one, or writing the root `CLAUDE.md`.

One repo per product. Every stack of the product lives in it as a folder, so one issue, one branch and one release
cover a change that crosses app and server.

## Folders

```
<project>/
├── CLAUDE.md                 # navigation index (AI entry point), common rules only
├── README.md                 # "## Latest version :" line is managed by a workflow
├── version.yml               # single version source, bumped by workflows, never by hand
├── CHANGELOG.md / .json      # written by the release workflow
├── .gitignore                # blocks secret files before the first commit
├── mobile/  or app/          # React Native (Expo) or Flutter app + its own CLAUDE.md
├── server/                   # Spring multi-module + its own CLAUDE.md
├── ai/                       # optional Python (FastAPI) service + its own CLAUDE.md
├── client/                   # optional web (React + Vite) + its own CLAUDE.md
├── api-contract/openapi.json # optional: server API spec, client types are generated from it
├── brand/                    # single source of brand colors and icons
└── docs/
    └── superpowers/specs/    # design specs (YYYY-MM-DD-<topic>-design.md)
```

- Folder names are the owner's habit, not a rule of the tools: `mobile/` for React Native, `app/` for Flutter.
  Tell projectops where they are with `version.yml` `project_paths` (`--paths "spring=server,react-native-expo=mobile"`).
- Stack-only docs stay inside the stack (`server/docs/`, `mobile/docs/`), not in the root `docs/`.
- Agent work output (`docs/projectops/`, `.superpowers/`) is local only and gitignored; results go to the GitHub issue.

## Root CLAUDE.md: an index, not a manual

Keep it short. It routes the agent to the per-stack file and holds only what applies to every stack.

1. One line on what the product is.
2. Stack navigation table: stack, folder, link to `<folder>/CLAUDE.md`, role.
3. Communication structure in one line, e.g. `app --(/api)--> server --> external sources`. Clients talk to the server
   only, never to AI providers or third-party sources directly.
4. Branch strategy and deploy (see `branch-strategy.md`), with "never commit to `main` or `deploy` directly" and
   "`version.yml` and the README version line are managed by workflows".
5. Product principles the agent must not break (e.g. "only public sources", "every summary links its source").
6. UI copy rules (tone of voice, error screens show an error code).
7. Common prohibitions: push only on request, no secrets in commits, no Co-Authored-By trailer, ask before deleting files.
8. Verification command table per stack.

Per-stack `CLAUDE.md` holds the stack, module or folder structure, dependency direction, the rules that architecture
tests enforce, and the stack's verify commands.

## brand/

- `brand/brand-colors.json` is the original of every brand color; icons and logos sit next to it (transparent, light and dark).
- Platform copies (app tokens, `app.json` splash color, launcher icons, favicon) are generated from it or listed next to
  the original as files that must change together. Never edit a copy alone.

## .gitignore (first commit)

Block these before anything is committed (a pushed secret in a public repo must be treated as leaked):

```
.env
.env.*
!.env.example
application-dev.yml
application-prod.yml
firebase-service-account*.json
google-services.json
GoogleService-Info.plist
*.jks
*.keystore
key.properties
*.p8
*.p12
*.mobileprovision
docs/projectops/
.superpowers/
```

Plus build output per stack (`build/`, `.gradle/`, `node_modules/`, `dist/`, `*.apk`, `*.aab`, `*.ipa`).
