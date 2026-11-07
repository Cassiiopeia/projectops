# Project notes: do not search twice

> When to read: `start` says the notes are missing or changed, or you just learned how this project's design works.

Three layers personalize this skill. Do not mix them.

| Layer | Holds | Where |
|---|---|---|
| Expression | Language, tone, extra rules for what you write | `preferences` · `skills.pro-ui-design` (`../../references/preferences.md`) |
| Behavior | Destination, designer, devices, themes, idle time | `ui_design_cli.py config` (`config options` lists every option) |
| Project knowledge | Token files, fonts, components, how to render, past decisions | The notes below |

## The notes

They are a `pro-launch` repo-scoped harness named `ui-design`, so `launch_cli.py harness list` and `show` see them too.

| File | Content |
|---|---|
| `README.md` | What the next agent should read: summary, tokens, fonts, components, render, avoid, decisions |
| `tokens.json` | The candidate files and their hashes, so a changed file is noticed |

## First use in a project

1. `start` reports `project_profile.exists: false`.
2. `tokens`, read the candidates, make the mockup.
3. After the first mockup works, ask the user once: "Save this project's design info so next time is faster?" Do not ask again in that session.
4. On yes: `tokens --save`, then fill in the README from what you read.

## Later uses

`start` returns the summary as `excerpt` and the path as `readme`. Read the README instead of searching again.
If `changed_files` is not empty, reread those files, update `tokens.css` and the README, then run `tokens --save`.

After a decision, add one line under `## Decisions`: what was chosen and why. It stops the next session from proposing what was already rejected.

**Never write secrets, tokens or passwords in the notes.** They stay on this computer and are not shared with teammates.
