# Driving apps — Android emulator · iOS simulator · physical devices

> When to read: when you boot, install on or record a device, when `app tap`·`app swipe` do not do what you expect, or when you need to drive iOS.

Use `launch_cli.py app tap` · `app swipe` for taps and swipes. Call the tools directly only for what those cannot do (install, logs, recording).
**Add `-s "$DEV"` to every adb command.** With several devices attached, a command without it goes to the wrong one.

## PATH

Android SDK tools may not be on PATH. Use the `adb_path` from the `doctor`·`devices` result as is, or:

```bash
export PATH="$PATH:$HOME/Library/Android/sdk/platform-tools:$HOME/Library/Android/sdk/emulator"
```

---

## Capture · launch · tap · swipe — common

```bash
source "{env_file value}"
{PYTHON} {SCRIPTS}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
{PYTHON} {SCRIPTS}/launch_cli.py app shot   --device "$DEV" --out 01_login --clean-status
{PYTHON} {SCRIPTS}/launch_cli.py app tree   --device "$DEV"                       # tappable labels·ids + screen language
{PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --text "Log in" --shot after_login
{PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --id login_button      # resource-id · accessibilityIdentifier
{PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --desc "Close" --index 1 # accessibility description · which one if several (from 0)
{PYTHON} {SCRIPTS}/launch_cli.py app tap    --device "$DEV" --at 0.5,0.8           # only when no element matches — ratio coordinates
{PYTHON} {SCRIPTS}/launch_cli.py app swipe  --device "$DEV" --dir up --shot list_scrolled
{PYTHON} {SCRIPTS}/launch_cli.py app swipe  --device "$DEV" --from 0.5,0.8 --to 0.5,0.2 --ms 500
{PYTHON} {SCRIPTS}/launch_cli.py app back   --device "$DEV"                       # back (Android back key · dismiss keyboard)
```

- `--device` is an Android serial or an iOS UDID. Without it: `$DEV` → the only attached device, if there is exactly one.
  **With several devices and none chosen, it stops with `no_device`** — so it never captures the wrong device.
- `--clean-status` pins the status bar to 9:41 · battery 100% for the capture and **restores it afterwards**
  (iOS `simctl status_bar`, Android demo mode + the allow setting restored). Captures then do not show different times.
- The default is WebP with the long side at 1200px. **When you need the original, for example for pixel comparison**, use `--keep-format`
  (or pass a full path to `--out` and it is saved as is). Tune with `--max-side` · `--quality`.
- **Find targets by screen element, not by eyeballed coordinates.** Write labels **in the screen language, as shown**. If unsure, check
  `locale` and `elements` from `app tree` first. On a miss you get `not_found` with the `candidates` actually on screen —
  **pick from them instead of guessing again**.
- With `--shot`, it captures **after the screen changes and settles** and returns the path (no extra `app shot` needed to check).
  `screen_changed: false` means the tap did nothing — pick another element.
- Use `--at 0.5,0.8` **ratio** coordinates (0–1) only for things that are not elements (canvas, map). Pixels are rejected (`bad_ratio`) —
  captures are downscaled, so taps at those coordinates miss.
- `swipe --dir up|down|left|right` moves 15% inside the screen edges to avoid edge gestures.
  For an exact path use `--from`·`--to` ratio coordinates and `--ms` (default 300).
- `app back` is the Android back key. iOS has no back button, so it returns `back_unsupported_on_platform` with alternatives
  (tap the on-screen back button with `app tap --desc|--text`, or an edge swipe `app swipe --from 0.02,0.5 --to 0.8,0.5`).
- Android uses the built-in `uiautomator`, so nothing to install. **iOS needs Maestro** (simctl has no tap command).
  Maestro starts fresh on every call and takes 10–40 seconds — visible in the result's `elapsed_seconds`.
  Without a resident session, when one call takes over 15 seconds, `next` becomes `app session start --device <UDID>` and the original next action moves to `hint`.
  **For two or more steps, bundle them with `app run`** (below). Run longer scenarios as the project's Maestro flow.

### Several steps at once — `app run` (#894)

```bash
cat > steps.json <<'JSON'
[{"tap": {"text": "Email"}}, {"type": {"env": "LOGIN_EMAIL"}},
 {"tap": {"id": "password_field"}}, {"type": {"cred": "staging", "submit": true}},
 {"wait": {"text": "Home", "timeout": 10}}]
JSON
{PYTHON} {SCRIPTS}/launch_cli.py app run --device "$DEV" --steps steps.json --shot after_login
```

| Step | Keys |
|---|---|
| `tap` | one of `text` · `id` · `desc` (+`index`), or `point: "0.5,0.8"` ratio |
| `swipe` | `direction: up\|down\|left\|right`, or `from`·`to` ratios (+`ms`) |
| `type` | `env` (environment variable name) or `cred` (+`field`), `submit` — **never write the value into the file** |
| `wait` | one of `text` · `id` · `desc` + `timeout` (seconds, default 10 · max 60) |
| `back` | `true` — Android only (iOS gives `step_unsupported_on_platform`) |

