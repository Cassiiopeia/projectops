# Writing release notes · approval gate messages

> When to read: the note skeleton and rewrite rules are in SKILL.md step 5. Open this only when you need good/bad examples or the approval gate messages (deploy 5.5 / fix 4.5).

Show every message below to the user in the user's language (or the configured `language` preference). The text here gives the meaning.

## Commit classification

| prefix | Category (`ko` catalog / `en` catalog) |
|--------|------|
| `feat` | 새 기능 / New features |
| `fix` | 버그 수정 / Bug fixes |
| `refactor` / `perf` / `style` | 개선 / Improvements |
| `docs` | 문서 / Documentation |
| the rest | 기타 / Other |

**Never copy commit messages as is.** Remove issue titles, URLs, type prefixes, file names and technical terms, and rewrite each item **from the point of view of a client (user) who should understand the feature or change**.

## Writing principles — write like app store update notes

Write as if an ordinary user is reading "what changed in this update?".

- **Never mention** file, class, function or variable names
- **Never use** technical prefixes such as `fix:`, `feat:`, `refactor:`, `chore:`
- **Never mention** internals such as API calls, DB queries, algorithms or library names
- **Never include** issue numbers or GitHub URLs
- Describe **only changes the user can feel directly**
- One line per item, 40 characters or fewer, concise
- **For app review repos (`APP_RELEASE == true`), apply the cleanup one level stricter.** If an item has even a hint of internal, CI/CD, test or build nature, **exclude** it from the release notes (these notes are the actual review submission)

**Good vs bad examples** (write the real notes in the repo's language):
```
❌ Fix cross-platform compatibility with the PYTHONPATH env var pattern
✅ Fixed a launch error on Windows and macOS

❌ Inline the per-skill config schema in config-rules.md §7
✅ Setting up is now simpler

❌ Upgrade Dockerfile Node.js 20 → 24 (fix npm ci lock file mismatch)
✅ Fixed a package install error during builds

❌ Delete the .projectops/ folder and clean up .gitignore
✅ The app install size is slightly smaller
```

## File location and fixed structure

**Save with the Write tool to `~/.projectops/tmp/{OWNER}__{REPO}__release_notes.md`** (the home directory, not inside the repo. It sits next to the config, so the repo stays clean, and the `{OWNER}__{REPO}` prefix keeps several repos or agents deploying at once from colliding). Windows: `C:\Users\<user>\.projectops\tmp\{OWNER}__{REPO}__release_notes.md`; macOS/Linux: `~/.projectops/tmp/{OWNER}__{REPO}__release_notes.md`. **If the tmp folder does not exist, create it before the Write.** Then pass this **absolute path** (`NOTES_FILE`) to the CLI as is.

Use a structure **100% identical** to the format the workflow parses. Use only the fixed category names below and omit categories with no items. The headings below are the `ko` catalog names (`.github/scripts/i18n/ko.json`); for a repo with `options.language: en` in `version.yml`, use the `en` names: `Release notes` / `New features` / `Bug fixes` / `Improvements` / `Documentation` / `Other`.

```
<!-- This is an auto-generated comment: release notes by coderabbit.ai -->

## Summary by CodeRabbit

## 릴리스 노트

* **새 기능**
  * (item)

* **버그 수정**
  * (item)

* **개선**
  * (item)

* **문서**
  * (item)

* **기타**
  * (item)

<!-- end of auto-generated comment: release notes by coderabbit.ai -->
```

> Per-language store translations (when `store_locales` has two or more entries) are appended as a separate block **after** this structure. Format and rules: `store-translations.md`. Do not change the base-language structure itself.

## Approval gate messages (deploy 5.5 / fix 4.5)

The branch conditions are in SKILL.md "approval gate". These are the messages to show.

### Review warning banner (only when `APP_RELEASE == true`; first, above the body, in either A or B)

```
⚠️ This deploy goes into real App Store / Play Store review.
   The release notes below become the store's "What's New" text as is.
   Check that CI/CD, internal improvements and test items are out, and only changes users feel directly are in.
```

### commit "leave it" + app review repo confirmation

```
Leave the release notes to automatic generation and create a deploy PR that leads into app review?
```

### A. Auto mode (show only, then proceed at once)

```
🤖 This repo is set to deploy without confirmation, so I am only showing the release notes and creating the PR.
   (To be asked every time again, say "ask me first".)

📋 Release notes:
{_release_notes.md body as is}

Creating the PR.
```

### B. Manual mode (loop until approved)

```
📋 Release notes body:

{_release_notes.md body as is}

Create the PR with this?
1. Yes, create it
2. Edit it (tell me how)
```

- **1** → go to PR creation. But if `CONFIG_HAS_KEY == false` and `APP_RELEASE != true`, run C once **right before** it
- **2 / an edit request** → apply the request, rewrite the notes file, and return to the start of the approval gate

### C. First-run automation offer (once only)

The user sees this screen for the first time, so say clearly **what** gets automated.

```
💡 How should the next deploys go?

By default, I show you the release notes right before each deploy and ask for confirmation.
If you want, I can skip this confirmation step and create the deploy PR right away.

1. Deploy this repo without confirmation from now on
2. Deploy all repos without confirmation from now on
3. Keep asking me to confirm the release notes every time

(You can change this any time by saying "ask me again" / "switch to automatic")
```

Config updates per answer: `config.md` §3. After the update, say:

- 1: "✅ From the next deploy, this repo proceeds without confirmation."
- 2: "✅ From the next deploy, all repos proceed without confirmation."
- 3: "✅ I will keep asking you to confirm the release notes every time."
