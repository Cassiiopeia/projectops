# TC format · writing style · example

> When to read: in Step 4, right before actually writing the TCs.

## TC format

Write labels and text in the output language (the `language` preference, else the repo's or user's language). Keep the structure: a header table, then one `TC-NN` table per case with the same four rows.

```markdown
## Test cases: [feature name]

| Field | Details |
|------|------|
| Issue | #XXXXX |
| Target | [module / screen] |
| Assignee | @[assignee] |
| Date | YYYY-MM-DD |

---

### TC-01: [test title]

| Item | Details |
|------|------|
| Preconditions | [required preconditions] |
| Steps | [concrete steps] |
| Expected | [expected result] |
| Result | |

### TC-02: [test title]

| Item | Details |
|------|------|
| Preconditions | [required preconditions] |
| Steps | [concrete steps] |
| Expected | [expected result] |
| Result | |
```

## Writing style (with reasons)

- No emoji (reason: testers fill only text into the result cell, and emoji break copy-paste and alignment)
- Short, keyword-based wording; avoid long explanations (reason: long steps make testers skip steps)
- Fixed table header `Item | Details` (reason: GitHub markdown needs a consistent header so many TCs stacked together still render)
- Join steps with an arrow (`→`)
- Wrap settings, paths and commands in code spans (`` ` ``) (reason: so they can be followed exactly, without typos)
- Security tests (permissions, authentication) and edge cases (large values, special characters, duplicate calls) are included automatically (reason: checking only normal behavior misses most real defects)

## Example

```markdown
## Test cases: Profile image upload

| Field | Details |
|------|------|
| Issue | #427 |
| Target | Profile > Image upload |
| Assignee | @chan |
| Date | 2026-06-02 |

---

### TC-01: Normal upload

| Item | Details |
|------|------|
| Steps | Open profile → click `Change image` → pick a JPG under 5MB → `Save` |
| Expected | Preview shows; on save the new image is applied, `200 OK` |
| Result | |

### TC-02: Reject oversized file

| Item | Details |
|------|------|
| Preconditions | Prepare a 6MB image file |
| Steps | Click `Change image` → pick the 6MB file |
| Expected | Validation error "Up to 5MB only", upload blocked |
| Result | |

### TC-03: Unsupported format

| Item | Details |
|------|------|
| Steps | Pick a `.bmp` file |
| Expected | Error "Only JPG/PNG/GIF are supported" shown |
| Result | |
```
