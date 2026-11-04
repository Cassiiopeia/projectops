---
title: Compared with release-please, semantic-release and changesets
description: How projectops compares with release-please, semantic-release and changesets, and when a smaller tool is the better choice.
---

# Compared with other release tools

projectops installs the whole cycle into a GitHub repository: issue, branch, release PR, version, changelog and deployment. If you only need one piece of that, a smaller tool may suit you better.

| | projectops | release-please | semantic-release | changesets |
|---|---|---|---|---|
| Version decided from | Commit titles (`feat` → minor, `feat!` → major) | Conventional Commits | Conventional Commits (configurable) | Changeset files written in each PR |
| Review step before a release | A release PR (develop → main), merged automatically | A release PR you merge | None by default, releases on push | A "Version Packages" PR |
| Changelog | Written in the release PR (commit analysis, or an AI summary) | Generated | Generated (plugin) | Assembled from changeset files |
| CI/CD workflows for your project type | Yes (Spring, Flutter, React, Python; npm publish for Node) | No | No | No |
| Agent skills that run the cycle | Yes | No | No | No |
| What it adds to your repository | About 60 files | A workflow and a config file | A config file and a CI step | A `.changeset/` folder and a CI step |

## Which one should you pick?

- **Only versioning and a changelog:** release-please or semantic-release is smaller.
- **npm packages from a monorepo, where each PR says what changed:** changesets fits better.
- **The whole cycle in one install, with agent skills on top:** that is what projectops is for.

## When projectops is not a fit

- You do not use GitHub. It relies on GitHub Actions, issues and PRs.
- You want the fewest possible files in your repository. A full install adds about 60 (measured on v4.84.0: 56 with `--type basic`, 60 with `--type spring`).
- You need to pin workflow templates to a version. `npx projectops@<version>` pins the installer only; templates come from the current `main`.

## Common questions

**Does it replace my existing workflows?**
No. A workflow you changed is kept, and the new template is saved next to it for comparison. See the [NPX wizard guide](./npx-wizard.md).

**Do I need an AI key?**
No. Release notes fall back to commit analysis, which needs no key and no network. A key only improves the summary. See [Changelog automation](./changelog-automation.md).

**Does it work on Windows, macOS and Linux?**
Yes. Every release runs an install on all three with Node 20 and 24, in a folder whose name has non-English characters and a space.

**Can I try it without changing anything?**
Run `npx projectops --mode options` to read every option. `npx projectops --mode doctor` only reads an existing install.

Next: [Getting started](./getting-started.md)
