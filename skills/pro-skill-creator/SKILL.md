---
name: pro-skill-creator
description: Create, review or improve a standard skill. Classifies intent as create/review/improve, then runs the matching phases. Use for 'make a skill', 'review this skill', 'improve this skill'.
version: 2.3
---

# Skill Creator

## When to use

- "make a skill", "add a skill", "turn this into a skill" (Korean: "skill 만들어줘", "skill 추가해줘", "이거 skill로 만들자")
- "review this skill", "validate this skill" (Korean: "이 skill 리뷰해줘", "skill 검증해줘")
- "improve this skill", "fix this skill" (Korean: "skill 개선해줘", "skill 고쳐줘")
- "create a skill", "review this skill"
- On invocation, classify the user's intent as one of create/review/improve, then run that mode's phases. Enforces 8 principles, including one question at a time, automatic inference first, no hard-coding, and separate config.

This document is **a decision procedure, not an essay**. Run it top to bottom, and do not move to the next phase until the current phase's "exit condition" is met.

> **On invocation**: **determine the mode** in §1 below → register with `TaskCreate` → start at that mode's Phase 1. Do not write analysis or explanation first.
> **Decision rules**: if unclear, do not force an inference — ask right away. One message = one question. Never ask again for information already given. Confirm risky work before running it.
> **Language**: talk to the user in the user's language (or the configured `language` preference).

## Where to read

| What you are doing | Details |
|---|---|
| CREATE Phase 0 — agree on scope, approach, boundaries | `references/phase0_brainstorming.md` |
| CREATE Phase 1 — define the 6 slots, automatic inference | `references/phase1_slots.md` |
| CREATE Phase 2 — one-question-at-a-time format | `references/phase2_question_format.md` |
| CREATE Phase 3 · IMPROVE Phase 2 — meta principles for writing the body, the Python CLI 3-layer standard for new skills | `references/meta_principles.md` |
| Attaching official troubleshooting knowledge to a skill (`troubleshooting/`, `known_fix` in failure responses) | `references/meta_principles.md` §3 |
| CREATE Phase 4 · REVIEW Phase 2 — 8-principle checklist | `references/phase4_checklist.md` |
| CREATE Phase 5 advanced — quantitative optimization with the official `run_loop.py` | `references/trigger_optimization.md` |
| CREATE Phase 6 · IMPROVE Phase 4 — standard report format | `references/phase6_report_format.md` |
| Full REVIEW · IMPROVE procedure | `references/review_improve.md` |
| When stuck — failure patterns | `references/anti_patterns.md` |
| config / Python CLI skeleton | `templates/config.json.example` · `templates/python_cli_script.py` |

## 0. Hard constraints

Never violate these in any phase or mode. If you detect a violation, stop and say so.

| ID | Rule | Why it matters |
|----|------|-----------|
| H1 | **At most 1 question** per message | With several questions, the user answers only one or two, and the agent reads the rest as "declined" and proceeds on wrong guesses. |
| H2 | Never ask again for information the user already gave | "I just told you" — trust is lost. It is the agent's failure to extract it. |
| H3 | Do not put real domains, IPs, emails, employee IDs or company names in the SKILL.md body | When the skill moves to another project, someone else's account and company details are baked in and it becomes unusable. Use placeholders. |
| H4 | Values that differ per user go in a separate config, not in SKILL.md | PEM keys, PATs and accounts differ per teammate. Personal values in a shared document collide. |
| H5 | Explain a technical term in one line the first time it appears | If users get stuck on a term, they stop using the skill. |
| H6 | Give UI directions down to the menu path and field name | "Find it there" is useless once the UI changes. Breaking it down like "Control Panel → External Access → DDNS tab → Hostname column" lets users find the area even then. |

The remaining 2 principles (automatic inference first, flexible input) are enforced by the Phase 1 procedure.

## 1. Determine the mode

| Mode | Example trigger utterances | Go to |
|------|----------------|-----------|
| **CREATE** | "make a skill", "turn this task into a skill", "add a skill for ~" (Korean: "skill 만들어줘", "이 작업 skill로 만들자", "~에 대한 skill 추가") | §2 |
| **REVIEW** | "review this skill", "anything to fix?", "evaluate it", "check it" (Korean: "이 skill 리뷰해줘", "어디 고칠 거 있어?", "평가해줘", "점검해줘") | `references/review_improve.md` |
| **IMPROVE** | "apply the review results", "fix only items 1~4", "improve the skill + an existing skill named" (Korean: "리뷰 결과 반영해줘", "1~4번만 고쳐줘", "skill 개선해줘 + 기존 skill 지정") | `references/review_improve.md` |

