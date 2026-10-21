# Phase 6 — Standard report format for the user

Shared by CREATE mode Phase 6 and IMPROVE mode Phase 4. Write the report in the user's language; the templates below give the structure.

## CREATE mode report format

```
## Created: {skill-name}

**Location:** {file path}
**Version:** {frontmatter.version}

### 8-principle results
| # | Principle | Result | One-line evidence |
|---|------|------|-----------|
| 1 | One at a time | ✅ | One question at a time enforced in Phase 0 |
| 2 | Automatic inference first | ✅ | {which values were extracted and how} |
| 3 | Explain technical terms | ✅ | {which terms were explained} |
| 4 | Concrete UI paths | ✅ | {example of a concrete path} |
| 5 | No hard-coding | ✅ | {values replaced with placeholders} |
| 6 | Separate config file | ✅ | {config file location} |
| 7 | Reflects real experience | ✅ | {source of the pitfalls section} |
| 8 | Flexible input | ✅ | {input accepted all at once} |

### Trigger utterance check (Phase 5 result)
3 should-trigger examples — all PASS  
2 should-not-trigger examples — all PASS

### Needs user verification (unverified assumptions)
- {assumption 1}
- {assumption 2}

### Next steps
1. Shall we invoke it once now to check how it behaves? (Phase 7)
2. If something is wrong, tell me where to fix it.
```

## IMPROVE mode report format

```
## Improved: {skill-name}

**Version:** {previous} → {new}

### Applied patches
| # | Item | File | Change summary |
|---|------|------|----------|
| 1 | ... | ... | ... |

### Principle re-evaluation
| # | Principle | Before | After |
|---|------|------|------|
| 1 | One at a time | ✅ | ✅ |
| 2 | Automatic inference first | ⚠️ | ⭐ improved ({how}) |
| ... | ... | ... | ... |

### Remaining room for improvement (not applied this time)
- {item 1} — {why it was postponed}

### Behavior check results
- {command run} → {result}
- Parts that could not be run: {why}
```

## Rules

- If any row of the 8-principle table is not ✅, go back to Phase 4 (self-review). Never report to the user with ⚠️/❌ remaining.
- Do not declare the work done until the user gives **explicit approval** such as "OK", "good", "merge it".
- **Print the report directly in the conversation.** Do not create a separate file (unless told to).
