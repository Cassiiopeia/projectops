---
name: pro-image
description: "Make image assets (backgrounds, characters, icons, illustrations, items) that fit the project's own style: you write the prompt from a per-repo harness, Codex or Antigravity draws it, the CLI fixes size and transparency. Use for 'make an image', 'draw', 'generate an icon'."
---

# Image: assets that look like this project

## When to use

- "Make a background / character / icon / illustration / item for this screen", "draw it", "regenerate the art",
  "several expressions of this character", in any language
- "What style fits this project?", "show me a few styles"
- Use it on your own whenever a task needs a new raster image (an empty state, a store graphic, a game scene).
  Do not draw such images with SVG or code unless every provider failed.

| Situation | Skill |
|---|---|
| A new image asset | **this one** |
| Screen layout mockups to compare in the browser | `pro-ui-design` (it can place images made here) |
| Moving a Figma design into code | `pro-figma` |

Talk to the user in their language. Apply the absolute rules in `../references/common-rules.md`.

**You write the brief and the prompt and judge every result. The CLI only runs the image tool, collects the file,
fixes format, size and transparency, and records history.**

## What the user sees

The user should see a short line while it works ("making 2 background candidates, about 3 minutes") and then the
finished image. Do not narrate background removal, resizing, retries or prompt edits; do not show raw or failed
images. If something cannot be met (a tool is missing, the same requirement failed twice), say it in one line
with the best result.

## Goal → command

Every command is `PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py image <command>`
(Windows: `python`). Output is always JSON with `ok`, `code`, `summary`, `next`.

| Goal | Command | Details |
|---|---|---|
| Which tools are ready, in what order | `providers` | `references/providers.md` |
| This repo's art memory (style, characters, references) | `harness [--init] [--character <id> ...]` | `references/harness.md` |
| The guide for a kind of image + its approved prompts | `kind <background\|character-sheet\|sprite\|icon\|illustration\|item\|...>` | `references/kinds/` |
| Generate one image, finished to spec | `run --name <stem> --prompt <file> --size WxH [--alpha] [--ref <img> ...] [--provider <name>] [--kind <kind>]` | below |
| Several candidates side by side, numbered | `board <img> ... --out <png>` | `references/style-explore.md` |
| Remove a background from any image | `remove-bg <img> --out <png> [--key-color "#00FF00"] [--mode flood\|global]` | |
| Fit an image to a size | `fit <img> --out <png> --size WxH [--mode cover\|contain]` | |
| Check size and transparency | `check <img> [--size WxH] [--alpha]` | |
| Record the user's decision · read past ones | `record --name <stem> --status approved\|rejected [--placed-at <path>] [--note "..."]` · `history` | |

## Quick path

A one-off picture ("just make me a cat image", a throwaway test, no app placement): skip the harness and style
explore. Write a short English prompt with size and background, `run`, Read the result, show it. Ask nothing unless
the size or the background is truly unknown. Use the full flow below when the image goes into an app.

## Flow

1. **Tools.** `providers`. On `ask_priority`, ask the user once which ready tools to use and in what order, and save
   `image.priority` (`references/providers.md`). Default order: codex > antigravity > claude-vector.
2. **Harness.** `harness`. On `no_style`: if the app already has art, `--init` and fill `STYLE.md` from it; if not,
   or the user wants to see options, run the style explore (`references/style-explore.md`) and let them pick.
3. **Brief.** Read the screen that will use the image, then write the numbered brief: purpose and placement, final
   size, background (opaque or `--alpha`), style anchor, subject, composition and empty zones, light, consistency
   anchors, must-nots (`references/prompting.md` §1). Ask the user only what the code cannot tell you.
4. **Prompt.** `kind <kind>`, then write the prompt in English in the order of `references/prompting.md` §2, reusing
   what worked in `approved_examples`. Save it to a file in your scratch folder.
5. **Run.** `run ...` in the background (each run takes 1-5 minutes; run several one after another, not at once).
   The CLI appends the output rules, converts to PNG, removes a fake or keyed background, fits the size and checks it.
6. **Judge.** Open `image.path` (the `.final.png`) with Read and check every brief line. `problems` lists spec
   failures. A transparent image can look like it has a dark glow when read directly; judge it on
   `board <img> --out <png>` (gray backdrop) instead. Retry a failed content line once with that line stronger; on provider failures follow `next`.
7. **Show.** Show only the finished image (or one `board` for several). Ask for approval with your agent's choice prompt (AskUserQuestion in Claude Code; a numbered list elsewhere) when
   there is a choice. If a `pro-ui-design` session is open, place the candidates there instead.
8. **Place and remember.** Convert to the app's format and put it where the brief said; `record --status approved
   --placed-at <path>`. Turn any lasting feedback into a line in `STYLE.md` or `characters/<id>.md`.

## Codes

| `code` | Meaning | Do |
|---|---|---|
| `ok` | Finished and matches size and transparency | Judge the content yourself |
| `spec_mismatch` | Finished but `problems` lists a size or alpha miss | Fix with `fit` / `remove-bg`, or run again |
| `ask_priority` | No saved tool order | Ask once, save `image.priority` |
| `no_style` | No `STYLE.md` in this repo | Fill it or run the style explore |
| `not_subscription` | Codex is signed in with an API key | Ask the user to `codex login` with ChatGPT, or use the next tool |
| `provider_missing` · `image_unavailable` · `timeout` · `no_image` | The tool could not deliver | Next provider in priority (`references/providers.md`) |
| `quota_exhausted` | The tool's image quota is used up (`quota.reset_in`) | Follow `next`: short wait → retry once, long → next provider now, and tell the user when it resets |
| `agent_draws` | The chosen provider is claude-vector | Draw SVG yourself, render it, `check` |
| `postprocess_failed` | Conversion or resizing failed | `raw_image` is kept; install Pillow (`pip install pillow`) or ImageMagick |

## Shared references

| Document | Read when |
|---|---|
| `../references/common-rules.md` | Always, at start: absolute rules, confirmation gates, issue state, push |
| `../references/agent-conduct.md` | When a tool is missing or you are about to say it cannot be done |
| `../references/config-rules.md` | When reading or writing `~/.projectops/config/config.json` |

## Customize

Your own language, tone and rules apply: see `../references/preferences.md`. Read them once at the start with `SKILL_ID=pro-image`.
Keys for this skill: the common `language`, `tone`, `rules` only. Behavior is under `config` (`image` section: priority, providers,
harness_dir, require_subscription); project art memory is the repo harness (`references/harness.md`).
Preferences change presentation only; approval gates and secret protection stay in force.

## Never

- Never use an API-key login for Codex unless the user set `image.require_subscription: false`.
- Never commit candidates. They stay in `~/.projectops/image/<owner__repo>/runs/`; only the approved, converted
  file goes into the app, and only small approved references go into `docs/image-harness/refs/`.
- Never put text, logos or brand marks of real companies into generated images.
- Never use art the project does not own as a reference (another game's characters, a stock photo). References
  shape the output; use the app's own approved art.
- Generated images follow the drawing tool's terms (OpenAI for Codex, Google for Antigravity). When the asset is for
  a commercial release, tell the user once which tool made it so they can check those terms.
- Never replace an approved asset without showing the new one first.
