---
type: issue-knowledge
id: "issue-1238"
title: "A tab named by web open is bound to the session, so later commands drive it"
created: 2026-11-26
topics: ["launch", "web", "tabs"]
status: active
related: []
supersedes: []
source: "https://github.com/Cassiiopeia/projectops/issues/1238"
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
issue: 1238
issue_url: "https://github.com/Cassiiopeia/projectops/issues/1238"
commit_base: "50a1cb54ebd6eca63b32a1b41c2de42795d6769e"
commit_head: "6e13ce5bfcc22d9fce92b8c2f911f67491507b90"
commit_count: 1
changed_modules: ["skills"]
main_files: ["skills/pro-launch/scripts/pro_launch/commands/web/actions/open.py", "skills/pro-launch/scripts/pro_launch/commands/web/tabs.py", "skills/pro-launch/scripts/pro_launch/commands/web/session.py", "skills/pro-launch/references/web.md", "skills/pro-launch/scripts/pro_launch/commands/web/actions/tab.py"]
lines_added: 81
lines_deleted: 11
---

# Named tab binding in pro-launch web

## Summary
After `web open --new-tab --tab-name X --url U`, the next `web text` read a blank page. The named tab existed, but nothing tied it to the session. `web open` now binds it, and the reply shows the URL that really loaded.

## Background
The default page lookup deliberately skips named tabs (they belong to whoever named them). With no unnamed tab left it opened a new blank one and read that. Both reported symptoms (URL "lost" on a fresh launch, wrong tab when attaching) were this one cause.

## Decisions
- **Bind in state, per session** (`session_tabs: {session: tab name}`) rather than asking every caller to set `LAUNCH_TAB`. Order: `LAUNCH_TAB` (explicit) > bound tab > old default lookup.
- **A closed bound tab falls back silently** to the old lookup instead of failing: the binding is a convenience, not a contract.
- **An unnamed `--new-tab` still makes a new tab** even when one is bound, and binds to the new one.
- **The reply reports loaded values** (`url`, `title` from the page), not the requested URL, and a failed attach after a fresh launch with a URL is returned as the failure instead of a plain ok.

## Code pointers
- `skills/pro-launch/scripts/pro_launch/commands/web/tabs.py` > `bind_session_tab()`, `recorded_session_tab()`, `adopt_session_tab()`, `forget_tab()`
- `skills/pro-launch/scripts/pro_launch/commands/web/session.py` > `_session_page()`
- `skills/pro-launch/scripts/pro_launch/commands/web/actions/open.py` > `_pick_tab()`, `_session_tab_note()`

## Cautions
- Another session reaches the tab only with `LAUNCH_TAB=X`; the binding is per session id.
- The issue's "the named tab is never created" did not reproduce on current code; only the wrong-tab read did.
- The attach-failure branch could not be triggered in testing. Windows not run.

## Verification
- The issue's throwaway-profile steps before and after: fresh open reads example.com with `session_tab: "t1"`; second open reads example.org; `LAUNCH_TAB=t1` still reads the first; an unloadable URL gives `goto_failed`.
