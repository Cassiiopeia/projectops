# SUH DevOps Skills Agent Instructions

This repository is both a GitHub project template and an agent skill package.
For Codex and other agents, `skills/` is the shared local skill library.

## Required Skill Flow

Before responding with an implementation, issue, commit, review, or debugging
result, check whether a local skill applies. Skill bodies live at:

```text
skills/{skill-name}/SKILL.md
```

If a skill applies, read the relevant `SKILL.md` and follow it. Codex does not
need a slash-command skill UI for this repository; use the local files directly.

Common routing:

| Request | Use |
|---------|-----|
| "커밋해줘", "commit" | `skills/pro-commit/SKILL.md` |
| "분석해줘", "영향 범위 봐줘" | `skills/pro-analyze/SKILL.md` |
| "계획 세워줘", "plan" | `skills/pro-plan/SKILL.md` |
| "구현해줘", "수정해줘" | `skills/pro-implement/SKILL.md` |
| "리뷰해줘" | `skills/pro-review/SKILL.md` |
| "뭔가 안 돼", "원인 찾아줘", 알아낸 것 기록 | `skills/pro-note/SKILL.md` |
| "작업 보고서 작성" | `skills/pro-report/SKILL.md` |
| "스킬 만들기/개선" | `skills/pro-skill-creator/SKILL.md` |
| "이슈 작성", "issue", "GitHub 이슈 만들어줘", "GitHub 이슈/PR 조회·관리" | `skills/pro-github/SKILL.md` |
| "배포", "deploy PR" | `skills/pro-changelog-deploy/SKILL.md` |
| "원격 서버 접속", "SSH" | `skills/pro-ssh/SKILL.md` |

## Codex Installation Model

**Method 1 (recommended):** Plugin marketplace source registration:

```bash
codex plugin marketplace add Cassiiopeia/projectops
```

After registering, open `/plugins` in Codex and verify the `projectops` entry.

**Method 2 (fallback):** Direct clone + symlink for immediate activation without
marketplace:

```bash
git clone https://github.com/Cassiiopeia/projectops.git ~/.codex/projectops
mkdir -p ~/.agents/skills
ln -s ~/.codex/projectops/skills ~/.agents/skills/projectops
```

Codex reads `.agents/plugins/marketplace.json` to discover the marketplace entry
and `.codex-plugin/plugin.json` to load the plugin metadata.

## Repository Safety

This repository is also used as a template for new projects. Agent package files
belong here, but should be removed from generated projects by the initializer:

- `AGENTS.md`
- `GEMINI.md`
- `gemini-extension.json`
- `.agents/`
- `.claude-plugin/`
- `.codex-plugin/`
- `.cursor/`
- `skills/`

Be especially careful when editing `.github/scripts/template_initializer.sh`,
`.github/workflows/`, `template_integrator.sh`, and `template_integrator.ps1`.
Do not push unless the user explicitly asks for it.
