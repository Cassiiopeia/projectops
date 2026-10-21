# Decide what to walk — confirm the target · read the structure · path · three axes

> When to read: when the `detect` result carries `confirm`, when the project is new to you, and when you pick the path to walk and the failure and environment conditions.

This expands Phase 0 · 0.5 · 1 of `SKILL.md`.

## Phase 0 — Decide the target

`detect` decides in this order: **① user-specified → ② what you confirmed and recorded → ③ project_types in version.yml → ④ marker files**.

| Result | What to do |
|---|---|
| One | Go with it |
| Several (e.g. `app`·`server`) | **Ask.** If you pick at random, you walk the wrong thing |
| None | Ask the user to tell you with `--target app\|web\|server\|other` |

> **If what you walk is not an app, web or server, it is `other`.** CI workflows, CLI tools, libraries, templates and
> batch jobs all go here. They are not detected automatically, so you decide and pass
> `--target other`, or record it with `note target`.

### If `confirm` is attached, you verify it ⚠️

If `target_source` is `version.yml`, the result is **a declaration, not a confirmed fact**. "This repo
is Spring" does not mean "there is no screen".

**A server that renders screens itself is perfectly normal** — Thymeleaf, JSP, Django templates,
Rails and Next server rendering all do it. But if you only read the declaration, you stop at `server`. Then
you never think of opening a browser, and you **miss every defect that only shows on screen.**

The py script does not try to guess this. Every framework puts templates in a different place, so a regex
cannot do it. **Judging from the code is your job.**

| What to check | Where |
|---|---|
| Is there a template folder | `templates/` · `views/` · `src/main/resources/templates` · `app/views` |
| Do routes return HTML | Does the controller return a view name, or only JSON |
| Does it serve static files | `static/` · `public/` · `assets/` |
| Is the client in the same repo | sibling folders `client/` · `web/` · `app/` |

Once you decide, **record it.** From the next run on, you will not be asked.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note target --root {ROOT} --targets server,web --why "{reason for the decision}"
```

`--why` is required — next time you must be able to check whether this record is still right. If the declaration is already
right, you do not need to do anything.

> **If a prerequisite is missing, ask and then install it.** The web target needs a browser (about 100MB) — do not just
> print instructions and stop. The detailed steps are in `target-web.md`; the common principle is
> "When something is missing" in `../../references/common-rules.md`.

### Pin the device — `app` target

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py device list --root {PROJECT_ROOT}
```

If there is only one, `$DEV` is set to it and there is nothing more to do. **If there are several, bind roles** — `devices.md`.

> **If you get `build_mismatch`, stop there.** It means each role has a different build installed.
> If you walk anyway, you create fake defects that "reproduce on one side only". Builds can differ even
> with the same version, so it is measured by APK hash — a rebuild that only changed compile-time flags has the same version.

If you booted a device later, run `device list` once more to refresh the environment.

> `adb` and `emulator` are often not on PATH even after the SDK is installed. Use `adb_path` from the `detect` result
> as is, so you avoid the misdiagnosis "no device". (AVD = Android Virtual Device, the emulator device definition)

> **detect does not guess the server address or DB.** Spring, Node, Django and Rails keep settings in
> different places, so a regex cannot find them. Read the code, find them yourself, then record them with `access`
> (`target-server.md`). Once recorded, `detect` reports them from the next run on.

## What works and what does not (measured on the Android emulator) — `app` target

**Do not guess; read this table.** If you plan without knowing what does not work, you stall midway.

| Action | Works | Command |
| --- | --- | --- |
| Tap · swipe | ✅ | `launch_cli.py app tap --text …` · `app swipe --dir up` (by element) |
| English/digit input | ✅ | `adb -s "$DEV" shell input text` · saved login: `app type --cred` |
| **Korean (non-ASCII) input** | ❌ | `input text` accepts ASCII only. Clipboard and keyevent do not work either |
| Dark mode toggle | ✅ | `cmd uimode night yes` |
| Cut the network | ✅ | `svc wifi disable && svc data disable` |
| Deny · grant permission | ✅ | `pm revoke` / `pm grant` |
| Font size (accessibility) | ✅ | `settings put system font_scale 1.3` |
| Reduce motion | ✅ | `settings put global transition_animation_scale 0` |
| Rotate screen | ✅ | `settings put system user_rotation 1` |
| Enter via deep link | ✅ | `am start -a android.intent.action.VIEW -d "{scheme}://..."` |
| Fingerprint auth | ✅ | `adb -s "$DEV" emu finger touch 1` |
| Real camera · mic input | ❌ | Virtual input only |
| Send a real push | ❌ | Must be sent from the server separately |
| Real in-app purchase approval | ❌ | Needs a test account and store setup |
| **iOS tap by host mouse coordinates** | ❌ **Do not do this** | `cliclick` and AppleScript move the real cursor and are banned — use `app tap` (Maestro) or the project's E2E. See `../../pro-launch/references/app.md` |

### If you must enter Korean (non-ASCII) text

1. **Substitute English and note it in the report** — enough when the value itself is not under test
2. If Korean handling (jamo splitting, length limits) is under test, **install an IME such as ADBKeyboard**
3. If that is also hard, **ask the user to type it** (in the Phase 4 format — `social-login.md`)

Screens with `FLAG_SECURE` (some finance and auth apps) capture as black screenshots. In that case,
only confirm which screen it is with `mCurrentFocus` from `dumpsys window` and hand over to the user.

## Phase 0.5 — Read how this project is built first

For a project you have not seen before, **read the structure once.** This saves you from hunting for
screens and endpoints every time.

