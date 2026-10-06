# Contributing to projectops

Thanks for helping out. This guide is short on purpose: it covers what you need to get a change from idea to merged PR.
A Korean version is in [docs/i18n/CONTRIBUTING.ko.md](docs/i18n/CONTRIBUTING.ko.md).

## What this project is

projectops is a template and installer (`npx projectops`) that adds GitHub Actions workflows, version management,
issue/PR templates and agent skills to a repository. If you want to understand how it fits together, start with
[docs/NPX-WIZARD.md](docs/NPX-WIZARD.md) and [docs/SKILLS.md](docs/SKILLS.md).

## Ways to contribute

- **Report a bug or request a feature**: open an issue. Use the issue forms and include your projectops version,
  OS, and the run log (see below) for installer problems.
- **Ask a question**: use [Discussions](https://github.com/Cassiiopeia/projectops/discussions) rather than an issue.
- **Fix something small**: look for issues labeled `good first issue` or `help wanted`.
- **Anything bigger** (new project type, new workflow, behavior change): open an issue first and wait for a maintainer
  to confirm the direction before you write code.

## Set up

You need Node.js 20.12 or newer, Python 3.12 (for the script and skill tests) and Git.

```bash
git clone https://github.com/<you>/projectops.git
cd projectops
git remote add upstream https://github.com/Cassiiopeia/projectops.git
python3 -m pip install pytest pyyaml pillow numpy
```

The project has no runtime npm dependencies, so there is nothing else to install.

## Run the tests

```bash
npm test                                   # installer (Node)
python3 -m pytest .github/scripts/test/ -q # workflow scripts
python3 -m pytest skills/ -q               # skill scripts
python3 -m pytest scripts/tests/ -q        # shared skill code
python3 .github/util/flutter/_shared/check-consistency.py   # only if you touched a Flutter wizard
```

CI runs the same commands on Linux, macOS and Windows. The installer must keep working on macOS
(bash 3.2, BSD tools) and Windows, so please do not use Linux-only shell features in `.sh` files.

To try the installer on a scratch project:

```bash
mkdir /tmp/try && cd /tmp/try && git init
node /path/to/projectops/bin/projectops.js --lang en
```

## Branches and commits

- Work on a branch named `YYYYMMDD_#<issue number>_<short title>` (the issue helper bot posts the exact name in your issue).
- `develop` collects finished work. `main` is the release branch and is only updated by release PRs.
- Open your PR against `develop`.
- Commit message format: `<issue title> : <type> : <what changed> <issue URL>`
  - `type` is one of `feat`, `fix`, `docs`, `chore`, `refactor`, `test`.
  - `feat` makes the next release a minor version, `feat!` a major one, everything else a patch.
    Use `!` only when existing users' settings or CLI arguments stop working.

## Releases

- Releases are batched: at most one release PR (`develop` to `main`) per day, plus an extra one only for a fix users are waiting on.
- Release PRs are titled `🚀 Deploy <date>-v<version>`. To hide them in the PR list, filter with `is:pr -head:develop`.
- This project is actively maintained. Pull requests are reviewed by the code owners listed in `.github/CODEOWNERS`.

## Pull requests

Before you open a PR:

- [ ] There is an issue that describes the change, and the PR links to it.
- [ ] Tests pass locally, and you added a test for new behavior or a fixed bug.
- [ ] User-facing text is in English and goes through `src/i18n/` (CLI) or the English-first docs. Korean goes in the `ko` catalog.
- [ ] If you changed a shared workflow, you changed both copies: `.github/workflows/` and `.github/workflows/project-types/common/`.
- [ ] Workflows declare `permissions:`, and new ones have `workflow_dispatch` and `concurrency`.

## Code conventions

- **Installer (`src/`)**: ES modules, standard library only. Prompts go through `src/ui/`, messages through `src/i18n/`.
  Comments explain why, not what.
- **Scripts and skills (Python)**: standard library first. A skill CLI prints JSON and takes its input from arguments or
  environment variables, never from heredocs or temporary files.
- **Workflows**: do not rename or delete a shipped workflow without registering it in `src/core/migrations/registry.js`,
  otherwise existing installs keep the old file.
- Files that only make sense in this repository must be excluded from user installs in both
  `src/core/exclusions.js` and `.github/scripts/template_initializer.py`.

## AI-assisted contributions

AI tools are welcome. You are responsible for what you submit:

- Read and understand every line before you open the PR, and run the tests yourself.
- Say so in the PR description if an agent wrote a significant part of the change.
- Keep PRs focused. Large generated refactors without a prior issue will be closed.

## Reporting problems with the installer

Every `full` and `workflows` run writes a log to `.github/.projectops/logs/` (not tracked by git).
Attach the `.log` file to your issue, after removing anything private.

## Security

Please do not open public issues for vulnerabilities. See [SECURITY.md](SECURITY.md).

## License

By contributing you agree that your contributions are licensed under the [MIT License](LICENSE).
