# projectops-extras

Optional plugin from the projectops marketplace. It holds skills that are not part of the core development cycle.

| Skill | Purpose |
|-------|---------|
| `pro-code-consult` | Keep AI-written code maintainable: audit against your coding conventions, refactor one approved item at a time with before/after checks, check each diff for stale or prose comments and duplicated code, and freeze existing violations so they only shrink (rule tests for Flutter, Spring, Python, JavaScript) |
| `pro-synology-expose` | Guide for exposing a web service on a Synology NAS under your own domain (DNS, reverse proxy, certificate) |

## Install

```bash
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops-extras@projectops-marketplace --scope user
```

`skills/references/` holds copies of shared docs from the core plugin. Do not edit them; run `python3 scripts/sync_extras.py` in the repository root (a test fails when they drift).