- On iOS, Maestro starts **only once** (measured: 4 steps in 20 seconds; called separately, 15–45 seconds per step). On Android the same file runs step by step.
- Result: `steps[]` (per-step `status`: completed · failed · not_run · unknown) · `failed_step` · `elapsed_seconds`.
  `--shot` captures only when every step succeeds. On iOS, `text`·`wait` must match the **full element label**.

| code | Next action |
|---|---|
| `bad_steps` | Fix step number `step_index` (`null` means the file itself — path, JSON, empty array) |
| `step_failed` | Inspect from `failed_step` with `app tree`, fix, and run again. `null` means it stopped before any step (`error`) |
| `step_unsupported_on_platform` | The alternative in `next` (tap the back button · edge swipe) |
| `env_not_set` · `cred_field_missing` · `non_ascii_unsupported` | Fix the value source of the type step at `step_index` |

If the result has a `cause` (for example `android_system_not_ready`), the **device state** is the problem, not the steps — check the device before changing steps.

### Waiting · recording · burst capture · status bar time (#928)

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app wait --device "$DEV" --text "Loading" --gone --timeout 30   # until it disappears (without --gone, until it appears)
{PYTHON} {SCRIPTS}/launch_cli.py app wait --device "$DEV" --settle --timeout 20                  # until the screen structure is the same twice in a row (transition·loading done)
{PYTHON} {SCRIPTS}/launch_cli.py app record start --device "$DEV" --out login_flow                # iOS simctl recordVideo · Android screenrecord (180-second limit)
{PYTHON} {SCRIPTS}/launch_cli.py app record stop  --device "$DEV" --gif                           # also poster · gif when ffmpeg is present
{PYTHON} {SCRIPTS}/launch_cli.py app tap --device "$DEV" --text "Continue" --burst 6:0.4          # 6 seconds around the action, every 0.4 seconds — returns only changed frames
{PYTHON} {SCRIPTS}/launch_cli.py app shot --device "$DEV" --out store_01 --time 7:42              # set the status bar time to match a notification time (includes --clean-status)
```

- **If you do not know which element to wait for, use `--settle`.** Waiting for any text, like `--text "."`, is not waiting (30–60 seconds per timeout).
  A screen that keeps moving (animation · auto-advance) gives `wait_timeout` — then pick a label to wait for and use `--text`.
- `app wait` does not count an unreadable screen as "gone". In `app run` steps, use `{"gone": {...}}` or `{"wait": {...}, "gone": true}`.
- `--burst` drops duplicates by byte hash (clock and animation changes count as changes). Max 150 frames · 30 seconds.
- `app shot --shot <name>` is an alias for `--out`.

### Gesture playbook — capture mid-swipe · swipe from an element · tap right after a swipe (#862)

We do not add dedicated options. **Use `tap`·`swipe`·`run` for what they can do; run anything else as a Maestro flow with `app flow`.**

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app flow --device "$DEV" --file .maestro/swipe_undo.yaml --shot undo [--timeout 300]
```

- Result: `commands[]` (per Maestro command `completed`·`failed`·`skipped`) · `failed_command` · `screenshots[]` (the flow's
  `takeScreenshot` output moved to `SHOT_DIR` as `<--shot>_<name>.webp`) · `driver_retried` · `elapsed_seconds`.
  The Maestro log (`maestro.log`) goes to a temp folder and is deleted. Project `.maestro/` flows work as is.
- Works on both Android and iOS (needs Maestro). It starts a new `maestro test`, so the iOS resident session loses its connection (it reattaches on the next call).

