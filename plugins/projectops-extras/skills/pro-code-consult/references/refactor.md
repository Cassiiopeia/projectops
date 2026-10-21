# refactor — fix one item at a time, safely

> When to read: a cleanup request with a target, such as "fix that", "item 3 from before", "clean up the logos that drifted apart".

Principle: **same behavior, new structure only.** One item at a time, one smell at a time.

## 1. Proposal → approval

Show the 8 steps of `references/proposal-template.md` and **stop.** Do not change files before approval.

- Fill step 1 (repeated pattern) from `scan`, `deps` and `assets` results plus `file:line` in the source. Count how many places and how they differ
- If it is not the 3rd copy (2 places or fewer), do not propose extracting it — except brand assets, config values and legal text, which get a single source even at 2 places
- The name table follows `references/conventions.md` §2. Fix abbreviations, booleans without `is`, and meaningless names together

## 2. Pin the behavior (before fixing)

- Run the existing tests and confirm **they pass now**. If they are failing, do not refactor; report it first
- If screens or API responses may change, **take a baseline**:
  - Screens: capture the screen with `pro-launch` (light and dark, plus empty and error states if needed)
  - Flows: run the scenario with `pro-agent-test`
  - API: save the response with `pro-launch`'s `http`
- If there are neither tests nor a baseline, **first write a test that pins the current behavior** (the narrowest one)

## 3. One smell at a time

Order: delete dead code → remove duplication and extract common code → names and error handling → strengthen tests.
Run the existing tests at the end of each step. If they fail, revert only that step. Do not slip in unrelated cleanup.

- Deletion first: deleting comes before new abstractions
- No new dependencies (unless the user asks)
- Fix only comments attached to code you changed. If a comment above describes old behavior, fix it; leave comments on untouched code as they are

## 4. Compare (after fixing)

Capture again under **the same conditions** as step 2. If a screen or response differs, show the user whether it is an intended difference; if not, revert.
Do not call it done just because the tests pass.

## 5. Seal

- If you created a common point, add a **rule that blocks bypassing it** as `docs/architecture/rules/<id>.rule`
  - If you fixed every place this time, no `.allow` (zero exceptions)
  - If you fixed only some, freeze the rest with `ledger PATH freeze --rule <id>`
- If you fixed violations of an existing rule, run `ledger PATH tighten` → confirm `ledger PATH check` passes
- `scan PATH --record`

## 6. Review · commit

- **Separate the fixer from the reviewer.** Give the diff and the proposal to `pro-review` (or a separate subagent) to look for behavior changes, remaining duplication and weak tests
- Run check mode once on this change (`diff PATH`) — to confirm the refactor did not create new smells
- Commit with `/pro-commit`. The commit type is `refactor`
