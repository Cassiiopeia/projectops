# Flutter wizard shared assets (`_shared/`)

The **single source** shared by the `testflight-wizard` · `playstore-wizard` · `firebase-wizard` · `oauth-wizard` (#156) wizards.

---

## Why share

Each of the three wizards used to carry its own copy. The result:

- **377 lines of component CSS were duplicated character for character** in two wizards,
- firebase lacked 20 of those components entirely, so it had no tooltips, modals or validation marks,
- the `.step-indicator` class meant **opposite things** in different wizards,
- improvements piled up in the iOS wizard only and never reached the other two.

All of that came from "each copy aging on its own". So we switched to sharing.

### What if someone takes just one folder?

A wizard folder **only ever worked as a whole folder** (`<script src="xxx-wizard.js">` is an external file).
`_shared/` sits in the same `flutter/` tree, so the copy engine moves it along with the rest.

If you take a single folder on its own, the shared CSS is missing, but Tailwind CDN handles the layout,
so **the page still reads fine and only the finish is rougher.** It does not break silently.

---

## Files

| File | Role |
|------|------|
| `wizard.css` | Component styles shared by all three (tooltips · code blocks · modals · toasts · uploads · custom secrets, and so on) |
| `wizard-i18n.js` | Language switching engine (English by default, switch to Korean, choice remembered) + shared phrase dictionary. The common wizards load this file too (#769) |
| `wizard-common.js` | Utilities shared by all three (escaping · clipboard · file conversion · OS detection · state saving · change-history modal) + the default flow that testflight and playstore had identically (`showStep` · `prevStep` · `saveState` · `clearState` · custom secrets) |
| `check-consistency.py` | Consistency checker that catches the wizards drifting apart again |
| `check_i18n.py` | Checks for missing dictionary keys (en · ko), unused keys and Korean left in the HTML (run by check-consistency.py) |

---

## Rules

### 1. Keep the load order

```html
<link rel="stylesheet" href="../_shared/wizard.css">
...
<script src="../_shared/wizard-i18n.js"></script>     <!-- language engine: before the shared utilities -->
<script src="../_shared/wizard-common.js"></script>
<script src="testflight-wizard-i18n.js"></script>     <!-- wizard phrase dictionary -->
<script src="testflight-wizard.js"></script>          <!-- after the shared files -->
<script src="testflight-wizard-export.js"></script>   <!-- per-step split file: after the main file -->
```

A wizard's JS can be split into several `<name>-wizard*.js` files. Split files hold **function declarations only**
(state and initialization code stay in the main file). The checker reads every `<name>-wizard*.js` in the folder and confirms
the HTML loads each one after the shared JS.

The shared files must load first so a wizard's JS can deliberately override them when needed.
If the order flips, the shared code overwrites the wizard's implementation and behavior changes silently.

### 2. Do not redefine shared utilities in a wizard's JS

Defining the same name again disables the single source.
`check-consistency.py` catches duplicate definitions.
If the flow differs and you must override, register it in `INTENTIONAL_OVERRIDES` with the reason
(currently firebase: `showStep` · `prevStep` · `addCustomSecret` · `updateCustomSecretKey` · `renderCustomSecrets`).
The shared flow functions call the wizard JS globals `state` · `STORAGE_KEY` · `updateProgress` · `initializeStep` · `saveCurrentStepData`.

### 3. What goes in the shared files and what stays in each wizard

| Shared (`_shared/`) | Each wizard |
|---|---|
| Pure utilities unrelated to the wizard flow | Step navigation that differs (`goToStep`/`nextStep`) · state restore (`loadState`) |
| Flow functions that were character-for-character identical in testflight and playstore | Step contents such as `initializeStep` · `saveCurrentStepData` |
| Component styles all three use the same way | Each wizard's own colors and brand styles |
| Shared UI behavior such as the change-history modal and security warnings | Output generation (`generateXxx`) · per-step validation |

The step count and flow differ, so **flow code stays in each wizard.** Do not force it together.

### 4. `.step-indicator` is "one step item"

It is not the whole container. firebase once used it to mean the container, and that collided.

```html
<div class="flex justify-between ...">            <!-- container: Tailwind -->
  <div class="step-indicator ..." data-step="1">  <!-- item -->
    <div class="step-circle ...">1</div>
    <span>Start</span>
  </div>
</div>
```

### 5. Screen text is English by default; Korean lives in the dictionary (#769)

- **Static markup**: write the HTML body in English and add `data-i18n="key"`. Korean goes in `ko` of `<name>-wizard-i18n.js`.
  For placeholder and title use `data-i18n-placeholder` · `data-i18n-title`.
- **JS text** (toasts, dynamic rendering): `translate('key', {values})` — put both `en` and `ko` in the dictionary.
- **Outputs people copy** (commands · yaml · Fastfile · secret names · JSON keys) are not translated. They are byte-identical in both languages.
- Put `data-i18n` only on elements that hold text and inline tags. If it wraps inputs, buttons or elements the JS rewrites, they are wiped on a language switch.
- Write keys as literal strings (no assembling) — the checker catches unused keys.
- The dictionary is JSON-shaped (`check_i18n.py` parses it). No comments inside the block and no trailing commas.
- Language choice: the `?lang=` URL parameter > the saved choice > Korean if the browser language is `ko*` > English.
  Switching fires a `wizardlanguagechange` event, and each wizard redraws its dynamic areas.

### 6. Named flags are the canonical Python CLI

```bash
python3 testflight-wizard.py setup --project-path . --bundle-id com.x.y ... --dry-run
```

Old positional-argument calls are still accepted — the commands the wizard HTML already handed out use that form.
Every wizard must support the common options `--dry-run` / `--no-backup` / `--non-interactive`.

### 7. Keep the `.py` shared blocks character for character identical

The `# >>> 공통 블록: 쓰기 게이트` ("shared block: write gate") and `# >>> 공통 블록: 인자 계약` ("shared block: argument contract")
sections of the testflight and playstore `.py` files must be the same in both files, and the checker compares them. These marker
lines are data the checker matches, so they stay in Korean. The oauth `.py` keeps the same `쓰기 게이트` (write gate) block, character for character
(it has no history of positional calls, so it uses argparse and has no `인자 계약` (argument contract) block). Why it is not a shared module: each `.py`
runs and ships as a single file (the firebase ZIP contains only the `.py`). Encoding and newline handling stay outside the block,
in `_READ_KWARGS` · `_WRITE_KWARGS`, per wizard. firebase has no history of positional calls, so it takes the same flags
through argparse and passes dry-run as a function argument.

`--dry-run` **must not be declared and then ignored.** Every primitive that changes files
(write · copy · move · delete · directory creation · keytool) must go through the gate function,
and for the "write, then read back to verify" steps it must take the same path as a real run through an in-memory overlay.

---

## Checks

```bash
# wizard consistency (CSS · JS · links · version sync · CLI contract · .py shared blocks · first-user notes)
python3 .github/util/flutter/_shared/check-consistency.py

```

If you changed a wizard, **get it passing before you commit**, and run the changed `.py` once with `--dry-run`.
If you edited `version.json`, also run that wizard's `./version-sync.sh` so the change shows on screen.
