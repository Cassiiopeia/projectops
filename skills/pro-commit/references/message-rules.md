# Commit message rules · mention cleaning

> When to read: when the type is unclear, when you need the issue title cleaning rule, or when you interpret a `sanitize-message` result (`removed: true`) or failure.

## Issue title cleaning (same as `extractIssueTitle` in SUH-ISSUE-HELPER)

Clean the `title` from `get-issue` deterministically. **Do not summarize or rewrite it.**

1. Remove every `[tag]` (`[버그]`, `[기능개선]`, `[Bug]`, and so on)
2. Remove leading emoji and control characters (So/VS16/ZWJ)
3. Trim surrounding whitespace. If the result is empty, use the original title

`commit_cli.py normalize-title "<title>"` applies the same rule. To build issue URL, cleaned title and type in one step, use
`commit_cli.py get-commit-template "<issue title>" "<issue URL>" [--type fix] [--scope S] --repo-root "{PROJECT_ROOT}"` (without `--type` the type is derived from the title tag, so pass it only when the tag and the actual work differ). The issue number for the current working directory is also available from
`commit_cli.py get-issue-number`.

## Type table

| Change | Suggested type |
|-----------|-----------|
| New feature, new file | `feat` |
| Bug fix, error handling | `fix` |
| Code structure change (same behavior) | `refactor` |
| Docs, comments, README | `docs` |
| Config files, build | `chore` |
| Add or change tests | `test` |
| Style, formatting | `style` |

**For a breaking change, add `!` after the type** (for example `feat!`, `fix!`, `chore!`).
On release this marker triggers a major bump (4.x.x → 5.0.0) (#546, in repos with `semver_auto` on).
Add it only when existing users' settings, API or CLI arguments stop working.
If unsure, do not add it (ask the user).

## Message format (default preset example)

`resolve-style` decides the real format (team `version.yml` `commit_template` > team-default in a repo with projectops installed > personal template/preset > `legacy-default` (`projectops`) for existing users > default `conventional`). A team `commit_type_map` also affects how a title tag maps to a type. The line below is only an example of the `projectops` preset.

`{clean_title} : {type} : {description} {html_url}`

| Part | How it is decided |
|------|-----------|
| `clean_title` | The cleaning result above, **as is**. The agent does not summarize or rewrite it again |
| `html_url` | The `get-issue` result, **as is** |
| `{type}` | Agent suggests it from the diff (user approves) |
| `{description}` | Agent writes it from the staged diff, following `language`, `tone`, `rules`, `examples` (user approves) |

- The agent decides freely **only the type and the description**.
- Never put an `@username` GitHub mention (`@claude` and so on) in `{description}`. If text copied from the issue body or title contains a mention, remove it first.
- Take the title from the user directly only when committing in free form without an issue.

## Mention trailer cleaning (`sanitize-message`)

Right before the commit, always remove an `@username` mention trailer at the end of the message (a sanitize step the skill enforces). It is the last line of defense if the writing step missed one.

> ⚠️ **Do not do this with shell `sed` (#523).** It used to be a one-line `sed -E ':a;$!N;$!ba;...'`. That label syntax is **GNU sed only**, so on macOS (BSD sed) it **passed silently with exit code 0 and let the input through unchanged.** The safety net looked on but was off. It moved to `commit_cli.py` so it does not depend on per-OS tools.

- Output JSON: `{"message": "<cleaned message>", "removed": true|false, "summary": "..."}`. If `removed` is `true`, a mention was really removed; go back to the writing step and find why it got in.
- **Never produce an empty message on failure.** If the script call fails or the result is empty, **stop the commit** (this prevents a broken `git commit -m ""`). The old sed approach reported failure as success; now the failure shows.
- Keep the cleaning rule **only** in `sanitize-message` in `commit_cli.py`. Do not copy the same regex into docs as a fallback. If the rule lives in two places, only one gets fixed and they drift (the same path that caused the sed incident).
- **Mentions in the middle of the body are kept.** A meaningful mention such as `fix for the @projectops build app trigger` stays; only a trailer **at the end** is removed.
