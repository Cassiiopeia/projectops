> When to read: at step 4, when writing the report (md). Per-repo report structure and batch scoreboard rules.

# Report structure

Write the report in the user's language (or the configured `language` preference). The headings below are the structure; translate them into that language.

```markdown
# {OWNER/REPO} open-source consulting (YYYY-MM-DD)

## One-line diagnosis
{type}, stage {N}. Do this first: {top priority}

## Scores
| Axis | Score | One line |
|---|---|---|
| A First impression | 00 | |
| B Proof of value | 00 | |
| C Community readiness | 00 | |
| D Code extensibility | 00 | ("unverified" if the code was not checked) |
| E Legal safety | 00 | |
| F Long-term operation | 00 | |

## Defects (must fix)
## Notes from a first-time contributor
(The result of actually walking the 7 steps in contributor.md, in the contributor's first person. If you could not see the code, only up to the steps you could check.
If review or batch could not see the code, write only "code unverified"; do not make things up)
- Where I got stuck: "I ran `npm test` as the README says, and it failed because there is no .env. Nothing says which values it needs"
- Where I hesitated: "To add a type I had to edit the README and test fixtures besides the files the guide lists. I worried I had missed more"
- What would have helped: "A link to one past PR that added a type would have let me just follow it"
- What worked: "The issue form asked for the version and the log location, so reporting was easy"
## Maturity: currently stage N → prerequisites for stage N+1
## Improvements (by impact)
| Rank | Action | Axis | Grade | Expected effect |
## What works well
## What we could not check
(`errors` · `truncated` · `unsupported_manifests` · code unverified and so on: items whose evidence you could not see, and why)
```

In batch mode, build **one scoreboard** instead of per-repo reports: repo, type, stage, the six axis scores ("unverified" for axes you could not see), and the top action.
Group `study` repos on one line with only "suggest archiving". **How to pick representative repos**: pushed within the last 90 days, not `study`,
lowest scores first, up to 3. A repo the user picked takes priority. Keep one fixed criteria table per type so the evidence does not drift
between earlier and later repos, and leave one line of score reasoning per repo.