**Priority**:
1. A specific **existing skill path** + "review"/"check" → REVIEW
2. A specific **existing skill path** + "improve"/"fix" → IMPROVE
3. Neither, and a new capability is proposed → CREATE
4. If unclear, ask once: "Should I create a new one, or review/improve an existing skill?"

After deciding, register the mode's task list with `TaskCreate` (CREATE below; REVIEW/IMPROVE in references).

## 2. CREATE mode — create a new skill

```
[create] Phase 0: Brainstorming (what to build and why)
[create] Phase 1: Absorb intent + automatic extraction
[create] Phase 2: Ask only for missing information, one at a time
[create] Phase 3: Write SKILL.md (+ config/scripts templates)
[create] Phase 4: 8-principle self-review
[create] Phase 5: Trigger utterance check (5 samples)
[create] Phase 6: Report to the user + agreement
[create] Phase 7: Check real invocation behavior
```

### Phase 0 — Brainstorming

- Goal: agree on scope, approach, boundaries and the relation to existing skills. Output: a one-line agreement on "what to build" + the chosen approach.
- Exit condition: scope is right / 1 approach chosen / boundaries clear / overlap resolved (all 4) → Phase 1.
- It can be short, but **do not skip it** — five minutes of design decides the quality of hundreds of calls. "Too simple to need design" is an anti-pattern.
- Procedure, the format for presenting 2~3 approaches, and scope criteria: `references/phase0_brainstorming.md`.
- **When you may skip it**: the user already stated scope, approach and the relation to existing skills. Even then, say in one line "Skipping Phase 0 because: ~".

### Phase 1 — Absorb intent + automatic extraction

- Keep a status table of the 6 slots `purpose`, `triggers`, `inputs`, `outputs`, `auto_extract`, `pain_points` **in memory only** (definitions and inference rules: `references/phase1_slots.md`).
- Exit condition: all 6 are "has value" or "inferable". 0 empty slots → Phase 3 / 1 or more → Phase 2.
- Show the user **only a one-line summary of the intent** and confirm with "Did I understand this right?" — showing the whole slot table overwhelms them.

### Phase 2 — Ask only for missing information, one at a time

One message = one slot (`references/phase2_question_format.md`). If the user answers several slots at once, take them all and re-check only the empty slots. If no slot is empty, skip this phase.

### Phase 3 — Write SKILL.md (+ config/scripts)

- Output: SKILL.md (required) + config.json.example (optional) + scripts/ (optional). Exit condition: the files exist + the required sections are present.
- Frontmatter: `name` and `description` required, `version` recommended.
- **Write the new skill's prose in English by default** (frontmatter `description`, headings and body). If the skill's users speak another language, add their trigger phrases next to the English ones in `description` and "When to use", and tell the skill to reply in the user's language. Use another language for the prose only when the user asks for it.
- Body skeleton:

```markdown
# {Skill Name}

## When to use
- Trigger scenario 1
- Trigger scenario 2
- (Also recommended: one line on when NOT to use it)

## Setup (only for skills that need a config file)

## Workflow
### Phase 0 — Gather information
### Phase 1 — Run
### Phase 2 — Verify / report

## Common pitfalls (from real experience)
```

- If you need scripts or a config, copy `templates/config.json.example` (the standard for separating accounts and URLs into settings) and `templates/python_cli_script.py` (stdlib CLI skeleton — UTF-8 console, SSL opt-out, structured errors). Python calls follow the **3-layer standard** and the router form "find the scripts once + reuse `{PYTHON} {SCRIPTS}/x_cli.py`" → `references/meta_principles.md` §2.
- How to write (give reasons, prefer multiple choice, length matched to complexity, confirm section by section, go back when needed): `references/meta_principles.md` §1.

### Phase 4 — 8-principle self-review

**Always re-read the file you just wrote with `Read`** and fill in the 8 checks one line each ("I just wrote it, so I know" is not allowed). Checklist and fixes: `references/phase4_checklist.md`. If anything FAILs, fix it and check again until there are 0 violations.

### Phase 5 — Trigger utterance check

The agent simulates this without a separate CLI.

1. **3 should-trigger** — utterances a user would really say, phrased without naming the skill directly.
2. **2 should-not-trigger** — nearby topics that must not invoke the skill.
3. For each, ask yourself "Would I call this skill from the description alone?" 5/5 passes; if any is wrong, fix the description and try again.

Quantitative optimization (the official `run_loop.py`) is optional — `references/trigger_optimization.md`.

### Phase 6 — Report to the user + agreement

Use the format in `references/phase6_report_format.md`. Report only when every row of the 8-principle table is ✅; if there is any ⚠️/❌, go back to Phase 4.

### Phase 7 — Check real invocation behavior (strongly recommended)

Offer "Shall we invoke it once now to test it?" — using it immediately exposes missing description triggers, script errors and config mismatches. If the user says "later", skip it.

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-skill-creator`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
