---
name: pro-agent-test
description: "QA that actually runs the app, web or server to find bugs and reports repro steps, evidence and severity without fixing code. Use for 'test it for real', 'run it in the emulator', 'find bugs', 'E2E'. Unlike pro-testcase, it executes."

version: "2.1"
---

# agent QA — actually walk the app, web or server to find bugs

## When to use

- 'test it for real', 'run it in the emulator', 'check it in the browser', 'walk the APIs in order'
  ('실제로 테스트해줘', '에뮬레이터로 돌려봐', '브라우저로 확인해줘', 'API 순서대로 밟아줘')
- 'do QA', 'find bugs', 'check edge cases', 'test sign-up'
  ('QA해줘', '버그 찾아줘', '엣지 케이스 봐줘', '회원가입 테스트해줘')
- 'run E2E', 'walk it from login to the end', 'verify on a real device'
  ('E2E 해줘', '로그인부터 끝까지 밟아줘', '실기기 검증')
- This is different from writing QA documents (pro-testcase) — this skill actually runs things.
- Do not look only at the requested spot — also check other screens of the same kind and symmetric actions (sign-up ↔ withdrawal, create ↔ delete). If there are no logs, report it as an untraceable defect.

**You are QA. Your side finds bugs, not fixes code.** Try to break things, leave repro steps and evidence,
rate severity and report. Fixing is the job of other skills (`superpowers:*`) —
if you start fixing here, nobody can tell what the original defect was.

> **The goal is discovery, not passing.** Developers have already walked the normal path dozens of times. Choose what to walk
> by **"where could this break"**, not "confirm it works", and **do not look only at the requested spot** (Phase 4.5).

Do not use it for: writing QA documents (`/pro-testcase`), widget-level verification (`flutter test` is faster and more precise).
Use it for: checking main flows before release · reproducing user reports · problems that occur only in release builds (R8, signing and manifest merging
do not take effect in debug) · checking step by step what remains on the device and server · other places of the same kind after one place was fixed.

Apply the **absolute rules** in `../references/common-rules.md` (no Git commits, protect sensitive data). Accounts and passwords the user gives
**must not be left in files, commits or report text** — use them only for device input. Arguments: $ARGUMENTS

Talk to the user in the user's language (or the configured `language` preference); this includes questions, hand-over messages and the final report.

## What you want to do → command → detailed document

QA judgment is this skill (`{SCRIPTS}/e2e_cli.py`); **running and capturing is pro-launch** (`{LAUNCH}/launch_cli.py`).

| What you want | Command | Details |
|---|---|---|
| What can be walked · per-target info (package name · device · `adb_path` · web address · recorded connection info) | `e2e_cli.py detect --path .` | `references/planning.md` |
| Record the decided target · accumulate screens, rules, pitfalls, run results · tidy scopes | `e2e_cli.py note show\|target\|screen\|constraint\|pitfall\|run\|tidy\|forget` | `references/learning.md` |
| Scenario skeleton · list · **validate before walking** | `e2e_cli.py scenario init\|list\|show` | `references/planning.md` |
| Walk a server scenario to the end | `e2e_cli.py api --name` | `references/target-server.md` |
| Run something that is not an app, web or server (CI, CLI, library) and look at its outputs | `e2e_cli.py other run` | `references/target-other.md` |
| Output location + `env.sh` | `launch_cli.py get-output-path --skill agent-test` | below |
| Borrow · return a device (start and end of every app run) | `launch_cli.py device acquire --platform ios\|android --purpose "#issue"` · `device release --device "$DEV"` | pro-launch app doc |
| Bind roles (two or more participants) | `launch_cli.py device list\|bind` | `references/devices.md` |
| Launch app · screen structure · tap · swipe · capture | `launch_cli.py app launch\|tree\|tap\|swipe\|shot` | `references/stepping.md` · `references/target-app.md` |
| Browser · stage empty list/500/delay | `launch_cli.py web …` · `web route` | `references/target-web.md` |
| Server DB · log cross-check | `launch_cli.py access` · `db` · `logs` | `references/target-server.md` |
| Login gate · screens a person must handle | `web open --headed` · `web type --text-env` | `references/social-login.md` |
| Works but looks wrong (axes 4·5·6·7) | — | `references/looks-wrong.md` |
| Cross-cutting · symmetry · other environments · ripple effects · proposals | `note constraint` · `other run --env` | `references/wide-view.md` |
| Defect report · file issue · correction | `launch_cli.py shrink` · `github_cli.py upload-image` | `references/reporting.md` |

## Find the scripts — once

