---
layout: home

hero:
  name: Projectops
  text: From issue to deploy, automated
  tagline: GitHub Actions handle versions, changelogs and deployment; Agent Skills handle issues, commits and reports.
  image:
    src: /images/hero-card-en.webp
    alt: npx projectops --mode doctor output
  actions:
    - theme: brand
      text: Getting started
      link: /getting-started
    - theme: alt
      text: CLI reference
      link: /cli
    - theme: alt
      text: GitHub
      link: https://github.com/Cassiiopeia/projectops

features:
  - title: Issue to deploy
    details: From opening an issue to the release PR, auto-merge and deployment, everything runs as one flow.
    link: /issue-automation
  - title: Versions and changelog
    details: Commit titles decide major/minor/patch, and release notes are generated automatically. It finishes even without an AI key.
    link: /version-control
  - title: Agent Skills
    details: /pro-* Skills for Claude Code, Cursor, Gemini CLI and Codex CLI create issues, commits and reports.
    link: /skills
  - title: npx wizard
    details: Integrate and update the workflows in an existing project with a single npx projectops command.
    link: /npx-wizard
  - title: PR Preview
    details: Deploy a temporary server with a one-line comment; it is cleaned up automatically when the PR closes.
    link: /pr-preview
  - title: SSH + Docker deployment
    details: Docker deployment to any server reachable over SSH, including Traefik/Nginx zero-downtime deployment.
    link: /ssh-docker-deployment-guide
---

## What it looks like

Run `npx projectops` in your project folder. This is a **real run** on a sample Spring project.

![npx projectops interactive wizard](../images/cli-wizard.gif)

### 1. Open an issue and a branch name and commit message arrive automatically

![Automatic guide comment after opening an issue](../images/feature-issue.gif)

When an issue is opened, GitHub Actions runs on its own and comments a **branch name and a commit message template**. Work on that branch name and the issue number links into your commits and reports automatically.

### 2. Open a PR and a change summary arrives automatically

![Change summary comment after opening a PR](../images/feature-pr-summary.gif)

Open a PR from a work branch and a **change summary** built from the commits is posted as a comment. Push more commits and the same comment is updated instead of piling up new ones.

### 3. Open a release PR and everything from versioning to merge and tag is automatic

![Release PR merging automatically and a tag appearing](../images/feature-release.gif)

Open a PR from the development branch to `main` and it writes the release notes, decides the version from commit titles (`feat`, `fix`, ...) and puts it in the PR title, merges automatically, and creates the **version tag**. This example had `feat` commits, so the minor version went up.

> The warning banner GitHub shows for Korean branch names is hidden in the recording. Everything else is the unedited screen.
