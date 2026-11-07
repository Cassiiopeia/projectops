# Sharing: capture a mockup and post it

> When to read: the user wants the mockup on an issue, or cannot open localhost.

`capture` opens the mockup without the viewer toolbar. Files go to `{run_dir}/captures/`, which Git ignores.

```bash
capture --screen layout.html                    # the whole page
capture --screen layout.html --option b         # one .ui-option card
capture --screen layout.html --all-options      # one PNG per card
capture --screen layout.html --theme dark --device tablet
# add --title "<screen>" when this repo has several sessions
capture --gif --screen sheet.html --steps steps.json [--max-width 900] [--max-frames 120]
```

## GIF: for anything that moves

A still image does not show motion or a linked flow. The GIF runs your steps in a real browser and keeps real timing. It records `.ui-screens` or `.ui-options`, so linked screens are filmed together.

```json
[
  {"action": "wait", "ms": 500},
  {"action": "click", "selector": "#send", "ms": 900},
  {"action": "press", "selector": "#tile", "ms": 600},
  {"action": "drag", "selector": "#tile", "dx": 60, "dy": 30, "ms": 300},
  {"action": "play", "option": "b", "ms": 900},
  {"action": "play-all", "ms": 1600},
  {"action": "reset", "ms": 300}
]
```

`ms` is how long to keep filming after the action. Selectors run inside the mockup. Keep it short: one flow per GIF. Over 10 MB gives a warning; lower `--max-width` or cut steps.

Open PNGs with Read before you post. GIFs show only their first frame in Read, so also check the steps ran (`frames`, no `step_failed`). Measured: a GIF uploaded this way does animate in an issue on a public repo.

## Post to an issue

Needs a GitHub repo. **Approval first** (`../../references/approval-and-questions.md`): show what you will post and where. Then:

```bash
PYTHONIOENCODING=utf-8 python3 ~/.projectops/bin/projectops_cli.py github upload-image {owner} {repo} <files...> --prefix mockup
```

Put the returned `markdown` in a comment file with one line per option: name, what differs, and whether it is an HTML mockup or a real render. Post with `add-comment` (or `create-issue`). Then `decide --comment-url <url>` once there is a decision. If `private_warning` comes back, images may not show for readers; tell the user.

## The user cannot open localhost

Remote Control and similar sessions see no local URL.

1. `capture` the page, with `--all-options` if there are cards.
2. Open each image with Read so it appears in the conversation. Say what differs.
3. For motion, describe it in one line and offer the GIF on an issue.
4. Offer to post. The reply can be a plain "B".
