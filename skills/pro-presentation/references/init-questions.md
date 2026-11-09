# First-run questions

`start` on a new deck returns `needs_init_questions: true` and the list below in `questions`.
Ask them **one at a time**, in the user's language, and skip any the user already answered in the conversation
or that you can read from their files (a pro-judge `rubric.yaml`, an announcement, an existing deck).

| id | Ask | Write the answer to |
|---|---|---|
| `purpose` | What is the talk for, where, and to whom? | `deck.json` `title`; `memory.md` Directions |
| `time_limit` | How long may it run? Q&A after it? | `deck.json` `time_limit_seconds` |
| `criteria` | Judging criteria or a rubric? | `deck.json` `rubric`; heavy criteria into Directions |
| `language` | Which language will you speak? | `deck.json` `language` (picks the style pack) |
| `material` | What do you have: nothing, an outline, a PPT, a PDF, a reference you like? | next step (building.md "Where a deck starts") |
| `terms` | Words the team always or never uses? | `memory.md` Glossary rows |
| `recording` | Will you record a full run-through later? | Directions (recordings are optional) |
| `exports` | What must you hand in: PDF, PPT, nothing? | Directions; `config set export_formats` if it is the same for all talks |

After the last answer, play back the setup in five lines (title, length, criteria, language, starting point) and start building or importing.

## Settings that save questions next time

If the user gives the same answer for every talk, offer to save it (`config set`): `language`, `time_limit_seconds`,
`export_formats`, `deck_root`. `config options` lists every option.
