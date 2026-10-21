# CLI reference

`npx projectops` is the **only official way** to install and update workflows, issue and PR templates, and Agent Skills in an existing project. All you need is Node.js 20.12 or later; it runs without a separate install (macOS, Linux and Windows). The source of truth for flags is `npx projectops --help`.

## At a glance

| You want to | Run |
|--------------|-----------|
| Install by answering questions | `npx projectops` |
| Install in one line, without questions | `npx projectops --mode full --type spring --force` |
| Install Agent Skills only | `npx projectops --mode skills` |
| Check the install state (read-only) | `npx projectops --mode doctor` |
| See every option at once (JSON for AI agents) | `npx projectops --mode options --json` |

## Interactive wizard

Run `npx projectops` in your project folder. This is a **real run** on a sample Spring project.

![npx projectops interactive wizard](../images/cli-wizard.gif)

The wizard asks in this order. Most defaults are the recommended values, so pressing Enter is usually enough.

| Step | Question | What it decides |
|------|------|---------------|
| 1 | What would you like to install? | Full install, version control, workflows, issue and PR templates, or AI skills |
| 2 | (automatic) Project detection | Finds the type (spring, flutter, react, etc.), version and branches from marker files such as `build.gradle` and `pubspec.yaml` |
| 3 | Choose the project kind | Fewer follow-up questions depending on whether you deploy a server or app, or publish a library |
| 4 | Choose how to deploy the runnable | Docker + SSH server deployment (default), Vercel, or no deployment |
| 5 | Choose the PR comment mode | Change summary, code review (CodeRabbit), both, or none |
| 6 | Development (release source) branch | The branch that collects development and is raised to the default branch (default `develop`). If it does not exist, the wizard offers to create it and push it to the remote |
| 7 | Secret server backup | Whether to include the Secret server backup workflow |
| 8 | Deployment environment values | Service name, domain, JDK version, etc. You can choose "Install everything with the defaults above" |
| 9 | AI agent skills | Whether to also install them for Claude Code, Cursor, Gemini CLI, Codex CLI and PI |

Every selected value is stored in `metadata.template.options.*` of `version.yml`, so the next run (update) does not ask again.

## One-line run (non-interactive)

In CI or scripts, `--force` skips every confirmation and uses the defaults. A typical flow is to install, then check the state with `--mode doctor`.

![One-shot install and doctor](../images/cli-oneshot.gif)

```bash
npx projectops --mode full --type spring,react --force
npx projectops --mode workflows --type flutter --paths "flutter=app"
npx projectops --deploy docker-ssh --publish nexus,npm
npx projectops --intent library
```

## Modes

The `--mode` value decides what to install. Without it, the CLI runs interactively.

| Mode | What it does |
|------|---------|
| `full` | Full integration: workflows + `version.yml` + issue and PR templates + Skills |
| `version` | `version.yml` only |
| `workflows` | Workflows only |
| `issues` | Issue and PR templates only |
| `skills` | Agent Skills only |
| `doctor` | Diagnose the integration state and repository settings (read-only, changes nothing) |
| `options` | Print every flag and every `version.yml` key with allowed values and defaults. Add `--json` for AI agents (read-only, no network) |

## Options

| Option | Description |
|------|------|
| `-m, --mode MODE` | One of the modes above. Default is interactive |
| `-t, --type CSV` | Project types, e.g. `spring,react,python`. Supported: `spring` `flutter` `react` `react-native` `react-native-expo` `node` `python` `basic` (`next` was merged into `react`; use `react` for Next.js) |
| `--project-version V` | Initial version of the target (e.g. `1.0.0`). Auto-detected if omitted |
| `--paths "t=p,..."` | Per-type project paths (monorepo), e.g. `flutter=app,react=client` |
| `--intent KIND` | Project kind: `app` `library` `both` `none` `manual`. If omitted, inferred from `--deploy`/`--publish`. `library`/`none` skip the deploy question, and `app`/`none` skip the publish question |
| `--deploy TARGET` | Deployment, pick one: `docker-ssh` (default) `vercel` `none` |
| `--publish CSV` | Publish targets: `nexus,npm,github-packages` (default: none) |
| `--deploy-branch NAME` | Head branch of the release PR (default `develop`). It is separate from the default (deployment) branch |
| `--secret-backup` / `--no-secret-backup` | Include or exclude the Secret backup workflow |
| `--ai-summary` / `--no-ai-summary` | Include or exclude the PR change summary workflow |
| `--coderabbit` / `--no-coderabbit` | Install the CodeRabbit PR code review config (`.coderabbit.yaml`), `--mode full` only. Needs the CodeRabbit GitHub app; an existing file is backed up as `.bak` and overwritten. Off when omitted (kept on if `version.yml` already stores on). Unrelated to release notes |
| `--projects-sync` / `--no-projects-sync` | Include or exclude the GitHub Projects status sync workflow (excluded for new installs, kept if already installed) |
| `--language LANG` | Language of the issue/PR templates and bot messages written into your repo: `en` `ko`. New installs `en`; existing installs keep the stored value (`ko` if none) |
| `--label-style STYLE` | Status label names: `en` (`status: todo`) or `ko` (legacy `작업전`). New installs `en` |
| `--lang LANG` | Language of the **CLI screen**: `en` `ko`. Not the same as the language written into the repo (`--language`). Defaults to the system language, `en` in CI and with `--force` |
| `--remove-legacy` | Rename retired old-generation deployment workflows to `.bak` (default: only list them with delete commands) |
| `--json` | With `--mode options`: JSON output for machines rather than people |
| `--force`, `-y`, `--yes` | Skip all confirmations and use non-interactive defaults |
| `-v, --version` | Print the projectops version |
| `-h, --help` | Show help |

`--nexus` and `--npm-publish` (and `--no-nexus`, `--no-npm-publish`) are no longer used. Use `--publish nexus` and `--publish npm` instead.

> Mobile app types (`flutter`, `react-native`, `react-native-expo`) already include the store deployment workflows, so the deploy and publish questions are skipped entirely. For the detailed rules, see the [NPX wizard guide](./npx-wizard.md).

## Diagnosis: `doctor`

`--mode doctor` writes no files and only checks the state.

- Whether the template is installed in this folder, and how many workflows are installed
- Whether any unreplaced values (placeholders such as `__APPLICATION_YML_DIR__`) remain that would fail at deploy time
- The Secrets required by the installed workflows
- Whether the workflows declare `permissions`

If you pass the `GITHUB_TOKEN` environment variable, it also checks repository settings (permissions, merge methods, Secrets).

```bash
GITHUB_TOKEN=ghp_... npx projectops --mode doctor
```

## Running again (update)

Running it again in a project that is already integrated works as an update.

- **Workflows you changed are not overwritten.** They are skipped, the new template is saved in `.github/.projectops/incoming/`, and the CLI shows a command to compare them.
- **A run record is kept.** Logs, events and a migration guide accumulate in `.github/.projectops/logs/`, and this folder is excluded from git tracking automatically. If something goes wrong, ask your AI agent to "check the run log".
- Old workflows that were renamed are cleaned up automatically. For the detailed policy, see the migration section of the [NPX wizard guide](./npx-wizard.md).

> The old `template_integrator.sh` / `.ps1` reached end of support and were removed from the repository. Use `npx projectops`. ([Details](./template-integrator.md))
