# audit — full review

> When to read: "look over the whole thing", "audit", "feels like a mess", or "tidy things up" when there is no frozen list yet.

Goal: find problems with evidence, and **freeze the current violations so they do not grow.** Do not stop at a report.

## 1. Start with what to carry over

Start with `detect PATH`.

- If `prior_audits` exists, **read it and re-judge each item against the current state** (fixed / unchanged / worse). Do not rewrite from scratch.
- If `allowlists` or `rule_tests` exist, they are enforcement the repo already uses. Do not create the same rule again in `docs/architecture/rules/`; first propose extending that mechanism.
- If `has_architecture_folder` is true (this skill's `rules/` or `CONVENTIONS.md` exists), check the current state with `ledger PATH check` and `conventions PATH check`.
- If the earlier audit is only an md file with no numbers, put "no numbers" in the report's "previous audit" column, and carry over only the current state of each of that document's items as a table.
- Do not audit `flutter_host_of` in `stacks` (the `android/` of a Flutter app) as a separate stack.

## 2. Collect facts

```
scan PATH --limit 50
assets PATH
deps PATH
rule-docs PATH
```

How to read the output: `references/facts.md`. Numbers are only candidates — report as a problem only what you confirmed in the source.

- **The audit scope is code the repo owns.** scan and deps already excluded installed, generated and external library code (`excluded`). Add one line to the report saying what was excluded.
- **Open samples in `review_order` order.** For each category, open up to 10 from the top to separate real hits from false positives. Do not report numbers for a category with a high false-positive rate.
- **Check "What scan cannot see" in `facts.md` yourself.** In real runs, the most dangerous problems (a catch that keeps going after rollback, a test API open in production, token handling in 3 places) came from outside the CLI or from its judgment hints.

## 3. Per-stack audit (parallel)

Start one read-only subagent per stack (or per monorepo folder). The prompt must include:

- Read that folder's `CLAUDE.md`, `AGENTS.md` and `.claude/rules` **first**. Rule documents are also audit targets (contradictions with code, references to missing files)
- The `references/conventions.md` criteria and the "Common AI smells" in `references/stacks/<stack>.md`
- Only that folder's facts: `scan PATH --only <folder> --limit 30` (do not pass the full JSON — it is tens of KB and the agent reads only the start)
- Requirements: `file:line` evidence, no guessing, severity (high/med/low), a "could not verify" list, top 10 priorities, under 700 words
- Also ask for what is done well — those are patterns to move to other folders

Assign one separate audit agent to cross-stack issues (asset copies, drift in token values, server enum ↔ client strings, hand-copied API types).

## 4. Judgment criteria

- **Be strict.** "Not bad for AI" is not the bar. Ask whether a person could maintain this code for a year.
- Judge by **section**, not by repo. Even a repo written by people has vibe-coded sections mixed in.
- When the same problem appears in many places, group it into **one cause line** (for example: "the common loading component is not documented, so 12 places each built their own").
- When a rule document **invites** a problem, that is the root cause (`prose_comment_inducing` in `rule-docs`).
- **When the repo's rules differ from the skill's criteria, the repo wins.** Do not report as violations what the repo's CLAUDE.md explicitly decided (for example "return entities as is", "presentation → data is allowed inside one feature"); if it is worth changing, list it separately as "team decision needed". The same applies to edges an existing exception list allows.
- Names that would break a contract if changed (`contract` tag) go into a separate "migration plan" item, not the fix list.

## 5. Report · freeze proposal

1. `get-output-path PATH --title "<title>"` → write in the `references/report-template.md` format (it only returns the path — the folder is created when you write the report. If `previous_audits` exists, carry it over)
2. For each repeated pattern, append a **candidate rule to freeze** (a `.rule` draft) at the end of the report. Start from "First rule candidates" in `references/stacks/<stack>.md`, but fit the pattern and `paths` to **this repo's real repeated problems** (`bypassed_components`, the audit Top 10). Check each draft's current violation count with a `ledger` verdict; if it is 0, the rule blocks nothing, so drop it or fix the path
3. Show the user the report summary and the candidate list, and create **only the approved rules**
4. For each rule, run `ledger PATH freeze --rule <id>` → confirm `ledger PATH check` passes
5. If there are no rule tests yet, propose `install-tests` (`references/init.md` step 5)
6. Record baseline numbers with `scan PATH --record`

Let the user choose the next action: "Which of the top 10 should I refactor first?"
