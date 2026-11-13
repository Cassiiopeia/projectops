# Getting started

## What to run for each goal

| You want to | Run |
|--------------|-----------|
| Start a new project | Click **Use this template** on GitHub (initialized automatically within a minute) |
| Integrate into an existing project | `npx projectops` |
| Install Agent Skills only | `npx projectops --mode skills` |
| Diagnose the integration state and repository settings | `npx projectops --mode doctor` (read-only) |

Requires Node.js 20.12 or later. Non-interactive example: `npx projectops --mode full --type spring,react --force`

For all options, see `npx projectops --help`. For how the wizard behaves, see the [NPX wizard guide](./npx-wizard.md).

## Minimum setup

Workflows run with the built-in `GITHUB_TOKEN`. **A personal access token (PAT) is optional.** Add one as the repository secret `_GITHUB_PAT_TOKEN` only when you need one of these features:

| Feature you need | Why the built-in token is not enough | Classic token scopes |
|---|---|---|
| Release PRs merge even when branch protection blocks the Actions bot | The release workflow retries the merge with `--admin`, which needs an admin's token | `repo`, `workflow` |
| Issue labels synced to a GitHub Projects board | `GITHUB_TOKEN` cannot use the Projects API | `repo`, `project` |
| In a private repository, the issue helper comment starts other workflows | Events created with `GITHUB_TOKEN` do not start other workflows | `repo` |

Without a token, workflows that should run after a release merge are started with an explicit dispatch, so you do not need a token for that.

A fine-grained token with **Contents**, **Pull requests**, **Issues** and **Workflows** set to *Read and write* should be enough for the first feature. We have not verified this end to end yet, and Projects sync has only been tested with a classic token. If it fails, please let us know in an issue.

```
Repository Settings → Secrets → Actions → New repository secret
Name: _GITHUB_PAT_TOKEN
```

For an organization repository, also check the following.

```
Settings → Actions → General
├─ Allow GitHub Actions to create and approve pull requests
└─ Read and write permissions
```

## From install to your first release

A short walk through the whole cycle. Each step links to the page with the details.

**1. Check the requirements.** Node.js 20.12 or later and Git. Python 3 is needed only for Agent Skills.

**2. Install.** Run this in the root of your repository and answer the questions.

```bash
npx projectops
```

**3. Look at the new files.** You get `version.yml`, workflows in `.github/workflows/PROJECT-*.yaml`,
helper files in `.github/scripts/`, `.github/config/` and `.github/util/`, issue and PR templates,
and `.github/.projectops/` (install record). Commit them. See [CLI reference](./cli.md).

**4. Check the install.** This only reads. It lists missing secrets and values that still need to be filled in.

```bash
npx projectops --mode doctor
```

**5. Create the development branch.** Work collects on `develop`. Releases go from `develop` to `main`.

```bash
git checkout -b develop && git push -u origin develop
```

**6. Open an issue.** A bot comments with a branch name and a commit message for that issue.
See [Issue automation](./issue-automation.md).

**7. Commit.** Use the suggested message: `issue title : type : what changed https://.../issues/N`.
The type decides the next version:

| Commit type | Next version |
|---|---|
| `feat!` (breaking change) | major: 1.4.2 > 2.0.0 |
| `feat` | minor: 1.4.2 > 1.5.0 |
| anything else (`fix`, `docs`, `chore` ...) | patch: 1.4.2 > 1.4.3 |

The highest one in the release wins. See [Version control](./version-control.md).

**8. Push `develop`.** Merge your issue branches into `develop` and push it. Pushing does not release anything.

**9. Open the release PR from `develop` to `main`.** Open it yourself or with the `/pro-changelog-deploy` skill.
The workflow then writes release notes, sets the version, updates `CHANGELOG.md` and `CHANGELOG.json`,
merges the PR and tags the release. Deploy workflows run on `main`.
See [Changelog automation](./changelog-automation.md).

## If you only want Agent Skills

```bash
# Claude Code
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user

# Gemini CLI
gemini extensions install https://github.com/Cassiiopeia/projectops

# Full install menu for Cursor and others
npx projectops --mode skills
```

Install methods per tool and the list of Skills are in the [Agent Skills guide](./skills.md).

## FAQ

**Does it replace my existing workflows?**
No. A workflow you changed is kept. The new template is saved in `.github/.projectops/incoming/` so you can compare.

**Do I need an AI key?**
No. Release notes fall back to commit analysis. It needs no key and no network.

**I pushed `develop` but no release happened.**
That is expected. A release starts only when a `develop` → `main` PR is opened.

**The release PR was not merged automatically.**
Turn on "Allow auto-merge" in the repository settings and check branch protection.
See [Troubleshooting](./troubleshooting.md).

**Can I try it without changing anything?**
Yes. `npx projectops --mode options` and `npx projectops --mode doctor` only read.
More questions: [Compared with other release tools](./compare.md).

## What to read next

- [CLI reference](./cli.md): every mode and option of `npx projectops`
- [Version control](./version-control.md): `version.yml` and automatic version bumps
- [Changelog automation](./changelog-automation.md): the release PR flow
- [Issue automation](./issue-automation.md): branch name and commit message guidance
- [Troubleshooting](./troubleshooting.md)
