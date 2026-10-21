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
