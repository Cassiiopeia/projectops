# Six-angle review criteria and output format

> When to read: in review Steps 2–4, when you need the Critical/Major/Minor criteria per angle and the result templates.

## Six angles

### 🔒 Security
**Critical**: SQL injection, XSS, hard-coded secrets, authentication/authorization bypass
**Major**: Vulnerable dependencies, insufficient input validation, sensitive data in error messages
**Minor**: Missing security headers, sensitive data in logs, no rate limiting

### ⚡ Performance
**Critical**: N+1 queries, memory leaks, infinite loops, synchronous blocking
**Major**: Unneeded re-renders, large bundles, inefficient O(n²) algorithms, missed caching
**Minor**: No useMemo, unoptimized images, no lazy loading

### 🐛 Bugs and logic
**Critical**: Null/undefined references, type errors, missing exception handling
**Major**: Unhandled edge cases, race conditions, async errors
**Minor**: Unclear error messages, weak fallbacks

### 📐 Code quality
**Major**: Functions over 100 lines, DRY violations, cyclomatic complexity > 10, inconsistent style
**Minor**: Unclear names, magic numbers, nesting deeper than 3 levels

### 🏗️ Architecture
**Major**: Poor separation of concerns, dependency cycles, SOLID violations
**Minor**: Unclear structure, unneeded dependencies

### 🧪 Tests
**Major**: No tests for core logic, missing edge cases
**Minor**: Coverage < 70%, brittle tests

## Prioritization (3 levels)

Write headings and text in the output language; keep the emoji markers and the level names (Critical / Major / Minor / Positive) so the levels stay recognizable.

```markdown
### 🚨 Critical (fix now)
**file:line**: problem / impact / fix

### ⚠️ Major (fix before deploy)
**file:line**: problem / impact / fix

### 💡 Minor (recommended)
**file:line**: current / suggestion / reason

### ✅ Positive (done well)
- [what deserves praise]
```

## Overall verdict (Step 4)

```markdown
### 📊 Review summary
**Verdict**: [Approve / Request Changes / Comment]
**Issue counts**: Critical X / Major Y / Minor Z

**Key improvements**:
1. [most important]
2. [second]
3. [third]
```
