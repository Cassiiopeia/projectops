# When you use more than one device (target: app)

> When to read: when there are two or more participants and you need two or more devices (connect, share, invite), or when you get `build_mismatch`.

Connect, share and invite flows have **two participants**, so one device cannot walk them. They are confirmed only when
what one side creates is received by the other side.

If you use only one device, you do not need this document. `$DEV` already points to that device.

Borrow a device per role with `device acquire` — when the same session calls it twice, it gives different devices. When done, `device release` both.

## 1. Bind roles to devices

**You name the roles.** Use the same value as the key you will use in the scenario.

```bash
{PYTHON} {LAUNCH}/launch_cli.py device list --root {PROJECT_ROOT}
{PYTHON} {LAUNCH}/launch_cli.py device bind --root {PROJECT_ROOT} \
  --role A --serial {serial} --note "{what this role is}"
```

`env.sh` gets this:

```sh
export DEV_COUNT=2
export ROLE1='A'; export DEV1='{serial1}'   # {description}
export ROLE2='B'; export DEV2='{serial2}'   # {description}
export DEV="$DEV1"
```

> ⚠️ **Do not use role names in shell variable names.** Variable names allow only `[A-Za-z_][A-Za-z0-9_]*`, so
> a name with Korean letters, spaces or hyphens makes `export DEV_{name}=...` fail with `not a valid identifier`,
> and **the reader `$DEV_{name}` does not fail but expands to a wrong value.** So the slot is fixed
> by number and the name is stored as a value. Look at `ROLE{n}` to decide which number.

## 2. Name the device in every command

```bash
source "{env_file value}"

{PYTHON} {LAUNCH}/launch_cli.py app tap --device "$DEV1" --text "{button}"   # A acts
{PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV2" --out {name}   # look at B's screen
```

**If you leave out `-s` with several devices, adb refuses or goes to the wrong device.** That is why every
example in these docs has `-s`. Do not remove it.

If you booted a device later, run `device list` once more — it refreshes the environment and fills `$DEV`.

## 3. Check that both sides have the same build ⚠️

`device list` compares the build installed for each role and tells you if they differ.

```json
{"build_mismatch": [{"roles": ["A", "B"], "field": "apk",
  "detail": "버전은 같은데 APK 가 다릅니다 — 한쪽만 다시 설치됐을 수 있습니다"}]}
```

(`detail` is printed in Korean by the script: "the version is the same but the APK differs — only one side may have been reinstalled".)

> **Do not measure by version.** A rebuild that only changed compile-time flags has **identical**
> `versionName` and `versionCode`. If only one side was reinstalled and the dev tools are on for only that side,
> you can never tell from the version alone. That is why it is measured by APK hash.

If a mismatch is reported, **stop there and align both sides.** If you walk anyway, you create fake defects
that "reproduce on one side only".

## 4. Write who does what in the scenario

```json
{ "target": "app",
  "roles": { "A": {"note": "{creating side}"}, "B": {"note": "{receiving side}"} },
  "steps": [
    {"device": "A", "screen": "{screen}", "do": "tap '{button}'",
     "expect_screen": "{result}", "capture": "handoff"},
    {"device": "B", "screen": "{screen}", "do": "input ${handoff}",
     "expect_screen": "{result}", "expect_server": "{check query}"}
  ]}
```

| What | What it does |
|---|---|
| `roles` | Which roles exist. The keys are the names used in `device` and `--role` |
| `device` | **Who** does this step. If it is not in `roles`, `scenario show` blocks it |
| `capture` | **Names the value obtained** in this step |
| `${name}` | Uses a value an earlier step obtained. Blocked if no earlier `capture` exists |

> **It is `${name}`, not `{name}`.** The scenario skeleton already uses `{braces}` to mean "fill this in",
> so using the same symbol would make the two indistinguishable.

If you leave `roles` empty, it walks with one device as before. Existing scenarios stay valid.

## 5. Remember tap targets separately per device

```bash
{PYTHON} {SCRIPTS}/e2e_cli.py note screen --root {PROJECT_ROOT} \
  --name "{screen}" --anchor "{clue that identifies it}" \
  --target "{label}=text:{text}" "{label2}=at:{0~1 horizontal},{0~1 vertical}" \
  --screen-size {width}x{height} --role A --build {apk value}

# result of tapping that target (ok if app tap --shot gives screen_changed true; fail if not_found or false)
{PYTHON} {SCRIPTS}/e2e_cli.py note screen --root {PROJECT_ROOT} \
  --name "{screen}" --target "{label}" --result ok --role A --screen-size {width}x{height}
```

**Even at the same resolution, a different build means a different screen.** Different builds per role are common, so
if you remember only one set of targets you tap the wrong spot. With `--role`, they are stored separately.
Pixels (`label=540,1200`) are rejected — `app tap` does not accept them. If the element is visible use `text:` · `id:` · `desc:`, otherwise an `at:` ratio.

Old records (one set of pixel coordinates) are converted to ratios when read and get `verify` (the original is in `legacy_taps`).
Tap once and record `--result ok`, and `verify` is cleared.

## 6. A test build flag is one unit together with reverting it ⚠️

If you installed a build with a dev switch on, **revert it as soon as walking ends.** If you put it off, it gets
committed in that state, or the next build ships misaligned.

With several devices, revert **every device you turned it on for.** If you revert only one, the next walk
again produces "reproduces on one side only".

Where the flag lives splits into two layers.

| Layer | Where | How to check |
|---|---|---|
| Runtime | Config files (dotenv, etc.) | Read the file directly |
| Compile time | Baked in as build arguments | **Not visible in files.** You only know after installing and tapping |

**The build passes even when only one layer is right.** Even if the log says "applied", it may actually be off.
After installing, tap to confirm that the feature is really on screen.
