# Exporting and verifying

`export --deck D [--pdf] [--pptx] [--converter auto|builtin|dom-to-pptx]` (no format flag = the `export_formats` setting) writes the next `exports/v<n>/`.
It never overwrites: a PPT open in PowerPoint is never in the way, and versions can be compared.

## Two PPT converters

| Converter | How | Good at | Weak at |
|---|---|---|---|
| `builtin` | measured `data-pp` pieces → python-pptx | plain themed slides, imported picture decks (embeds the original files), no download | gradients, shadows, mixed bold or colour inside one paragraph, table styles, numbered lists, rounded pictures all fall back to plain; parts without `data-pp` become pictures |
| `dom-to-pptx` | the slide DOM converted inside the browser ([dom-to-pptx](https://github.com/atharva9167j/dom-to-pptx), MIT) | the styles above, and parts without `data-pp` stay editable | pictures go in at display size (up to 2560 px wide); heavy on decks of many huge pictures |

`auto` (the default, setting `pptx_converter`) uses `dom-to-pptx` only when a slide has a style the built-in converter cannot map, else `builtin`.
The result and `verify.json` name the converter and list those styles per slide in `unmapped_styles`.
The dom-to-pptx bundle is not shipped: the first export that needs it downloads the pinned version (hash checked) into `~/.projectops/presentation/vendor/`.
If that fails (no network), `auto` falls back to `builtin` and sets `converter_fallback`: tell the user which slides in `unmapped_styles` will look plainer.

## What a run makes

| File | What |
|---|---|
| `slide-NN.png` | each slide rendered from HTML at 1920 x 1080 |
| `<title>.pdf` | the PNGs as pages |
| `<title>.pptx` | editable PPT: text boxes, shapes, pictures, tables; the script goes into speaker notes |
| `layout.json` | the measured `data-pp` pieces (position, font, colour, text) and `unmapped` styles per slide; the built-in converter builds from it, and the text check uses it for both converters |
| `verify.json` | the checks below |
| `render-back/` | the PPT drawn again by LibreOffice (only when it is installed) |

## Verify before you say "done"

Read `verify.json`, then look at a few slide PNGs and, if present, the matching `render-back` images.

| Field | Meaning | If not clean |
|---|---|---|
| `text_match` per slide | every text line of the HTML is in the PPT | read `missing_text`; usually a piece without `data-pp` or text inside an image |
| `converter`, `converter_fallback` | which converter made the PPT, and why `auto` could not use dom-to-pptx | on a fallback, name the slides in `unmapped_styles` to the user |
| `picture_parts` | elements without `data-pp` that went in as pictures (built-in converter only) | add `data-pp` (building.md) or accept it and tell the user which slide |
| `missing_images` | an image piece whose file is not in the deck | put the file next to `slide.html` |
| `missing_fonts` | fonts used but not found on this computer | the PPT falls back to another font on machines without it; tell the user, or switch `theme.css` to a common font |
| `render_back` | `done`, `failed`, or `skipped_no_libreoffice` | when skipped, say the visual comparison was not run |

Report to the user: the version (`v3`), the files, and any slide that is not clean, by number.

## Tools

The browser step runs in the pro-launch environment (Playwright). Missing: `launch_cli.py web setup`.
python-pptx is installed into that environment on first use if missing. LibreOffice is optional.
The converters are `pro_presentation/pptx_builder.py` (built-in) and `pro_presentation/dom_to_pptx.py`; verification compares both results the same way.
