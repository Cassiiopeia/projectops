# Store images: specs · export · per-locale check

> When to read: preparing App Store / Google Play screenshots, the Play feature graphic or the Play app icon, in one or more languages.

The most common mistake is **the spec**: a size the store does not accept, too many or too few images in a slot,
a language with no images. You usually learn it only after uploading to the console. This recipe catches it before.

The tools return **facts only**. Where the images come from (Figma frames, app captures from pro-launch) and what to fix is your call.
`store-compose` (below) builds the images from app captures. Nothing here resizes, uploads or submits anything.

## The spec source

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py store-specs [--store ios|play]
```

Prints `figma_tools/store_specs.json` as is: slot ids, accepted sizes (`exact` list or `range` with side limits and aspect ratio),
`min_count`/`max_count`, formats, alpha rule, `requirement`, and `source_url` + `checked_at` for every value.
**Do not copy these numbers into docs or code.** Read them from this command each time.
When a store page changes, update the JSON with the new source date; never add a value without a source.

| `requirement` | Meaning |
|---|---|
| `required` | Every target locale needs it |
| `one_of` | Every target locale needs at least one slot of the `group` (iOS iPhone sizes fall back to each other's scaled screenshots) |
| `when_present` | Needed in every target locale only if the store folder has it somewhere (iPad: the tool does not guess whether the app supports iPad) |

Slots with `localized: false` (Play app icon) are checked once under `{store}/_global/{slot}/`.

## Folder layout (the only contract)

```
<dir>/ios/en-US/iphone-dynamic-island-large/01.png
<dir>/ios/ko/iphone-dynamic-island-large/01.png
<dir>/play/ko-KR/phone-screenshots/01.jpg
<dir>/play/ko-KR/feature-graphic/feature.png
<dir>/play/_global/app-icon/icon.png
```

- Locale folders use **the store's own code** (App Store `ko`, Play `ko-KR`). The tool does not convert codes;
  `ko` against target `ko-KR` is reported as `locale_code_mismatch`, not counted as a match.
- `.png`, `.jpg`, `.jpeg` are read (header only, no Pillow needed). Anything else, unknown stores or slots,
  and slots in the wrong place are listed in `unknown` (reported, not failed).
- Keep `<dir>` inside the evidence folder from `get-output-path`: exports are regenerated, not committed.

## Target locales

`--locales a,b` (applies to both stores) → `version.yml` `store_locales_ios` / `store_locales_play` → `store_locales` →
the locale folders found (`locales.<store>.source: "folder"`, no base locale). The first target is the **base locale**.
A missing slot in the base locale is an issue. In other locales it is an issue too unless the spec's `fallback_to_base` is `true`
(the official pages checked do not state a fallback, so it is `null` today).

## Recipe

1. Find the store frames in Figma (`mcp__figma__get_figma_data`, `depth: 2`). A frame name like `store/ios/iphone-dynamic-island-large/en-US/01` helps but is **not required**.
2. `store-specs` → compare each frame size × export scale with the accepted sizes of its slot.
3. `mcp__figma__download_figma_images` with `pngScale` chosen so the export hits an accepted size, `localPath` = the layout folder above.
   App captures work the same way: put them in the same layout.
4. `store-check --dir <dir>` → `verdict`:
   - `issues`: fix each entry in `issues` **at the source** (frame size, export scale, background without alpha) and export again. Do not resize exports.
   - `empty`: nothing to check; check the layout and slot ids.
   - `ready`: every image matches. Review `warnings` (recommended sizes or counts, untargeted folders, code mismatches).
5. On `ready`, write the upload checklist (store × locale × slot, count, file names) from `matrix` into the evidence folder.
   To share it with the team, post it as an issue comment with `pro-github`.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py store-check --dir {dir} --root {PROJECT_ROOT} [--locales en-US,ko]
```

## Issue codes

| code | Meaning |
|---|---|
| `size_not_allowed` · `side_out_of_range` · `aspect_ratio_too_large` | Pixel size outside the slot rule |
| `alpha_not_allowed` | PNG with an alpha channel or `tRNS` transparency where the store forbids it |
| `format_not_allowed` · `extension_mismatch` · `unreadable_image` | Wrong format, extension does not match content, not a PNG/JPEG |
| `file_too_large` | Over the slot's `max_bytes` |
| `too_few` · `too_many` | Image count outside `min_count`–`max_count` |
| `missing_slot` | A needed slot (or `group:<id>`) has no images in that locale |

## Composer: app captures → per-locale store images

Use it when the images are an app capture with a caption (and a device frame) or a text banner. Everything it writes goes under
`<run_dir>/store/` (`run_dir` from `get-output-path`); it never writes anywhere else. Nothing is committed (evidence folder).
It has no third-party device art: the frame is plain CSS.

1. `get-output-path --title <name>` → note `run_dir`. Take the app captures per locale with pro-launch (`app shot --keep-format`).
2. Write `<run_dir>/store/scenes.json`:

```json
{
  "theme": {"background": "#0b1d3a", "foreground": "#ffffff", "accent": "#4da3ff",
            "font_family": "sans-serif", "font_files": [{"family": "Noto Sans KR", "path": "/abs/NotoSansKR.otf"}]},
  "outputs": [
    {"store": "ios",  "slot": "iphone-dynamic-island-large", "size": [1320, 2868], "scenes": ["home", "search"]},
    {"store": "play", "slot": "feature-graphic", "scenes": ["feature"]}
  ],
  "scenes": [
    {"id": "home", "layout": "caption-top", "screenshot": "/abs/captures/{locale}/home.png",
     "text": {"en-US": {"title": "Practice SQL\nanywhere", "subtitle": "Short daily questions"},
              "ko": {"title": "<Korean headline>"}}},
    {"id": "feature", "layout": "banner", "icon": "/abs/icon.png", "text": {"en-US": {"title": "passQL"}}}
  ]
}
```

   - `layout`: `caption-top` · `caption-bottom` (portrait sizes, need `screenshot`; `{locale}` is replaced per locale) · `banner` (landscape, text only, optional `icon`).
   - `size` must match the slot's spec (`store-specs`); it may be left out only when the slot has exactly one accepted size.
   - Locale keys in `text` use **the store's own codes**, like the folders. Target locales: `--locales` → `version.yml` → the locales found in `text`.
   - `font_files` is how CJK text renders the same on every machine; without it the system font is used.
3. `store-compose --run-dir {run_dir} --root {PROJECT_ROOT} [--locales ...] [--store ios|play]` → `verdict` and `issues`
   (`slot_unknown` · `size_not_allowed` · `size_required` · `layout_size_mismatch` · `text_missing` · `screenshot_missing` ·
   `icon_missing` · `font_missing` · `theme_invalid` · `scene_unknown`). Fix `issues` in `scenes.json` and run again.
4. Render with pro-launch **in your own tab**; the command is in `next`:
   `LAUNCH_TAB=compose launch_cli.py web script --file {run_dir}/store/render.py`.
   Do not use `web shot` for this: it saves a shrunk WebP. The script saves exact-size PNGs without alpha.
   Read `result`: `text_overflow` lists the images whose caption does not fit (shorten the text), `failed` lists images that did not render.
5. `store-check --dir {run_dir}/store/images` → `ready` means the images match the specs.
   `app-icon` is not composed; put the icon in `play/_global/app-icon/` yourself.
   `stale_image` warnings list files in `images/` that this run did not produce; they still count in `store-check`.
