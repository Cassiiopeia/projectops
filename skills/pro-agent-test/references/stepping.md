# Walking — observability · core loop · reset · limits · pitfalls

> When to read: right before actually walking the app (Phase 2·3), when a tap does not take or a verdict is unclear, and when you want to walk again from the start (Phase 6).

This expands Phase 2 · 3 · 6 of `SKILL.md`. For the commands themselves (options, codes), `../../pro-launch/references/app.md` is the source of truth.

## Phase 2 — Secure observability ⚠️

Before walking, first check **whether you can see the state**.

```bash
adb -s "$DEV" logcat -c
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
sleep 5 && adb -s "$DEV" logcat -d | grep -i "flutter"
```

If there are no logs, **that itself is a defect.** Record it as "untraceable" and walk on — do not add logging
for them. This skill **finds bugs; it does not fix them.**
Without logs you cannot know "the screen moved on, but was it saved?", so a pass verdict becomes a guess.

Minimum conditions for the logs that should exist (when reporting, use these to write "what is missing"):

| Subject | What to log | What must not be logged |
| --- | --- | --- |
| Local storage | Key name, read/write, **whether** a value exists | Raw tokens or PINs (mask as `***`) |
| API calls | Path, method, result summary | Personal data in the request body |
| Screen transitions | From where to where | — |

If you walked without logs, **also write "insufficient evidence"** in that stretch's verdict. It means the screen moved on but
you could not confirm the save; writing it as "pass" leaves a guess looking like a fact.

## Phase 3 — Walking (core loop)

For each step, repeat the following **in order**.

```
① read the screen → ② act by element → ③ check the result → ④ cross-check both sides → ⑤ server side
```

### ① Read the screen

```bash
source "{env_file value}"   # SHOT_DIR · DEV · PKG — from 'Where outputs go' in SKILL.md
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tree --device "$DEV"            # tappable text and ids + screen language (locale)
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV" --out step_N # only when you must look
```

- **If text confirms it, do not read the image.** If `elements` from `app tree` tells you what is there, that is enough.
  Images are the most expensive.
- **Read again before every action.** Do not tap from memory of the previous screen — a keyboard may have come up or
  a hint text may have been added and pushed elements down (this happens often).

> **Two things about captures need shrinking, and they need different methods (measured).**
>
> | What | By what | Effect |
> | --- | --- | --- |
> | Session tokens | **Lower resolution** | 1080x2400 original 1,473 tokens → 864 tokens at 1200 on the long side |
> | File size and transfer | **WebP conversion** | 495KB → 34KB |
>
> **Format has no effect on tokens** — tokens come only from width x height. That is why
> `app shot` · `web shot` do both before saving. If you need the original, use `--keep-format`.
> For images captured with other tools, `{LAUNCH}/launch_cli.py shrink` does the same processing.
> With 20 screenshots in a session, that is **29,460 → 5,880 tokens**. The gap grows as the walk gets longer.

