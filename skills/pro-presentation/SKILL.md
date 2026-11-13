---
name: pro-presentation
description: "Prepare a talk: build or import the deck as HTML, rehearse it aloud slide by slide with coaching that fits the script to the speaker and remembers their directions, export PDF and editable PPT. Use for 'let's rehearse', 'make slides', 'review my script', 'export to PPT'."
---

# Presentation: build the deck, rehearse it, export it

## When to use

- "Let's prepare my talk", "help me rehearse", "make the slides for this", "rehearse with this PPT" (Korean: '발표 준비하자', '발표 연습하자', '발표 자료 만들어줘', '이 PPT로 연습하자', '대본 봐줘')
- The user speaks a slide and wants feedback, or states how they want the talk to sound.
- "Export it to PPT / PDF" (Korean: 'PPT로 뽑아줘', 'PDF로 내보내줘').
- After the deck is ready, "I recorded a run-through" (optional).

| Situation | Skill |
|---|---|
| Score the deck against a rubric, Q&A drill | `pro-judge-score`, `pro-judge-grill` (if installed; otherwise skip and say so once) |
| Pick a visual style among a few options | `pro-ui-design`, then put the pick into `theme.css` |
| Decide what the talk should argue | `superpowers:brainstorming` |

Talk to the user in the user's language (or the configured `language` preference). Apply the **absolute rules** in `../references/common-rules.md`.

**You do the coaching and the writing.** You edit the deck files directly. The CLI only runs the practice server, imports, checks, records and exports.

## Read before you start

1. `references/coaching.md`: how one coaching turn goes, how directions are kept, the rules. **This is the core.**
2. The style pack for the deck language: `references/style-pack.ko.md` or `references/style-pack.en.md` (add a pack per new language; fallback en).
3. The deck's `memory.md`, every session, before the first slide.

## Goal → command → details

Every command is `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py presentation <command>` (add `--root <project>` if the shell left the project). All output is JSON with `next`; follow it.

| Goal | Command | Details |
|---|---|---|
| Create a deck (template + first-run questions) or reopen one; get the page URL | `start [--deck DIR] [--title T] [--open]` | Step 1 · `references/init-questions.md` |
| Where to put a new deck | `get-output-path --title T` (or the `deck_root` setting) | |
| Server state · stop | `status [--deck]` · `stop [--deck]` | |
| Bring in an existing PPT or PDF | `import --deck D --pptx F` or `--pdf F` | `references/building.md` |
| Build or change slides | edit `slides/<id>/slide.html`, `theme.css`, `deck.json` | `references/building.md` · `references/deck-format.md` |
| Mechanical check: missing files, glossary hits, time against the limit, per-take timing, picture parts | `check --deck D` | |
| Export (never overwrites: `exports/v<n>/`) | `export --deck D [--pdf] [--pptx] [--converter C]` | `references/exporting.md` |
| Add a recorded run-through (optional) | **Record** on the practice page, then `recording add --deck D --label <take>`; or `recording add --deck D --file F \| --url U \| --transcript T` | `references/recording.md` |
| Settings | `config show \| set <name> <value> [--project P] \| options` | `../references/config-rules.md` §7 |

## Step 1: start

- No deck yet: `start --title "<talk>"` (or `--deck <folder>`). On `needs_init_questions`, ask the questions **one at a time** (skip what you already know), write the answers into `deck.json` and `memory.md`, then follow `building.md` "Where a deck starts".
- A deck exists: `start --deck <folder>`, read `memory.md`, and continue where the takes stop.
- Large pictures (an imported PPT, photos) are shown as lighter copies the server builds in the background; the originals stay untouched and the PPT export uses them. If `start` returns `image_copies: false`, relay `image_copies_hint`.
- Give the user the full `url`. It opens only on this computer. Arrow keys move slides, F is full screen.
- When the slide, script and feedback do not fit one screen, tell the user the page can be arranged (the deck remembers it): **A− / A+** set the text size of the Script and of the right-hand cards, the **handles** between the parts drag to resize (double-click resets), and **↗** opens the slide, the Script or the feedback cards in its own window that follows the current slide (close it to bring the part back).

## Step 2: rehearse

The user speaks a slide (often by voice input), you coach it as in `coaching.md` §1:
record the take, verdict, 0 to 3 points, one corrected version from their own words, update `script.md`, one line that the page changed.
When the user states a direction, follow `coaching.md` §3 at once (write it, apply it to every slide, report the slides).
Run `check` after structural edits and whenever time matters.

## Step 3: export

`export` makes the next `exports/v<n>/` with PDF and PPT (the `export_formats` setting picks the default), then verifies the PPT.
**Look at the verify report and the diff images before you say it is done** (`references/exporting.md`).

## Do not

- Do not ask for a recording before the deck is ready, and never treat one as required.
- Do not invent numbers or facts for a slide. Ask, or leave a visible placeholder.
- Do not put the deck in git unless the user removes the deck's `.gitignore` lines.
- Do not overwrite an export; versions exist so an open PPT is never in the way.

## Shared references

| Document | Read when |
|---|---|
| `../references/common-rules.md` | Always, at start: absolute rules, confirmation gates, issue state, push |
| `../references/agent-conduct.md` | When a tool is missing or you are about to say it cannot be done |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start with `SKILL_ID=pro-presentation`.
Keys for this skill: the common `language`, `tone`, `rules` only. Behavior is under `config`; how the user likes to speak is in `~/.projectops/presentation/memory.md`.
Preferences change presentation only; approval gates and secret protection stay in force.
