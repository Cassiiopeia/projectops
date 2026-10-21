# REVIEW · IMPROVE mode details

> When to read: when the mode was determined to be REVIEW (review an existing skill) or IMPROVE (apply review results).

## REVIEW mode — review an existing skill

### Register tasks

```
[review] Phase 1: Read the target skill files
[review] Phase 2: Compare against the 8 principles + official best practices
[review] Phase 3: Produce an issue report by priority
[review] Phase 4: User agreement (decide the scope of improvements)
```

### Phase 1 — Read the target skill files

Get the target path from the user or infer it from the conversation. Check SKILL.md, related scripts and config examples, all with `Read`. **Never judge from memory alone.**

### Phase 2 — Comparison check

Apply the 8 below plus the 4 best practices of the official skill-creator together.

**8 principles (reuses the CREATE Phase 4 checklist)**: `phase4_checklist.md` (same folder).

**Official skill-creator best practices**:

| # | Criterion | Check question |
|---|------|----------|
| a | Lean prompt | Are there sentences, MUSTs or ALWAYSes that could go without changing results? |
| b | Explain the why | Do "do not" rules come with a reason? Without one, the agent misjudges edge cases. |
| c | Progressive disclosure | SKILL.md ≤ 500 lines? If over, is it split into references/? |
| d | Bundle repeated work | Is logic repeated across calls moved into scripts/? Otherwise the agent rewrites it every time. |

### Phase 3 — Issue report by priority

Classify each issue as 🟥 (bug-level, fix now) / 🟨 (degrades UX, recommended) / 🟩 (nice to have) and organize them in a table. For each issue:

- **What the problem is** (evidence: quote the file and line)
- **How to fix it** (a concrete patch idea)
- **Why it matters** (the principle, the real side effect)

Print the report directly in the existing conversation. Do not create a separate file (unless told to).

### Phase 4 — User agreement

Ask the user "How much should I apply?". Options:
- "Only 1~2 (the essentials)"
- "Apply everything"
- "Just the review, stop here"

If **just the review**, stop here. Otherwise, move to IMPROVE mode.

---

## IMPROVE mode — apply improvements to an existing skill

### Register tasks

```
[improve] Phase 1: Finalize the list of patches to apply
[improve] Phase 2: Apply Edit/Write per file
[improve] Phase 3: Check the changes work (run them when possible)
[improve] Phase 4: Report a change summary + bump the frontmatter version
```

### Phase 1 — Finalize the list of patches to apply

From the review report, take only the items the user approved and make a list of "N patches". Mark the target file, change summary and risk level for each patch.

**Scope limit (targeted improvements only)**: if you find a problem outside the original scope while patching, **do not touch it on the fly**. Record it in the report as "related problem found: ~", and after the current patch, ask the user "Should I fix this too?".

> **Reason**: refactoring that starts with "since I am touching it anyway..." blurs the review scope, so the user cannot track what the patch contains. Fix problems in the code you are working on, but handle unrelated refactoring as a separate item.

### Phase 2 — Apply Edit/Write per file

- Changing an existing file → prefer `Edit` (minimal diff)
- Creating a new file → `Write`
- The same change in several files → do not do them all at once; confirm file by file

### Phase 3 — Check behavior

If the changed part is runnable code or configuration, **call it directly and look at the result** whenever possible (if the network blocks it, at least a parse test). Do not pass it with "the code should be right".

### Phase 4 — Change summary report

| Item | Content |
|------|------|
| Applied patches | number · target file · summary |
| Principle re-evaluation | Update the 8-principle table (mark improvements with ⭐) |
| Remaining room for improvement | Items not applied this time / follow-up suggestions |
| Version | Bump the frontmatter `version` (e.g. 1.0 → 1.1) |

The report format is shared with `phase6_report_format.md` (same folder).
