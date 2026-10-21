# Trigger utterance optimization (optional)

Use when the quick check in CREATE mode Phase 5 passed but the skill still does not seem to get invoked well. In most cases the quick check (5 samples) is enough.

## Why the description matters

The `description` in the SKILL.md frontmatter is almost the only signal Claude uses to decide "should I invoke this skill?". However good the body is, a vague description means the skill never gets invoked.

## Quick check (Phase 5 default)

1. **3 should-trigger**: utterances that should invoke it. Natural phrasing that does not name the skill directly.
2. **2 should-not-trigger**: nearby topics that must not invoke it.
3. The agent asks itself "Would I think of this skill from the description alone?"

5/5 is OK. If even one misses, fix the description and check again.

## Quantitative optimization with the official `run_loop.py` (advanced)

The official skill-creator has a loop that improves the description automatically. Requirements:
- the `claude` CLI is available (Claude Code environment)
- about 20 eval queries prepared (a mix of should-trigger / should-not-trigger)

### Run

```bash
python -m scripts.run_loop \
  --eval-set <trigger-eval.json> \
  --skill-path <skill-dir> \
  --model <model-id> \
  --max-iterations 5 \
  --verbose
```

- 60% train / 40% test split
- each query runs 3 times for a stable trigger rate
- extended thinking proposes description improvements → re-evaluate → repeat (up to 5 times)
- best_description is picked by test score (prevents overfitting to train)

### Tips for writing eval queries

- **Bad**: "Format this data", "Extract text from PDF" — too abstract
- **Good**: utterances a real user would type, with context: file paths, work background, a bit of small talk

Example:
> "I just want to see the changed files in MR !347 of the api-server repo on our team's gitlab.example.com"

### In-house network limits

If `claude -p` is blocked on the in-house network, this loop does not run. Use the quick check (Phase 5 default) instead.

## Description writing tips (without quantitative optimization)

1. **Quote example trigger utterances directly** — "show me the MR changed files", "make a skill"
2. **Write in English by default, and add the users' own language** — e.g. a Korean team types mostly Korean but uses English technical terms, so include both
3. **Include concrete topics/project aliases** — CM, query server, systemdashboard, etc.
4. **Use "pushy" wording** — "always invoke", "when the user mentions X, Y, or Z". Too modest and it never gets invoked.
5. **Not too long** — ~200~300 characters. Too long lowers the signal-to-noise ratio.
