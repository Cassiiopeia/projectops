# Refactoring proposal format (8 steps)

> When to read: refactor step 1. Show the proposal in this format and wait for approval.

```markdown
## Proposal: <one-line title>

### 1. Repeated pattern
- What, in how many places: `<pattern>` in N places (evidence: 3–5 `path:line`)
- How they differ: <3 sizes, 2 kinds of error handling, etc.>
- Cause in one line: <why each place built its own — no common point / not documented / a rule document invites it>

### 2. Layer · location
- Where the common code goes: `<folder>` (per the layer table in conventions §3.1)

### 3. New common components
| Name | What it handles in one place |
|---|---|

### 4. Name table
| Now | New name | What the name alone tells you |
|---|---|---|

### 5. Scope
- Same behavior, structure only. How it is pinned: <existing tests / new pinning test / pro-agent-test scenario / captures>
- N files change

### 6. Rule test
- Forbids: `<pattern>` (`paths=...`)
- Exceptions: <none / N frozen — reason>

### 7. Documents
- Add <common components · model files> to `docs/architecture/stacks/<stack>.md`

### 8. Not doing
- <out of scope this time · excessive tooling · deferred to later>
```

Rules:
- Step 1 numbers are only what you **confirmed in the source**, not raw CLI results
- Step 4 names follow conventions §2 (boolean `is/has/can/should`, no abbreviations, file name = type name)
- Never leave step 8 empty. If you do not state the scope, the refactor grows into feature work
