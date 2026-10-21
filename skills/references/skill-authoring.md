# Rules for writing skill docs

Read this when **writing or editing** skill docs (SKILL.md and references). It is not needed when running a skill.
For subcommand design, see `mcp-subcommand-rules.md`; for adding a config schema, `config-rules.md` §8.

## Reference document path rules (#543)

There are **two kinds** of reference docs, and they are written with different paths. Mixing them up means the
skill cannot find the doc and proceeds on its own judgment instead of the prescribed procedure.

| Kind | Where it lives | How SKILL.md writes it |
|------|------------|----------------------|
| **Shared docs** (common-rules, config-rules, personas, and so on) | `skills/references/` | `../references/<file>.md` |
| **Skill-specific docs** (checklists only that skill uses, and so on) | `skills/<skill>/references/` | `references/<file>.md` |

In SKILL.md, `references/<file>` without a prefix points **inside the skill's own folder**. Shared docs are not
there, so always add `../`.

> Breaking this rule left 16 skills pointing to non-existent paths in 50 places, and in one real incident the
> issue creation procedure doc could not be found, so the duplicate check and approval gate were skipped (#543).

**When docs in the same folder (`skills/references/`) refer to each other, use just the file name with no prefix** —
`config-rules.md`. Adding `references/` points to a subfolder under its own folder that does not exist.

Do not run the check by hand. CI runs it every time (#612).

```bash
python3 -m pytest scripts/tests/test_skill_docs.py -q -k reference_paths
```

`test_skill_doc_reference_paths_exist` checks every reference with a `references/` prefix. This spot used to hold
a Python snippet to paste, but it had to be run by hand, so no one ran it, and the doc itself broke the
no-heredoc rule.

## What goes in the common rules doc (#828)

Every skill reads `common-rules.md` when it starts, so keep it short with **only the absolute rules that apply to every skill**.
Move details needed only by specific skills or situations into topic docs (`commit-convention.md`, `sensitive-info.md`,
`work-start-protocol.md`, `script-invocation.md`, `agent-conduct.md`) or that skill's `references/`,
and leave a one-line pointer under the same heading in `common-rules.md` — other docs refer to it by section name.
