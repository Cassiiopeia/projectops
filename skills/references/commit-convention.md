# Commit message convention (detail)

This is the detail behind `common-rules.md` §"Commit message convention". Skills that propose commit messages use it.
The format itself is chosen by the person or team. The one thing to respect: if this repo uses `semver_auto`, the commit type decides the release version.

## Format (projectops team format as an example — the real format is what get-commit-template returns)

```
{issue title} : {type} : {description of the change} {issue URL}
```

| Type | Use |
|------|------|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Refactoring (no behavior change) |
| `docs` | Docs or comment changes |
| `chore` | Build, config, other |
| `style` | Code style (no logic change) |
| `test` | Add or change tests |

**Example** — when the issue title is `⚙️[기능추가][Skills] Add new commit skill`, the commit template made by
SUH-ISSUE-HELPER uses only the plain content, with the emoji and tags removed.

```
Add new commit skill : feat : generate commit messages from issue context https://github.com/Cassiiopeia/projectops/issues/224
Add new commit skill : docs : fix commit convention example in common-rules https://github.com/Cassiiopeia/projectops/issues/224
Add new commit skill : fix : fix owner/repo extraction bug https://github.com/Cassiiopeia/projectops/issues/224
```

## Core rules

- `{issue title}` is the leading part of the commit template made by SUH-ISSUE-HELPER, used **as is**. Do not include the emoji and tags (`⚙️[기능추가][Skills]`)
- `{type}` is decided by **what this commit changes**. `feat` is the default, but it is not always feat
- Several commits on the same issue can have different types (feat → fix → docs is possible)
- Use this format only when there is issue context. Commits unrelated to an issue (hotfix, config change, and so on) may use a free format
- When the user calls the `/commit` skill, this format is filled in automatically

Use the `template` from `github_cli.py get-commit-template "{issue title}" "{issue URL}" --repo-root "{PROJECT_ROOT}"` **as is**.
The type is inferred from the title tag (bug → `fix`, feature → `feat`, docs → `docs`, and so on). Change it with
`--type` only when the actual work differs from the tag.

## The commit type decides the release version (#546)

In a repo where `metadata.template.options.semver_auto` in `version.yml` is on, the commit titles in the release
range decide how far the version is bumped. Pick the type carelessly and the wrong version ships.

| Commit type | Release result |
|---|---|
| `title : feat! : content` (or `feat!:`) | **major** — 4.2.45 → 5.0.0 |
| `title : feat : content` | **minor** — 4.2.45 → 4.3.0 |
| `fix` / `docs` / `chore` / `refactor` / `test` | patch — 4.2.45 → 4.2.46 |

- **Add `!` only when compatibility breaks** — a change after which existing users' settings, APIs, or CLI
  arguments no longer work. If unsure, do not add it; ask the user.
- When types are mixed in one release range, the highest wins (major > minor > patch).
- In a repo where the key is missing or `false`, it is always patch, so the type does not affect the version.

## Issue-based commit principle

The issue number must be confirmed before committing. Take the number from the branch name (`YYYYMMDD_#number_title`)
(and check it with `github_cli.py get-issue`), or look up the issue by the number the user gave. If the branch
name has no number, as when committing straight to develop, ask the user for it. If you cannot confirm the
number, **stop immediately** and offer choices. Do not invent a commit message and commit anyway.
