# SUH DevOps Skills for Gemini CLI

This repository is both a GitHub project template and an agent skill package.
When working as Gemini CLI, treat `skills/` as the shared skill library.

## Skill Usage

Before acting on a task, check whether a local skill applies. Skill bodies live
at:

```text
skills/{skill-name}/SKILL.md
```

If a skill applies, read its `SKILL.md` first and follow its workflow before
editing files, creating issues, committing, or reporting completion.

Common routing:

| User intent | Skill |
|-------------|-------|
| Commit staged work | `skills/pro-commit/SKILL.md` |
| Analyze code without editing | `skills/pro-analyze/SKILL.md` |
| Create an implementation plan | `skills/pro-plan/SKILL.md` |
| Implement a planned change | `skills/pro-implement/SKILL.md` |
| Review code or changes | `skills/pro-review/SKILL.md` |
| Investigate failures, record findings | `skills/pro-note/SKILL.md` |
| Generate implementation reports | `skills/pro-report/SKILL.md` |
| Create or improve skills | `skills/pro-skill-creator/SKILL.md` |
| Create or register a GitHub issue, query or manage GitHub issues/PRs | `skills/pro-github/SKILL.md` |
| Deploy (main push → deploy PR) | `skills/pro-changelog-deploy/SKILL.md` |

## Repository Safety

This repository also initializes other projects. Be careful when editing:

- `.github/scripts/template_initializer.sh`
- `.github/workflows/`
- `template_integrator.sh`
- `template_integrator.ps1`
- `skills/`

Keep agent package files in this repository, but make sure generated projects do
not keep files such as `skills/`, `.claude-plugin/`, `.codex-plugin/`,
`gemini-extension.json`, `GEMINI.md`, or `AGENTS.md` after template
initialization.

Do not commit or push unless the user explicitly asks for it.