### ② Act by element

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --text "Next" --shot step_N_after
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --id submit_button
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --desc "Close" --index 1
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app tap   --device "$DEV" --at 0.5,0.8      # only when there is no element — 0~1 ratio
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app swipe --device "$DEV" --dir up --shot list_scrolled
adb -s "$DEV" shell input text "{string}"        # space is %s, ASCII only
adb -s "$DEV" shell input keyevent KEYCODE_BACK  # dismiss keyboard · device back
```

- Use text **exactly in the screen's language** (`locale` from `app tree`). If not found, you get `not_found` and `candidates`
  (values actually on screen) — **do not keep guessing; pick from those.**
- **Do not compute pixel coordinates to tap.** Captures are downscaled, so coordinates measured on them miss.
  Only canvases and maps with no elements use `--at` ratio coordinates (pixels are rejected with `bad_ratio`).
- When scrolling a list, **go all the way to the end.** Swiping once and judging "it is cut off" is a misdiagnosis
  (why: this misdiagnosis really happened and an issue was filed for a bug that did not exist).
- On iOS, `app tap` · `app swipe` run through Maestro (10–40 seconds per call). Use the project's E2E flow for long scenarios.

### ③ Check the result

If `--shot` returns `screen_changed: false`, **you tapped and nothing happened** — pick another element, or
check whether that itself is a defect ("unresponsive element", `looks-wrong.md` axis 5). Do not look only at the screen. Check crashes and errors too.

If you tapped a target recorded with `note screen`, **record the result** — the next run then knows whether it can trust that record.

```bash
# screen_changed: true → ok / not_found · screen_changed: false → fail
{PYTHON} {SCRIPTS}/e2e_cli.py note screen --root {PROJECT_ROOT} --name "{screen}" --target "{label}" --result ok
```

```bash
adb -s "$DEV" shell dumpsys window | grep mCurrentFocus   # which screen is this now
adb -s "$DEV" logcat -d -b crash | tail -40               # did it crash
```

If you see `Application Error` or `FATAL EXCEPTION`, **stop there and find the cause first.**

### ④ Cross-check both sides

Check "what should remain", as set in Phase 1.

```bash
adb -s "$DEV" logcat -d | grep -E "action:|key:"          # what was stored on the device
{project's DB client} -c "select ..."        # what reached the server
```

If the screen moved on but the server is empty, **it is not a pass.** The reverse is also true.

> Designs that save **all at once at the end** instead of at every step are common. Do not call it a bug
> just because it is empty; check in the code when it saves first.

### ⑤ Look at the server side too ⚠️

**Do not pass on the screen alone.** The screen can be fine while a strange value went into the server.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py db   --profile db --root {ROOT} --sql "select ... where ..."   # did it really go in
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py logs --root {ROOT} --tail 100 --grep "{keyword}"                 # what was sent · was there an error
```

**How to connect and read logs differs per project.** Read the code to find out, record it in `access`,
and from then on use it directly with `--profile`. Connection: `../../pro-launch/references/server.md`; QA that walks a server: `target-server.md`.

## Phase 6 — Reset

To walk the same path again from the start, you must clear **both the account and the app state**. With social login,
once signed up, the account is tied to the provider identifier, so you cannot take the "first login" path again.

```bash
adb -s "$DEV" shell pm clear {package}     # app local data
# delete the server account with a tool the project provides
```

When deleting server accounts, **query and show what will be deleted first**, confirm that only test accounts are
deleted, then run it. If production data is mixed in, get the user's confirmation.

## Limits of this approach — when to move to integration_test ⚠️

This skill walks by **reading the screen and tapping on the spot.** Deciding what to tap must be done by a person (the model),
so the following are structurally impossible.

| Cannot do | Why |
| --- | --- |
| Unattended runs in CI | Reading the screen needs a person |
| Regression detection | It cannot compare with earlier runs automatically |
| Fast iteration | It reads the screen at every step |
| Inspecting widget internal state | It can only see what is drawn on screen |

**Flutter's element tree can be empty.** `uiautomator dump` sees only the canvas, and even with
`SemanticsBinding.ensureSemantics()` in the app, semantics are exposed only when an accessibility service is actually attached,
so the tree was still empty on the emulator (measured 2026-09-17). If `app tree` is empty,
use `app tap --at` ratio coordinates, and always confirm with `--shot` after tapping.

### So split the work like this

| | `integration_test` · `patrol` | This skill |
| --- | --- | --- |
| Finding elements | Finder — by widget key, does not break | Accessibility tree (text, id). Without a tree, ratio coordinates — they miss when the layout changes |
| Repeated CI runs | Yes | No |
| App changes | **Required** (pubspec, integration_test, build config) | Not required |
| External apps (social login web) | Limited (patrol reaches native) | **Crosses over** |
| Server DB cross-check | Not directly | **Does it** |
| Exploratory discovery | Sees only what was defined | **Finds the unexpected** |

**Once a path for repeated verification is settled, move it to `integration_test`.** This skill is the stage before that —
use it when you do not yet know what to verify, when external apps are involved, and when the server must be checked too.

> If the project already has `integration_test/` or `patrol`, **check those first.**
> There is no reason to verify the same thing twice.

## Common pitfalls (from real use)

| Pitfall | Symptom | What to do |
| --- | --- | --- |
| **The tap does not take** | `screen_changed: false` | Read `app tree` again. A keyboard or hint text pushes the layout. If the same text appears several times, use `--index` |
| **Cannot find by text** | `not_found` | Pick from `candidates` · `locale`. The screen language can differ from the device setting |
| **Did not scroll far enough** | An element looks cut off and you misjudge it as "hidden" | Swipe several times to the end. If it looks cut off where overlap is structurally impossible, suspect scrolling |
| **Crashes only in release** | debug is fine, only the release build crashes | Do not try to reproduce in debug. R8, signing and manifest only take effect in release |
| **Install fails on signature mismatch** | `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | Uninstall the existing app and install. CI builds and local builds have different signatures |
| **Screen loads from local data** | Account deleted on the server but home still shows | Clear app data too to reach the initial state |
| **Session remains so 2FA does not appear** | Sometimes it appears, sometimes not | Browser cookies remain. Assume it appears every time and prepare the instructions |
| **Korean (non-ASCII) text does not go in** | `NullPointerException` from `input text` · `non_ascii_unsupported` from `app type` | ASCII only. Substitute English and note it in the report, or install an IME if Korean itself is under test |
| **The element tree is empty** | Widget text does not show in `app tree` | Flutter is a canvas. Even with `ensureSemantics()`, an accessibility service must be attached, so it does not work on the emulator — use `--at` ratio coordinates |
| **Mistaking a screen transition for motion** | The centroid measurement (mean position of elements measured by brightness) keeps jumping | Narrow the measurement area to the element size. If the title or keyboard is mixed in, the value is meaningless |
| **Walked only the success path of an irreversible action** | Reported a pass, but failure behavior is undefined | **Deliberately create** a server failure and press the same button. You need both success and failure paths for a verdict |
| **Assumed the first screen shows everything** | Missed the effect of a button that affects off-screen items (select all, etc.) | For tall lists, **scroll to the end and count the items.** If there is select-all, check how far it turns things on |
| **Passed on the screen alone** | The screen is fine but a strange value went into the server | Cross-check **what the app sent** against the request body in the server logs (`logs --grep`) |
| **DNS does not come back after toggling the network** | `Failed host lookup` for specific domains only | Use `cmd connectivity airplane-mode enable/disable` instead of `svc wifi disable` |
| **The Google account picker looks empty** | Just added an account to the device but the app does not show it | It is registered. It appears after restarting the app |
| **Used old ratio coordinates on a screen whose list changed** | The wrong item is tapped and a completely different screen opens | Even one more item shifts everything below. Tap with `--text` when possible; with `--at`, **measure again on a screen whose list changed.** If builds differ per device, do it per device (`devices.md`) |

More commands and iOS handling: `target-app.md` · `../../pro-launch/references/app.md`.
