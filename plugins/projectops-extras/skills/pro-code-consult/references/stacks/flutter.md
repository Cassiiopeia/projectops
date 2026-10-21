# Flutter stack rules

> When to read: when the target has a `pubspec.yaml` (flutter). Shared by audit, refactor and init.

## Layer map

| Layer | Folder | What goes in |
|---|---|---|
| Presentation | `features/<feature>/presentation/{pages,widgets,providers}` | Screens, feature-only widgets, Riverpod state |
| Application | `features/<feature>/application` or `domain/usecases` | Use cases, business rules outside screens |
| Domain | `features/<feature>/domain/models` | Pure models (no Flutter or dio imports) |
| Infrastructure | `features/<feature>/data/{repositories,sources}`, `core/network` | dio, repositories, local DB |
| Common | `core/` (config, errors, formatting), `design/` or `presentation/design/` (tokens, components) | |

A **layer-first structure** (`lib/presentation/{pages,widgets,providers}`, `lib/domain`, `lib/data`, `lib/core`) is also common. The layers are the same and only the folder order differs — set a rule's `paths` to the real folders, such as `lib/presentation/pages/,lib/presentation/widgets/` (with `lib/features/` it freezes 0 hits).
Many teams allow a provider or notifier to import `data/` (`from_role: "state"` in `deps`) as a Riverpod convention. If the repo's rules do not mention it, list it as "team decision needed", not as a violation.

Dependency direction: presentation → application → domain ← infrastructure. **A screen importing `data/` or `core/network` directly is a violation.**
`core/` or `shared/` importing `features/` is also a violation (the common code gets tied to a feature).

## Common AI smells

- Direct presentation → data imports inside one feature (`ref.watch(xxxRepositoryProvider)` right in a screen)
- Direct use of `CircularProgressIndicator(`, `CupertinoActivityIndicator(`, `showDialog(`, `SnackBar(` while a common component exists
- Direct `Color(0x`, `Colors.xxx`, numeric `EdgeInsets`, `fontSize:` (bypassing tokens)
- Direct paths in `Image.asset('...')` (bypassing asset constants and components)
- `bool loading`, `bool selected` (no prefix), file name ≠ class name
- Screen files of 500+ lines (state, widgets and business rules in one file)

## First rule candidates (`docs/architecture/rules/`)

```
# no-direct-progress-indicator.rule
description=No direct loading indicators in screen code (use the common loading component)
paths=lib/features/
extensions=.dart
pattern=\b(?:CircularProgressIndicator|CupertinoActivityIndicator)\(

# no-color-literal-in-features.rule
description=No color literals in screen code (use tokens)
paths=lib/features/
extensions=.dart
pattern=\bColor\(0x|\bColors\.(?!transparent\b)[a-z]

# presentation-must-not-import-data.rule
description=Presentation layer must not import the data layer directly (go through providers or use cases)
paths=lib/features/
extensions=.dart
pattern=^import .*/data/
```

Narrow the last rule's `paths` to the `presentation` folders (`lib/features/<feature>/presentation/` for each feature, comma-separated).
In a monorepo, prefix `paths` with the app folder (`app/lib/features/`).

## Rule tests

`install-tests PATH --stack flutter --module <app folder>` → `test/architecture/architecture_rules_test.dart`.
Run with `flutter test test/architecture`. For a pure Dart package, change the import to `package:test/test.dart`.

## Choosing model files

During init, pick one per layer: 1 screen with clean state management, 1 widget that uses only tokens, 1 repository.
Write the path and a one-line reason in the "Model files" section at the bottom of `docs/architecture/stacks/flutter.md`.
