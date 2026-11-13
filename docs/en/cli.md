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
| `--deploy-trigger-branch NAME` | Branch whose push runs the deploy workflows. Set it only when it differs from the default branch (default: the default branch) |
| `--create-development-branch` | Non-interactive runs: create the development branch from the default branch and push it to origin when it is missing. Does nothing if it exists. The push never asks for credentials, so a remote that needs a login fails at once instead of waiting; a failed push does not fail the run and the summary prints the command to run yourself (default: off) |
| `--secret-backup` / `--no-secret-backup` | Include or exclude the Secret backup workflow |
| `--ai-summary` / `--no-ai-summary` | Include or exclude the PR change summary workflow |
| `--coderabbit` / `--no-coderabbit` | Install the CodeRabbit PR code review config (`.coderabbit.yaml`), `--mode full` only. Needs the CodeRabbit GitHub app; an existing file is backed up as `.bak` and overwritten. Off when omitted (kept on if `version.yml` already stores on). Unrelated to release notes |
| `--projects-sync` / `--no-projects-sync` | Include or exclude the GitHub Projects status sync workflow (excluded for new installs, kept if already installed) |
| `--ci-minutes-saver` / `--no-ci-minutes-saver` | Save Actions minutes in private repos: CI runs on PRs only and skips docs-only changes; the iOS build and Secret backup run only on manual dispatch (default: off) |
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

## Full option reference

Every flag and every `version.yml` key, with values and defaults.
This section is generated from `src/core/options-schema.js`, the same source as `npx projectops --mode options --json`.
After changing that file, run `node scripts/build_options_reference.mjs` to refresh it.

<!-- generated: options -->
<!-- Do not edit by hand. Source: src/core/options-schema.js. Rebuild: node scripts/build_options_reference.mjs -->

### CLI flags

| Flag | `version.yml` key | Values / default | Description |
|---|---|---|---|
| `-m`, `--mode MODE` |  | values: `interactive` `full` `version` `workflows` `issues` `skills` `doctor` `options`; default: interactive | What to do. Agents and CI should always pass an explicit non-interactive mode together with --force. |
| `-t`, `--type CSV` |  | values: `spring` `flutter` `react` `react-native` `react-native-expo` `node` `python` `basic`; default: auto-detected | Project types, comma separated. The first one is the primary type. |
| `--project-version VERSION` |  | default: auto-detected | Initial version of the target project (x.y.z). |
| `--paths type=path,...` | `project_paths` | default: repo root | Per-type project folders for monorepos, e.g. flutter=app,react=client. |
| `--intent KIND` | `metadata.template.options.intent` | values: `app` `library` `both` `none` `manual`; default: inferred from --deploy/--publish | Project kind. Decides whether deploy and publish questions are asked. |
| `--deploy TARGET` | `metadata.template.options.deploy` | values: `docker-ssh` `vercel` `none`; default: docker-ssh | Where the app is deployed. Pick one. |
| `--publish CSV` | `metadata.template.options.publish` | values: `nexus` `npm` `github-packages`; default: none | Registries a library is published to. Several allowed. |
| `--deploy-branch NAME` | `metadata.development_branch` | default: develop | Development branch: the head of the release PR. Not the repository default branch. |
| `--deploy-trigger-branch NAME` | `metadata.template.options.deploy_trigger_branch` | default: the default branch | Branch whose push runs the deploy workflows. Only when it differs from the default branch. |
| `--create-development-branch` |  | default: off | Non-interactive runs: create the development branch from the default branch and push it to origin when it does not exist. |
| `--language LANG` | `metadata.template.options.language` | values: `en` `ko`; default: en for new installs, ko for existing installs | Language of issue/PR templates and bot messages written into the repo. |
| `--label-style STYLE` | `metadata.template.options.label_style` | values: `en` `ko`; default: en for new installs, ko for existing installs | Status label names: en = 'status: todo', ko = legacy Korean names. |
| `--secret-backup`, `--no-secret-backup` | `metadata.template.options.secret_backup` | default: excluded | Include / exclude the workflow that uploads GitHub Secrets to a server over SSH. |
| `--ai-summary`, `--no-ai-summary` | `metadata.template.options.code_review.ai_summary` | default: included | Include / exclude the workflow that comments an AI summary on work PRs. |
| `--coderabbit`, `--no-coderabbit` | `metadata.template.options.code_review.coderabbit` | default: off unless version.yml already says on | Install the CodeRabbit code review config (.coderabbit.yaml). Only --mode full installs it. |
| `--projects-sync`, `--no-projects-sync` | `metadata.template.options.projects_sync` | default: excluded for new installs; kept if already installed | Include / exclude the GitHub Projects status sync workflow. Needs a PAT secret and PROJECT_URL variable. |
| `--ci-minutes-saver`, `--no-ci-minutes-saver` | `metadata.template.options.ci_minutes_saver` | default: off | Cut GitHub Actions minutes for private repos: CI runs on PRs only and skips docs-only changes, the iOS (macOS) CI build runs only on manual dispatch, secret backup runs only on manual dispatch. |
| `--remove-legacy` |  | default: off | Rename retired old-generation workflows to .bak. Without it they are only listed in the summary and in doctor. |
| `-y`, `--yes`, `--force` |  | default: off | Skip every confirmation and use non-interactive defaults. Required for agents and CI. |
| `--lang LANG` |  | values: `en` `ko`; default: system language; pinned to en in CI and with --force | Language of the CLI screen. Not the language written into the repo (that is --language). |
| `--json` |  | default: off | With --mode options: print machine-readable JSON instead of a table. |
| `-v`, `--version` |  |  | Print the projectops package version and exit. |
| `-h`, `--help` |  |  | Print the human-readable help and exit. |
| `--nexus`, `--no-nexus` |  |  | (deprecated) Use --publish nexus. Also implies --deploy none. |
| `--npm-publish`, `--no-npm-publish` |  |  | (deprecated) Use --publish npm. |

