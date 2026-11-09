# Deck folder format

Every file is plain text you edit directly. There is no build step: the server reads the files on each request.

```
<deck>/
├── .gitignore         "*" by default: the deck can hold field photos and personal data. Remove the lines to track it
├── deck.json          title, language, time limit, rubric, slide order
├── memory.md          presentation memory (coaching.md section 3)
├── theme.css          design variables; every slide.html uses only these
├── slides/<id>/       one folder per slide (any id without "/")
│   ├── slide.html     the slide (or slide.jpg / slide.png from an import)
│   ├── script.md      what to say; text in ( ) is a stage direction, not counted in time
│   ├── notes.md       right-side cards: each "## Heading" is one card ("## Title" sets the slide title)
│   ├── takes.md       spoken takes with feedback, oldest first
│   └── memo.md        the user's own memo (edited in the page)
├── recordings/<label>/   optional: meta.json, transcript.txt, ranges.json
├── exports/v<n>/      export results, one folder per run
└── .presentation/     server state (pid, port, key); do not edit
```

## deck.json

```json
{
  "title": "Team ELUM final",
  "language": "ko",
  "time_limit_seconds": 600,
  "rubric": "docs/pro-judge/codegate2026/rubric.yaml",
  "characters_per_second": null,
  "slides": [
    {"id": "01-cover", "kind": "cover"},
    {"id": "06-comparison", "kind": "comparison"}
  ]
}
```

- `slides` order is the talk order. Strings (`"01-cover"`) are accepted as well as objects.
- `characters_per_second`: leave `null`; it is measured from the newest recording that has ranges, else 6.0.

## memory.md sections

| Section | Holds | Read by |
|---|---|---|
| `## Directions` | dated user directions, quoted, with the rule you took | you, every session |
| `## Voice` | the user's own phrasings that work | you, when writing scripts |
| `## Glossary` | table: Avoid, Instead, Why | `check` (plain substring match) and you |
| `## Transcript fixes` | table: Heard, Actual | recordings (applied to transcript lines) |
| `## Decisions` | suggestions the user overruled; do not raise again | you |

## notes.md cards that the page treats specially

- `## Title`: first line becomes the slide title (not shown as a card).
- A heading containing "caution", "warning" or "recording" (or the language pack's words) is shown in the warning colour.

## ranges.json

`{"01-cover": [0, 9], "02-agenda": [9, 15]}`: seconds into the recording, end exclusive. You write it after reading the transcript.