**The Bash tool resets state on every call.** Find them once, then **write the actual paths as values into later blocks.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
for SKILL in pro-agent-test pro-launch; do
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  [ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
    H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
    [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
  done
  # Home-copied installs from npx projectops: GitHub Copilot and Cursor (#200)
  [ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.copilot ~/.cursor; do [ -d "$B/skills/$SKILL/scripts" ] && { ROOT="$B"; break; }; done
  [ -d "$ROOT/skills/$SKILL/scripts" ] || { echo "$SKILL scripts not found. Check the plugin installation."; exit 1; }
  echo "$SKILL=$ROOT/skills/$SKILL/scripts"
done
echo "PYTHON=$PYTHON PROJECT_ROOT=$PROJECT_ROOT"
```

The `pro-agent-test=` value is `{SCRIPTS}` and the `pro-launch=` value is `{LAUNCH}`. Per-command options and pitfalls: `../pro-launch/SKILL.md`.
(If the scripts are missing, the snippet prints a Korean message saying the scripts were not found and to check the plugin install.)

## Where outputs go — get it first. Do not make up paths ⚠️

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py get-output-path --skill agent-test --title "{what you are walking}"
```

**Source the returned `env_file` on the first line of every later block** — `$SHOT_DIR` · `$RUN_DIR` · `$DEV` · `$PKG`.
Do not pile things up in arbitrary paths like `/tmp` or `docs/testing` — in one real case **8MB piled up outside `.gitignore`**
in the target repo (#611). This location is under the `docs/projectops/` umbrella, and the folder carries its own `.gitignore`.

> If you call old names (`web` · `device` · `access` …) through `e2e_cli.py`, they are forwarded to pro-launch for one minor version
> (`moved_to` · `next`). Write new commands with `{LAUNCH}`.

## Common rules

- **Each command returns one JSON object.** `ok` tells success or failure, `code` tells the branch (judge by code, not by message text), and read `next` as the candidate next command.
- **Tap apps by element.** Use `app tree` to see text, ids and `locale`, then `app tap --text|--id|--desc [--index N]`.
  Only when there is no element, use **ratio** coordinates like `--at 0.5,0.8`. Do not compute pixel coordinates, use raw `adb shell input tap`, or use the host mouse (`cliclick`, AppleScript). A program window on the host screen (installer, OS dialog) goes through `pro-launch desktop` only.
- **Tap with `--shot name`.** It captures after the screen changes and settles. `screen_changed: false` means there was no response.
- **If text confirms it, do not read the image** (`app tree` · `web assert` · logs). Captures default to WebP at 1200px on the long side.
- **Always `adb -s "$DEV"`.** With several devices, a command that leaves it out goes to the wrong device.
- **Do not pass on the screen alone.** Cross-check device storage, the server DB and server logs too.
- Changed settings (text size, dark mode, network, rotation, test build flags) **must be reverted as soon as you finish.**
- Passwords go through `--text-env` · `--cred`, not `--text`. Auto-retry at most once.

## Order — decision rules per phase

**Phase 0 — Decide the target first ⚠️** If `detect` returns one `targets` entry, use it; if several, **ask**; if none, get `--target app|web|server|other`.
If it is not an app, web or server, it is `other`. If `target_source` is `version.yml` and has **`confirm`**, it is only a declaration —
look at the code to judge whether the server renders screens itself (template folder, controllers returning views) and record it with `note target --targets server,web --why "…"`.
Once the target is set, read **only that document**: `references/target-app.md` · `references/target-web.md` · `references/target-server.md` · `references/target-other.md`.
For an app, borrow a device with `device acquire --platform <ios|android> --purpose "#issue"` (do not create new simulators or AVDs),
and check the build with `device list` — on `build_mismatch`, stop there (`references/devices.md`). When done, `device release`.

**Phase 0.5 — Read the structure.** Read screens, routes, endpoints, auth and resource ownership **yourself with Grep and Read**, and record them with `note screen` · `access set`.

**Phase 1 — Fix the path.** `scenario list` → if none, user-specified → if neither, ask once. For each step write
"what to tap → what appears → what should remain on the device/server". For paths you will walk again and for the `server` target,
`scenario init` → fill in → **validate with `scenario show`**. Do not walk only the happy path — pick from three axes:
state combinations, failure injection and environment conditions (`references/planning.md`).

**Phase 2 — Secure observability.** Before walking, check whether you can see state through logs. **If there are no logs, that itself is a defect** (observability) —
do not add logging; write "insufficient evidence" in that stretch's verdict.

**Phase 3 — Walk.** `① app tree/shot → ② app tap/swipe --shot → ③ screen_changed · mCurrentFocus · crash log →
④ cross-check device storage → ⑤ cross-check the server with db · logs`. Scroll lists to the end. If you see a crash, stop and find the cause first. Details and pitfall table: `references/stepping.md`.

```bash
source "{env_file value}"
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tree  --device "$DEV"
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --text "{on-screen text}" --shot step_01
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py db --profile db --root {ROOT} --sql "select ..."
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py api --name {scenario} --root {ROOT}       # server
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py other run --command "{command}" --watch {expected path}   # other
```

**Phase 4 — Stop where a person must act.** 2-step verification, biometrics, payment, external apps, captchas. Tell the user in one line
what to tap and where. **Get through the login screen itself yourself** — enter the email and password, and stop only at 2-step verification.
Before tapping, **read `flowName` in the address**: `WebLiteSignIn` means it was detected as automation and will be rejected at the email step (do not try);
`GlifWebSignIn` is normal. So when login is needed, **open with `web open --headed` from the start** (measured 2026-09-18: headless gets
`WebLiteSignIn`, `--headed` gets `GlifWebSignIn`). Passwords go through `--text-env`. Details: `references/social-login.md`.
Native Android Google login (the Play Services account picker) is a screen outside the app — if the device has a test account, pick it with `app tap --text <account>`; if there is none or 2-step verification appears, stop and hand over to the user.

**Phase 4.4 — Works but looks wrong.** Lay the screens in `$SHOT_DIR` side by side and check axes 4 (same things look the same) · 5 (does tapping make sense) ·
6 (motion) · 7 (design comparison record) **as values** — not "a feeling" but "title size: 3 variants across 4 screens". If a screen comes from a design
but has no comparison record, report that itself as a defect (`pro-figma`). `references/looks-wrong.md`.

**Phase 4.5 – 4.8 — Look wide (always, after walking).** State the rule in one sentence and check **every** place of the same kind (cross-cutting),
check pairs like sign-up ↔ withdrawal and create ↔ delete (symmetry), other environments (defaults · installed tools · first state · unwalked branches · outputs), places that move together when fixed (ripple effects),
and better approaches that are not defects (proposals). Accumulate rules with `note constraint`. `references/wide-view.md`.

**Phase 5 — Defect report.** Write functional defects, consistency defects, observability, improvement proposals, passes and on-hold items **separately**. For each defect: repro steps,
expected vs actual, evidence, severity (Critical/High/Medium/Low/Observability), impact. Do not raise severity by guessing. For images,
`shrink` → `upload-image` → body, in that order. Correct misjudgments immediately. `references/reporting.md`.

**Phase 6 — Reset.** `pm clear` + clean up server test accounts (query and show what will be deleted first). `references/stepping.md`.

## Accumulating records

When starting app or web work, check `pro-launch`'s `recall --area ios|android|web|server` once, and when done record the method that worked with `learn --result ok|fail`.
Record screens, rules, pitfalls and run results you learned with `note`. **The `memory` in `detect` · `scenario show` responses carries a few rules and pitfalls that fit the context**
(once per day per area) — read it first. For everything, `note show --all`; the default `note show` is a summary. Records are stored in the home directory
(`knowledge_dir` from `detect`), so they survive creating new worktrees. Anything containing an email, phone number, JWT or password is rejected.

- Record screens by **element** (`--target "label=text:text"`) or **ratio** (`"label=at:0.5,0.8"`). Pixels are rejected.
- If you ran `app tap --shot` on a recorded target, **record the result** — with `screen_changed: true`, `note screen --name screen --target label --result ok`;
  with `not_found` or `screen_changed: false`, `--result fail`. Targets where failures lead get `verify`, so they are rechecked next time.
- When writing pitfalls or rules, it looks for similar ones first. If clearly the same, they are merged (`merged_into`); if ambiguous, you get `related` — if it is the same knowledge, merge as `next` says.
- Pitfalls with `flutter` · `platform` scope are stored at this-computer scope (`_machine`). Move old records with `note tidy` (plan) → `note tidy --apply`.

`references/learning.md`.

## Failure code → next action

| code | Next action |
|---|---|
| `no_device` | Check with `devices` and pass `--device`. If there is no device, follow the boot instructions in `next` |
| `not_found` · `index_out_of_range` | Pick from `candidates`. Screen language is in `locale`. Do not keep guessing |
| `bad_ratio` | `--at` takes only 0–1 ratios. If you have pixels, divide by the screen size |
| `pixels_rejected` (note screen) | Pixels are not stored. Use the `label=at:…` ratio from `hint`, or `text:` · `id:` · `desc:` if the element is visible |
| `tree_unsupported` · empty `elements` | Flutter canvas, etc. — tap with `--at` ratio coordinates and confirm with `--shot` |
| `build_mismatch` | Builds differ per device. Stop and align both sides |
| `ios_tool_missing` · `android_tool_missing` · `adb_missing` | Offer the install instructions from the result to the user |
| `non_ascii_unsupported` | Korean (non-ASCII) text not supported. Substitute English and note it in the report, or, if it is under test, use an IME or user input |
| `playwright_missing` | Ask the user, then `web setup` |
| `env_not_set` | The environment variable given to `--text-env` is empty. Set the value and retry |
| Validation failure in `scenario show` | Fill in expected results, braces and target, then `show` again |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start: run the snippet in `../references/preferences.md` with `SKILL_ID=pro-agent-test`.
Keys for this skill: the common `language`, `tone`, `rules` only.
Preferences change presentation only; approval gates, secret protection and `--dry-run` stay in force.
