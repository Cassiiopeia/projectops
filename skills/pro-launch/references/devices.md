# Devices — borrow · boot · own · clean up · capacity

> When to read: before the first app task on a computer (borrow and return), when booting, creating, cloning, erasing or cleaning up
> emulators and simulators, when `acquire` answers `wait` · `ask` · `no_match`, when measuring device capacity, or when binding roles to several devices.
> Driving the app on the device (launch · tap · capture) is in [`app.md`](app.md).

## Contents

- [Commands and rules](#commands-and-rules)
- [With several devices](#with-several-devices)
- [Failure code → next action](#failure-code--next-action)

## Commands and rules

Issues: #923 · #924 · #925 · #929 · #953.

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

## Failure code → next action

| code | Next action |
|---|---|
| `device_shutdown` | The chosen simulator/AVD is off. Boot it with `device boot --device <id>` from `next`, then retry (to borrow one, use `device acquire`) |
| `device_busy` · `needs_user` · `no_matching_device` | `device acquire`'s `wait` · `ask` · `no_match` — see the per-verdict actions in the SKILL.md common rules |
| `device_owned_by_other` | Another session borrowed this device. Mutating actions (tap · type · install, etc.) are refused; reads (shot · tree · wait) only get a warning field. Get another device with `device acquire`, or, if it must be that device, ask the user and pass `--yes` |
| `device_unresponsive` | The device does not respond (`resources` includes host memory). Ask the user, then run `device reboot --cold` |
| `device_budget_exceeded` · `host_memory_pressure` | Booting another device would exceed this computer's device memory budget / host memory is at a risky level (`reasons` · `non_device_consumers`). Return or shut down unused devices, or show this to the user and pass `--user-approved` after they answer. If the budget was never measured, run `device benchmark` |
| `devices_in_use` · `benchmark_no_room` | Not started because measuring could stall other sessions / no room to boot even one test device (config unchanged) |
| `ledger_busy` | Could not get the device ledger lock within 10 s. Call again shortly |
| `device_protected` · `device_in_use_unrecorded` | The device you want to erase or reset holds prepared state / a person may be using it. Show `marks` to the user and ask; if they agree, pass `--yes` |
| `emulator_no_acceleration` | The emulator stopped because it could not get hardware acceleration (host memory or swap is short). Waiting will not help, and it is already shut down. Ask the user to free memory |
| `source_booted` | A running device cannot be cloned. Retry after the source is shut down |
| `resources_low` · `create_failed` | Not enough room to create a new device (memory · disk) / creation failed. Use an existing device with `device acquire` first |
| `build_mismatch` | Devices have different builds installed. Stop and make them match |
