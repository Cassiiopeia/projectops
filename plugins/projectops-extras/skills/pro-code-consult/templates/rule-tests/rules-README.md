# Architecture rules

One rule = two files. The per-stack rule tests (`architecture_rules_test.dart` · `ArchitectureRulesTest.java` ·
`test_architecture_rules.py` · `architecture.rules.test.mjs`) read this folder and judge it in CI.

## `<id>.rule`

```
description=No direct platform loading indicators in screen code (use the common component)
paths=app/lib/features/
extensions=.dart
exclude=app/lib/features/_generated/
pattern=CupertinoActivityIndicator\(
```

- `paths`, `exclude`: path prefixes relative to the repo root, comma-separated. Not globs
- `pattern`: a regex (multiline mode). Everything after the first `=` is the value
- Empty `paths` means the whole repo

## `<id>.allow` (frozen list)

- The list of files that violated the rule when it was created. One path per line, `#` for comments
- **Lines can only be removed, never added.** Fix the code for new violations
- If a fixed file is still on the list, the test fails — remove that line

Verdict: violations − list = new violations (fail); list − violations = fixed items (fail, asking you to remove them from the list).
