---
name: pro-launch
description: "Capability skill that launches and drives apps, web, desktop windows and servers: emulator/simulator and browser capture, OS dialogs, API mocking for empty/error states, HTTP/DB/log access. Use when asked to launch, screenshot or drive one; pro-agent-test, pro-ui-design and pro-figma call it."
---

# pro-launch — launch, drive, capture

## When to use

- "Launch the emulator and take a screenshot", "simulator screenshot", "capture this screen in the browser", "capture it at mobile width"
  (Korean triggers: '에뮬레이터 띄워서 찍어줘', '시뮬레이터 스크린샷', '브라우저로 이 화면 캡처해줘', '모바일 폭으로 찍어줘')
- "Capture the empty list screen", "show the screen when it returns 500", "call this API once"
  (Korean triggers: '빈 목록 화면 찍어줘', '500 났을 때 화면 보여줘', '이 API 한 번 불러줘')
- This skill does not decide what to capture or why. That is the job of the calling task skill (pro-agent-test · pro-ui-design · pro-figma).
- QA that walks a flow end to end while hunting bugs is pro-agent-test. On Google and Apple login screens, this skill hides automation markers to reduce blocking.

**This is a capability skill.** It documents only what each call does and returns. The calling task skill
(pro-agent-test · pro-ui-design · pro-figma · pro-report) decides what to capture and why, and calls this **as a script, not as a Skill call** (capability skills on the same layer: pro-github · pro-ssh).
The agent decides; the script only executes and records. It does not scan routes or screen lists to guess the project structure.

The **absolute rules** in `../references/common-rules.md` apply (no Git commits, protect sensitive data). Arguments: $ARGUMENTS

Reply to the user in their language (or the configured `language` preference).

## Calling the CLI

`PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py launch <subcommand> [args]` (Windows: `python`).
If that file is missing or answers `scripts_not_found`, find the scripts with the fallback block in `../references/script-invocation.md` §Fallback lookup block (`SKILL=pro-launch`) and call `launch_cli.py` directly.

