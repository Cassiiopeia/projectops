# Flutter wizard rules

> **When to read:** when you touch the wizards in `.github/util/flutter/` (testflight · playstore · firebase · oauth) or `_shared/`
> Canonical text split out of `CLAUDE.md`. `CLAUDE.md` keeps only a summary and a link to this document.

### ⚠️ The four Flutter wizards share common assets (#521 — agent must read)

The `testflight` / `playstore` / `firebase` / `oauth` (#156) wizards **share the canonical files in `.github/util/flutter/_shared/`.**
Each used to carry its own copy, which drifted (377 duplicated CSS lines, the same class name with opposite meanings, improvements piling up only on iOS), so they were merged.

| File | Role |
|------|------|
| `_shared/wizard.css` | Shared component styles (tooltips, modals, toasts, code blocks, custom secrets, etc.) |
| `_shared/wizard-common.js` | Shared utilities (escaping, clipboard, file conversion, OS detection, state saving, change-history modal) |
| `_shared/wizard-i18n.js` | Language switching engine (English by default, Korean on switch, #769). The common wizards load it too. Korean lives in the `<name>-wizard-i18n.js` dictionaries |
| `_shared/check-consistency.py` | Consistency check across the four — **CI (`PROJECT-TEMPLATE-CI`) runs it** (`check_i18n.py` also checks for missing dictionary keys and leftover Korean) |

**If you touched a wizard, this must pass:**

```bash
python3 .github/util/flutter/_shared/check-consistency.py
```

- **Do not redefine shared utilities in a wizard's JS** (it disables the canonical one — the checker catches it).
- **Fixed load order**: `wizard.css` → `wizard-common.js` → `<name>-wizard.js`. If the shared file loads later, it overwrites the wizard's implementation.
- **`.step-indicator` is "a single step item"** (not the whole container). This is where firebase used it the other way and collided.
- **The oauth wizard has dynamic steps** — only the steps of the chosen providers (Kakao, Google) get `data-step` numbers, and it uses the shared `showStep` / `prevStep` without overriding them. Its `.py` uses argparse because it has no positional-argument history, and only the `write gate` part of the shared block is kept character-for-character identical with testflight and playstore.
- **The canonical Python CLI form is named flags** (`--project-path`, etc.), and the old positional calls are still accepted (the commands the wizard HTML handed out use that form).
- **`--dry-run` must not be declaration-only.** Every write, copy, move, delete, directory creation and `keytool` call must go through the gate function, and because of the "write then read back to verify" steps it must follow the same path as a real run through an in-memory overlay.
- After editing `version.json`, run that wizard's `./version-sync.sh` so the change history on screen picks it up.
- Folders starting with `_` are shared assets, not modules (excluded from the module count in `src/core/copy/util.js`).

Details: `.github/util/flutter/_shared/README.md`
