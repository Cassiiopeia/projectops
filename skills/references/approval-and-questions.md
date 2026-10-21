# Approval gate and key questions standard

The single standard for how a skill that produces an artifact (an md file) **gets user confirmation before
saving**, and **what it must ask before starting**.

Applies to: `report` · `review` · `testcase` · `oss-consult`

> Commit (`commit`), deploy (`changelog-deploy`), and issue creation (`github`) already use the same pattern.
> This document extends that proven approach to artifact skills (#526). Do not invent a new one.

Show every message template below in the user's language (or the configured `language` preference). The
English text is the reference wording, not a fixed string.

---

## 1. Why it is needed

Saving without confirmation meant that when the direction was wrong, the file had to be deleted and the work
redone from scratch. Starting without asking about scope once led to analyzing the whole repository when the
user wanted one module. Skills that ask or do not ask inconsistently is itself a consistency problem.

---

## 2. Before starting — the conversation comes first

**Before investigating, check whether the conversation already has the answer.** If the work was done in the
same conversation, what was done and why is already there. Investigating again gathers the same information
twice and only spends more tokens.

```
Already in the conversation   → use it as is (do not investigate again)
Not in the conversation       → investigate only that
Called without a conversation → investigate from scratch, as before
```

In particular, **"why it was done that way" and "the traps hit along the way" cannot be recovered from files
or the diff.** They exist only in the conversation, so when they are there, use them. If you miss them, the
artifact becomes an empty shell that only says "what was done".

---

## 3. Before starting — key questions

**Do not ask about everything.** If the answer is already clear, do not ask; proceed. The list below holds
only items where *the answer changes the result a lot*.

### Deciding whether to ask

| Situation | Action |
|------|------|
| The user's input already has the answer | **Do not ask** (for example "analyze only the payment module" → scope is fixed) |
| The repository structure allows only one answer | **Do not ask** (for example the analysis scope of a single-module project) |
| Depending on the answer, the whole artifact would have to be redone | **Ask** |
| A minor choice that is easy to undo | Do not ask; proceed with a sensible default and state what you chose in the result |

**One question at a time.** Do not bundle several questions together.

### Key questions per skill

| skill | What to ask | When you do not need to ask |
|---|---|---|
| `review` | Which angle to focus on this time, the lowest severity to report | Stated in the input, or the diff is small enough to review entirely |
| `testcase` | Target level, existing test framework | The framework is clearly detected in the repository |
| `report` | Who will read it (internal team / client) | Stated in the input |
| `oss-consult` | The repo owner's goal (stars, portfolio, real users, recruiting contributors); for a batch audit, the target scope (include other orgs / private repos?) | Stated in the input, or the step only collects facts and the goal does not affect the score |

Offer the question as choices, with the recommended option as number 1.

```
How should I scope the analysis?

1. The whole repository (recommended — for a codebase you have not seen before)
2. A specific folder or module only (tell me the path)
```

---

## 4. Before saving — the approval gate

Apply this **right before saving the artifact to a file**. It is the same three-way A/B/C split used by
`commit` and `changelog-deploy`.

### Reading the setting (once at start)

Read the config with the procedure in `config-rules.md` §2~3 and determine `auto_approve`.

Resolution order (take the first value found):

1. `<skill_id>.auto_approve` in the `github.repos[]` entry for the current OWNER/REPO
2. `output.auto_approve` (the shared default for artifact skills)
3. If neither exists, `false` (safe default — manual approval)

Remember two values:

- `AUTO_APPROVE` — boolean
- `CONFIG_HAS_KEY` — `true` if the key was found in 1 or 2 above, `false` if not (first run)

> **⚠️ Auto-approval applies only to saving the artifact (md).** In a skill that changes someone else's repo,
> such as `oss-consult`, approval for repo-changing actions (API edits, file commits) is **always per repo**,
> regardless of `AUTO_APPROVE`. A blanket delegation like "apply everything" or "just handle it" does not replace it.

### A. Automatic mode (`AUTO_APPROVE == true`)

Show only a summary and save immediately. Do not wait for a reply.

```
🤖 This repository is set to save without confirmation, so here is a summary before saving.
   (If you want to confirm every time again, just say "ask me first".)

📄 {title}
   {3–5 line summary of the key content}
   Location: {path}

Saving now.
```

> If the user replies in natural language such as "ask me first", update the config **before** saving and switch to branch B.

### B. Manual mode (`AUTO_APPROVE == false`)

```
📄 {title}

{artifact summary or key sections}

Location: {path}

Save it as is?
1. Yes, save it
2. I'll tell you what to change
3. Don't save; I just want to see the content
```

- **1** → Save. If `CONFIG_HAS_KEY == false`, run [C] once, **right before** saving
- **2** → Apply the instructions, rewrite, and return to the start of this step (repeat until approved)
- **3** → End without saving

### C. First-run automation offer (chose 1 in B + `CONFIG_HAS_KEY == false`, once only)

```
💡 How should I proceed next time?

By default I show you the content and ask for confirmation right before every save.
If you like, I can skip this step and save right away.

1. Save without confirmation from now on, in this repository
2. Save without confirmation in all repositories
3. Keep asking me every time

(You can change this any time by saying "ask me first again" or "switch to automatic".)
```

Update the config with Read/Write based on the reply:

- **1** → `<skill_id>.auto_approve: true` in the `github.repos[]` entry for the current OWNER/REPO
- **2** → `output.auto_approve: true`
- **3** → `output.auto_approve: false` (keep the key itself so you do not ask again)

Updates follow the rules in `config-rules.md` §4: Read the whole file, change only that key, then Write. Never drop the PAT or any other entry.

---

## 5. Absolute rules

- **Never show setting key names or file paths to the user.** Do not use words like `auto_approve` or
  `config.json` in messages to the user. The user states intent in natural language, such as "just go ahead
  automatically"; the agent interprets and stores it.
- **Even in automatic mode, show what is being saved.** Do not save silently.
- **Ask only when the answer changes the result.** Questions asked for form's sake only add friction.
- **Do not build paths yourself.** Get the save location from each skill CLI's `get-output-path` (`doc-output-path.md`).
