# Demo GIF recording

The demo GIFs in `docs/images/` are recorded from real runs with the scripts in this folder. Re-record them when the CLI output or the GitHub comments change.

English is the default: `cli-wizard.gif` is English, `cli-wizard.ko.gif` is Korean. The English README, the ja and zh-CN READMEs and the English docs use the default files. The Korean README and the Korean docs use `*.ko.gif`.

Both recordings use the CLI and the templates **from this working tree**, not the published npm package, so a GIF recorded before a release already shows what that release prints.

## Terminal GIFs (`cli-wizard`, `cli-oneshot`)

Needs [vhs](https://github.com/charmbracelet/vhs) (`brew install vhs`), Node.js 20.12+ and rsync.

```bash
docs/recording/record_cli.sh en
docs/recording/record_cli.sh ko
```

The script builds a sample Spring project in a temporary folder and runs `npx projectops` (mapped to this working tree) with `PROJECTOPS_LANG` set, so the system language never leaks into the recording. The interactive wizard takes every default answer.

## GitHub GIFs (`feature-issue`, `feature-pr-summary`, `feature-release`)

Needs a GitHub token that can create and delete repositories in the `git-sandboxes` organization (`GITHUB_PAT`, or `github.global_pat` in `~/.projectops/config/config.json`), Node.js, ffmpeg and [uv](https://docs.astral.sh/uv/).

```bash
uv run --with playwright playwright install chromium   # once
cd docs/recording/github_demo
uv run --with playwright --with pillow python record_github.py --lang en
```

The script creates the public repository `git-sandboxes/pops-qa-demo-gif-<lang>`, installs projectops with `--language <lang>`, then really opens an issue, a work PR and a release PR. A logged-out browser captures the pages while the workflows run. Waiting is fast-forwarded, and the timer in the corner shows the real elapsed time. The repository is deleted at the end (`--keep-repo` keeps it).

## Mockup GIF (`feature-ui-design`)

Needs the browser that `pro-launch web setup` installs (Playwright and Pillow).

```bash
python3 docs/recording/ui_design_demo/record_ui_design.py --lang en
python3 docs/recording/ui_design_demo/record_ui_design.py --lang ko
```

It starts a `pro-ui-design` session from this working tree in a temporary git repo, writes `linked.html` with the text for that language, and records the steps with `capture --gif`. The GIF is then re-encoded with one palette shared by all frames, so unchanged areas are not rewritten every frame (about 0.7 MB instead of 5 MB). Nothing is published.

## README images (`readme-hero`, `readme-cycle`, `readme-features`, `readme-skills`)

The designed images on the README landing page are HTML pages in `readme_assets/` (one design system in `tokens.css`, text for each language at the bottom of each page). Needs the browser that `pro-launch web setup` installs.

```bash
python3 docs/recording/readme_assets/render_readme_assets.py              # all, en + ko, light + dark
python3 docs/recording/readme_assets/render_readme_assets.py --only cycle --lang en
```

Each page is rendered at 2x to `docs/images/readme-<name>.webp` (light), `readme-<name>-dark.webp` (dark) and `*.ko.webp` for Korean. READMEs pick light or dark with `<picture>` and `prefers-color-scheme`. The cycle image shows real records (issue #1155, release PR #1156, v4.102.0); change the facts in `cycle.html` and `hero.html` when you swap the example.
