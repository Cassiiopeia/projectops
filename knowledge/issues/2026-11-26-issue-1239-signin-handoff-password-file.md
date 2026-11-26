---
type: issue-knowledge
id: "issue-1239"
title: "web signin hands the password over as a short-lived owner-only file, never as a value"
created: 2026-11-26
topics: ["security", "credentials", "launch", "ego"]
status: active
related: ["[[issue-1266]]"]
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1239"
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
issue: 1239
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1239"
commit_base: "6e13ce5bfcc22d9fce92b8c2f911f67491507b90"
commit_head: "b4d9b5c1eb77047583c03da857b5b93bba3e40c4"
commit_count: 1
changed_modules: ["skills"]
main_files: ["skills/pro-launch/scripts/pro_launch/runtime/secret_handoff.py", "skills/pro-launch/references/web-sign-in.md", "skills/pro-launch/scripts/pro_launch/runtime/ego_engine.py", "skills/pro-launch/scripts/pro_launch/commands/web/actions/signin.py", "skills/pro-launch/scripts/pro_launch/runtime/output.py"]
lines_added: 123
lines_deleted: 16
---

# Sign-in hand-over without the password value

## Summary
`web signin --engine ego` returned the stored password inside `handoff.password`, so it ended up in the agent's transcript. The hand-over now gives `password_file`: the path of a file only the user can read, which the Ego script reads and deletes.

## Decisions
- **A file path, not an environment variable.** Ego scripts do not inherit the shell environment (the Ego guide says so and `process.env` was empty in a real run), so the `--text-env` / `$CRED_*` convention used elsewhere in pro-launch cannot reach them.
- **Under the user's state folder, not a shared temp folder**, created owner-only from the first byte (`os.open` with mode 0600, folder 0700). Changing the mode after writing leaves a readable window.
- **Three removals**: the reader deletes it; a detached timer deletes it after 10 minutes; the next hand-over sweeps expired files (covers a timer that never ran, such as after a reboot).
- **`handoff` stays in the keys `--brief` keeps.** The agent needs the path, and the block no longer holds a secret.
- The earlier code comment called the plain password "on purpose (owner's choice)" (#1231). The newer issue reverses that.

## Behavior change
- `handoff` fields: `provider`, `account`, `password_file`, `password_file_valid_seconds`, `second_factor`, `login_policy`. `password` is gone: anything that read it must read the file.

## Code pointers
- `skills/pro-launch/scripts/pro_launch/runtime/secret_handoff.py` > `write_secret_file()`, `remove_expired_secret_files()`
- `skills/pro-launch/scripts/pro_launch/runtime/ego_engine.py` > `build_signin_handoff()`
- `skills/pro-launch/references/web-sign-in.md` > the Ego snippet (read, delete, fill)

## Cautions
- The agent must not `cat`, Read or log the file: that puts the password back into the transcript. The doc says so; nothing enforces it.
- On Windows the mode bits do nothing; protection is the user profile's ACL. Not run on Windows.
- The path is given with forward slashes because it is pasted into a JavaScript string.
- No permanent test guards "no reply contains the password" (repo rule: no new test files). It was checked by hand only.

## Verification
- With a throwaway credential and Ego Lite: default, `--brief`, `--fields handoff`, auto and legacy engines printed the password 0 times; file mode `-rw-------`; the documented snippet read it and the file was gone; timer and sweep checked with a 2-second validity.
