# Stage a state and capture it — render recipes per stack (#632)

> When to read: before calling `render run` — when you write temporary render code for the target stack (Flutter · React · RN · Spring).

Real-device capture makes **edge states** (empty list · failure · long text · permission denied) hard to reach. You would have to
touch server data, which is slow and risky. So **draw that state in code and capture it.**

Two principles:

1. **You write the render code temporarily in the target repo, following the recipe.** The script does not guess the
   state-management approach (Riverpod · Bloc · Provider · Redux …).
2. **`render run` only runs, collects, cleans up, and checks for leftovers.** The command enforces a `git status` check
   that the repo is the same as before.

## Order — this order is the contract

```bash
# ① Take the baseline **before** creating temporary files
{PYTHON} {SCRIPTS}/launch_cli.py render snapshot --root {target repo}

# ② Create the temporary render code (per-stack recipes below) — keep it in one dedicated folder
#    Flutter: let the command create it (see "Flutter — scaffold" below)
{PYTHON} {SCRIPTS}/launch_cli.py render scaffold --root {target repo}

# ③ Run · collect · clean up · check for leftovers
source "{env_file value}"      # collected images go to $SHOT_DIR
{PYTHON} {SCRIPTS}/launch_cli.py render run --root {target repo} --cwd client \
  --cmd "flutter test test/_launch_render --update-goldens" \
  --collect "client/test/_launch_render/shots/*.png" \
  --cleanup client/test/_launch_render
```

| Result `code` | Meaning | What to do |
|---|---|---|
| `ok` | Collected, no leftovers | Open it with Read |
| `render_failed` | The command failed — **nothing was collected, only cleanup ran** | **Look at `first_error` first** — the first compile-error line found in the full output (+2 lines of source and caret). If it is `null`, look at `output_tail` (the last 40 lines of output). Check the pitfalls table below first |
| `residue` | After the run, the repo has **something that was not there at the start** | If you created it, delete it or add it to `--cleanup` and run again. **If you do not recognize the change, do not touch it** — it may be another session's work. The script does not delete it either |
| `nothing_collected` | Succeeded but no images | Check that the `--collect` glob is relative to the repo root |
| `unsupported_stack` (scaffold) | Not a Flutter app — scaffold is Flutter only | Write the render code by hand from this file's recipe for that stack |
| `scaffold_exists` (scaffold) | The temporary folder is already there — **not overwritten** | `created_by_scaffold: true` means an earlier scaffold left it: run `render run --cmd true --cleanup {folder}` and scaffold again. Otherwise it is someone else's — leave it and ask |
| `flutter_app_not_found` (scaffold) | No `pubspec.yaml` with `flutter:` | Pass `--app {folder}` (relative to `--root`) |

