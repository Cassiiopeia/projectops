# Architecture rules

One rule = two files. The per-stack rule tests (`architecture_rules_test.dart` · `ArchitectureRulesTest.java` ·
`test_architecture_rules.py` · `architecture.rules.test.mjs`) read this folder and decide pass/fail in CI.

## `<id>.rule`

```
description=No direct platform loading indicator in screen code (use the shared component)
paths=app/lib/features/
extensions=.dart
exclude=app/lib/features/_generated/
pattern=CupertinoActivityIndicator\(
```

- `paths`, `exclude`: path prefixes from the repo root, comma-separated. Not globs
- `pattern`: regular expression (multiline mode). Everything after the first `=` is the value
- Empty `paths` means the whole repo

## `<id>.allow` (frozen list)

- The files that violated the rule when it was created. One path per line, `#` for comments
- **Lines can only be removed, never added.** Fix the code for new violations
- If a fixed file stays in the list, the test fails — remove that line

Verdict: violations − list = new violations (fail), list − violations = fixed entries (fail, asking you to remove them from the list).
