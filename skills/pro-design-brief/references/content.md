# Alternatives · copy · UI elements · must-keep rules

> When to read: Step 4, when filling `alternatives` · `copy` · `ui` · `summary.must_keep` in the board data.

## ① Layout alternatives: differ in axis, not in looks

- 3 to 5 options. Axes that split them: position · density · representation (text, icon, badge) · entry (in place, new screen, sheet).
- **Always include a "current implementation" option and a "minimal" option.**
- For each option: `pros · cons · dev impact`. Dev impact means things like "this option needs a new screen, so it costs extra development".
- The recommendation is **one line with its reason.** Name options A · B · C, and use the same names as the issue body.

## ② Copy: `current → 2–3 candidates → reason`

| What to flag | Examples |
|---|---|
| Translated-sounding or stiff phrasing | "You are able to …", "… has been completed" (Korean: "~하실 수 있습니다", "~되었습니다") |
| Wordy · repetitive | Title and body say the same thing |
| AI punctuation | Overuse of em dashes (—) and middle dots (·) |
| Hype | "revolutionary", "perfect" |
| Violates repo terms or voice rules | Glossaries in root/module `CLAUDE.md` and `docs/*design*`; **read them automatically** |

- **For legal text (terms, consent), mark only "must not change"** and offer no candidates (`legal: true`).
- If a state has no copy, mark **"copy needed"** (`needed: true`).
- After writing candidates, run the mechanical check with `copy-lint` (`--file` takes the `copy` array or the whole board data;
  `--banned` takes the "do not use" column of the repo glossary, as a comma list or a file with one per line). Flagged items come back as `candidate_issues`.
  **It does not write good copy for you.** Fixing the flagged ones is your job.

## ③ UI element candidates: pick from the data shape

| Data shape | Candidates |
|---|---|
| Pick one | Radio · segmented control · dropdown · card selection |
| Pick several | Checkboxes · chips · toggle list |
| Long content | Accordion · "show more" · bottom sheet |
| Confirmation · notice | Popup · toast · inline message |
| Collection | List · grid · cards |
| One read-only value | Value on the right of a list row · new screen · long-press to copy |

Use **components the repo already has first** (`existing`). Anything else is a "new component" (`new`).

## ④ Must-keep rules: collect automatically, with sources

Brand specs (for example the Sign in with Apple button), minimum touch size and font size (the repo's design principles doc), and **exceptions already agreed on**.
Agreed exceptions **often live in code comments**. Read the comments in the target screen's files (phrases like "left out on purpose",
"do not bring back"). If a repo principle conflicts with the target (for example 10px text vs a 14px minimum), raise it **as a question,
not as a defect**.
