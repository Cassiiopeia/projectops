# projectops-extras

Optional plugin from the projectops marketplace. It holds skills that are not part of the core development cycle.

| Skill | Purpose |
|-------|---------|
| `pro-synology-expose` | Guide for exposing a web service on a Synology NAS under your own domain (DNS, reverse proxy, certificate) |

## Install

```bash
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops-extras@projectops-marketplace --scope user
```

`skills/references/` holds copies of shared docs from the core plugin. Do not edit them; run `python3 scripts/sync_extras.py` in the repository root (a test fails when they drift).