| Goal | How |
|---|---|
| Tap **right after** a swipe (swipe to delete > "Undo" within 4 seconds) | iOS: `swipe` > `wait` > `tap` in `app run` (one Maestro run). Android re-reads the screen structure each step and can be late — bundle it with `app flow` (example below) |
| Start from an element | Re-read `app tree` **right before** the swipe (a banner shifts the row's y — 87% > 80% measured). Start from the label side, **avoiding switches·buttons (right edge)** in the row. In a flow, start from the element, like `swipe: {from: {text: "..."}, direction: LEFT}` |
| First tap right after Maestro starts does not register | `retryTapIfNoChange: true` on `tapOn`, preceded by `extendedWaitUntil: {visible: ...}` |
| Screen **in the middle of** a swipe | See "Mid-gesture frames" below |

```yaml
appId: com.example.app
---
- extendedWaitUntil: {visible: "Notification 1", timeout: 5000}
- swipe: {from: {text: "Notification 1"}, direction: LEFT, duration: 400}   # start from the label — avoid the switch on the right
- takeScreenshot: after_swipe
- tapOn: {text: "Undo", retryTapIfNoChange: true}
- takeScreenshot: after_undo
```

**Do not capture mid-gesture frames (finger down, paused) by driving the device.**

- iOS simulator: Maestro `swipe` is "long press, then move fast" even with a longer `duration`, so there is no middle frame (at 20·40 seconds, all 34 frames unchanged — reported upstream).
- Android: `adb shell input motionevent DOWN/MOVE/UP` spawns a process per command, **3.5 seconds per call on a loaded emulator**,
  and it was read as a long press before the first MOVE, opening the home screen menu (measured 2026-10-17, API 36). Running a slow `input swipe` in the background
  while taking `screencap` gave black frames and could not be confirmed — results vary by device and load, so do not rely on it.
- **Instead**: in Flutter, put the widget into the mid-drag state in a test and export a PNG with `RepaintBoundary`'s `toImage()`
  (seconds with `flutter test`, no device needed). If it must feel like a real device, record with `simctl io recordVideo` / `screenrecord`,
  have a person do the swipe, and extract frames (see "Measure motion with numbers" below).

| code (`app flow`) | Next action |
|---|---|
| `flow_file_required` · `bad_timeout` | Fix the arguments |
| `flow_failed` | Inspect `failed_command` with `app tree` and fix the flow. `screenshots` holds captures up to the failure |
| `flow_timeout` | Raise `--timeout` or split the flow |
| `maestro_driver_timeout` | The driver did not start in time (`did not start up in time`). The CLI returns this after force-stopping the driver app (Android `dev.mobile.maestro*`) and retrying once. **The machine is overloaded** — stop builds or ask the user about a cold boot |
| `maestro_tool_missing` | Suggest the install command in `next` to the user |

### iOS resident session — `app session` (#894 phase 2, optional)

Instead of starting Maestro (JVM) on every call, start `maestro mcp` once and reuse it. Turn it on when you look → decide → tap many times.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app session start  --device "$DEV"      # by UDID ("booted" gives session_needs_udid)
{PYTHON} {SCRIPTS}/launch_cli.py app tree           --device "$DEV"      # transport: session
{PYTHON} {SCRIPTS}/launch_cli.py app session status --device "$DEV"
{PYTHON} {SCRIPTS}/launch_cli.py app session stop   --device "$DEV"
```

- **If `tap_failed` keeps repeating at 90 seconds and `session start` also fails**, check `stale_maestro_drivers` (leftover Maestro drivers) and `host_load` (load) in the response.
  Stop leftovers with `app session stop --device "$DEV" --kill-stale` (processes with a live parent are not touched, only reported in `other_maestro_processes`). Under high load, `MAESTRO_DRIVER_STARTUP_TIMEOUT=180000` is set automatically.
  Maestro startup is serialized by a machine-wide lock (`maestro_lock.waited_seconds`).
- **When tapping by label**, `--text` checks text · desc · label. Order: exact match > normalized (Flutter's duplicated `"X\nX"`, invisible markers, whitespace) > partial match.
  `matched_by` in the response tells which field matched. On a miss you get `did_you_mean` (for example `--desc 'Home tab'`) plus text · desc candidates.

| Measured (iOS 18.3 simulator, Maestro 2.10.0) | No session | Session |
|---|---|---|
| `session start` (startup + device connection warm-up) | — | 7.8 s |
| `app tree` | 11.5 · 11.7 s | 0.6 s |
| `app tap --at` · `--text` | 16.8–17.5 s | 0.9–1.1 s |
| `app swipe` | 14–22 s | 1.3 s |
| `app run` 4 steps | 20 s | 0.1–1 s per step |

- When a session is on, `tap`·`swipe`·`tree`·`run` use it **automatically**. The result shows `transport: session`. If it cannot be used, the call silently
  falls back to the normal path and records the reason in `session_fallback` (`session_gone` · `session_timeout` · `session_not_ready` · `device_unreachable`, etc.).
- `app run` in a session calls run separately per step (about 1 second per step), so it pinpoints which step failed.
- **`app type` (and any `app run` with a type step) does not use the session** — `maestro mcp` echoes env values back in plain text in the run response,
  and a resident process's log location cannot be moved to a temp folder per call. Instead, the per-call path redirects the Maestro log
  to a temp folder and deletes it (measured: input values were left in plain text at the default location `~/.maestro/tests/*/maestro.log`).
- **When another `maestro test` attaches to the same device, the session's device connection drops** (including type). The relay reattaches on the next call
  (about 9 seconds once, `session_reconnected: true`).
- It ends by itself after 20 minutes idle (`--idle-minutes`, 1–240 minutes). If the relay was killed, the next call or `status` cleans up the leftover files.
- Turn off the web viewer (default port 9999) with `--no-viewer`. Older Maestro versions without that option start it on a free port and record it in `viewer.url`
  (if 9999 is taken, the next free port — it does not fail).
- State: `{PROJECTOPS_HOME or ~/.projectops}/launch/maestro-sessions/<UDID>.json` (mode 600 — access token) · relay log `<UDID>.log`.

| code | Next action |
|---|---|
| `session_start_failed` | Check `reason` (`device_unreachable` · `maestro_mcp_start_failed` · `session_start_timeout`). You can keep working without a session |
| `session_tools_missing` | This Maestro version uses different MCP tool names (`tools_available`). Work without a session |
| `session_starting` | Another call is starting it. Check `status` shortly |
| `session_needs_udid` · `session_verb_required` · `bad_idle_minutes` | Fix the arguments |
| `session_stop_failed` | The kill command in `next` |

| code | Next action |
|---|---|
| `no_device` | List with `devices` and pass `--device` |
| `not_found` | Pick from `candidates`. The screen language is in `locale` |
| `index_out_of_range` | Check `matches` (number of matches) and pick with `--index 0..matches-1` (range in `next`) |
| `back_unsupported_on_platform` | iOS — the alternative in `next` (tap the on-screen back button · edge swipe) |
| `ui_dump_failed` | The screen is mid-transition or a secure screen. Re-read `app tree` shortly. If it keeps failing, use `--at` ratio coordinates. With several iOS simulators, suspect a Maestro driver port (22087) conflict (`kb show ios-maestro-driver-port-conflict`) |
| `no_focused_window` | Android has no focused window (screen off · locked · right after reboot). The CLI returns this after waking the screen (`WAKEUP` · unlock) and re-reading up to three times. For a password lock, ask the user to unlock |
| `android_system_not_ready` | The boot animation is showing (system_server restart loop measured). If waiting does not help, ask the user about a cold boot |
| `ui_automation_unavailable` | uiautomator could not attach to UiAutomation. Check whether another automation (Maestro · Appium) holds the device |
| `ui_dump_timeout` | Did not finish in 20 seconds (after one retry). On a screen with continuous animation, use `--at` ratio coordinates |
| `tree_unsupported` | This device backend cannot read the screen structure. Look with `app shot` and tap with `--text`, or use `--at` ratio coordinates |
| `ios_tool_missing` · `android_tool_missing` | Suggest the install command in `next` (Maestro for iOS) to the user |
| `adb_missing` | Set PATH as below, or use `adb_path` from `doctor` |
| `capture_failed` | Locked screen or `FLAG_SECURE` (see "Observe" below) |

## Terminate · relaunch · location · permissions · push · deep links (#893)

Use these instead of raw `xcrun simctl` · `adb shell am|pm`. The package comes from `--pkg` → `$PKG` → the package from `device bind`.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app terminate  --device "$DEV" --pkg "$PKG"      # was_running=false if it was not running (null on Android)
{PYTHON} {SCRIPTS}/launch_cli.py app relaunch   --device "$DEV" --pkg "$PKG"      # does not launch if terminate failed
{PYTHON} {SCRIPTS}/launch_cli.py app location   --device "$DEV" --lat 37.5665 --lon 126.978
{PYTHON} {SCRIPTS}/launch_cli.py app permission --device "$DEV" --pkg "$PKG" --service photos --grant   # or --revoke
{PYTHON} {SCRIPTS}/launch_cli.py app push       --device "$DEV" --pkg "$PKG" --payload push.json       # iOS simulator only
{PYTHON} {SCRIPTS}/launch_cli.py app openurl    --device "$DEV" --url "myapp://home?id=1"              # on Android, --pkg pins it to that app
```

| Action | iOS simulator | Android |
|---|---|---|
| terminate · relaunch | `simctl terminate` · `launch` | `am force-stop` · `monkey` |
| location | `simctl location set` | emulator only, `emu geo fix` (physical device → `unsupported_on_platform`) |
| permission | `simctl privacy` — services: `all` `calendar` `contacts` `location` `location-always` `photos` `photos-add` `media-library` `microphone` `motion` `reminders` `siri` (the app is killed when a permission changes) | `pm grant/revoke` — `camera` `microphone` `location` `location-always` `contacts` `calendar` `photos` `notifications` or a raw `android.permission.X` |
| push | `simctl push` (`--pkg` not needed if the payload has `Simulator Target Bundle`) | `unsupported_on_platform` — use an FCM test message |
| openurl | `simctl openurl` | `am start -a VIEW -d` |

| code | Next action |
|---|---|
| `package_required` | Pass `--pkg` |
| `unsupported_on_platform` | The alternative in `next`. Permission services that exist only on the other platform (iOS `camera`, etc.) also give this code |
| `bad_coordinates` · `permission_mode_required` · `payload_invalid` · `url_required` | Fix the arguments (reason in `error`) |
| `unknown_permission_service` | Pick from `candidates` |
| `terminate_failed` · `launch_failed` · `location_failed` · `permission_failed` · `push_failed` · `openurl_failed` | Read the tool output in `error`. For openurl, check that the app registered the scheme |

To add a new platform (backend), see `extending.md`.

---

## Borrow · boot · own · language·appearance (#923 · #924 · #925 · #929 · #953)

```bash
{PYTHON} {SCRIPTS}/launch_cli.py device boot    --device "{UDID|name|AVD}" [--window headless|small|normal] [--scale 0.4] [--cold]
{PYTHON} {SCRIPTS}/launch_cli.py device reboot  --device "$DEV" [--cold] [--yes]   # soft · cold (emu kill > force stop > -no-snapshot-load)
{PYTHON} {SCRIPTS}/launch_cli.py device acquire --platform ios --purpose "#953 login" [--form tablet] [--os ">=17"] [--wait 90]
{PYTHON} {SCRIPTS}/launch_cli.py device release --device "$DEV" [--keep-booted]    # restore changed language·appearance > shut down if this borrow booted it
{PYTHON} {SCRIPTS}/launch_cli.py device release --all                              # every lease of this session (the session-end hook calls this too)
{PYTHON} {SCRIPTS}/launch_cli.py device shutdown --device "$DEV" [--yes]            # shut down (refuses a device borrowed by someone else without --yes)
{PYTHON} {SCRIPTS}/launch_cli.py device claim   --device "$DEV"                    # this session takes a specific device
{PYTHON} {SCRIPTS}/launch_cli.py device acquire --platform ios --need login:kakao   # a device with that state recorded (#954)
{PYTHON} {SCRIPTS}/launch_cli.py device acquire --platform ios --fresh | --count 2  # an unused new phone · two different devices (created if none)
{PYTHON} {SCRIPTS}/launch_cli.py device mark    --device "$DEV" --kind login --name kakao --note "guardian account"   # --verify refreshes the checked time
{PYTHON} {SCRIPTS}/launch_cli.py device unmark  --device "$DEV" --kind login --name kakao
{PYTHON} {SCRIPTS}/launch_cli.py device adopt   --device "{UDID|AVD name|device name}"   # add a device that was not in the ledger
{PYTHON} {SCRIPTS}/launch_cli.py device records [--platform ios]                    # origin · marks · temp expiry · borrowing session · limits
{PYTHON} {SCRIPTS}/launch_cli.py device create  --platform ios --reason "#954 two at once" [--form tablet] [--os ">=17"] [--ttl-days 3] [--name ...]
{PYTHON} {SCRIPTS}/launch_cli.py device erase|delete --device "{key}" [--yes]          # refuses without --yes for marks · others' borrows · devices a person booted
{PYTHON} {SCRIPTS}/launch_cli.py device clone   --device "{shut-down iOS device}" --reason "#955 two logged-in devices"   # state records are copied as unverified
{PYTHON} {SCRIPTS}/launch_cli.py device gc [--sizes]                                 # report only · --apply to run
{PYTHON} {SCRIPTS}/launch_cli.py device benchmark [--platform ios] [--full] [--yes]  # measure this machine's device capacity and store it in config
{PYTHON} {SCRIPTS}/launch_cli.py device locale  --device "$DEV" --lang en --region US [--app "$PKG"]   # --restore to revert
{PYTHON} {SCRIPTS}/launch_cli.py device appearance dark --device "$DEV"            # light|dark, --restore to revert
{PYTHON} {SCRIPTS}/launch_cli.py device text-size largest --device "$DEV"           # default|large|largest (or 1.3), --restore to revert (large-text QA)
```

- **Window size and capture size are unrelated.** Captures read the device screen directly and shrink it with `--max-side`. A window is only needed when a person debugs, so **headless is the default** when an agent boots a device.
  On iOS, `--window small|normal` writes that device's window scale (`DevicePreferences.<UDID>.SimulatorWindowGeometry.<screen>.WindowScale`) **only when Simulator.app is not running**, and opens only that device's window.
  If Simulator.app is already running (it may belong to another session), it is not closed; you get only `window_scale_pending: true` + `window_hint`. A device that is already booted is not changed (`already_booted`).
- **Is it in the foreground? (#923)** `app launch|relaunch` checks after launching. On Android it watches up to ~5 seconds for the focused window·resumed activity to be the target package — otherwise `not_foreground` (`foreground_package` · `blocking_activity`).
  On iOS, after ~2.5 seconds it checks that `UIKitApplication:<bundle>` is in `launchctl list` — otherwise `app_exited` + the newest crash report (`crash_report.path` · `exception_line`). If the check itself fails (`dumpsys` timeout), it does not turn the success into a failure.
- **Borrow · return (#953).** `acquire` picks a free device that matches the conditions (platform · form factor · OS): booted > recently used, and boots it if it is off.
  A booted device with no ledger record may be in use by a person, so it is not picked. When the same session calls again, it gets a **different** device (parallel sub-agents).
  If others are using all of them, the verdict is `wait`; if the combined wait exceeds 10 minutes (`launch.devices.wait_limit_minutes`) or a new boot is needed under `critical` memory, it is `ask`.
  One `--wait` is at most 90 seconds — within the tool command time limit. In Claude Code, a hook calls `release --all` when the session ends.
- **Prepared state · creating devices (#954).** Record state that cannot be read from the device (login · test data · permissions · settings) with `device mark`. kind·name are free strings (suggested kinds: login · data · permission · config · other).
  A mark becomes `is_stale` after 14 days (`launch.devices.mark_stale_days`) — check that the login still works and run `mark --verify`. `--need` still picks the device even when the mark is stale.
  `acquire` creates a temporary device only when no device is free and neither `--need` nor `--device` was given (`verdict: create`). It does not create one when any of 3 limits applies:
  memory `critical` · free disk below 20GB (`min_free_disk_gb`) · number of booted virtual devices at `max_booted` (computed from RAM: 2 at 16GB, 6 at 32GB).
  A created device stays in the ledger with its reason and expiry (`temp_ttl_days`, default 3 days). `erase` also clears marks and setting records and marks it as a new phone.
  iOS uses the first device type (per form factor) of the newest runtime; Android uses an AVD of the same form factor as the template (system image · hardware profile) — without a template AVD you get `create_failed`.
- **Clone · cleanup (#955 · #959).** Only a shut-down source can be cloned. iOS (simctl), measured: data and keychain files carry over, it is an APFS clone so disk use is about 10MB, 8 seconds.
  Android copies the whole AVD folder (macOS `cp -c`) — the disk backing paths are relative, so the clone is not tied to the source, and the login lives in userdata, so it survives even a fresh boot when the snapshot does not match.
  A clone's marks are "unverified" (stale) — some services bind login tokens to the device, so check the login still works on the clone and run `mark --verify`.
  `acquire --count 2 --need login:X` clones first when there are not enough shut-down devices with that state. Android read-only parallel runs (`-read-only`) are not used — cloning does the same job.
  `gc` deletes only expired temporary devices (no borrowing session · no marks), and shuts down devices the ledger booted and left unused for over 20 minutes.
  Devices without records and devices with marks are only reported. Sizes count only cleanup targets — use `--sizes` for everything (scans tens of GB, takes tens of seconds).
- **Capacity · memory budget (#964).** How many devices can run depends on the machine (Mac · Windows · Linux) and on what else is running. `device benchmark` boots one test device per type,
  measures memory per device (on macOS the top footprint — RSS leaves out compressed and swapped memory, so a 5.6GB emulator showed as 245MB) · boot time · capture time, and writes
  `boot_cost_mb` · `memory_budget_mb` · `memory_reserve_mb` into the `launch.devices` config. `--full` adds devices one at a time until a stop signal (slow).
  - 2 boot checks: sum of costs of booted virtual devices (booted by any session) + new device cost <= budget · current free memory >= new device cost + reserve
  - If never measured, defaults apply (iOS 1500MB · Android 6000MB · budget = RAM - 8GB)
  - Boots happen one at a time across the whole machine (boot-turn lock) — the session that gets the turn re-checks against current memory before booting. `device boot` goes through the same turn · budget (a memory risk is asked of the user and only bypassed with `--user-approved` after an answer)
  - For a type that already has a booted device, it measures that device's real usage (no new boot — even with other sessions present). It boots a test device only when there is none
  - On iOS it sums every process under that UDID's `launchd_sim` (inner processes do not have the UDID on their command line). Measured (18GB Mac): one iOS device footprint 3,590MB · free memory down 2,055MB · boot 23 s · capture 1.1 s; one Android device 5,589MB
  - A test device boots only when cost + 1GB is free (using acquire's 3GB reserve would mean a busy machine could never be measured)
  - On macOS, trust the OS memory-pressure verdict — macOS grows swap as it uses it, so usage always sits near 90%; judging risk by swap ratio blocked every boot (measured)
  - Measurement does not start while another session is using a device, and stops on a stop signal (memory critical · free swap under 1GB · boot 2.5x or capture 3x slower · acceleration failure). Test devices are always shut down and deleted
- **If an emulator gets stuck at offline**, check the log for `hvf is not enabled` · `mprotect failed` — when host swap is nearly full it cannot get hardware acceleration,
  falls back to software mode and never finishes (measured: swap 28.9/29.7GB). `boot`·`acquire` see these signs, shut it down without waiting, and report `emulator_no_acceleration`.
- **Ownership (#925 · #953).** The owner is a lease = (session, agent host pid). It is released immediately when the host dies, or after 30 minutes unused (`launch.devices.lease_idle_minutes`) even if the host is alive.
  **Changing actions** (install · launch · tap · type · swipe · run · flow · permission · push · locale · appearance, etc.) on a device owned by another live session are refused with `device_owned_by_other` — ask the user, then use `--yes`.
  Reads (shot · tree · wait) only get a warning field. `device reboot`·`release`·`shutdown`·`claim` also stop without `--yes`.
  The session is identified by `LAUNCH_SESSION` > `CLAUDE_CODE_SESSION_ID`, or by host pid when neither exists (if `owner_identity: weak`, set `LAUNCH_SESSION`). See owners in `owners` from `device list`·`devices`.
- **Language limits.** The iOS system language needs `defaults write -g AppleLanguages/AppleLocale` and then a reboot (that simulator's app state is lost). `--app` changes only the app domain and needs only an app restart.
  Android is API 33+ only: per app with `cmd locale set-app-locales` (when labels such as Google Maps follow the app language); system-wide only on images that have `cmd locale set-device-locale`.

---

## Android

### Prepare the device

```bash
adb devices                       # check connection
emulator -list-avds               # available AVDs

# boot — start without a window and wait until usable (instead of raw emulator / nohup loops)
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device {AVD name}                  # headless by default (-no-window)
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device {AVD name} --window small   # when you need a window (-scale 0.4)
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device {AVD name} --cold           # -no-snapshot-load
```

Ready = shell responds + `sys.boot_completed` + package service + focused window is not "Not Responding" (3 times in a row). `init.svc.bootanim` is not checked.

If you booted the device later, run `device list` once more — it fills `$DEV` in `env.sh`.

> **Google Play images do not allow `adb root`.** You cannot open app-internal files (`/data/data/...`)
> directly, so check state through **app logs**. Google APIs images allow root but are
> further from a real user environment.

### Install

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app install --device "$DEV" --path {apk}   # readiness check > push > pm install -r -t (time limit per stage)
adb -s "$DEV" uninstall {package} && adb -s "$DEV" install {apk}   # in this order when signatures differ
adb -s "$DEV" shell pm clear {package}        # reset data only (app stays installed)
```

When `app install` hits `Broken pipe` / `Can't find service: package` right after boot, it waits for the service to come back and retries **once**.
If the device does not respond, it returns `device_unresponsive` + host memory figures (`resources`) and `next: device reboot --device <id> --cold`.

`INSTALL_FAILED_UPDATE_INCOMPATIBLE` is a signature mismatch. CI builds and local builds use different keys.

### Drive

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
{PYTHON} {SCRIPTS}/launch_cli.py app terminate --device "$DEV" --pkg "$PKG"

{PYTHON} {SCRIPTS}/launch_cli.py app tap   --device "$DEV" --text "{on-screen label}" --shot {name}
{PYTHON} {SCRIPTS}/launch_cli.py app swipe --device "$DEV" --dir up
{PYTHON} {SCRIPTS}/launch_cli.py app back  --device "$DEV" --shot after_back   # dismiss keyboard / back
{PYTHON} {SCRIPTS}/launch_cli.py app type  --device "$DEV" --text-env QUERY --submit   # text + done key ("Typing text" below)
```

Do not use raw `adb shell input keyevent` · `input text` — they skip the device ownership check and logging, and the value stays on the command line.
If Korean (non-ASCII) text cannot be typed, substitute English and record that you did.

### Typing text — use stored login info (Android · iOS)

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app type --device "$DEV" --cred naver-test --cred-field account
{PYTHON} {SCRIPTS}/launch_cli.py app type --device "$DEV" --cred naver-test --submit      # password + Enter
QUERY='coffee' {PYTHON} {SCRIPTS}/launch_cli.py app type --device "$DEV" --text-env QUERY  # non-secret values also go through an environment variable
```

- The value reaches the device **only through stdin, not the command line** (it does not show up in host `ps`). There is no way to pass the value directly with `--text`.
- It goes into the focused input — tap the input first with `app tap --text|--id` (by element) to focus it. Check with `app shot` after typing.
- **`adb input text` handles ASCII only** (no Korean → `non_ascii_unsupported`). Install an IME if you need Korean.
- **Even ASCII gets composed into jamo on Korean·Japanese·Chinese keyboards.** `--ime auto` (default) detects a composing keyboard and, only while typing, switches to an input method that inserts characters as is (Maestro IME · ADBKeyboard), then switches back.
  After typing it re-reads the input; if it differs you get `typed_text_mismatch` (for secrets only the length, never the value · password fields give `verification: skipped_password_field`). `--ime keep` does not switch, `--ime ascii` forces the switch. The input method is a device-wide setting, so ask first on someone else's device.
- **iOS types with Maestro `inputText` (#895).** The value is passed only through a `MAESTRO_` environment variable, so it stays out of flow files and the command line.
  Without Maestro you get `ios_tool_missing` (install command in `next`); on failure, `app_type_failed` (values in the output are `***`). 10–40 seconds per call.
  type does not use the resident session even if one exists (`session_fallback: secret_input_per_call`, see "iOS resident session" above).
- If no login info is stored, ask the user and **`cred set` only what they allowed** ("When storing login info" in `references/web.md`).
- Handle in-app login interstitials (trust this device · stay signed in · upsell) with `login_policy` in the result — the rules are the same as for the web
  ("Login interstitials" and "Two-factor authentication" in `references/web.md`). Read the screen with `app shot` · the tree, send the capture into the conversation,
  get the code from the conversation and type it with `app type --text-env`. For approval waits, re-read the screen to confirm it moved on.

### Observe

```bash
{PYTHON} {SCRIPTS}/launch_cli.py app shot --device "$DEV" --out {name}
adb -s "$DEV" shell dumpsys window | grep mCurrentFocus    # current screen
adb -s "$DEV" logcat -c                                     # clear the buffer
adb -s "$DEV" logcat -d | grep -i flutter                   # app logs
adb -s "$DEV" logcat -d -b crash | tail -40                 # crashes

# record (to check animations)
adb -s "$DEV" shell screenrecord --time-limit {seconds} --bit-rate 12000000 /sdcard/rec.mp4
adb -s "$DEV" pull /sdcard/rec.mp4 "$RUN_DIR/{name}.mp4" && adb -s "$DEV" shell rm /sdcard/rec.mp4
```

If `app shot` stops with `capture_failed`, the screen is locked or a secure screen (`FLAG_SECURE`).
A secure screen captures as black or is blocked — the app blocks it on purpose, so it is not a defect.

### Measure motion with numbers

```bash
ffmpeg -i rec.mp4 -vf "fps=60,crop={w}:{h}:{x}:{y}" frames/f%03d.png
```

**Narrow `crop` to the size of the element you measure.** A wide crop also catches the title·keyboard, and the center of mass
moves in misleading ways (this mistake once made a screen transition look like jitter).

---

## iOS simulator

```bash
xcrun simctl list devices                      # list
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device "{device name or UDID}"         # boot without a window (headless by default)
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device "{device name}" --window small  # open with window scale 0.4
{PYTHON} {SCRIPTS}/launch_cli.py device boot --device "{device name}" --scale 0.5     # set the scale directly (0.3–1.0, opens a window)

{PYTHON} {SCRIPTS}/launch_cli.py app install --device {UDID} --path {Runner.app}   # .app folder (.ipa is for physical devices)
{PYTHON} {SCRIPTS}/launch_cli.py app launch --device {UDID} --pkg {bundle ID}
{PYTHON} {SCRIPTS}/launch_cli.py app terminate --device {UDID} --pkg {bundle ID}
xcrun simctl uninstall {UDID} {bundle ID}

{PYTHON} {SCRIPTS}/launch_cli.py app shot --device {UDID} --out {name} --clean-status
xcrun simctl io {UDID} recordVideo {path}.mp4   # stop with Ctrl+C
```

Pass the bundle ID to `--pkg`. For your own app, use the bundle ID returned by `detect --path .`.
System app examples: Settings `com.apple.Preferences` · Safari `com.apple.mobilesafari` · Photos `com.apple.mobileslideshow`.

### Never tap the iOS simulator by coordinates ⚠️

**Forbidden: `cliclick` · clicking the Simulator window with AppleScript/`osascript` (System Events) · CGEvent, and any other method
that moves the host mouse to tap screen coordinates.**

- It **moves the user's real cursor.** If the user is working in another app, it interrupts them and clicks the wrong app
  (real incident: an app other than the simulator was clicked).
- It depends on window position, size and which window is in front, so it misses, and **you cannot tell what was clicked.**

When you need to drive the UI, follow this order:

0. **Use `app tap --text` · `app swipe` for one or two taps, and `app run --steps` for several steps.** They call Maestro internally and find
   elements through accessibility data, so the host cursor is never touched. Without Maestro you get `ios_tool_missing` with the install command in `next`.
1. **For long scenarios, first look for the E2E approach the project already has.** Check `e2e/` · `.maestro/` · `tool/*e2e*` ·
   `integration_test/`. If one exists, use it — it **finds widgets by text**, so no coordinates are needed.
   Do not pick one arbitrarily without checking what the project already uses.
2. If none exists, **ask the user which approach to use**: write a Maestro flow / write `flutter drive`·`integration_test`
   / for only a few steps, the user drives it by hand.
3. For what works **without coordinates**, use `app` actions: launch·terminate (`app launch|terminate|relaunch`) · deep links (`app openurl`) ·
   permissions (`app permission`) · location (`app location`) · push (`app push`) · capture (`app shot`). Only recording uses `simctl` directly.

**Screens outside the app cannot be tapped automatically.** Web auth windows such as Naver·Google are outside the app, so E2E cannot drive them.
Verify automatically only up to the point where the app sends the auth request, and ask the user to handle what happens inside.

Biometrics can be substituted from the simulator menu: `Features → Face ID → Matching Face`.

---

## With several devices

```bash
{PYTHON} {SCRIPTS}/launch_cli.py device list
{PYTHON} {SCRIPTS}/launch_cli.py device bind --role A --serial {serial} --note "{what this role is}"
```

They go into `env.sh` **by number**, like `ROLE1='A'; DEV1='{serial}'`.

> ⚠️ **Do not use role names in shell variable names.** Names with Korean characters, spaces or hyphens
> make `export DEV_{name}=...` fail, and `$DEV_{name}` **expands to the wrong value without an error.**

`device list` compares the build installed for each role **by APK hash** and reports `build_mismatch` when they differ.
**Do not compare by version** — a rebuild that only changes compile-time flags keeps the same version (#603).
When a mismatch is reported, stop there and align both sides.

## Build flags ⚠️

| Trap | Response |
|---|---|
| **Passed as a build argument but has no effect** | Check **where** the app reads that flag. Compile-time (`String.fromEnvironment`, etc.) and runtime config files (dotenv, etc.) are **different layers** |
| **Appended to the end of a config file but ignored** | When a key appears twice, **the first one usually wins.** Edit that line directly |
| **Test flags stay on** | Revert them **right after** use. With several devices, on every device you turned them on |

> **The build passes even when only one layer is right.** Even if the log says "applied", the feature may actually be off
> — install it and check that the feature really appears on screen.
