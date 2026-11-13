---
name: pro-desktop-control
description: "Drive programs on this computer's screen that are not web pages or emulators: installer wizards, OS dialogs, desktop apps, macOS notifications. Asks before installs and sign-in approvals. Use when asked to press through an installer, answer a dialog or change a desktop app setting."
---

# pro-desktop-control — programs on this computer's screen

## When to use

- "Press Next in the installer", "finish this setup wizard", "click OK in that dialog", "change this setting in the app"
  (Korean: '설치 프로그램 다음 눌러줘', '이 설치 마법사 끝까지 진행해줘', '저 대화상자 확인 눌러줘', '이 프로그램 설정 바꿔줘', '내 컴퓨터 화면 조작해줘', '오른쪽 위 알림 눌러줘', '애플 로그인 코드 읽어서 넣어줘')
- A web flow hands off to a downloaded program (a security module installer, a certificate tool) and the agent must continue there.
- macOS: a notification or system dialog must be answered — for example the Apple Account sign-in alert (Allow) and the code window that follows.
- **Not for**: pages inside a browser (`pro-launch` `web`), emulator or simulator screens (`pro-launch` `app`), bug-hunting QA (`pro-agent-test`).

Reply to the user in their language (or the configured `language` preference).

This skill is the procedure. The commands are `pro-launch`'s `desktop` group, and **their contract (commands, what is blocked, what only a person can do,
macOS permissions and overlays, failure codes, pitfalls) has one source: `../pro-launch/references/desktop.md`** — read it before the first `desktop` command.

## Calling the CLI

`PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py launch desktop <action> [args]` (Windows: `python`; `~/.projectops/bin/launch_cli.py desktop <action>` works too).
If that file is missing or answers `scripts_not_found`, find the scripts with the fallback block in `../references/script-invocation.md` §Fallback lookup block (`SKILL=pro-launch`) and call `launch_cli.py` directly.

## Workflow

### Phase 0 — Check and tell

1. `desktop doctor`. On `desktop_deps_missing`, ask the user, then `desktop setup`. On `unsupported_on_platform`, say that this computer's OS is not supported yet and stop.
   On macOS `permission_missing`, relay `ask_user` and `grant` (desktop.md, section macOS). Only a person can grant it; you cannot do it for your own host.
2. `desktop session start --purpose "<issue or task>"`. **Relay `tell_user` to the user as is** — they need to know the keyboard and mouse are in use and that moving the mouse pauses the work.
   On `desktop_busy`, another session holds them: tell the user and wait.

### Phase 1 — Read, pick, press

1. `desktop windows` → pick the window (`--window "<part of the title>"`). If the window in front is a browser, the page belongs to `web`.
   macOS notifications and system dialogs are `overlay` windows: use `--window overlay` (see `../pro-launch/references/desktop.md`, section macOS).
2. `desktop find --window "<title>" --text "<button text>"` → pick a `ref` from `items`. Use `tree` only when you do not know the text.
3. `desktop click --ref N` (or `type --ref N ...`). Read `transport` and `screen_changed`:
   - `screen_changed: false` → nothing happened; pick another candidate.
   - `ref_stale` → the screen moved on; `find` again.
4. Long steps (an installer copying files): `desktop wait --text "<text of the next step>" --timeout 120`. Do not loop `shot`.
5. Notification banners (macOS) vanish in about 5 seconds: `wait --window overlay --text "<text>"` returns refs — click right away.
   Their hidden buttons are in `named_actions`; press with `click --ref N --action "<name>"`.

### Phase 2 — Approval gates (never skip)

| Result | Do |
|---|---|
| `mutating_blocked` | Tell the user in one line what pressing it changes (installs X, agrees to terms, deletes, saves). Press with `--confirm-mutating` only after they say yes, **for that one click** |
| `needs_user` · `screen_locked` · `elevated_window` | Relay `ask_user`. Wait until the user says it is done. Do not try to get around it |
| `user_interrupted` | The user moved the mouse or typed. Stop. Ask whether to continue. `desktop session resume` only after a yes |
| `secret_requires_cred` | The field is a password. Use a saved credential (`--cred`) or `--text-env`. Never ask the user to paste a password into the chat |

Terms and licence agreements: read the agreement's title to the user and let them decide. Do not accept on their behalf.

**Sign-in approvals (Allow · Trust, in any UI language)**: approving lets someone into the user's account. Ask every time, naming the sign-in it belongs to
(the one this session just started, with the location the alert shows). Never approve a request this session did not cause.
"Trust this browser" is the user's choice. A wrong code entry invalidates the code — resend once, never loop (the account can be locked).
Full Apple Account recipe (alert wording per macOS version, split code boxes, failure branches): `../pro-launch/references/web-sign-in.md` (section "Apple").

### Phase 3 — Finish and report

1. `desktop session stop` — always, also after a failure.
2. Report: what was pressed (names, not refs), what is now on screen, and anything left for the user (a restart, a prompt they must answer).
   Attach a `desktop shot` only when the result is visual.

## Common pitfalls

See `../pro-launch/references/desktop.md` sections "What is blocked until the user approves", "Failure code → next action" and "Common pitfalls" (content drawn in another window, UAC on the secure desktop, "Don't save" being blocked on purpose).

## Shared references

| Document | Read when |
|---|---|
| `../references/common-rules.md` | Always, at start: absolute rules, confirmation gates, issue state, push |
| `../references/agent-conduct.md` | When a tool is missing or you are about to say it cannot be done |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-desktop-control`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
