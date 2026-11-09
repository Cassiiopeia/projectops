# refactor — fix one item at a time, safely

> When to read: a cleanup request with a target, such as "fix that", "item 3 from before", "clean up the logos that drifted apart".

Principle: **same behavior, new structure only.** One item at a time, one smell at a time.

## 1. Proposal → approval

Show the 8 steps of `references/proposal-template.md` and **stop.** Do not change files before approval.

- Fill step 1 (repeated pattern) from `scan`, `deps` and `assets` results plus `file:line` in the source. Count how many places and how they differ
- If it is not the 3rd copy (2 places or fewer), do not propose extracting it — except brand assets, config values and legal text, which get a single source even at 2 places
- The name table follows `references/conventions.md` §2. Fix abbreviations, booleans without `is`, and meaningless names together

## 1.5 Look wide (before the proposal is final)

Run once, before you show the proposal. Both return a short summary; do not ask for more than `--limit`.

- `copies PATH --name <identifier> --value <literal> --file <asset>` for what you are about to change: every copy across code, native (`android/`, `ios/`), web, config, docs, store metadata and assets. Fill the "Copies" line of proposal step 1. A kind with hits that stays out of scope needs a reason
- `cochange PATH --target <file>` for the main files you will touch: partners that usually change with them. A partner with a high `ratio` that this change does not touch goes into scope, or the proposal says why not. `is_referenced: false` means the two files never name each other: that coupling is invisible in the code, so check it by reading both

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

## 6. Wide review (inside this skill) · commit

**Separate the fixer from the reviewer, but keep it in this skill.** Start one read-only reviewer subagent. Do not hand off to another review skill.
Give it the diff, the proposal, and from step 1.5 only the short lists: `cochange` partners **not touched** by this change and `copies` **left** out of scope.

The reviewer checks, for each changed code path:

| Check | Question |
|---|---|
| Missed partner | A partner that always changed with this file was not changed: should it have been? |
| Diverged copy | A remaining copy still has the old behavior: do the two now disagree? |
| Empty · null | Empty list, empty string, null or missing key, first run with no saved state |
| Error path | Exception, failed request, timeout, permission denied: same handling as before? |
| Boundaries | 0, 1, maximum, last page, exactly at a limit |
| Repeat · concurrency | Called twice, re-entered, double tap, two requests in flight |
| Platform | iOS, Android, web, Windows path and encoding (cp949, non-ASCII paths) |

- On a suspicion, **write the narrowest pinning test first** and run it on the code before the refactor too. Fails on both: an old bug, report it separately. Fails only after: the refactor broke it, fix or revert that step
- Screens and flows that must be pressed to judge: suggest `pro-agent-test` to the user; this skill does not drive the app
- Run check mode once on this change (`diff PATH`) to confirm the refactor did not create new smells
- At the end, report **remaining copies** (conventions §9.5): the kinds and paths you left, with the reason
- Commit the way this repo commits. The commit type is `refactor`
