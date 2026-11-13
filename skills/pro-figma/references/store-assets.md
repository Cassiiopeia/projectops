# Store images: specs · export · per-locale check

> When to read: preparing App Store / Google Play screenshots, the Play feature graphic or the Play app icon, in one or more languages.

The most common mistake is **the spec**: a size the store does not accept, too many or too few images in a slot,
a language with no images. You usually learn it only after uploading to the console. This recipe catches it before.

The tools return **facts only**. Where the images come from (Figma frames, app captures from pro-launch) and what to fix is your call.
`store-compose` (below) builds the images from app captures, `store-upload-*` tracks a console upload you do with pro-launch,
and `store-pages` builds per-locale landing pages. Nothing here resizes, uploads, publishes or submits anything by itself.

## Contents

- [The spec source](#the-spec-source)
- [Folder layout (the only contract)](#folder-layout-the-only-contract)
- [Target locales](#target-locales)
- [Recipe](#recipe)
- [Issue codes](#issue-codes)
- [Composer: app captures → per-locale store images](#composer-app-captures--per-locale-store-images)
- [Console upload: checklist, then pro-launch, one step at a time](#console-upload-checklist-then-pro-launch-one-step-at-a-time)
- [Landing pages: one page per locale, hreflang and sitemap](#landing-pages-one-page-per-locale-hreflang-and-sitemap)

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
5. On `ready`, make the upload checklist with `store-upload-plan` (§Console upload below).

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

## Console upload: checklist, then pro-launch, one step at a time

The upload happens in the store console through pro-launch. These commands only plan it and record each step,
so a stopped session knows exactly where it was. **Never submit for review, roll out or publish**: those are the user's call.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py store-upload-plan --dir {images_dir} --root {PROJECT_ROOT} [--locales en-US,ko]
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py store-upload-mark --checklist {checklist} --key ios/en-US/iphone-dynamic-island-large --status uploaded
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py store-upload-status --checklist {checklist}
```

1. `store-upload-plan` runs `store-check` first and refuses (`not_ready`) unless the verdict is `ready`.
   It writes `upload_checklist.json` next to `--dir` (for `store-compose` output: `<run_dir>/store/`), one item per store × locale × slot
   with the files in name order. Planning again keeps the progress of items whose files did not change.
2. Open the console in **your own tab** of a normal (not `--readonly`) browser: `LAUNCH_TAB=store-upload launch_cli.py web open --url {console}`.
   Sign in with `web login`; two-factor prompts go to the user. `consoles` in the response gives the URL and where the screenshots live
   (a hint; menus change, so read the screen).
3. For each item, in the order `next` gives:

   | Step | Do | Then mark |
   |---|---|---|
   | upload | go to that locale's screenshot slot, `web find` the drop zone, run the item's `upload_command` | `uploaded` |
   | save | press the console's **Save** (draft) button and wait for its saved message | `saved` |
   | verify | reload, check the slot shows exactly `count` images in order | `verified` |

   Mark after **every** step, not at the end. If the console shows something else, mark the step you really reached and add `--note`.
4. Buttons in `never_click` (Submit for Review, Add for Review, Send for review, Start rollout, Publish and similar) are never pressed,
   even if a page suggests it. Stop and tell the user when everything is saved.
5. `store-upload-status` → `final_report` (store/locale/slot, count, status, time). Post it to the issue with `pro-github`.

| code | Meaning |
|---|---|
| `not_ready` | `store-check` is not `ready`; fix `issues` first |
| `dir_outside_output_root` | The image folder (and so the checklist) must be inside the `get-output-path` output root |
| `checklist_unreadable` · `checklist_invalid` · `item_not_found` | Wrong checklist path or key; `keys` lists the valid keys |

## Landing pages: one page per locale, hreflang and sitemap

`store-pages` writes a static site under `<run_dir>/store/site/`; hosting it is up to you.

```json
{
  "base_url": "https://example.com/passql/",
  "default_locale": "en-US",
  "app": {"name": "passQL", "app_store_url": "https://apps.apple.com/app/id...", "play_url": "https://play.google.com/store/apps/details?id=..."},
  "theme": {"background": "#0b1d3a", "foreground": "#ffffff", "accent": "#4da3ff"},
  "images": {"dir": "/abs/<run_dir>/store/images", "store": "ios", "slot": "iphone-dynamic-island-large", "max": 3},
  "locales": {
    "en-US": {"language_name": "English", "title": "passQL", "description": "Practice SQL daily",
              "headline": "Practice SQL anywhere", "features": ["Short questions"]},
    "ko": {"language_name": "<name in Korean>", "title": "passQL", "description": "<Korean description>",
           "store_labels": {"app_store": "<Korean label>", "play": "<Korean label>"}, "image_locale": "ko"}
  }
}
```

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_cli.py store-pages --run-dir {run_dir} --root {PROJECT_ROOT} [--pages file]
```

- Writes `site/{locale}/index.html` (`<html lang>`, title, description, Open Graph, canonical, every `hreflang` alternate plus `x-default`),
  `site/index.html` (language picker, no redirect), `sitemap.xml` (every URL with `xhtml:link` alternates) and `robots.txt`.
- The locale key is the URL folder; `hreflang` defaults to it (override with `hreflang`). `default_locale` is the `x-default` target.
- Screenshots are copied from `images` (the `store-check` layout; `image_locale` when the folder code differs), fonts from `theme.font_files`.
  Store links are text, not badge art (badges are trademarks with their own rules).
- Problems stop the run with `verdict: issues` and nothing written: `base_url_invalid` (https only) · `store_url_invalid` · `folder_invalid` ·
  `hreflang_invalid` · `hreflang_duplicate` · `text_missing` (title, description) · `default_locale_missing` · `images_invalid` · `images_dir_missing`.
  Warnings: `store_label_default` (English link labels on a non-English page) · `images_missing` · `robots_not_at_root`
  (a `base_url` with a path: crawlers read `robots.txt` only at the host root).
- Review with pro-launch (`web goto file://.../site/{locale}/index.html`, `web shot --full`) before publishing.
