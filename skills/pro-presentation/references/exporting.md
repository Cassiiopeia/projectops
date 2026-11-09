# Exporting and verifying

`export --deck D [--pdf] [--pptx]` (no flag = the `export_formats` setting) writes the next `exports/v<n>/`.
It never overwrites: a PPT open in PowerPoint is never in the way, and versions can be compared.

## What a run makes

| File | What |
|---|---|
| `slide-NN.png` | each slide rendered from HTML at 1920 x 1080 |
| `<title>.pdf` | the PNGs as pages |
| `<title>.pptx` | editable PPT: `data-pp` pieces become native text boxes, shapes, pictures, tables; the script goes into speaker notes |
| `layout.json` | the measured pieces (position, font, colour, text) the PPT was built from |
| `verify.json` | the checks below |
| `render-back/` | the PPT drawn again by LibreOffice (only when it is installed) |

## Verify before you say "done"

Read `verify.json`, then look at a few slide PNGs and, if present, the matching `render-back` images.

| Field | Meaning | If not clean |
|---|---|---|
| `text_match` per slide | every text line of the HTML is in the PPT | read `missing_text`; usually a piece without `data-pp` or text inside an image |
| `picture_parts` | elements without `data-pp` that went in as pictures | add `data-pp` (building.md) or accept it and tell the user which slide |
| `missing_images` | an image piece whose file is not in the deck | put the file next to `slide.html` |
| `missing_fonts` | fonts used but not found on this computer | the PPT falls back to another font on machines without it; tell the user, or switch `theme.css` to a common font |
| `render_back` | `done`, `failed`, or `skipped_no_libreoffice` | when skipped, say the visual comparison was not run |

Report to the user: the version (`v3`), the files, and any slide that is not clean, by number.

## Tools

The browser step runs in the pro-launch environment (Playwright). Missing: `launch_cli.py web setup`.
python-pptx is installed into that environment on first use if missing. LibreOffice is optional.
The converter is `pro_presentation/pptx_builder.py` (reads `layout.json`); it can be swapped without touching the rest,
because verification compares the result the same way.
