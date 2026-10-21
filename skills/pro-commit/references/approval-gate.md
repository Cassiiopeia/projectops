# Approval gate · auto-approve setting

> When to read: when you reach Step 5 of SKILL.md (approval after proposing the message), or when the user says "go ahead automatically" / "ask me first" (Korean: "자동으로 진행해줘" / "확인받게 해줘").

## Decide auto-approve mode: read the value from config with the Read tool

Read the config file with the `Read` tool. **Look only at this one fixed path. Do not search with `ls` or globs, and do not dig through plugin caches (`~/.claude/plugins/cache/...`).**
- Windows: `C:\Users\<user>\.projectops\config\config.json`
- macOS/Linux: `~/.projectops/config/config.json`

Decide `auto_approve` from the `github` section. Precedence (check top to bottom, take the first value found):

1. `commit.auto_approve` of the `github.repos[]` entry with `owner == current OWNER && repo == current REPO`
2. `github.commit.auto_approve` (global default)
3. If neither exists, `false` (safe default: manual approval)

**Remember** the result as two values:

- `AUTO_APPROVE`: boolean (`true` / `false`)
- `CONFIG_HAS_KEY`: boolean (`true` if the key was found at level 1 or 2; `false` if neither exists, which is the first-run case)

`CONFIG_HAS_KEY=false` triggers **C. First-run automation offer** below.

> **Every path that writes the approval setting (A, C, and any "switch to automatic" / "ask me first" request at any time) applies Rule D below right before writing.**

> **Speak to the user only in natural language.** Never write key names or file paths such as "auto_approve", "config.json" or "commit section" in messages to the user. The user expresses intent in natural language ("go ahead automatically" / "ask every time") and the agent updates the config itself.

## A. Auto mode (`AUTO_APPROVE == true`)

Only show the message to the user, then go straight to Step 6. Do not wait for a reply.

```
🤖 This repo is set to commit without asking, so here is the message and I'm committing now.
   (To be asked every time again, say "ask me first".)

📝 Commit message:
{final commit message}

Committing.
```

> If the user sees the message and replies in natural language such as "ask me first", "switch to manual" or "confirm with me next time" (Korean: "확인받게 해줘", "수동으로 바꿔줘", "다음부턴 확인받아줘"), update `config.json` with Read/Write **before** running Step 6. If the key existed at level 1 (per repo), set that value to `false`; otherwise set level 2 (global) to `false` (apply Rule D). After the update keep the message as is and ask for approval again (switch to branch B).

## B. Manual mode (`AUTO_APPROVE == false`)

```
📝 Proposed commit message:

{final commit message}

Commit with this message?
1. Yes, commit
2. Change the type (feat/fix/refactor/docs/chore/test/style; add `!` such as `feat!` for a breaking change)
3. I'll edit the description
4. Cancel
```

Wait for the reply. **Never commit before the reply.**

- **1** → go to Step 6. If `CONFIG_HAS_KEY == false` (first run), run C below once, **right before** Step 6
- **2** → show the type list, take the input, rebuild the message → back to the start of the gate
- **3** → take only the description, rebuild the message → back to the start of the gate
- **4** → stop

## C. First-run automation offer (only when 1 was chosen in B and `CONFIG_HAS_KEY == false`, once)

```
💡 How should I handle commits from now on?

By default I show the message and ask you right before every commit.
If you like, I can skip this check and commit directly.

1. Commit in this repo without asking from now on
2. Commit in all repos without asking from now on
3. Keep asking me to confirm every commit message

(You can change this any time by saying "ask me first again" / "switch to automatic")
```

Depending on the reply, the agent updates `config.json` with Read/Write:

- **1** → add `commit.auto_approve: true` to the `github.repos[]` entry matching the current OWNER/REPO
- **2** → add `github.commit.auto_approve: true` (create the object if missing)
- **3** → add `github.commit.auto_approve: false` (keep the key itself so the next run does not ask again)
- **1, 2 and 3** → apply Rule D.

Then tell the user:

- 1: "✅ From the next commit, this repo commits without asking."
- 2: "✅ From the next commit, all repos commit without asking."
- 3: "✅ I'll keep asking you to confirm every commit message."

Then go to Step 6.

## D. Format lock rule (every time you write the approval setting)

**Whenever you write** `github.commit` or `github.repos[].commit` (the manual switch in A, the first-run offer in C, or any time the user says "switch to automatic" / "ask me first"), handle this in the same Write:

- If the user never chose a format (no `preset` or `template` in `skills.pro-commit` of the config or in `repos[].skills.pro-commit` of the current repo, and this run's `resolve-style` `source` is not `legacy-default`), also write `skills.pro-commit.preset: "conventional"`.
  This holds whether `source` is `default` or a team format (`team-default` / `version.yml`). A team-format repo does not use this value, but without it the approval key makes the next run classify the user as an "existing user" (`legacy-default` → `projectops`), so the format changes from conventional to projectops **in other repos**.
- If `source` is `legacy-default` (a long-time user), write nothing. Keep `projectops` as it is now.
- If `source` is `preferences`, or a `preset`/`template` already exists, leave it alone.
- Do not mention this key to the user (natural-language rule above).

> **When updating**: follow §4 of `../../references/config-rules.md`. Read the whole file first, keep the other sections, add or change only the key, then Write. Never drop the PAT or other repos entries.
