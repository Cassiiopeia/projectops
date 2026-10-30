# Desktop — drive programs on this computer's screen

> When to read: before the first `desktop` command in a session, and when a `desktop` result surprises you.

`desktop` covers windows that are **neither a web page nor an emulator**: installer wizards, OS dialogs (file open, permission prompts),
desktop app settings. Pages inside a browser stay with `web` (it reads the DOM, which is more exact). Emulators and simulators stay with `app`.

**Platforms**: Windows (UI Automation) and macOS (Accessibility API, `AXPress` · `AXValue`). Same commands and JSON on both; macOS specifics are in [macOS](#macos).

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
| The user moved the mouse or typed → `user_interrupted` (`input_detected`: `mouse` · `keyboard` · `keyboard_or_mouse`), session paused | Never type into what the user is doing. Ask, then `desktop session resume` |
| Keys typed into the terminal or app running this agent are not a takeover | Answering "yes" to an approval question must not pause the session |

**How typing is detected.** Before every `click` · `type` · `press` · `focus`, the OS clock of the last user input is compared with this
session's last input. Windows reads `GetLastInputInfo` (keyboard and mouse together); macOS reads
`CGEventSourceSecondsSinceLastEventType` for key presses (no extra permission). If the OS cannot answer, input is not blocked and
`desktop doctor` / `session start` report `keyboard_check.is_available: false` (only mouse movement is checked then).

## What is blocked until the user approves

| Target | Result | Approve with |
|---|---|---|
| Buttons whose text installs, agrees, finishes, formats, resets, deletes, saves, sends, pays… | `mutating_blocked` + `ask_user` | `--confirm-mutating` on that click |
| `--at` ratio clicks | `mutating_blocked` (`reason: unknown_target`) | `--confirm-mutating` |
| `alt+f4` · `ctrl+w` · `ctrl+s` · `shift+delete` | `mutating_blocked` | `--confirm-mutating` |

| Allow · Trust in either UI language (sign-in approvals, permission prompts, certificates) | `mutating_blocked` | `--confirm-mutating` — say what is being allowed (which sign-in, which app) |
| A named hidden action (`click --action`) whose name is one of the above | `mutating_blocked` | `--confirm-mutating` |

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
- Measured on macOS 15.1 (2026-10-22): `windows` 0.85 s per call (process start included), an Electron app's 196 elements 0.16 s, a banner 0.02 s.

## Setup

`desktop setup` installs into the shared venv (ask the user first):

| OS | Packages (all MIT) | Input |
|---|---|---|
| Windows | `mss` · `comtypes` | standard library `ctypes` → `SendInput` |
| macOS | `mss` · `pyobjc-framework-ApplicationServices` · `pyobjc-framework-Quartz` (about 45 MB) | `CGEvent` |

## macOS

**Permissions belong to the terminal app**, not to Python: System Settings → Privacy & Security → Accessibility and
Screen & System Audio Recording → turn on the app that runs the agent (Terminal, iTerm, VS Code, Orca…), then reopen it. `desktop doctor` shows both.

**System windows (`overlay`)**: notification banners and system dialogs belong to background processes, so they are never "the window in front".
`desktop windows` lists them with `overlay: true` and `overlay_kind: "dialog" | "notification"`. Name them with `--window overlay`:
`find` and `wait` search every overlay (dialogs first, then Notification Center); `tree` and `shot` take the first one.

**Hidden buttons**: a banner's Close · Show · Allow · Don't Allow appear in `named_actions` without hovering. Press one with
`click --ref N --action "<name>"`. The decision uses the action name only — the banner body is content, and opening a banner is not blocked.

**Banners leave after about 5 seconds.** `wait --text` returns `matches` with refs, so go straight to `click`:

```
desktop wait --window overlay --text "<banner text>" --timeout 30   # → matches[0].ref, named_actions
desktop click --ref <ref> --action "<Close in the UI language>"     # names come from named_actions
```

**Keys need the window in front.** macOS 14+ ignores a background process asking to activate another app; `desktop` uses `AXFrontmost`
and checks the result. Keys are refused (`focus_failed`) for a system window that cannot take focus — press its buttons instead.
`type --keys` focuses the field through accessibility before typing (no click), and sends one character per key event, so per-digit code boxes work.

**Browsers and Electron**: Chrome and Electron build the page tree only for an assistive client. When the page area is empty, `desktop`
turns it on (`AXEnhancedUserInterface` / `AXManualAccessibility`) and reads again. Pages are deep — pass `--max-nodes 1500 --depth 60`.
If the page belongs to a `pro-launch web` session, use `web` instead.

**Captures** come out at point resolution (half the pixels on Retina); text stays readable.

### Apple Account two-factor on this Mac

1. Ask the user first: Allow approves a sign-in to their Apple Account. Only for the sign-in this session just started.
2. `desktop session start --purpose "Apple sign-in code"`
3. `desktop wait --window overlay --text "Apple" --timeout 60` → the alert; its `named_actions` include Allow (in the UI language)
4. `desktop click --ref <ref> --action "<Allow name>" --confirm-mutating` (after the user agreed)
5. `desktop tree --window overlay` → the code window (FollowUpUI) shows the code as `4 1 9   2 0 1`; drop the spaces
6. Press its Done button with `--confirm-mutating` — the code window holds keyboard focus until it closes
7. Type the code: `web type` for a `pro-launch web` page, otherwise `desktop type --ref <first box> --text <code> --keys`
8. A wrong or split entry invalidates the code. Resend once from the page; never retry in a loop (the account can be locked).
9. `desktop session stop`. Leave "Trust this browser" to the user.

## Common pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| `windows` shows a title but `tree` finds almost nothing | Some dialogs (Open With, UWP flyouts) draw their content in another window, or close when they lose focus | `desktop windows` again and pick the window that holds the content |
| `click` returns `screen_changed: false` | The press went to a container, or the app ignores the pattern | `find` again with `--role button`, or try the next candidate |
| `focus_failed` | Windows refuses to let another process take the front | ask the user to click the window once |
