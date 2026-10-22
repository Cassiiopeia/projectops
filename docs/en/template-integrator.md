# Template Integrator: ⚠️ end of support (EOF)

> **Support for `template_integrator.sh` / `.ps1` ended in v4.3.0 (#458), and the guidance shim has also been removed from the repository (#800).**
> The old `curl .../template_integrator.sh | bash` command now gets a 404. Use `npx projectops` below.

## Replacement: npx projectops

Integrating into an existing project, updating, and installing skills now all go through one path: npx.

```bash
# Interactive wizard (macOS / Linux / Windows)
npx projectops

# Non-interactive (CI, etc.)
npx projectops --mode full --type spring,react --force

# Install Agent Skills only
npx projectops --mode skills

# All options
npx projectops --help
```

- **Requirement**: Node.js 20.12 or later -> https://nodejs.org
- The npx wizard provides every feature of the old script (type detection, version detection, workflow copy, `version.yml` generation, rollback, deploy/publish axis questions).
- Selected values are stored in `metadata.template.options.*` of `version.yml`, as before.

## Old flags -> npx

| Old script | npx |
|---|---|
| `--mode full/version/workflows/issues/skills` | Same (`--mode ...`) |
| `--type spring,react` | Same (`--type ...`) |
| `--deploy docker-ssh\|vercel\|none` | Same |
| `--publish nexus,npm,github-packages` | Same |
| `--secret-backup` | Same |
| `--force` | Same |

For details, see the [NPX wizard guide](./npx-wizard.md), the [README](../../README.md), and `npx projectops --help`.