### `version.yml` keys

| Key | Type | Values / default | Set by | Description |
|---|---|---|---|---|
| `version` | string |  | workflow-managed | Project version (x.y.z). The single source of truth; workflows sync it into build files. |
| `version_code` | integer |  | workflow-managed | App build number. +1 on every release. Android release only; iOS and test builds use build_number.py. |
| `project_types` | string[] |  | wizard | Project types; the first is primary. Do not change after setup. |
| `project_paths` | map |  | wizard (--paths) | Per-type project folder relative to the repo root (monorepo). |
| `metadata.default_branch` | string | default: main | wizard | Repository default (production) branch. Pushes here deploy. |
| `metadata.development_branch` | string | default: develop | wizard (--deploy-branch) | Development branch: head of the release PR. Old name deploy_branch is still read and written with the same value. |
| `metadata.template.options.intent` | enum | values: `app` `library` `both` `none` `manual` | wizard (--intent) | Project kind; derives the deploy and publish questions. |
| `metadata.template.options.deploy` | enum | values: `docker-ssh` `vercel` `none`; default: docker-ssh | wizard (--deploy) | Where the app is deployed. |
| `metadata.template.options.publish` | enum[] | values: `nexus` `npm` `github-packages`; default: `[]` | wizard (--publish) | Library registries. |
| `metadata.template.options.secret_backup` | boolean | default: `false` | wizard (--secret-backup) | Secret-to-server upload workflow installed. |
| `metadata.template.options.semver_auto` | boolean | default: `true` | by hand | Decide the release bump from commit titles: 'type!:' = major, 'feat:' = minor, anything else = patch. Applies both to the release PR and to direct pushes to the default branch. |
| `metadata.template.options.close_on_release` | boolean | default: true for new installs; missing for existing installs | by hand | A release merge closes issues that carry the done label and are referenced by a release commit. |
| `metadata.template.options.language` | enum | values: `en` `ko` | wizard (--language) | Issue/PR template and bot message language. |
| `metadata.template.options.deploy_trigger_branch` | string | default: the default branch | wizard (--deploy-trigger-branch) | Branch whose push runs the deploy workflows (app store, server, package publish). |
| `metadata.template.options.ci_minutes_saver` | boolean | default: `false` | wizard (--ci-minutes-saver) | Install the CI workflows in their Actions-minutes-saving form (PR-only CI, docs-only changes skipped, iOS CI build and secret backup on manual dispatch only). |
| `metadata.template.options.label_style` | enum | values: `en` `ko` | wizard (--label-style) | Status label names. |
| `metadata.template.options.projects_sync` | boolean |  | wizard (--projects-sync) | Projects status sync workflow installed. |
| `metadata.template.options.app_release` | boolean |  | by hand | Releases go through App Store / Play Store review. Release notes get a review warning banner. Never auto-enabled. |
| `metadata.template.options.excluded_workflows` | string[] |  | by hand | Workflow file names the update must never install. Deleted files are also not restored; a copy is kept in .github/.projectops/incoming/. |
| `metadata.template.options.store_locales` | string[] |  | by hand | Store release-note languages, first is the default (for example ["ko-KR", "en-US", "ja-JP", "zh-CN"]). Missing = one text for every store language, as before. Per-language text comes from store_notes in CHANGELOG.json; a language without text gets the default-language text (the stores reject an empty What's New). |
| `metadata.template.options.store_locales_ios` | string[] |  | by hand | Only when the App Store languages differ from store_locales: the App Store uses this list instead. fastlane deliver ACTIVATES every language folder the app version does not have yet, so a language the App Store listing lacks must not be in this list. |
| `metadata.template.options.store_locales_play` | string[] |  | by hand | Only when the Play languages differ from store_locales: Google Play uses this list instead. |
| `metadata.template.options.code_review.coderabbit` | boolean |  | wizard | CodeRabbit config installed. |
| `metadata.template.options.code_review.ai_summary` | boolean | default: `true` | wizard (--ai-summary) | AI PR summary workflow installed. |
| `metadata.template.options.changelog.provider` | enum | values: `copilot` `coderabbit` `openai` `gemini` `claude` `groq` `mistral` `ollama` `commit`; default: commit | by hand | Release note generator. 'commit' is free and always works; AI keys are picked up automatically when registered as secrets. |
| `metadata.template.options.changelog.base_url` | string |  | by hand | Only for provider ollama. |

<!-- /generated -->

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
