---
name: pro-desktop-control
description: "Drive programs on this computer's screen that are not web pages or emulators: installer wizards, OS dialogs, desktop apps. Reads elements, presses without moving the mouse, asks before installs and hands security prompts to the user. Windows for now."
---

# pro-desktop-control — programs on this computer's screen

## When to use

- "Press Next in the installer", "finish this setup wizard", "click OK in that dialog", "change this setting in the app"
  (Korean: '설치 프로그램 다음 눌러줘', '이 설치 마법사 끝까지 진행해줘', '저 대화상자 확인 눌러줘', '이 프로그램 설정 바꿔줘', '내 컴퓨터 화면 조작해줘')
- A web flow hands off to a downloaded program (a security module installer, a certificate tool) and the agent must continue there.
- **Not for**: pages inside a browser (`pro-launch` `web`), emulator or simulator screens (`pro-launch` `app`), bug-hunting QA (`pro-agent-test`).

Reply to the user in their language (or the configured `language` preference).

This skill is the procedure. The commands are `pro-launch`'s `desktop` group; their contract is in `../pro-launch/references/desktop.md`.
Call them as scripts, the same way `pro-launch` documents (`{PYTHON} {SCRIPTS}/launch_cli.py desktop <action>`, with the fixed entry point
`~/.projectops/bin/launch_cli.py` when it exists).

## Workflow

### Phase 0 — Check and tell

1. `desktop doctor`. On `desktop_deps_missing`, ask the user, then `desktop setup`. On `unsupported_on_platform`, say that this computer's OS is not supported yet and stop.
2. `desktop session start --purpose "<issue or task>"`. **Relay `tell_user` to the user as is** — they need to know the keyboard and mouse are in use and that moving the mouse pauses the work.
   On `desktop_busy`, another session holds them: tell the user and wait.

### Phase 1 — Read, pick, press

1. `desktop windows` → pick the window (`--window "<part of the title>"`). If the window in front is a browser, the page belongs to `web`.
2. `desktop find --window "<title>" --text "<button text>"` → pick a `ref` from `items`. Use `tree` only when you do not know the text.
3. `desktop click --ref N` (or `type --ref N ...`). Read `transport` and `screen_changed`:
   - `screen_changed: false` → nothing happened; pick another candidate.
   - `ref_stale` → the screen moved on; `find` again.
4. Long steps (an installer copying files): `desktop wait --text "<text of the next step>" --timeout 120`. Do not loop `shot`.

### Phase 2 — Approval gates (never skip)

| Result | Do |
|---|---|
| `mutating_blocked` | Tell the user in one line what pressing it changes (installs X, agrees to terms, deletes, saves). Press with `--confirm-mutating` only after they say yes, **for that one click** |
| `needs_user` · `screen_locked` · `elevated_window` | Relay `ask_user`. Wait until the user says it is done. Do not try to get around it |
| `user_interrupted` | Stop. Ask whether to continue. `desktop session resume` only after a yes |
| `secret_requires_cred` | The field is a password. Use a saved credential (`--cred`) or `--text-env`. Never ask the user to paste a password into the chat |

Terms and licence agreements: read the agreement's title to the user and let them decide. Do not accept on their behalf.

### Phase 3 — Finish and report

1. `desktop session stop` — always, also after a failure.
2. Report: what was pressed (names, not refs), what is now on screen, and anything left for the user (a restart, a prompt they must answer).
   Attach a `desktop shot` only when the result is visual.

## Common pitfalls (from real use)

- A dialog listed in `windows` can draw its content in another window or close when it loses focus (Windows "Open With"). Re-list windows rather than retrying the same ref.
- An installer that asks for administrator rights shows a UAC prompt on the secure desktop. Nothing can read or press it — `needs_user` is expected, not a bug.
- "Don't save" is blocked because it contains "save". That is intended: it throws work away.

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-desktop-control`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
