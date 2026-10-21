# Phase 4 — 8-principle self-review checklist

Shared by CREATE mode Phase 4 and REVIEW mode Phase 2.

**Mandatory procedure**: **always re-read the file you just wrote with the `Read` tool** and fill in the 8 checks below one line each. "I just wrote it, so I know without looking" is not allowed.

## Checklist

| # | Principle | PASS condition | Fix on violation | Evidence (where to check) |
|---|------|----------|-------------|-----------------|
| 1 | One at a time | No place in the Phase 0/Phase 2 sections puts 2 or more questions in one message? | Split the questions | Question examples in the SKILL.md body |
| 2 | Automatic inference first | Not asking again for values inferable from user input (URL → domain, compose → port, etc.)? | Change to automatic extraction | Scripts + SKILL.md instructions |
| 3 | Explain technical terms | Each abbreviation/proper noun has a one-line explanation where it first appears? | Add a one-line explanation | Skim the whole body |
| 4 | Concrete UI paths | UI directions are at the "menu → tab → field name" level? No "check it there" | Add path detail | Search for vague words like "check", "settings" |
| 5 | No hard-coding | No real domain/IP/email/employee ID baked into the body? | Replace with `{placeholder}` | `grep` for `.com`, `@`, IP patterns |
| 6 | Separate config file | Values that differ per user moved into a config file? | Add a config file definition | Check that config.json.example exists |
| 7 | Reflects real experience | Warnings written as "general advice" were verified by user experience? Unverified warnings only confuse | Delete or mark `(unverified)` | Skim the pitfalls section |
| 8 | Flexible input | Is there a branch that accepts it when the user gives all the information at once? | Add an automatic extraction branch | Argument parsing logic in scripts |

## Extra checks from the official skill-creator best practices (REVIEW mode only)

On top of the 8 principles, REVIEW mode also checks the 4 items below.

| # | Criterion | PASS condition | Fix on violation |
|---|------|-----------|-------------|
| a | Lean prompt | Are there decorative sentences or duplicate MUSTs that could go without changing results? | Delete |
| b | Explain the why | Do "do not" rules come with a reason? | Attach one line `(reason: ~)` |
| c | Progressive disclosure | SKILL.md ≤ 500 lines? If over, is it split into references/? | Split |
| d | Bundle repeated work | Is repeated logic moved into scripts/? | Extract into a script |

## If even one item FAILs

Fix SKILL.md immediately and check again. Repeat until there are 0 violations. Never declare "roughly fine" to the user.

## Special cases

- **The skill runs in a network-restricted environment** → read the "automatic extraction" of principle 2 (automatic inference) as "must work without external API calls".
- **The skill wraps a single command** → the phase split (Phase 0/1/2) may be omitted. The 8 principles still apply.
- **Description language** → write the `description` in English by default. If the users speak another language (for example a mixed Korean/English team), also include trigger keywords in that language. A single-language team may use only one.