- pro-launch also has its own fixed entry point, `~/.projectops/bin/launch_cli.py` (#897; it appears after the first run). It finds the newest install
  (checkout > highest plugin-cache version > Cursor) on every call. To force a specific folder, set `PROJECTOPS_LAUNCH_SCRIPTS`. Do not paste a cache path with a version in it.
- In this skill's docs, `{PYTHON} {SCRIPTS}/launch_cli.py <command>` stands for either call above. **The Bash tool resets its state on every call**, so write the actual path as a literal value.
- **In zsh, do not store the command in a variable** (`L="python3 …/launch_cli.py"; $L web …` fails with `no such file`). Call it directly or wrap it in a function: `launch() { python3 "$HOME/.projectops/bin/launch_cli.py" "$@"; }`.
- If a response contains **`newer_installed`**, a newer version is installed; switch to the `use` command it suggests. If `docs_dir` from `doctor` differs from the folder of this SKILL.md, your docs are an old version.
- **From outside the repo (after the shell's working directory changed), add `--root <project>`.** Without it the root is `$PROJECT_ROOT` > working directory (git) > most recently used root; a failed lookup returns `root_candidates` and `retry` (#885).

## Output location — get it first. Never invent a path ⚠️

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py get-output-path --title "{what you are capturing}"
#   --skill ui-design   # when the calling task skill wants the output in its own folder (evidence skills only — otherwise not_evidence_skill)
#   --package {package}    # written to env.sh as PKG
```

**Source the returned `env_file` on the first line of every later block.** It provides `LAUNCH_RUN` (per skill: `{SKILL}_RUN`) · `$RUN_DIR` · `$SHOT_DIR` ·
`$DEV` (with bound roles: `DEVn` · `ROLEn`; filled only when exactly one device is free of other sessions — if empty, use `device acquire`) · `$PKG`. `--skill` accepts only
`EVIDENCE_SKILLS` from `scripts/common/paths.py`. Captures stored in a document skill's folder have no git exclusion and get committed.

## What you want to do → command → read when

| Group | Commands | Read when |
|---|---|---|
| Tools · what can be launched · attached devices · host memory | `doctor [--resources]` · `detect --path .` · `devices` | Always fine to call; `--resources` before booting more virtual devices (rules below) |
| **Devices** — borrow and return (start and end of every app task) · prepared state (`mark`) · create · clone · erase · clean up · capacity · roles · boot · reboot · locale · appearance · text size | `device acquire\|release\|shutdown\|claim\|mark\|unmark\|adopt\|records\|create\|clone\|erase\|delete\|gc\|benchmark\|list\|bind\|unbind\|show\|boot\|reboot\|locale\|appearance\|text-size` | [`references/devices.md`](references/devices.md) — before the first app task, when `acquire` answers `wait` · `ask` · `no_match`, before creating, erasing or cleaning up devices |
| **App** — install · launch · capture · read the screen · tap · swipe · type · several steps · gestures · iOS resident session · wait · record · terminate · location · permissions · push · deep links | `app install\|launch\|shot\|tree\|tap\|swipe\|back\|type\|run\|flow\|session\|wait\|record\|terminate\|relaunch\|location\|permission\|push\|openurl` | [`references/app.md`](references/app.md) — before driving an app, on iOS, when a tap misses or a code is not in `next` |
| **Web** — open · read · find · click with verification · type · capture · forms · width · response staging · wait · scroll · upload · iframes · tabs · profiles · `web script` | `web setup\|open\|goto\|text\|find\|inspect\|click\|type\|select\|check\|press\|hover\|dialog\|download\|shot\|assert\|console\|viewport\|route\|wait\|scroll\|upload\|value\|clipboard\|script\|tab\|profile\|login\|close` | [`references/web.md`](references/web.md) — **read its safety contract before the first web drive**; when a selector misses or a code is not in `next` |
| **Web sign-in** — Google · Apple · Naver · Kakao · GitHub, including Apple's code on this Mac; interstitial screens | `web open --need login:<provider>` · `web type --cred` · `cred policy get\|set\|unset` | [`references/web-sign-in.md`](references/web-sign-in.md) — before any sign-in; interstitials: `references/web.md` "Interstitial login screens" |
| **Desktop** — programs on this computer's screen (installer wizards · OS dialogs · desktop apps · macOS notifications; not web pages, not emulators) | `desktop setup\|doctor\|session\|windows\|tree\|find\|click\|type\|press\|focus\|shot\|wait` | [`references/desktop.md`](references/desktop.md) — the single source for the `desktop` contract; the procedure is the `pro-desktop-control` skill |
| **Render** — draw a hard-to-reach state in code and capture it | `render snapshot` → `render scaffold` (Flutter) → `render run` | [`references/render.md`](references/render.md) — before writing temporary render code; on `render_failed` read `first_error` |
| **Server** — one HTTP request · record how to connect · SQL · logs | `http` · `access show\|set\|unset` · `db` · `logs` | [`references/server.md`](references/server.md) — before touching a server or DB (read the code to decide how to connect, then `access set`) |
| **Credentials** — store · remote commands · sudo on this Mac | `cred list\|show\|set\|unset\|import-ssh` · `ssh` · `local sudo` | [`references/credentials.md`](references/credentials.md) — before a server, DB or login screen, and before saying "the user has to log in themselves" |
| **Evidence** — shrink captures · cover image areas · replace secrets in a log | `shrink` · `mask` · `redact` | [`references/evidence.md`](references/evidence.md) — before attaching captures or logs anywhere |
| **Memory** — recall · save · delete · tidy what worked · stuck areas not learned · work journal · official troubleshooting | `recall` · `learn` · `forget` · `tidy [--buckets]` · `session-check` · `journal` · `kb search\|show\|list\|propose` | [`references/memory.md`](references/memory.md) — first use of these; [`references/troubleshooting.md`](references/troubleshooting.md) — the official entries `known_fix` summarizes |
| **Harness** — a guide folder for a site, app or window you repeat | `harness list\|show\|match --url\|new <name> --description "..." --url "<pattern>"` (`--app` · `--window`) | [`references/harness.md`](references/harness.md) — when a response carries `harness`, or a workflow repeats |
| Output location + `env.sh` | `get-output-path` | Above |
| Add a new platform · new action (contributors) | — | [`references/extending.md`](references/extending.md) |

Options per command: `<command> --help` (for `web` · `app` · `desktop`: `<group> <action> --help`).

## Common rules

- **Borrow devices; do not pick them by name (#953).** Start every app task with `device acquire --platform <ios|android> --purpose "#issue"`,
  use the returned `device` as `$DEV`, and **always** finish with `device release --device "$DEV"` (it shuts the device down if this borrow booted it).
  Several sessions share the devices on one computer. Do not create new simulators or AVDs with `simctl create` or `avdmanager`.
  Action per `verdict`: `reuse` · `reclaim` → proceed · `wait` (`device_busy`) → call again with `--wait 90` or do other work first ·
  `ask` (`needs_user`) → show the `reasons` to the user as is and ask · `no_match` → check `devices` and widen the conditions.
  **Memory risk** (`is_memory_risk` in `needs_user` · `host_memory_pressure` · `device_budget_exceeded`): call again with
  `--user-approved` only after the user answers (`acquire` · `boot`). `--yes` does not pass this gate. Never add it without asking the user.
  Do not take a running device that has no ledger record (a person may be using it). If it must be that device, ask the user and pass `--device`.
- **As soon as a person finishes login, 2FA or data setup, run `device mark --device "$DEV" --kind login --name <provider>`** (#954) — or, in the browser,
  `web profile mark --kind login --name <provider>` (#956). The next session gets that state with `--need login:<provider>`.
  On a marked device, `erase` and `delete` refuse without `--yes`. In Claude Code, a hook blocks raw `simctl create|delete|erase` · `avdmanager create|delete` · `-wipe-data` · `emu kill` in Bash.
- **Pass the device for control commands with `--device`.** Without it: `$DEV` → the only attached device. With several devices and no choice, the command stops with `no_device`.
- **Each command returns one JSON object.** `ok` is success or failure, `code` is the branch (decide by code, not by message text), and `next` lists candidate next commands.
  When an element is not found, you get `candidates` (values actually on screen) and `locale`. **Pick from them; do not keep guessing.**
- **If a failure response has `known_fix`, try that fix first.** It summarizes verified official knowledge (up to 2 entries). For the full symptom and cause use
  `kb show <id>`; to search when the response has none, use `kb search "<error text>" --code <code>`.
- **If a response contains `memory`, read it first and try that approach first**; after using it, run `learn --key <that key> --result ok|fail`.
  If `learn_hint` arrives, record the approach that got you unstuck with `learn` (`--scope machine` for methods unrelated to the repo). Secrets and host-mouse methods are never stored.
  **If a response contains `harness`, open its `readme` before repeating work on that site, app or window.**
- **Do not trim results with `head`, `cut` or python.** You would cut off `next`, `memory` and `known_fix` too.
  For a short response, add `--brief` to any command (only ok · code · summary · next · error · known_fix · memory · learn_hint · journal · harness; on failure also `reasons` · `output_tail`).
  For specific keys only, add `--fields file,url` (`path` is an alias of `file`). Both always keep those guidance keys. Key order is always
  `ok` · `code` · `summary` · `next` → `known_fix` · `memory` · `journal` · `harness` → the rest.
- **On `bad_args`, read `unknown` · `did_you_mean` · `valid_options` · `example` and fix the call.** Do not retry by guessing.
  `empty_values` means that option's value was empty (`$VAR` unset). If you give `device <action>` an option that action does not read,
  it is not silently ignored; it comes back as `bad_args` (`unused_options` · `valid_options`).
- **If `pressure: critical` (from `doctor --resources` or the `resources` in `devices`), ask the user before booting a new virtual device.**
  Do not shut down another session's emulators, simulators or processes. Only look at `owners` to see who uses them. In this case `acquire` does not boot anything and returns `ask`.
  Do not poll `doctor --resources` waiting for the pressure to drop. Show `non_device_consumers` and ask the user what to close.
- **Boot devices within the memory budget, one at a time across this whole computer** (#964). `device benchmark` measures the budget and per-device cost and saves them to config.
  When `doctor --resources` recommends `device benchmark` (never measured · older than 30 days · RAM changed), run it once while no other session is active.
- Captures default to WebP with a 1200 px long edge. Use `--keep-format` only when you need the original, such as for pixel comparison. **Open what you captured with Read.**
  If text is enough to confirm (`web assert` · `app tree` · logs), do not read the image. Images are the most expensive thing to read.
- **Do not click coordinates with raw host-mouse tools** (`cliclick` · AppleScript · CGEvent called directly). They steal the user's cursor and you cannot tell what was pressed. Use `app tap` for apps, `web find` → `web click --ref` for the web,
  and for other programs on the screen **only `desktop`**, inside a `desktop session start` (it presses through accessibility without moving the mouse whenever it can, and stops if the user moves the mouse or types).
- **Never handle credentials as plain text.** Instead of `--text` on the command line, use `--cred` (saved) · `--text-env` (one-off),
  and `$CRED_*` environment variables in command strings. Never copy values into results, reports, issues or commits. Do not write secrets into `access`.
  **Do not read credentials straight from config files.** Use saved values only through `--cred`.
- Mutating actions (submit · delete · pay · send) run without asking **only locally**. Anywhere else, stop and ask (`references/web.md` safety contract).
  **For admin consoles (Play Console · App Store Connect · billing · admin), use `web open --readonly`**; `--confirm-mutating` only when approved.
  `desktop` blocks install · agree · finish · delete · save buttons by default (`mutating_blocked`) — tell the user what it changes, then `--confirm-mutating` on that one click.
- Do not call AI generation APIs to produce captures. Do not guess the state management approach or the project structure.
- **When stuck, go in this order before building something yourself** (#934): the action's `--help` > `kb search` > `web script` (web) · `app flow` (app).
  Do not write new raw Playwright or CDP scripts, direct `adb` · `simctl` · `maestro` calls, or wait loops. They bypass the shared connection, time limits and secret masking.
  **Ask first before workarounds that write to the user's account** (creating script projects such as Apps Script, calling APIs directly).
  When you delegate work to another agent, do not tell it to use raw Maestro, simctl or adb; tell it to use this skill.
- While waiting for a one-time code (OTP), **do not submit the login form again**. A new code is sent and the previous one becomes invalid.
- `--timeout` is in **seconds** (max 300). A value of 3000 is rejected with `timeout_too_large`.
- If you got stuck and solved it with a workaround, record it with `learn` before you finish, so the next session does not rebuild the same workaround.
  Run `session-check` when you finish a task.

Failure codes and their next action are in each group's reference (section "Failure code → next action").

## Shared references

| Document | Read when |
|---|---|
| `../references/common-rules.md` | Always, at start: absolute rules, confirmation gates, issue state, push |
| `../references/agent-conduct.md` | When a tool is missing or you are about to say it cannot be done |
| `../references/sensitive-info.md` | Right before saving an artifact or posting to GitHub: masking table, self-review |
| `../references/evidence-attach.md` | When attaching screenshots, logs or results to an issue or comment |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-launch`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
