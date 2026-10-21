# Image attachments (issue body · comments · PR body)

> When to read: when putting screenshots or evidence images into an issue, comment or PR.

Commands have the form `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py ...` (SKILL.md "Find the scripts").

Attach screens to test results that used to be text only. GitHub's official attachment upload **needs a browser session, so it cannot be used with a PAT.** Instead, upload the images as assets to an evidence-only release (`qa-evidence`) and put those URLs in the markdown. Measured in practice: they render as `<img>` in both issue bodies and comments.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py upload-image {owner} {repo} {files...} --prefix issue585
# --tag {tag} : evidence release tag (default qa-evidence)
```

One release holds up to 1000 assets. When it is full, uploads continue automatically to the next release, `qa-evidence-2`, `-3` and so on (created if missing). The tag actually used is in `tag` and `images[].tag` of the response. When all 20 are full you get `code: release_asset_limit` and a `next` (delete old evidence or use a new `--tag`).

**Paste the `markdown` field of the output JSON into the body file as is.** You can upload several images at once.

```json
{"count": 2, "markdown": "![step1](https://...)\n![step2](https://...)", "tag": "qa-evidence",
 "images": [{"name": "...", "url": "...", "asset_id": 123, "renderable": true, "tag": "qa-evidence"}],
 "private_warning": null}
```

If you upload only one image, its address is also in the top-level `url` (`--field url`).

**Order**: get the URLs with `upload-image` → put that markdown into the body `.md` file → post with `create-issue` / `add-comment` / `update-pr`. If you reverse the order, the body goes up without images first.

| Know this | Details |
|---|---|
| **Private repos** | Anonymous access is blocked, so images **do not render.** `private_warning` tells you in advance |
| Formats that render | `.png` `.jpg` `.gif` `.webp` `.svg`; others (mp4 etc.) stay as links only |
| File names | Non-ASCII characters and spaces break in URLs, so names are converted to alphanumerics automatically and a timestamp makes them unique |
| Undo | `delete-image {owner} {repo} {asset_id}`, for cleaning up uploads made for verification |

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py delete-image {owner} {repo} {asset_id}
```

> Do not commit images to the repo. They stay in git history forever and make the repo heavy.
