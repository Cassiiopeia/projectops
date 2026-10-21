# Walk an app (target: app)

> When to read: when Phase 0 sets the target to `app`.

**How to boot, install, operate and capture devices has moved to pro-launch** →
`../../pro-launch/references/app.md` (Android emulator · iOS simulator · real devices · recording · limits of iOS coordinate input).

Only **what you need when walking as QA** stays here.

```bash
source "{env_file value}"
{PYTHON} {LAUNCH}/launch_cli.py app launch --device "$DEV" --pkg "$PKG"
{PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV" --out step_N
{PYTHON} {LAUNCH}/launch_cli.py app tap --device "$DEV" --text "{on-screen text}" --shot step_N_after   # tap by element (not coordinates)
{PYTHON} {LAUNCH}/launch_cli.py app swipe --device "$DEV" --dir up
```

> **Google Play images do not allow `adb root`.** You cannot open the app's internal files (`/data/data/...`)
> directly, so check state through **app logs** (`stepping.md` Phase 2).

## Pitfalls that only happen in apps

### Screens

| Pitfall | What to do |
|---|---|
| **Text does not grow after switching to large text** | Before concluding the whole app ignores it, check **whether that screen uses scaled units** (in Flutter, things like `.sp` from `flutter_screenutil`). It is common for only some screens to use fixed sizes — measure again on an ordinary screen |
| **Some screen cannot go back** | Check whether the router opened the screen by **replacing** or by **pushing** (`go` vs `push` in `go_router`). If it replaced, there is nothing to go back to. Fixing only the arrow **still leaves the device back button blocked** — walk the two separately |

### Build flags ⚠️

This is where people get lost most when a dev switch does not take effect. The table is in the "Build flags"
section of `../../pro-launch/references/app.md`. There is one thing to add when walking as QA.

> **If you walked with a build that has test flags on, note it in the report.** Those results are not results of the release build.
> Reverting is part of the same unit — with several devices, revert every device you turned it on for (`devices.md`).

## Cross-checking server data

**Do not hard-code connection details.** Read the code to learn how to connect, record it in pro-launch `access`,
and query through that record (`../../pro-launch/references/server.md`).

```bash
{PYTHON} {LAUNCH}/launch_cli.py access set --root {ROOT} --key db --json '{"how":"direct","engine":"postgres","host":"...","db":"...","user":"...","password_env":"DB_PASSWORD"}'
DB_PASSWORD=... {PYTHON} {LAUNCH}/launch_cli.py db --profile db --root {ROOT} --sql "select ..."
```

> Config files are usually gitignored. **Do not print or commit their values.**
> In the report, write only the host and DB name.
