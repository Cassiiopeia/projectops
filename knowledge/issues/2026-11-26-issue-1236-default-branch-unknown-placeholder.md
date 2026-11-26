---
type: issue-knowledge
id: "issue-1236"
title: "Default branch detection rejects git's (unknown) placeholder; doctor reports branch values that cannot be branches"
created: 2026-11-26
topics: ["installer", "cli", "branches", "doctor"]
status: active
related: []
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1236"
pr: 1284
pr_url: "https://github.com/Cassiiopeia/projectops/pull/1284"
deploy_version: "4.120.0"
capture_mode: "issue-end"
captured_at: "2026-11-26T19:20:29+09:00"
captured_by: "pro-brain"
project: "projectops"
stacks: ["basic"]
app_version: "4.119.0"
build_number: 648
issue: 1236
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1236"
commit_base: "b4d9b5c1eb77047583c03da857b5b93bba3e40c4"
commit_head: "3869394c00ffc7d0ff3568d4546d32143a691ac3"
commit_count: 1
changed_modules: ["src"]
main_files: ["src/commands/doctor.js", "src/core/detect-fs.js", "src/i18n/doctor.en.js", "src/i18n/doctor.ko.js"]
lines_added: 53
lines_deleted: 5
---

# Default branch on an empty remote

## Summary
With `origin` set to a repository that has no branches yet, the installer wrote `(unknown)` as the default branch into `version.yml` and workflow triggers, so release workflows never ran and doctor said nothing. Detection now skips that value and doctor has a "Branch names" row.

## Background
This is the normal order for a new project: create the GitHub repo, add the remote, run the installer, then make the first commit. On an empty remote `git remote show origin` prints `HEAD branch: (unknown)`, and the regex took it as a name, so the later fallbacks (current branch, `main`) were never reached.

## Decisions
- **Validate, do not special-case one string.** `isValidBranchName()` rejects characters git forbids in a ref plus parentheses. Parentheses are legal in git refs, but the value to keep out is git's own placeholder, and a real default branch with parentheses is not a realistic case.
- **Doctor reports, it does not rewrite.** Re-running the installer fixes an affected repo because detection now returns the current branch.
- Same release: the optional AI summary keys were removed from doctor's "Required secrets" row (#1237), since both edits touch `doctor.js`.

## Code pointers
- `src/core/detect-fs.js` > `isValidBranchName()`, `detectDefaultBranch()`
- `src/commands/doctor.js` > `findInvalidBranchLines()`, `AI_KEY_NAMES`

## Cautions
- Doctor flags only values that cannot be branch names. It does not check that a trigger branch exists on the remote.
- `AI_KEY_NAMES` (local row) and the `AI_KEYS` map in the remote check are two lists; add a provider key to both.

## Verification
- The issue's reproduction with a bare empty remote: `default_branch: "main"`, no `(unknown)` anywhere. Doctor shows a warning with file and line after the value is put back by hand.
