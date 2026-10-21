# check — inspect only the code that just changed

> When to read: "is what I just wrote OK?", "look before I commit", "any odd comments?", or when one AI task has finished.

Goal: catch the smells one round of vibe coding left behind **the moment they appear**. Do not look at everything.

## 1. Collect

```
diff PATH                 # uncommitted changes (default --base HEAD)
diff PATH --base develop  # the whole branch
```

## 2. Judge each item

| Output | What to look at | Action |
|---|---|---|
| `stale_comment_suspects` | Code changed, but the comment above it or the enclosing function's doc comment did not | Read whether the comment describes **the current behavior**; if not, fix it (most important) |
| `added_comment_problems` | History wording, banners, full-sentence endings, long blocks in new comments | Shrink to a one-line summary or a step header. History goes in the commit message |
| `rewritten_existing_comments` | Only the comment was rewritten; the code is unchanged | Revert it (do not fix comments on code you did not touch) |
| `new_definitions[].similar_existing` | Existing definitions whose names resemble a new function or class | Open the existing one; if it does the same job, switch to reusing it |
| `new_boolean_names` · `new_naming_problems` | Booleans without a prefix, abbreviations, meaningless names | Rename |
| `ledger_new_violations` | New violations of a frozen rule | Fix the code. **Do not add lines to the frozen list** |

`similar_existing` is only a candidate based on shared name words. If it does a different job, leave it.

## 3. Show, then fix

Show the fix list briefly with `file:line` and fix only what is approved. If the user already said "fix everything", fix right away.
After fixing, run the existing tests and `ledger PATH check`.

## 4. If it keeps repeating

If the same smell shows up in every check, propose turning that pattern into a rule (the same way as `references/refactor.md` step 5).
