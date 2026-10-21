# Audit report format

> When to read: audit step 5. Get the path with `get-output-path PATH --title "<title>"`.

```markdown
# Architecture audit: <repo> (<date>)

## One-line conclusion
<the single biggest cause — e.g. common points exist but nothing enforces them, so bypasses piled up>

## Numbers (scan · assets · deps · rule-docs)
| Item | Value | Previous audit |
|---|---|---|

## Top 10
| # | Severity | Problem | Evidence | Cause |
|---|---|---|---|---|

## By stack
### <stack>
- [high] <problem> — `path:line`

## Compared with the previous audit (when carried over)
| Previous item | Now (fixed / unchanged / worse) |
|---|---|

## Rule documents
- Contradictions with code · references to missing paths · phrases that invite prose comments

## What is done well
- <patterns that can move to other folders or repos>

## Could not verify

## Candidate rules to freeze
| id | What it forbids | Current violations |
|---|---|---|
```

- Fill the "previous audit" column from earlier lines of `docs/architecture/metrics.jsonl`
- Severity: high = visible to users or leads to outages or security issues, or a structure that keeps producing the same problem / med = maintenance cost / low = names and formatting
- Do not write sentences without evidence. If something feels off, find the reason and write it down
