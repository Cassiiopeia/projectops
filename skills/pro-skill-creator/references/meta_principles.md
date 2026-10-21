# Meta principles · Python call standard for new skills

> When to read: when writing or changing a SKILL.md body (CREATE Phase 3 · IMPROVE Phase 2), and when a new skill needs a Python CLI.

## 1. Meta principles

### 1.1 Explain the why — not ALL CAPS

Rather than an ALL CAPS "NEVER do this", give the agent one sentence on **"why it matters"**. Models are smart; once they know the reason, they decide correctly in edge cases too. When you write a rule, make a habit of adding one line `(reason: ~)`.

### 1.2 Prefer multiple choice (multiple choice > open-ended)

When asking the user, **offer options** whenever possible. Open-ended questions make users dig for an answer every time, and the answers vary so the agent must interpret them again. With multiple choice, the user only picks, and the agent branches easily.

```
❌ "Which authentication method should we use?"
✅ "Which authentication method should we use?
   1) Personal Access Token (recommended)
   2) ID/password
   3) Other (enter it directly)"
```

But when the user would rather not narrow the answer (creative design, naming, etc.), open-ended is better. Use judgment.

### 1.3 Scale to complexity

Not every section of a skill needs the same depth. **A simple action gets one line**; a complex one gets 200~300 words. Documenting every action at length drowns the signal for the reader.

Examples:
- `config-show`: "show the current settings (tokens/passwords masked)" — one line is enough
- `mr-create-from-branch`: branch-name parsing logic, automatic target selection, conflict-check rules — needs several paragraphs

### 1.4 Incremental validation — confirm section by section

Do not throw a long design at the user all at once. After each section, confirm "Is this right so far?". If there was a misunderstanding, you fix only that section instead of overturning the whole design.

Going step by step through Phase 0 is an application of this principle.

### 1.5 Go back when needed (be flexible)

Phase numbers are linear, but **the procedure is not rigid**. If you realize during Phase 3 that the Phase 0 scope was wrong, go back to Phase 0 and agree again. Resist the temptation of "we came this far, let's push through".

When going back, tell the user: "I found an unclear boundary during Phase 3, so I am briefly going back to Phase 0 to confirm."

SKILL.md being short and phase-centered is a result of this habit. Details live in references/, and the body keeps the agent asking itself just two questions: **"which phase am I in?"** and **"is the exit condition met?"**

## 2. When a new skill needs Python calls (the 3-layer standard)

If a new skill needs the GitHub API, external systems or subcommand calls, it **must follow the 3-layer standard**:

1. **Check shared domain logic**: is the needed function already in `scripts/common/`? (`gh_client`, `config`, `paths`, `title`, etc.) If so, import and reuse it. Do not write it again.
2. **Write a skill-specific CLI**: copy the `templates/python_cli_script.py` skeleton.
   ```bash
   cp skills/pro-skill-creator/templates/python_cli_script.py skills/pro-<new>/scripts/<scope>_cli.py
   ```
3. **Replace prog + subcommands**: replace the skeleton's `<scope>_cli` parts and `cmd_example` with the real domain.
4. **Import shared logic**: in the form `from common.<module> import ...`. Do not rewrite Layer 1.
5. **Calls in SKILL.md**: the standard self-contained 5-line pattern (see `../../references/common-rules.md` §"skill별 py 분산 호출" (per-skill py calls)). Put the script-finding block in SKILL.md **only once**, and later blocks reuse the found values, as in `{PYTHON} {SCRIPTS}/<scope>_cli.py` (model: `pro-launch/SKILL.md`).
6. **If shared logic is missing, add it to Layer 1**: keep only single-skill logic in the CLI; if 2 or more skills may use it, move it to `scripts/common/<new>.py`.

### What the skeleton provides

- Works regardless of cwd (sys.path is set from `__file__`)
- Automatic argparse `--help`
- The `common.emit.emit()` helper guarantees the 4 MCP-style JSON fields (ok/code/summary/next)
- Works on both Windows Git Bash and macOS/WSL (verified)

### Verification

- After writing the new skill CLI, dry-run it: `cd skills/pro-<new>/scripts && python <scope>_cli.py --help` → check the argparse usage output
- Call one subcommand for real → check the 4 JSON fields

The CREATE Phase 6 report standard depends on this standard: when creating a new skill, the Python call items are done with the procedure above.

## 3. Attaching official troubleshooting knowledge to a skill (#889)

- Put entries in `skills/<skill>/troubleshooting/<area>/<id>.json` (schema and writing rules: `skills/references/memory-principles.md` §6).
- Build the index and `references/troubleshooting.md` with `python3 scripts/build_troubleshooting.py skills/<skill>` — do not edit them by hand.
- In one place in the CLI's failure output, attach the result of `common.troubleshoot.find_known_fixes(<skill folder>, code, error text)` as `known_fix` (swallow exceptions — it is auxiliary). Example: `attach_known_fix` in `pro-launch`'s `runtime/output.py`.
- Add tests for `--check` (generated files are current) and "is each entry's `match.codes` a code the CLI really emits" (example of the `match.codes` check: `skills/pro-launch/tests/test_troubleshooting_kb.py`).
