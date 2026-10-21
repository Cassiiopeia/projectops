# projectops documentation index

For an overview of the whole project, read the [root README](../../README.md) first. This page guides you through the documents in `docs/` by purpose.

---

## Getting started

| Document | Contents |
|------|------|
| [NPX wizard guide](./npx-wizard.md) | Integrate or update the template in an existing project with `npx projectops`. Project kind (intent), the two deploy/publish axes, automatic legacy migration |
| [Agent Skills guide](./skills.md) | The 14 Skills used in Claude Code / Cursor / Gemini CLI / Codex CLI |
| [Integration script guide](./template-integrator.md) | End of support and removal of the old `template_integrator.sh`/`.ps1` |

---

## Automation

| Document | Contents |
|------|------|
| [Version control](./version-control.md) | `version.yml`, automatic version bumps, multi-type and monorepo paths |
| [Changelog automation](./changelog-automation.md) | Release PR flow, release note provider ladder, CodeRabbit integration |
| [Issue automation](./issue-automation.md) | Issue Helper comments, QA bot, label sync, issue templates |
| [Branch naming convention](./branch-convention.md) | The `YYYYMMDD_#number_title` format and the consumers that depend on it (for maintainers) |
| [GitHub Projects sync](./projects-sync.md) | Two-way sync between Issue Labels and Projects Status |
| [Projects sync wizard](./github-projects-sync-wizard.md) | Setup wizard for the Status -> Label direction (Cloudflare Worker) |

---

## Deployment

| Document | Contents |
|------|------|
| [SSH + Docker deployment guide](./ssh-docker-deployment-guide.md) | Spring and Python server deployment, zero-downtime deployment (Traefik/Nginx), Flutter APK SMB upload |
| [PR Preview](./pr-preview.md) | Deploy and clean up a temporary server with a one-line comment |

---

## Flutter CI/CD

| Document | Contents |
|------|------|
| [Flutter CI/CD overview](./flutter-cicd-overview.md) | Overall architecture, workflow list, **full list of GitHub Secrets** |
| [TestFlight wizard](./flutter-testflight-wizard.md) | Generates iOS deployment settings |
| [Play Store wizard](./flutter-playstore-wizard.md) | Generates Android Play Store deployment settings |
| [Firebase App Distribution wizard](./flutter-firebase-wizard.md) | Generates Firebase tester distribution settings |
| [Test build trigger](./flutter-test-build-trigger.md) | APK and TestFlight test builds from PR or issue comments |

---

## For contributors

| Document | Contents |
|------|------|
| [Workflow comment standard](./workflow-comment-guidelines.md) | Workflow comment conventions, type classification, **complete per-file status list** |
| [Branch naming convention](./branch-convention.md) | Consumers that break when the convention changes, and the extension procedure |
| [CONTRIBUTING](../../CONTRIBUTING.md) | How to contribute |
| [CLAUDE.md](../../CLAUDE.md) | Project rules for agents (working branch, issue handling, extension rules) |

---

## Troubleshooting

| Document | Contents |
|------|------|
| [Troubleshooting](./troubleshooting.md) | Problems with Actions, versions, changelogs, PR Preview, SSH deployment, Flutter builds |

---

## Output folders

| Path | Purpose |
|------|------|
| `docs/projectops/` | Skill outputs (issues, reports, plans, reviews, etc.). Local only, not tracked in the repository |
| `docs/superpowers/` | Design documents (specs) and implementation plans (plans). Local only, not tracked in the repository |
| `docs/qa/` | QA records |

> These folders are **work records** and reflect the facts at the time they were written. Always check current behavior against the documents at the `docs/` root and the actual workflows and source.
