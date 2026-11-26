---
type: issue-knowledge
id: "issue-1275"
title: "Ctrl+C stops the installer run; ESC only skips one prompt"
created: 2026-11-26
topics: ["installer", "cli", "signals"]
status: active
related: []
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1275"
pr: 1284
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1284"
deploy_version: "4.120.0"
capture_mode: "issue-end"
captured_at: "2026-11-26T19:20:28+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.119.0"
build_number: 648
issue: 1275
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1275"
commit_base: "3869394c00ffc7d0ff3568d4546d32143a691ac3"
commit_head: "92b4103cabf6164a95f8578b49ebca4e2272ffda"
commit_count: 1
changed_modules: ["src", "docs"]
main_files: ["src/ui/cancel-notice.js", "src/ui/readline-engine.js", "src/commands/interactive.js", "src/core/run-trace.js", "src/index.js", "docs/architecture/agent/installer.md", "src/i18n/en.js", "src/i18n/ko.js"]
lines_added: 98
lines_deleted: 11
---

# Installer Ctrl+C handling

## Summary
A user pressed Ctrl+C many times during an update and the installer still finished as "Setup Complete", with default answers applied. Ctrl+C now stops the whole run, prints what state the repository is in and leaves a log. ESC keeps its meaning: skip this one prompt.

## Background
Two separate causes produced the same symptom.
- At a prompt the terminal is in raw mode, so Ctrl+C arrives as a key, not as a signal. The prompt engine returned the same `CANCEL` symbol as ESC, and almost every caller reads `CANCEL` as "keep the default".
- Between prompts the code is synchronous (file copies, `spawnSync` for IDE CLIs). A signal handler runs only when the event loop turns. The handler was removed in `finally` before that, so the signal was dropped.

## Decisions
- **Ctrl+C at a prompt goes to the armed SIGINT handler** (`process.emit("SIGINT")`), not to the callers. Rejected: rejecting the prompt promise with a cancel error, because several "must not kill the wizard" catch blocks would swallow it. Rejected: `process.kill(pid, "SIGINT")` from the engine, because on Windows that ends the process without running the handler, so the log would be lost.
- **Yield points instead of making the steps async.** `yieldToSignals()` (one `setImmediate` turn) sits before the install step, between IDE adapters and before disarming. Smaller change than rewriting the sync engines.
- **No rollback.** Files written before the stop stay. The cancel notice says so and points to `git status`; undoing a half-applied install automatically could destroy the user's own edits.
- **Order in the handler: record > notice > finalize.** The notice must print before `finalize()` or it is missing from the `.log` mirror.

## Behavior change
- Ctrl+C at any prompt: exit by SIGINT (130), notice "No project files were changed" or "Some files... were already changed".
- Mode-select Ctrl+C used to exit 0 with "Installation cancelled"; it now exits by signal. ESC there still exits 0.
- The run log file name now matches the name the summary announces (one timestamp for both).

## Code pointers
- `src/ui/readline-engine.js` > `stopRunOnCtrlC()`
- `src/core/run-trace.js` > `yieldToSignals()`, `armSignals()` (options may be a function, `onCancel`)
- `src/ui/cancel-notice.js` > `printCancelNotice()`, `hasChangedRepoFiles()`
- `src/commands/interactive.js`, `src/commands/skills.js`, `src/index.js` > yield points
- `docs/architecture/agent/installer.md` > the two rules

## Cautions
- A new long synchronous step needs a `yieldToSignals()` after it, or Ctrl+C during it is delayed to the next yield.
- `hasChangedRepoFiles` decides from trace events (`step/start install-*`, `legacy|orphan neutralized`). A new step that writes repo files before the install step must emit one of these or the notice will wrongly say nothing changed.
- Not run on Windows.

## Verification
- Pseudo-terminal runs against the working tree: Ctrl+C at mode select and at a later prompt, ESC at mode select.
- A scratch script raising SIGINT inside a sync step: success and exit 0 without the yield, notice and exit 130 with it.

## Follow-ups
- Update mode re-detects the default branch instead of keeping the saved `default_branch` (seen in the same report: `deploy` became `main`). Needs an owner decision.
