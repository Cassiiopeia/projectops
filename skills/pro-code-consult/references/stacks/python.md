# Python stack rules

> When to read: when the target has a `pyproject.toml`, `requirements.txt` or `setup.py`. Shared by audit, refactor and init.

## Layer map

| Layer | Location (FastAPI) | What goes in |
|---|---|---|
| Presentation | `routers/` | Request and response model conversion, dependency injection |
| Application | `services/` | Business rules |
| Domain | `domain/`, `models/` | Pure models and rules |
| Infrastructure | `repositories/`, `clients/`, `config` | DB, external APIs, reading config |
| Common | `core/` (config, exceptions, logging) | |

Dependency direction: routers → services → domain ← repositories. **A router importing a repository or client is a violation.**
For script and CLI repos (no layers), use one rule instead of layers: "keep entry points thin, put logic in reusable modules".

## Common AI smells

- `except Exception: pass` (swallowed exceptions), a `catch-all` that exposes the raw message
- Config key strings and environment variable names repeated across files
- "Not implemented yet" stubs left on production paths
- Multi-line docstrings longer than the function, work history in module-head docstrings
- `ok: bool`, `strict: bool` (no prefix), a function that returns `-> bool` but has a verb name (`create_branch`)
- Abbreviations and meaningless names such as `tmp`, `res`, `cfg`, `util`

## First rule candidates

```
# router-must-not-import-repository.rule
description=Routers must not import repositories or external clients directly (go through services)
paths=app/routers/
extensions=.py
pattern=^(?:from|import)\s+[\w.]*(?:repositories|clients)\b

# no-swallowed-exception.rule
description=No silently swallowed exceptions (log or re-raise)
paths=app/
extensions=.py
pattern=except[^:\n]*:\s*\n\s*pass\b
```

import-linter (`[importlinter]` contracts) is more precise for layer imports — it is a new dependency, so **only propose** it.

## Rule tests

`install-tests PATH --stack python --module <package folder>` → `tests/architecture/test_architecture_rules.py`. Uses pytest only.

## Choosing model files

1 router (thin), 1 service (step-header comments, question-style booleans), 1 client (timeouts and retries in one place).