**You do the reading.** Look directly with Grep and Read — a script used to guess with common conventions
(`lib/features/` · `*_screen.dart`), but every project is structured differently, and when it guessed wrong it
**answered "none" and misled you.** Reading it yourself is always more accurate.

| Target | What to look at |
| --- | --- |
| app | Where screen files live and how they are named · how routes are defined · the login method |
| web | Page and route definitions · state management · where the API is called |
| server | Endpoint list · auth method · **whether resources have owners** (the premise for permission checks) |

**Record what you learn.** The next run starts from here.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py note screen --root {ROOT} --name "{screen}" --anchor "{clue that identifies it}"
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py access set --root {ROOT} --key {db|logs|base_url} --json '{...}'
```

What to record in what order, and how credentials are filtered out, is in `learning.md`.

## Phase 1 — Fix the path to walk

If a scenario already exists, follow it (`scenario list`). If not, and the user named a path,
go with it. If neither, ask **once**.

```
How far should I walk?
1) From first launch to the home screen (login, terms, onboarding — the whole stretch)
2) A specific screen only — tell me which one
3) Reproduce a bug a user reported — tell me the symptom
```

Once the path is set, write the **step list** first. For each step write "what to tap → what should appear
→ what should remain on the device/server". This list becomes the pass criteria (why: if you walk
without criteria, you stop at "the screen appeared, so it works", while in fact nothing may have reached the server).

### Freeze it as a scenario

If you will likely walk the same path again, save it to a file. The `server` target **must** have one,
because `api` requires a scenario.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py scenario init --root {ROOT} --name {name} --target {app|web|server}   # create the skeleton
#   fill the {brace} slots in the skeleton — the file location is the output's file field
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/e2e_cli.py scenario show --root {ROOT} --name {name}                              # validate before walking
```

**Do not skip `show`.** It blocks steps with no expected result, unfilled braces and unknown targets
here. If these get through, you tap the wrong place or end with "the screen appeared, so pass".

> Scenarios and records are stored in the **home** directory (`knowledge_dir` from `detect`), not in the project.
> They survive when you create a new worktree.

## Do not walk only the happy path — three axes ⚠️

Developers have already walked the normal path dozens of times. **Bugs are usually outside it.**
Pick what to walk from the three axes below — you do not need all of them, only what makes sense for this app.

**Axis 1 — State combinations.** An app starts differently depending on its saved state.

| Session | Onboarding | Expected | How to check |
| --- | --- | --- | --- |
| None | — | Starts at login | Launch after `pm clear` |
| Present | Not finished | Resumes | Force-quit mid-onboarding, then relaunch |
| Present | Finished | Straight to home | Just relaunch |
| Expired | Finished | Refresh or re-login | Revoke the token on the server, then launch |

When choosing what to walk, **pull candidates from the code first.** `catch` blocks and fallbacks usually
ship without ever having run once.

```bash
# e.g. where exception handling and fallbacks are (find them with Grep yourself)
catch · rescue · except · \.catch\( · onError · fallback · ?? · orElse
```

Candidates: exception paths, network failures, empty lists, denied permissions, fallbacks, error codes, token expiry, retries.
**You do not need to walk them all** — start where many hits cluster and where users often land.
Finding and choosing are **your judgment.** If a script chose for you, anything outside its list would never be walked.

**Axis 2 — Failure injection.** Use the actions in the table above to **create** failures and walk them.

| Situation | How to create it | What to check |
| --- | --- | --- |
| Network down | `svc wifi disable && svc data disable` | Is there a retry path, not endless loading or a blank screen |
| Permission denied | `pm revoke {package} {permission}` | The app does not crash and offers a way around |
| Server error | Take the server down briefly or inject a bad token. **For web, `web route --status 500`** — do not touch the server | **Is the error code visible on screen** (needed to trace user reports) |
| Zero items | Use an account with emptied data. **For web, `web route --status 200 --body "[]"`** | Is there an empty-state screen distinct from loading |
| Slow response | **For web, `web route --delay 5000`** | Is there a loading indicator · can it not be tapped twice |

**Axis 3 — Environment conditions.** Change accessibility and display settings and see whether the layout holds. **On both platforms**, change them with the pro-launch commands below:
the value before the change is recorded automatically, and `--restore` or `device release` restores it, so no "changed and forgotten" state is left behind.

| Condition | Command (Android · iOS) | What to check |
| --- | --- | --- |
| Large text | `launch_cli.py device text-size largest --device $DEV` (restore with `--restore`) | Text is not cut off and does not push buttons out |
| Dark mode | `launch_cli.py device appearance dark --device $DEV` (`--restore`) | Contrast does not collapse, no invisible text |
| Language | `launch_cli.py device locale --lang ja --device $DEV` (`--restore`) | Missing translations, long text cut off |
| Reduce motion (Android) | `settings put global transition_animation_scale 0` | Screens that relied on animation do not freeze |
| Landscape (Android) | `settings put system user_rotation 1` | No overflow |
| Offline (Android) | `svc wifi disable && svc data disable` | Is there a retry path |
| Offline (iOS) | The simulator uses the host network — do not turn off host Wi-Fi. For an app that `web route` cannot cover, use a build/config that points the API at a blocked address. If you cannot create it, do not skip it — **record it in the report as `blocked` (condition that cannot be created)** | No endless loading |

> **Changed settings affect results.** After each condition, run `--restore`, and before the next item, confirm with `app shot` that the original value is back.
> **Note in captured evidence which condition it was taken under (`text-size largest`, etc.)** — without the condition, you get false positives.

> **These three axes choose "what to walk".** "What to look at while walking" is separate:
> axes 4·5·6·7 in `looks-wrong.md`. If you only check that features run,
> mismatched fonts or a blocked back button all end up as passes.
