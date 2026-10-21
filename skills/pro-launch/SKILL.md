---
name: pro-launch
description: "Capability skill that launches and drives apps, web and servers: emulator/simulator screenshots, browser navigation and capture, API mocking for empty/error states, HTTP/DB/log access. Used by pro-agent-test, pro-design-brief, pro-figma."
---

# pro-launch — launch, drive, capture

## When to use

- "Launch the emulator and take a screenshot", "simulator screenshot", "capture this screen in the browser", "capture it at mobile width"
  (Korean triggers: '에뮬레이터 띄워서 찍어줘', '시뮬레이터 스크린샷', '브라우저로 이 화면 캡처해줘', '모바일 폭으로 찍어줘')
- "Capture the empty list screen", "show the screen when it returns 500", "call this API once"
  (Korean triggers: '빈 목록 화면 찍어줘', '500 났을 때 화면 보여줘', '이 API 한 번 불러줘')
- This skill does not decide what to capture or why. That is the job of the calling task skill (pro-agent-test · pro-design-brief · pro-figma).
- QA that walks a flow end to end while hunting bugs is pro-agent-test. On Google and Apple login screens, this skill hides automation markers to reduce blocking.

**This is a capability skill.** It documents only what each call does and returns. The calling task skill
(pro-agent-test · pro-design-brief · pro-figma · pro-report) decides what to capture and why, and calls this **as a script, not as a Skill call** (capability skills on the same layer: pro-github · pro-ssh).
The agent decides; the script only executes and records. It does not scan routes or screen lists to guess the project structure.

The **absolute rules** in `../references/common-rules.md` apply (no Git commits, protect sensitive data). Arguments: $ARGUMENTS

Reply to the user in their language (or the configured `language` preference).

## What you want to do → command → detailed doc

