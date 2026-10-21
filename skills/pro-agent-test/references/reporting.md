# Reporting results and filing issues

> When to read: Phase 5 — when you write a defect report or file it as an issue, and when you correct something you misjudged.

**The deliverable is what went wrong, not "how many passed".** You did your job when you
**found a defect**, more than when you report a pass.

Write the report in the user's language (or the configured `language` preference).

## Separate the categories

| Category | What |
| --- | --- |
| **Functional defect** | What was requested does not behave as expected |
| **Consistency defect** | The requested spot works, but **another spot of the same kind does not** (Phase 4.5 — `wide-view.md`) |
| **Observability** | The feature works, but **cannot be traced later** |
| **Improvement proposal** | Not a defect, but a better approach seems to exist (Phase 4.8) |
| Pass | Walked and confirmed |
| On hold | Could not proceed because a person must step in |

Do not mix them. If you mix consistency defects into functional defects, the report **reads as "this work failed".**

## What a report must have

If any one is missing, it is not a report.

| Must have | If missing |
| --- | --- |
| **What you actually walked** (commands, responses, screens, query results) | It reads as a guess |
| **What broke** | It ends as "it works" without a defect |
| **Why it was not caught until now** | You miss the same kind again |
| **Other places of the same kind** (4.5) | One spot gets fixed and the rest remain |
| **What moves together if this is fixed** (4.7) | Something else breaks silently after the fix |
| **When it blows up if not fixed** | Nobody can decide what to do first |

**Do not write judgments without evidence.** "It will probably work" is not a report. If you walked it, write what you walked;
if you could not, write that you could not.

## Recheck gate before posting (preventing false positives)

For each defect candidate, clear the three below **before posting**. If you cannot clear even one, write it as a "suspicion", not a defect.

1. **Is it a leftover setting** — if text size, dark mode, language or orientation was changed before this test, `--restore` and reproduce again.
2. **Is it the tool's fault** — it can be a limit of the input tool, like simulator taps not registering at the screen edge. **Tap once more through a different input path** (element selection `--text` ↔ ratio coordinates, or the project's E2E).
3. **Is another session using the same device** — check `owners` in `devices`.

If the second reproduction gives the same result, post it as a defect. The goal is fewer posts that get retracted later.

## What one defect should contain

| Contains | Why |
| --- | --- |
| **Repro steps** | Following them exactly must trigger it again. If not, nobody can confirm the fix |
| **Expected vs actual** | Not "it is weird" but "expected 403, got 200" |
| **Evidence** | Raw response · DB query result · logs · screenshots |
| **Severity** | Criteria below |
| **Impact** | What this defect makes possible · how far it spreads |

## Severity

| Level | Criteria |
| --- | --- |
| **Critical** | Data leaks or gets corrupted (access to others' resources, passwords exposed in logs) |
| **High** | A main flow is blocked (sign-up, payment or login fails) |
| **Medium** | There is a workaround (unexplained error message, duplicate creation) |
| **Low** | Inconvenient |
| **Observability** | The feature works but cannot be traced |

**Do not raise severity by guessing.** Mark as Critical only **what you actually walked and saw happen**, not
"it could be breached". If you could not walk it, say so.

## Minimum report shape

Record walk results as a **per-step table**. "It works" is not a report.

```markdown
| Step | Screen | Stored on device | Stored on server | Verdict |
|---|---|---|---|---|
| Login | Home reached | refreshToken, provider | member created, login_count=1 | Pass |
| Accept terms | Consent screen | — | terms_agreed=t, consented_at | Pass |
| Enter name | Next screen | (nothing yet — saved in one batch at the end) | nickname empty | Pass |
```

As in the third row, **when empty is correct, write why.** Otherwise the next reader
mistakes it for a bug.

## Putting screenshots in an issue

GitHub issues render only external image links. **Do not commit them to the repo** — QA evidence
is not product code, and once committed it stays in history even after deletion, making the repo keep growing.
`upload-image` in `pro-github` uploads them as release assets and returns URLs (#585).

Shrink first. An issue does not need the original resolution.

```bash
# uses whichever of Pillow → sips (macOS) → ffmpeg is available (pro-launch).
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py shrink {screenshots...} --max-side 700
```

> `sips` exists only on macOS. Do not call it directly; use the script above — calling it directly fails on other people's Linux
> or Windows.

Then upload to get URLs.

```bash
... github_cli.py upload-image {owner} {repo} {images...} --prefix qa{issue number}
```

Paste the output's `markdown` field into the body as is. **Keep the order** — upload images first,
then post the body. If you do it the other way round, a post without images goes up.

Files captured with `web shot` are stored in the record folder (`knowledge_dir`/shots), not in the project.
Find it from the `knowledge_dir` value of `detect`.

## Filing as an issue

Use `/pro-github`. Title and body follow the target repo's issue template rules.

What a bug issue **must include**:

| Item | What happens without it |
| --- | --- |
| Repro steps | Others cannot confirm it, so it is left alone |
| Why it was not caught until now | You miss the same kind again |
| Impact | Nobody can tell whether it is urgent |
| Evidence (logs · screenshots) | It reads as a guess |

"Why it was not caught until now" matters most. For example, a sentence like *"devices with KakaoTalk installed
take a different path and never pass this screen"* shows how the test environment
has to change.

## When you were wrong

**Correct a misjudgment as soon as you find it.** If an issue is already filed:

1. A correction comment — what you misjudged, what is actually true, evidence image
2. Replace the label with `status: cancelled` (`취소`) and close with `close-issue --reason not_planned`
3. If a **real remaining problem** turned up along the way, write it up separately

Example: you filed "it looks cut off", but you had just not scrolled far enough → cancel the issue, but
"there was no cue that more content was below, which actually caused the misjudgment" is worth keeping.

## Handling UX problems too

Even if a feature works, write up **places that are awkward to use** separately. While walking E2E, the agent itself gets stuck
in places, and those are exactly where users get stuck.

| What happened | What to write |
| --- | --- |
| Could not find what to press next | What was hidden, and what makes it visible |
| Had to repeat the same action every time | Which repetition it was, whether it can be automated |
| Could not find a way to undo | Where it got stuck, and which path is needed |

For these issues, **present options.** A fix that affects the whole layout and a minimal change
need different judgment, so a person must decide.

## Write evidence for "looks wrong" as values ⚠️

"Works but looks wrong" (axes 4·5·6 of `references/looks-wrong.md`) **is judged differently by different people.**
If you do not pin the evidence to values, the report turns into an argument about taste.

| Write it like this | Not like this |
|---|---|
| Title font size has **3 variants** (20 · 22 · 24) across 4 screens | Fonts feel inconsistent |
| Button heights **48 / 44 / 52** | Buttons are uneven |
| Tapped but **no screen change · 0 log lines** | It seems unresponsive |
| **Moves for 280ms** with reduce motion at 0 | Animation is excessive |

**It is evidence only if it can be counted again.** If someone else can look at the same screen later and reach the same numbers,
the verdict does not bend toward the result you wanted.

Separate defects from proposals — "a screen with only one thing to press" is a **proposal**, not a defect.
