# CLI summary

`npx projectops [options]` integrates or updates the template in an existing project. Source of truth: `node bin/projectops.js --help`.

## Modes (`-m, --mode`)

| Mode | What it does |
|------|--------------|
| `full` | Workflows + version.yml + issue templates + Skills |
| `version` | version.yml only |
| `workflows` | Workflows only |
| `issues` | Issue/PR templates only |
| `skills` | Agent Skills only |
| `doctor` | Diagnose integration state and repository settings (read-only) |
| `options` | Print every flag and every `version.yml` key with allowed values and defaults. Add `--json` for AI agents (read-only, no network) |

Default is interactive.

## See it run

Interactive wizard on a sample Spring project (a real run; the wizard UI is currently Korean):

![npx projectops interactive wizard](../images/cli-wizard.gif)

One-shot install followed by a read-only `doctor` check:

![One-shot install and doctor](../images/cli-oneshot.gif)

## Options

| Option | Meaning |
|--------|---------|
| `-t, --type CSV` | Project types: spring, flutter, react, react-native, react-native-expo, node, python, basic |
| `--project-version V` | Initial version for the target (auto-detected if omitted) |
| `--paths "t=p,..."` | Per-type project paths for monorepos, e.g. `flutter=app,react=client` |
| `--intent KIND` | app, library, both, none, manual |
| `--deploy TARGET` | docker-ssh (default), vercel, none |
| `--publish CSV` | nexus, npm, github-packages (default: none) |
| `--deploy-branch NAME` | Release PR head branch (default: develop) |
| `--secret-backup` / `--no-secret-backup` | Include or exclude the secret backup workflow |
| `--ai-summary` / `--no-ai-summary` | Include or exclude the PR summary workflow |
| `--json` | With `--mode options`: machine-readable JSON |
| `--remove-legacy` | Rename retired old-generation workflows to `.bak` (default: only list them) |
| `--force` | Skip all confirmations, use non-interactive defaults |
| `-v, --version` | Print the projectops version |
| `-h, --help` | Show help |

`--nexus` and `--npm-publish` are deprecated; use `--publish nexus` / `--publish npm`.

## Examples

```bash
npx projectops --mode full --force --type spring,react
npx projectops --mode workflows --type flutter --paths "flutter=app"
npx projectops --mode doctor
GITHUB_TOKEN=ghp_... npx projectops --mode doctor   # also diagnoses repository settings
```
