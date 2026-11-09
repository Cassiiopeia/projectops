# Recordings (optional, after the deck is ready)

Rehearsal happens in conversation: the user speaks a slide, you coach it. A full recording is only useful once the deck is
ready and the user wants to check timing end to end. Do not ask for one earlier.

## Add a take

| The user has | Run |
|---|---|
| Pressed **Record** on the practice page (microphone only; the page saved `recordings/<take>/audio.*`, `marks.json` and `ranges.json`) | `recording add --deck D --label <take>` (transcribes the saved audio locally) |
| A file recorded on a phone or laptop (mp4, m4a, mp3, wav, mov, webm) | `recording add --deck D --file <path>` (faster-whisper + ffmpeg, local) |
| A video link | `recording add --deck D --url <link>` (captions first, else transcribed) |
| Captions or a transcript (srt, vtt, "[mm:ss] text") | `recording add --deck D --transcript <path>` |

On `no_transcript_source`, tell the user what is missing in one line and offer the next option.

## Split it per slide

A take recorded on the practice page already has `ranges.json` from the moments each slide was shown (`ranges_measured: true`); skip this step.
If the user revisited a slide, the longest visit counts. Edit the file only when the user says a range is wrong.

Read `transcript.txt` and write `ranges.json` (`{"<slide id>": [start, end]}`, seconds, end exclusive).
Cut where the content of the next slide starts; if a sentence spans two slides, give it to the slide whose content it carries.
Then run `check`: it returns per-slide seconds for every take and each take's total.

## Review it

1. Report the total against the limit and the slides that moved most since the last take (a short table).
2. Read each slide's lines against `coaching.md` and the style pack. Name only the slides that broke a rule.
3. Write the details into a `## Take <n> review` card in that slide's `notes.md`; the page shows it in the warning colour.
4. Add obvious transcription slips to `memory.md` `## Transcript fixes`.