Every command is `{PYTHON} {SCRIPTS}/launch_cli.py <command>`. **When you call it from outside the repo (after the shell's working directory changed), add `--root <project>`.**
Without it, the root is resolved in this order: `$PROJECT_ROOT` > working directory (git) > most recently used root. A failed lookup returns `root_candidates` and `retry` (#885).

| Goal | Command | Details |
|---|---|---|
| Tools (adb · simctl · Chromium · Pillow · cwebp · ffmpeg) · what can be launched (app · web · server, package name · bundle ID) · attached devices · booted simulators · AVDs | `doctor` · `detect --path .` · `devices` | — |
| Host memory pressure (ok · high · critical) · large processes · repos holding running devices — **before booting more virtual devices** | `doctor --resources` | Common rules below |
| **Borrow and return a device — the start and end of every app task** (get a free device that matches conditions; when done, shut down what you booted) | `device acquire --platform ios\|android [--form tablet] [--purpose "#issue"] [--wait 90]` · `device release --device $DEV` · `device shutdown` | `references/app.md` |
| Record prepared state (login · test data · permissions) — protected from cleanup and reset; next time `--need` gets you that device · view device records | `device mark\|unmark --kind login --name kakao` · `device adopt` · `device records` | `references/app.md` |
| When you really need a new device (two at once · a completely fresh phone · a different form factor) — **instead of raw simctl create/avdmanager** · clone a logged-in device · erase · delete | `device acquire --fresh\|--count 2` · `device create\|clone --reason "..."` · `device erase\|delete` | `references/app.md` |
| Clean up accumulated devices — delete expired temporary devices · shut down abandoned running devices (report only by default) | `device gc [--apply] [--sizes]` | `references/app.md` |
| **Measure how many devices this computer can handle and save it to config** — on a new computer · when several sessions stall while booting | `device benchmark [--platform ios\|android] [--full]` | `references/app.md` |
| Bind roles to devices (two or more participants) · show the owner · claim a specific device | `device list\|bind\|unbind\|show\|claim` | `references/app.md` |
| Boot an emulator/simulator (no window by default; small window if you need one) · reboot · locale · dark mode — **instead of raw simctl/emulator** | `device boot\|reboot [--cold]\|locale\|appearance\|text-size` · `app install --path` | `references/app.md` |
| Launch an app · capture | `app launch` · `app shot [--clean-status]` | `references/app.md` |
| App screen structure · tap · swipe · back · wait for the screen to settle | `app tree` · `app tap` · `app swipe` · `app back` · `app wait --settle` | `references/app.md` |
| Several app steps at once (one Maestro run on iOS) | `app run --steps steps.json` | `references/app.md` |
| Complex gestures (swipe then tap immediately · swipe from an element) — run the project's Maestro flow and capture | `app flow --file x.yaml` | `references/app.md` gesture playbook |
| When you look and tap on iOS many times — resident session (20 s → 1 s per call) | `app session start\|stop\|status` | `references/app.md` |
| Type text into the app (saved login; Maestro on iOS) | `app type --cred <name>` | `references/app.md` |
| Wait until the screen changes (or something disappears) · screen recording · burst capture right after an action | `app wait [--gone]` · `app record start\|stop` · `--burst` | `references/app.md` |
| Terminate · relaunch · location · permissions · push (iOS) · deep links — **instead of raw simctl/adb** | `app terminate\|relaunch\|location\|permission\|push\|openurl` | `references/app.md` |
| Open a browser · **read the screen · pick what to press** · click with verification · type · capture | `web setup\|open\|goto\|text\|find\|click\|type\|shot\|assert\|console\|close` | `references/web.md` |
| Reuse a logged-in browser profile across repos · record logins (so you do not log in or pass 2FA again) | `web open --profile <name>\|--need login:google` · `web profile list\|use\|mark\|unmark` | `references/web.md` |
| Change width · replace responses (empty list · 500 · delay) | `web viewport` · `web route` | `references/web.md` |
| **Read a form** (inputs · buttons · checkboxes · selects + values · disabled state · ref) · read only matching lines · select · check · keys · hover · dialogs · downloads — **instead of raw CDP scripts** | `web inspect` · `web text --grep` · `web select\|check\|press\|hover\|dialog\|download` | `references/web.md` |
| Wait for a condition (approval · toast · URL) · scroll an inner box and capture a piece · upload files · act inside an iframe · **anything the fixed actions do not cover** | `web wait\|scroll\|upload` · `web shot --container` · `--frame` · `web script` | `references/web.md` |
| Confirm a save went through by its request · save a secret from an input or copy button without printing it · type key by key · clean up leftover browsers | `--capture-requests` · `web value\|clipboard --save-env` · `web type --keys` · `web close --stale` | `references/web.md` |
| Render a state in code and capture it | `render snapshot` → `render run` | `references/render.md` |
| Single HTTP request · record how to connect · SQL · logs | `http` · `access show\|set\|unset` · `db` · `logs` | `references/server.md` |
| Store credentials · remote commands · sudo on this Mac | `cred list\|show\|set\|unset\|import-ssh` · `ssh` · `local sudo` | `references/credentials.md` |
| Policy for interstitial login screens (trust this device · stay signed in · upsells) | `cred policy get\|set\|unset` | `references/web.md` "Interstitial login screens" |
| Shrink for issue attachments | `shrink` | `references/memory.md` |
| Recall · save · delete · tidy what worked on this computer | `recall [--match <word>]` · `learn [--detail]` · `forget` · `tidy` (scattered memory) · `tidy --buckets` (size and bogus buckets; deletes only with `--apply`) | `references/memory.md` |
| When you finish a task — areas where you got stuck, got unstuck, and did not `learn` | `session-check` | `references/memory.md` |
| Search · show · list official troubleshooting · draft an official entry from your memory | `kb search\|show\|list\|propose` | `references/troubleshooting.md` · `references/memory.md` |
| Write free-form notes about work you did and read them next time (work journal) | `journal [--add "..."] [--title] [--site]` | `references/memory.md` |
| Output location for this run + `env.sh` | `get-output-path` | Below |
| Add a new platform · new action (contributors) | — | `references/extending.md` |

## Find the scripts

**The Bash tool resets its state on every call.** After you find the path once, **write the actual path as a literal value in later blocks.**
When another skill calls this one, keep `SKILL=pro-launch` as is.

**Use the fixed entry point if it exists** (#897). Hard-coding a version folder (`.../projectops/4.xx.x/...`) lets the docs and
the scripts drift apart during a session. `~/.projectops/bin/launch_cli.py` appears after the first run. On every call it finds the
newest install (checkout > highest plugin-cache version > Cursor) and passes the arguments through. To force a specific folder, set `PROJECTOPS_LAUNCH_SCRIPTS`.

```bash
E="${PROJECTOPS_HOME:-$HOME/.projectops}/bin/launch_cli.py"; [ -f "$E" ] && echo "Instead of SCRIPTS: {PYTHON} $E <command>"
```

- **In zsh, do not store the command in a variable like `L="python3 …/launch_cli.py"; $L web …`.** zsh treats it as one word and fails with `no such file`. The fixed entry point is executable, so call it directly as `"$E" <command>`,
  or wrap it in a function: `launch() { python3 "$HOME/.projectops/bin/launch_cli.py" "$@"; }`. Do not paste a cache path with a version in it.
- If a response contains **`newer_installed`**, a newer version is installed (it is in the JSON and also comes with success responses). Switch to the `use` command it suggests.
  If `docs_dir` from `doctor` differs from the folder of the SKILL.md you are reading, your docs are an old version.

If it does not exist (first run), find the scripts as below.

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-launch; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS PROJECT_ROOT=$PROJECT_ROOT"
```

## Output location — get it first. Never invent a path ⚠️

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py get-output-path --title "{what you are capturing}"
#   --skill design-brief   # when the calling task skill wants the output in its own folder (evidence skills only — otherwise not_evidence_skill)
#   --package {package}    # written to env.sh as PKG
```

**Source the returned `env_file` on the first line of every later block.** It provides `LAUNCH_RUN` (per skill: `{SKILL}_RUN`) · `$RUN_DIR` · `$SHOT_DIR` ·
`$DEV` (with bound roles: `DEVn` · `ROLEn`; filled only when exactly one device is free of other sessions — if empty, use `device acquire`) · `$PKG`. `--skill` accepts only
`EVIDENCE_SKILLS` from `scripts/common/paths.py`. Captures stored in a document skill's folder have no git exclusion and get committed.

## Common rules

- **Borrow devices; do not pick them by name (#953).** Start every app task with `device acquire --platform <ios|android> --purpose "#issue"`,
  use the returned `device` as `$DEV`, and **always** finish with `device release --device "$DEV"` (it shuts the device down if this borrow booted it).
  Several sessions share the devices on one computer. Do not create new simulators or AVDs with `simctl create` or `avdmanager`.
  Action per `verdict`: `reuse` · `reclaim` → proceed · `wait` (`device_busy`) → call again with `--wait 90` or do other work first ·
  `ask` (`needs_user`) → show the `reasons` to the user as is and ask · `no_match` → check `devices` and widen the conditions.
  **Memory risk** (`is_memory_risk` in `needs_user` · `host_memory_pressure` · `device_budget_exceeded`): call again with
  `--user-approved` only after the user answers (`acquire` · `boot`). `--yes` does not pass this gate. Never add it without asking the user.
  Do not take a running device that has no ledger record (a person may be using it). If it must be that device, ask the user and pass `--device`.
- **As soon as a person finishes login, 2FA or data setup, run `device mark --device "$DEV" --kind login --name <provider>`** (#954).
  The next session gets that device with `device acquire --need login:<provider>`. A new device would not have that state.
  On a marked device, `erase` and `delete` refuse without `--yes`. `acquire` creates new devices only when needed (recording the reason and expiry), and does not create one when a limit (running device count · disk · memory) is hit.
  In Claude Code, a hook blocks raw `simctl create|delete|erase` · `avdmanager create|delete` · `-wipe-data` · `emu kill` in Bash.
- **Pass the device for control commands with `--device`.** Without it: `$DEV` → the only attached device. With several devices and no choice, the command stops with `no_device`.
- **Each command returns one JSON object.** `ok` is success or failure, `code` is the branch (decide by code, not by message text), and `next` lists candidate next commands.
  When an element is not found, you get `candidates` (values actually on screen) and `locale`. **Pick from them; do not keep guessing.**
- **If a failure response has `known_fix`, try that fix first.** It summarizes verified official knowledge (up to 2 entries). For the full symptom and cause use
  `kb show <id>`; to search when the response has none, use `kb search "<error text>" --code <code>`.
- **Do not trim results with `head`, `cut` or python.** You would cut off `next`, `memory` and `known_fix` too.
  For a short response, add `--brief` to any command (only ok · code · summary · next · error · known_fix · memory · learn_hint; on failure also `reasons` · `output_tail`).
  For specific keys only, add `--fields file,url` (`path` is an alias of `file`). Both always keep those guidance keys. Key order is always
  `ok` · `code` · `summary` · `next` → `known_fix` · `memory` → the rest.
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
- **Do not click coordinates with the host mouse** (`cliclick` · AppleScript · CGEvent). It steals the user's cursor. Use `app tap` for apps and `web find` → `web click --ref` for the web.
- **Never handle credentials as plain text.** Instead of `--text` on the command line, use `--cred` (saved) · `--text-env` (one-off),
  and `$CRED_*` environment variables in command strings. Never copy values into results, reports, issues or commits. Do not write secrets into `access`.
- Mutating actions (submit · delete · pay · send) run without asking **only locally**. Anywhere else, stop and ask (`references/web.md` safety contract).
- Do not call AI generation APIs to produce captures. Do not guess the state management approach or the project structure.
- **When stuck, go in this order before building something yourself** (#934): the action's `--help` > `kb search` > `web script` (web) · `app flow` (app).
  Do not write new raw Playwright or CDP scripts, direct `adb` · `simctl` · `maestro` calls, or wait loops. They bypass the shared connection, time limits and secret masking.
  **Ask first before workarounds that write to the user's account** (creating script projects such as Apps Script, calling APIs directly).
- **Do not read credentials straight from config files.** Use saved values only through `--cred`. When you delegate work to another agent, do not tell it to use raw Maestro, simctl or adb; tell it to use this skill.
- While waiting for a one-time code (OTP), **do not submit the login form again**. A new code is sent and the previous one becomes invalid.
- `--timeout` is in **seconds** (max 300). A value of 3000 is rejected with `timeout_too_large`.
- If you got stuck and solved it with a workaround, record it with `learn` before you finish, so the next session does not rebuild the same workaround.

## App — use this when

```bash
source "{env_file value}"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app shot   --device "$DEV" --out 01_login --clean-status
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app tree   --device "$DEV"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --text "Log in" --shot after_login
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app swipe  --device "$DEV" --dir up --shot list_scrolled
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app relaunch   --device "$DEV" --pkg "$PKG"     # terminate takes the same form
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app location   --device "$DEV" --lat 37.5665 --lon 126.978
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app permission --device "$DEV" --pkg "$PKG" --service location --grant
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app push       --device "$DEV" --pkg "$PKG" --payload push.json
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py app openurl    --device "$DEV" --url "myapp://home"
```

- Find what to tap **by element**: `--text` (exactly as shown, in the screen's language) · `--id` (resource-id · accessibilityIdentifier) · `--desc` (accessibility description);
  if several match, `--index N` (from 0). If you do not know the text, check `elements` and `locale` from `app tree` first.
- Use `--at 0.5,0.8` **ratio (0–1)** coordinates only when there is no element, such as a canvas or map. Pixels are rejected (`bad_ratio`).
- Swipe with `--dir up|down|left|right`; for an exact path, `--from 0.5,0.8 --to 0.5,0.2 --ms 300`.
- **Bundle two or more steps with `app run --steps steps.json`.** On iOS this launches Maestro only once (step format in `references/app.md`).
- With `--shot <name>`, it captures after the screen settles. `screen_changed: false` means nothing reacted; pick a different element.
- On iOS, **`app tree` also uses Maestro**, not only `app tap` and `app swipe` (10–40 s per call). Run long scenarios at once as the project's E2E flow.
- **On iOS, if you look → decide → tap many times, run `app session start --device $DEV` first** (8 s to start, then tree 0.6 s · tap 1 s measured).
  `transport: session` in the result means it used the session; `session_fallback` gives the reason it fell back to launching per call. When done, `app session stop` (it also ends itself after 20 minutes idle).
  `app type` handles secret values, so it does not use the session (`session_fallback: secret_input_per_call`).
- If you get `not_found` right after a screen transition or loading, check the current screen with `app shot`, then tap again **once** with `--shot`. If it fails again, pick from `candidates`.
- iOS bundle IDs (including system apps): the iOS section of `references/app.md`.
- Do not type `xcrun simctl` or `adb shell am|pm` directly to terminate apps or set location, permissions, push or deep links. The `app` actions above handle device selection and failure codes.

| code | Next action |
|---|---|
| `no_device` | Check `devices` and pass `--device` |
| `device_shutdown` | The chosen simulator/AVD is off. Boot it with `device boot --device <id>` from `next`, then retry (to borrow one, use `device acquire`) |
| `not_found` | Pick from `candidates` |
| `ui_dump_failed` | Could not read the screen structure (mid-transition · secure screen). If `foreground_package` in the response is not your app, another app is covering it. Retry shortly; if it persists, use `--at` ratio coordinates |
| `not_foreground` · `app_exited` | launch/relaunch was sent but the app is not in front / it died immediately. Read `blocking_activity` · `crash_report` · `exception_line`. If it is someone else's device, ask first |
| `device_unresponsive` | The device does not respond (`resources` includes host memory). Ask the user, then run `device reboot --cold` |
| `typed_text_mismatch` | The input text differs from what was typed (composing keyboard). Use `app type --ime ascii` |
| `device_owned_by_other` | Another session borrowed this device. Mutating actions (tap · type · install, etc.) are refused; reads (shot · tree · wait) only get a warning field. Get another device with `device acquire`, or, if it must be that device, ask the user and pass `--yes` |
| `device_busy` · `needs_user` · `no_matching_device` | `device acquire`'s wait · ask · no_match — see the per-verdict actions in the common rules above |
| `device_budget_exceeded` · `host_memory_pressure` | Booting another device would exceed this computer's device memory budget / host memory is at a risky level (`reasons` · `non_device_consumers`). Return or shut down unused devices, or show this to the user and pass `--user-approved` after they answer. If the budget was never measured, run `device benchmark` |
| `devices_in_use` · `benchmark_no_room` | Not started because measuring could stall other sessions / no room to boot even one test device (config unchanged) |
| `ledger_busy` | Could not get the device ledger lock within 10 s. Call again shortly |
| `device_protected` · `device_in_use_unrecorded` | The device you want to erase or reset holds prepared state / a person may be using it. Show `marks` to the user and ask; if they agree, pass `--yes` |
| `no_matching_profile` | No browser profile has the `--need` state recorded. After a person logs in, run `web profile mark` |
| `emulator_no_acceleration` | The emulator stopped because it could not get hardware acceleration (host memory or swap is short). Waiting will not help, and it is already shut down. Ask the user to free memory |
| `source_booted` | A running device cannot be cloned. Retry after the source is shut down |
| `resources_low` · `create_failed` | Not enough room to create a new device (memory · disk) / creation failed. Use an existing device with `device acquire` first |
| `no_focused_window` | No focused window (screen off · locked · mid-transition). This comes after waking it and reading up to three times. Look at the screen with `app shot` |
| `android_system_not_ready` · `ui_automation_unavailable` · `ui_dump_timeout` | A device-side problem (system restarting · UiAutomation connection failed · timeout). Look with `app shot`; if it persists, ask the user about an emulator cold boot |
| `session_start_failed` · `session_tools_missing` | Continue without a session (Maestro per call). Read `reason` |
| `tree_unsupported` | This device cannot read the screen structure. Look with `app shot` and use `--text` or `--at` ratio coordinates |
| `ios_tool_missing` · `android_tool_missing` · `adb_missing` | Offer the user the install instructions from the result |
| `non_ascii_unsupported` · `ios_text_unsupported` | `app type` cannot enter this text. Use an English substitute or leave it to the user |
| `unsupported_on_platform` | The action does not work on this platform or device (Android push · location on a real Android device, etc.). Use the alternative in `next` |
| `build_mismatch` | Devices have different builds installed. Stop and make them match |

## Web — use this when

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web open --url {url}                 # reattaches if already running (reused)
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web text                           # read the screen text — cheaper than a screenshot
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web find --text "Log in"            # candidates with ref · link URL
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web click --ref 1 --expect-url /home   # only what you picked, verified through to the result
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web viewport --preset mobile
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --status 200 --body "[]"
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web goto --url {that screen}         # rules apply when you navigate
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web shot --out 02_empty_list
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web route --clear
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web wait --url-contains /home --timeout 180   # 2-step approval · save toast — wait, do not navigate
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web scroll --to "Payment history"     # or --ref N · --by 600 [--container "#list"]
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web upload --files a.png,b.png       # hidden input[type=file] · for a drop zone, --click-ref N
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web type --frame login --selector "#account_name_text_field" --cred apple --cred-field account   # inside an iframe
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web script --file snippet.py          # anything the fixed actions do not cover — a Playwright snippet with page · context
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web tab new --name edit --url {url}  # long work goes in your own tab — then prefix LAUNCH_TAB=edit
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/launch_cli.py web login --cred {name} --user-selector "#email" --password-selector "#pw" --submit-selector "#go" --until-url /home --handoff-seconds 120   # hands 2FA to the user and waits
```

- **Call `find`/`inspect` before `type` or `click`** whenever the selector did not come from the latest `find` or `inspect` result. A wrong guess fails after 4 s with `candidates` (including refs).
- **Read → pick by number → press with verification.** Do not guess selectors. `click` returns what it pressed (`clicked`) and whether the URL or title
  changed (`changed`). `changed: false` means you pressed the wrong thing; pick again with `find`. Read information with `web text`; use `shot` only to see the layout.
- **For admin consoles (Play Console · App Store Connect · billing · admin), use `web open --readonly`.** **Buttons** such as delete, release or submit
  are blocked with `mutating_blocked` (links, tabs and table rows are navigation and stay open). Use `--confirm-mutating` only when approved.
- Stage empty lists, failures and loading with `route` **without touching the server** (`--status 500` · `--delay 5000`). Run `--clear` when done.
- If a Google or Apple login is blocked, try `web open --headed` first. If a site behaves oddly, compare with `--no-stealth`.
- **As soon as a person finishes logging in in the browser, run `web profile mark --kind login --name <provider>`** (#956). In other repos, open that profile with `web open --need login:<provider>`.
  When done, run `web close`. The session-end hook also closes browsers this session started (it leaves them if other sessions have tabs). Closing keeps the login (cookies) in the profile.
- On `playwright_missing`, ask the user and run `web setup`. On `browser_not_open` · `browser_gone`, run `web open` again.
- Read forms with `web inspect --role input --near "Email"` and use the returned `ref` for `type` · `check` · `select`. A disabled element returns `element_disabled` immediately instead of waiting.
- **Frequent, risky work uses fixed actions; the long tail uses `web script`.** Do not write new scripts that attach to CDP directly. `script` goes through the shared connection, reinstall, time limits and secret masking.
- If the login form is inside an iframe (`find` returns `nothing_found` + `frames`), add `--frame <name|iframe selector|part of URL>` to `find` · `type` · `click` · `assert` · `text` · `inspect`.
- **Sessions in the same repo share one browser.** Do long, unsaved input in your own tab created with `web tab new --name <name>` (`LAUNCH_TAB=<name>`), and save after each step.
  If another session moved your tab, the result carries `tab_warning` (`page_changed_by_other_session`).
- `web open` clears a hung browser and leftover profile locks by itself and reports `recovered`. Do not delete locks by hand.
- Options differ per action: `web <action> --help`. Options the action does not accept are rejected with `bad_args` (the usable options are in the error).

| code | Next action |
|---|---|
| `nothing_found` · `selector_not_found` | Pick from `candidates` in the result and retry with `--ref` as `next` says. If there are no candidates, read the screen text with `web text` and then `find` |
| `element_not_actionable` | The element exists but is hidden or covered, so it could not be pressed within 4 s. If `covered_by` is present, a fixed header or overlay covers it — use `--dom-click` as `next` says. Otherwise pick again from `candidates` |
| `frame_not_found` | Put a name or part of a URL from `frames` into `--frame` |
| `wait_timeout` | The condition was not met. Decide from `url` · `title`. If you are waiting for approval, do not navigate; `wait` again |
| `script_failed` · `script_timeout` | Read the snippet's first error line and fix it · raise `--timeout` or wait less |
| `ref_stale` | The screen changed. Run `find` again |
| `expect_not_met` | The expected result did not come. Look at the current screen with `web text` and pick another candidate |
| `mutating_blocked` | The read-only session blocked a risky button. Tell the user what would change and get approval |
| `needs_user` | Hand the remaining login steps (2FA · device approval) to the user. Ask with `ask_user`; when they say they are done, run `web login --resume ...` from `next` |
| `tab_gone` | The `LAUNCH_TAB` tab was closed. Run `web tab new --name <same name>` |
| `browser_start_failed` | Still failing after self-recovery. Read `stderr_tail` · `causes` and decide |
- **Before you drive the web for the first time, read the safety contract in `references/web.md`.**

## render · server · credentials · memory — use this when

- For states that are hard to reach on a real device (empty list · long text · permission denied): `render snapshot` → temporary render code → `render run`.
  On `render_failed`, read `first_error` first (or `output_tail` if absent) and fix it. In `residue`, delete **only what you created** (`references/render.md`).
- Decide how to connect to the server by reading the code, and write it down with `access set`. `http --url /path` · `db --profile db --sql …` · `logs --tail 100`.
- Before touching a server, a DB or a login screen, and before saying "the user has to log in themselves", **check `cred list` first.**
  Use only entries whose `use_when` matches. For new information, ask whether you may save it, then `cred set`. Remote: `ssh --cred <name> --command '…'` (without saving: `ssh --host … --user … --password-env|--key-path …`).
  Admin rights on this Mac: `local sudo --cred <name> -- <command>` (the user does the first registration with `cred set --prompt`). Details: `references/credentials.md`.
- **If a response contains `memory`, read it first and try that approach first** (it is attached automatically — no separate recall needed). After using it, run `learn --key <that key> --result ok|fail`.
  If `learn_hint` arrives, record the approach that got you unstuck with `learn`. For methods unrelated to the repo, use `--scope machine`.
  Secrets and host-mouse methods are never stored. Run `shrink` on captures before attaching them to an issue. Details: `references/memory.md`.

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-launch`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