> **`first_error` (#901)**: Added near the front of the response (after `summary`) on `render_failed`. It first looks for the Dart format
> (`test/x_test.dart:12:9: Error: ...`), then for a generic `error:` line (javac · tsc, etc.).
> Compile errors appear early in the output and are easily pushed out of the last 40 lines (`output_tail`). The first line also goes into `summary`.

> **Do not skip ①.** If you call only `run` without a baseline, it takes that moment as the baseline. Temporary files you already
> created become part of the baseline, so a file you forgot to put in `--cleanup` **is not caught as a leftover.**
> (Found while actually writing this during implementation.)

- `--cleanup` deletes **only paths inside the repo**. A path outside is refused with a warning.
- Collected images are the original PNGs. Shrink them with `shrink` before attaching them to an issue.
- **Do not call AI generation APIs for captures** — they cost money. Put fake data in through code.
- **Do not mix with golden baseline files.** Keep everything in a temporary folder (`_launch_render`) and delete it afterwards.
  Writing to the repo's `goldens/` changes the regression-test baseline.

---

## Flutter

**Default capture**: widget-test render — `matchesGoldenFile` to a temporary path + `--update-goldens`.

**Scaffold first (#948)**: `render scaffold --root {repo}` builds the harness instead of you writing it each time.

- Finds the app: `--app` > `version.yml` `project_paths.flutter` > `pubspec.yaml` search.
- Creates `{app}/test/_launch_render/` with `flutter_test_config.dart` (loads the app's `FontManifest.json` fonts **and** the SDK's
  Roboto and `MaterialIcons`, so icons are not boxes), `render_test.dart` (a golden skeleton writing to `shots/`) and `shots/`.
- **Refuses if the folder exists** (`scaffold_exists`) — it never overwrites. It takes the leftover baseline itself if you skipped
  `snapshot`, and records what it created in a manifest outside the repo; `render run` drops the manifest once the folder is cleaned up
  (`"scaffold": "cleaned"`, or `scaffold_warning` if the folder is still there).
- Its `next` is the exact `render run` command (`--cwd`, `--cmd "flutter test test/_launch_render --update-goldens"`, `--collect`, `--cleanup`).
  Edit `render_test.dart` (real screen widget, fake data, one `testWidgets` per state) and run that command.
- Korean (CJK) text still needs a CJK font **declared in the app's `pubspec.yaml`** — the loader only has what the app bundles.

The recipe below is what the skeleton contains, for when you write it by hand.

```dart
// client/test/_launch_render/states_test.dart — deleted when render run finishes
import 'package:flutter/material.dart';
import 'package:flutter/services.dart'; // MethodChannel · SystemChrome · key input — needed to stub plugin channels
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget wrap(Widget child) => MaterialApp(
        theme: /* the repo's theme */ ThemeData(),
        home: Scaffold(body: Center(child: child)),
      );

  for (final (name, items) in [('empty', <String>[]), ('many', List.generate(30, (i) => 'Item $i'))]) {
    testWidgets('list $name', (tester) async {
      await tester.pumpWidget(wrap(/* the real screen widget with fake data */ Text('$items')));
      await tester.pumpAndSettle();
      await expectLater(find.byType(MaterialApp), matchesGoldenFile('shots/list_$name.png'));
    });
  }
}
```

**Check first**: Is there a `test/flutter_test_config.dart` that loads fonts? **Without it, all Korean (CJK) text renders as □.**
If it exists, use it as is. If not, create a `flutter_test_config.dart` inside the temporary folder that loads the app fonts with
`FontLoader` (it applies only to that folder).

**Staging edge states**

| State management | How to inject fake values |
|---|---|
| Riverpod | `ProviderScope(overrides: [xProvider.overrideWith(...)])` |
| Bloc | `BlocProvider.value(value: MockBloc(...))` or a cubit that has `emit`ted the state you want |
| Provider | `ChangeNotifierProvider.value(value: fakeModel)` |
| Constructor injection | Pass fake data straight to the widget — the simplest option |

- Reproduce safe areas and device size with `MediaQuery` padding and `tester.view.physicalSize`.
  If the repo has a viewport helper (e.g. `useFigmaViewport()`), use it.
- Dark mode and text size: `MaterialApp(themeMode:)` · `MediaQuery(textScaler:)`.

**Fallback**: simulator `app shot` — when you need real screen transitions or animations.

**Pitfalls (measured while building a design request for one Flutter app)**

| Symptom | Cause | Fix |
|---|---|---|
| **Yellow double underline** under text | The overlay was drawn outside `Material` | Wrap it in `Material` (placing it inside `Scaffold` is enough) |
| `pumpAndSettle` never finishes | Infinite animation (loading spinner · repeating effect) | Use `pump(Duration)` for a single frame, or turn on "reduce motion" (`MediaQuery(disableAnimations: true)`) |
| Diff on lines you did not touch | `dart format` rewrote the whole file | Run it only on temporary files. Never run the formatter on repo files |
| Korean (CJK) text is □ | Fonts were not loaded | See "Check first" above |
| **Icons are □ (boxes)** | The `MaterialIcons` font was not loaded — loading only the Korean font above makes `Icons.*` render as boxes | In `flutter_test_config.dart`, also load the SDK's `bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf` with `FontLoader('MaterialIcons')`. Load custom icon fonts (`fonts:` entries) under the exact names written in `pubspec.yaml`. Also check that the app package has `uses-material-design: true` |
| `render_failed` + `first_error` is `Error: Undefined name 'MethodChannel'` (or `SystemChrome`, etc.) | Missing `package:flutter/services.dart` import — the most common cause of render failures (#901) | Keep the recipe's three import lines as they are. If you use a screen widget or fake model, **also add that file's `package:{app}/...` import** |
| `render_failed` + overflow | The repo's test config turns overflow into a failure | **That is a finding in itself.** The screen breaks in that state — put it in the report |

## React / Next

**Default capture**: Playwright screenshot. **If Storybook exists, prefer story URLs** — when per-state stories
already exist, you do not need to write render code.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py web open --url http://localhost:6006/iframe.html?id=list--empty
{PYTHON} {SCRIPTS}/launch_cli.py web shot --selector "#storybook-root" --out list_empty
```

**Staging edge states**: Swap API responses with `web route` without touching the server. Set width with `web viewport`.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --status 200 --body "[]"
{PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --status 500 --body '{"message":"x"}'
{PYTHON} {SCRIPTS}/launch_cli.py web route --match "**/api/items*" --delay 5000     # loading
{PYTHON} {SCRIPTS}/launch_cli.py web viewport --preset mobile
{PYTHON} {SCRIPTS}/launch_cli.py web goto --url http://localhost:3000/items
{PYTHON} {SCRIPTS}/launch_cli.py web shot --out items_empty_mobile
{PYTHON} {SCRIPTS}/launch_cli.py web route --clear
```

This path creates no files in the repo, so `render run` is not needed.

| Pitfall | Fix |
|---|---|
| You set an empty list but the list is filled | Server-side rendering (SSR) already put the data in. route changes **only browser requests** — use a story or test mock for SSR data |
| You set a rule but nothing changed | The screen was already open. Load it again with `web goto` |

**Fallback**: the real dev-server screen.

## React Native

**Default capture**: simulator/emulator `app shot`.

**Staging edge states**: Change responses with a mock server (MSW native · json-server), a dev-menu flag, or test-build environment variables.
Do **not permanently add** staging branches to app code — if you added one, revert it afterwards
(you can also do `render snapshot` → edit → capture → revert → `render run --cmd true` to check only for leftovers).

**Fallback**: If an Expo web build works, use the same Playwright path as React.

## Spring server rendering (Thymeleaf, etc.)

**Default capture**: Start the server with the test profile and use Playwright.

**Staging edge states**: Seed data · test profile. Never use the production DB.

**Fallback**: Extract only the HTML with MockMvc, open it as a static file, and capture it (when you cannot start the server).

```bash
# Assuming the test writes HTML to build/_launch_render/*.html
{PYTHON} {SCRIPTS}/launch_cli.py render snapshot --root {repo}
{PYTHON} {SCRIPTS}/launch_cli.py render run --root {repo} \
  --cmd "./gradlew test --tests '*LaunchRender*'" --collect "build/_launch_render/*.png" \
  --cleanup src/test/java/{package}/LaunchRenderTest.java
```

## Pure API server — no screen

There is no screen to capture. Instead, collect **the words the user will see**.

1. User-message catalog per error code — read the code and build a `code → message` table
2. State list — which request leads to which state
3. ASCII wireframes if needed

Check each error response for real with `http`.

```bash
{PYTHON} {SCRIPTS}/launch_cli.py http --url /api/items/999 --expect-status 404
```

## When you cannot render — ASCII wireframe

For states where the tool is missing or rendering failed, draw them in ASCII and write **"render failed"**.

Rules: **monospace** · box characters (`┌ ─ ┐ │ └ ┘ ├ ┤`) · count **CJK characters (such as Korean) as two columns** (if the width is off, the lines do not line up).

```
┌──────────────────────────────┐
│  List                    ⚙   │
├──────────────────────────────┤
│                              │
│    (empty-state picture)     │
│    No cards created yet      │
│       [ Create card ]        │
│                              │
└──────────────────────────────┘
  State: 0 items · render failed (no font) → ASCII
```

> It does not replace the real screen. It only conveys **what is where** — also note that it cannot show fonts, spacing, or color.
