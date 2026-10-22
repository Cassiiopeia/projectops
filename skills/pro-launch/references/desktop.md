# Desktop — drive programs on this computer's screen

> When to read: before the first `desktop` command in a session, and when a `desktop` result surprises you.

`desktop` covers windows that are **neither a web page nor an emulator**: installer wizards, OS dialogs (file open, permission prompts),
desktop app settings. Pages inside a browser stay with `web` (it reads the DOM, which is more exact). Emulators and simulators stay with `app`.

**Platforms**: Windows (UI Automation). macOS is not available yet (#985) — `desktop` returns `unsupported_on_platform` there.

## How a press works

```
desktop click --ref N
  1) the window comes to the front if it is not
  2) the element supports an action pattern (Invoke · Toggle · SelectionItem · ExpandCollapse)
       → pressed through UI Automation, the mouse does not move        transport: "invoke"
  3) otherwise → mouse click at the element's center, after checking
       that the user has not moved the mouse since our last click     transport: "mouse"
  4) before/after capture of the window → screen_changed, wait until it stops changing, then --shot
```

`desktop type` puts the value through the Value pattern when the field has one (no keys, no mouse). Otherwise it presses the field and
types the characters as Unicode, so Korean and emoji go in regardless of the keyboard layout. `--keys` forces key-by-key typing for fields
that ignore a direct value.

Refs come from the last `tree` or `find` **of this session**, stored per session. A CLI call is a new process, so the element is found again by
its path in the window's tree and checked by kind and name before it is pressed. If they differ, the result is `ref_stale` instead of a wrong press.

**Every `find` or `tree` renumbers.** A ref you kept from an earlier `find` now points at whatever the latest `find` numbered —
if you looked something else up in between (for example, reading a status label), `find` the button again right before you press it.

## The input session

| Rule | Why |
|---|---|
| Reads (`windows` · `tree` · `find` · `shot` · `wait`) need no session | Looking does not disturb the user |
| `click` · `type` · `press` · `focus` need **this session's** `desktop session start` | The user must know the keyboard and mouse are in use. Relay `tell_user` from the start result |
| One input session per computer (`desktop_busy`) | Two agents on one mouse fight each other |
| Expires after 10 minutes without input; the session-end hook runs `desktop session stop` | A session that left without stopping must not hold the mouse |
| The user moved the mouse → `user_interrupted`, session paused | Never type into what the user is doing. Ask, then `desktop session resume` |

## What is blocked until the user approves

| Target | Result | Approve with |
|---|---|---|
| Buttons whose text installs, agrees, finishes, formats, resets, deletes, saves, sends, pays… | `mutating_blocked` + `ask_user` | `--confirm-mutating` on that click |
| `--at` ratio clicks | `mutating_blocked` (`reason: unknown_target`) | `--confirm-mutating` |
| `alt+f4` · `ctrl+w` · `ctrl+s` · `shift+delete` | `mutating_blocked` | `--confirm-mutating` |

"Next" and "Cancel" are not blocked — a wizard would be impossible otherwise. "Don't save" contains "save" and **is** blocked; that is on purpose,
because it throws work away.

## What only a person can do

| Situation | code | What to say |
|---|---|---|
| UAC consent, sign-in, Ctrl+Alt+Del (the secure desktop) | `needs_user` | relay `ask_user`, wait for "done", then `desktop windows` |
| Locked screen | `screen_locked` | ask the user to unlock |
| The window runs as administrator and this session does not (Windows blocks the input) | `elevated_window` | ask the user to press it |
| A password field | `secret_requires_cred` for plain `--text` | use `--cred <name>` or `--text-env VAR`; never paste the value into the command |

## Reading cheaply

- Start with `find --text "<what you want>"`. `tree` lists everything up to 150 elements and says `truncated` when there is more.
- `tree` reads the window in front unless `--window` names one (part of a title, pid or handle from `desktop windows`).
- Read a `shot` image only when the window has no readable elements (`tree_unavailable`, canvases, some games).
- Measured on Windows 11 (2026-10-22): window list 0.004 s, a Chrome window's 227 elements 0.23 s, Explorer's 219 elements 0.39 s.

## Setup

`desktop setup` installs `mss` (capture, MIT) and `comtypes` (UI Automation, MIT) into the shared venv `~/.projectops/launch/.venv`.
Input uses only the standard library (`ctypes` → `SendInput`). Ask the user before running it.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `windows` shows a title but `tree` finds almost nothing | Some dialogs (Open With, UWP flyouts) draw their content in another window, or close when they lose focus | `desktop windows` again and pick the window that holds the content |
| `click` returns `screen_changed: false` | The press went to a container, or the app ignores the pattern | `find` again with `--role button`, or try the next candidate |
| `focus_failed` | Windows refuses to let another process take the front | ask the user to click the window once |
