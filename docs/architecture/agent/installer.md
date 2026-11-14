# Installer (npx CLI) rules

> **When to read:** when you touch the CLI, wizard, options or run logs in `src/`, breaking changes, doc language, or the Korean line budget
> Canonical text split out of `CLAUDE.md`. `CLAUDE.md` keeps only a summary and a link to this document.

### Options have one canonical source (agent must read)

The names, values and defaults of CLI flags and `version.yml` options live in one place, **`src/core/options-schema.js`**,
and `npx projectops --mode options --json` prints it as is. AI agents check options with this command instead of searching the docs.

- When you add a new flag (`src/cli/args.js`) or `version.yml` option (`parseTemplateOptions`), **add it to the canonical source too.**
  `test/options-schema.test.js` compares the code with the canonical source and fails if they differ.
- Do not copy the option table into docs again — copies go stale. Docs point to the canonical source.
- After editing `src/core/options-schema.js`, regenerate the generated tables (`<!-- generated: options -->`) in `docs/en/cli.md` and `docs/CLI.md` with `node scripts/build_options_reference.mjs`. `--check` writes nothing and only checks that they are current.
- **Option values (flag > saved value > default) are decided in one place, `src/core/resolve-options.js` (#851).** `index.js` (non-interactive) uses the result as is, and `interactive.js` uses it as initial values and overrides only what the user answered. Do not restate defaults at the entry points — the two paths once diverged and the interactive PR-summary choice was dropped.
- `.github/.projectops/AGENT-GUIDE.md` is installed into user repos (`src/core/agent-guide.js`). It does not embed option values; it only points to the command.
- This repo's `AGENTS.md`, `GEMINI.md` and `llms.txt` are template-only, so they are excluded in both `exclusions.js` and `template_initializer.py`.

### Docs and demo GIFs follow the reader's language — English by default (#976)

| Target | English (default) | Korean |
|---|---|---|
| Docs site URL | `/projectops/<slug>` ← `docs/en/<slug>.md` | `/projectops/ko/<slug>` ← `docs/<SLUG>.md` |
| Demo GIF | `docs/images/<name>.gif` | `docs/images/<name>.ko.gif` |
| Used in | `README.md`, ja and zh-CN READMEs, `docs/en/` | `docs/i18n/README.ko.md`, `docs/*.md` |

- **Files are not moved; only URLs change.** The rule lives in one place, `site/.vitepress/locale-paths.mts` (shared by `rewrites` and the old-URL redirects). Both languages must use the same slug so the language switch lands on the matching page — when you add a Korean doc, add the English doc with the same slug.
- **GIFs are not recorded by hand.** Re-record them per language with the scripts in `docs/recording/` (see its `README.md`). Set `PROJECTOPS_LANG` / `--language` explicitly so the system language does not leak in, and record with the working-tree CLI and templates, not the npm release.
- The wizard deploy-environment prompts (`.github/config/wizard-prompts.yml`) use `label` = English and `label_ko` = Korean. Add both languages for every new key.

### Korean lines on English surfaces may only shrink (#769)

- `scripts/tests/test_korean_line_budget.py` counts, per file, the **Korean lines excluding comments and docstrings** in skills, src, workflows, scripts, wizards, READMEs, etc., and compares them with the frozen ledger `scripts/tests/korean_line_budget.json`. Files not in the ledger must be at 0; files in it fail if they exceed the ledger number.
- When removing Korean lowers a count, the test fails with "lower the ledger" → `python3 scripts/tests/test_korean_line_budget.py --update` (applies only decreases, never raises).
- Write user-facing text in English and put Korean in the i18n ko dictionaries. Adding Korean to a counted file needs a strong reason, such as **data the code compares** (Korean labels like `작업전`); only then raise the ledger number by hand and state the reason in review.
- The excluded scope (ko dictionaries, `docs/`, tests, pro-launch troubleshooting, etc.) and the reasons are canonical in the test file's `EXCLUDED_PATTERNS`.

### Three layers of run logs (#493 · #494 · #561 — agent must read)

When the wizard (full/workflows) finishes, it writes run logs to `.github/.projectops/logs/` in the **target repo**.
They lived under `docs/` before #561 — they are **diagnostic material for agents to pinpoint causes**, not documents for people,
so there is no reason to keep them in repository history.

| Layer | File | Contents | Source module |
|------|------|------|----------|
| 1 | `PROJECTOPS-MIGRATION-GUIDE.md` | Fixed header (AI interpretation guidelines) + append-only run entries: dynamic checklist, full text of passed breaking changes, yaml metadata (`schema` versioning) | `src/core/migration-guide.js` |
| 2 | `{stamp}_v{from}_to_v{to}.jsonl` | Structured events (trace causes by grepping file names) | `src/core/run-trace.js` |
| 3 | `{stamp}_..._.log` | **Server log format** — internal events and terminal output merged in time order | 〃 |

**New templates for skipped workflows are kept in `incoming/` (#654).** Workflows the user modified are not overwritten but
kept as `skipped-conflict`, and there was no way to see what differed. So the new template (with env and branch substitution applied)
is saved to `.github/.projectops/incoming/<file name>`, and the comparison commands (`diff -u`, `git diff --no-index`) are left on the final screen,
in the `skipped-conflict` event detail (`incoming`, `added`, `removed`) and in the MIGRATION-GUIDE checklist.

- **Same pattern as `logs/`**: the folder carries its own `.gitignore` (`*` + `!.gitignore`), so the root `.gitignore` is not touched.
- **Never write into `.github/workflows/`** — GitHub runs any file there as a real workflow.
- **Failure must not kill the wizard** — save or diff failures are absorbed as an `incoming-failed` event plus one warning line. The exit code is unchanged.
- Code: `src/core/incoming.js`, called from `applyDecision` in `copy/workflows.js`.

**The folder carries its own tracking exclusion.** `logs/.gitignore` (`*` + `!.gitignore`) is ensured on every run,
so the root `.gitignore` is not touched. The sibling `.github/.projectops/baseline.json` (#557) is a team-shared
asset and **stays tracked** — that is why the folders are separate.

**Log levels** (`levelOf`): `ERROR` (failure) / `WARN` (will fail if left, or needs a decision) / `INFO` (step boundaries, settled decisions) /
`DEBUG` (per-item detail). **DEBUG is always written to the file in full** — "if only it had been on" is useless after the fact.

- The engines (copy/env/legacy/orphan) **emit null-safely** through `hooks.trace` / `ctx.trace` — paths without an injected trace (existing tests) are unaffected.
- **Wrap steps with `trace.step(name, fn)` / `stepAsync`** — entry, exit, elapsed ms and failure are recorded automatically.
  Scattering start/done across call sites always leaves some spot uncovered.
- The guide's workflow list and env values are **derived** from trace events (single source). When you add a new engine behavior, add the event emit with it.
- **The call is `trace.event(phase, action, target, detail)`.** `emit` does not exist —
  because of optional chaining (`?.`), a typo was silently ignored without an exception and the log vanished entirely (#561).
- Sensitive values (PAT, token, secret, password, credential keys) are removed from events automatically by `scrubDetail` — **do not bypass it**.
  If a value is not secret but its key name matches (e.g. `token` → `placeholder`), **rename the key**.
- **The log must survive every exit path**: normal completion, mid-way cancel and exceptions are handled by `trace.finalize()` (idempotent) in `finally`,
  and forced exit (Ctrl+C) by `trace.armSignals()`. If you create a new exit path, check this contract.
- **Print the completion screen inside `try`, and call `finalize()` only in `finally` (#561).** `finally` runs right after leaving
  the try block, so if the completion screen is outside the try, the log closes first and **that screen is missing from the `.log` entirely.**
  A user's run log really did stop at `step/done install-full` and came back as a report that "the log has no guidance at all".
  `finalize()` is idempotent, so calling it again later does not recover anything — the order is the contract.

### Breaking Changes
Register compatibility-breaking changes in `.github/config/breaking-changes.json`:
```json
{
  "<version>": {
    "severity": "critical | warning",
    "title": "English title",
    "message": "English details and action steps",
    "title_ko": "제목 (선택)",
    "message_ko": "상세 설명 및 조치 방법 (선택)"
  }
}
```

> **`title`/`message` are English, canonical and required (#988).** Older CLIs fetch this file from `main` and read only these two keys,
> so do not change the key names or format. Korean goes into the optional keys `title_ko`/`message_ko` and is shown only when the CLI
> display language (`--lang`, `resolveLang`) is `ko`. Without them it falls back to English (`localizeBreakingEntry` in `src/core/breaking.js`).
> The migration guide (run log) keeps the English original.
> (every entry has English `title`/`message`), and the Korean line watch does not count `*_ko` key lines.
