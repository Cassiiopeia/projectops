---
layout: home

hero:
  name: Projectops
  text: From issue to deploy, automated
  image:
    src: /images/hero-card-en.webp
    alt: npx projectops --mode doctor output
  tagline: GitHub Actions handle versions, changelogs and CI/CD; Agent Skills handle issues, commits and reports.
  actions:
    - theme: brand
      text: Getting started
      link: /en/getting-started
    - theme: alt
      text: CLI reference
      link: /en/cli
    - theme: alt
      text: GitHub
      link: https://github.com/Cassiiopeia/projectops

features:
  - title: Issue to deploy
    details: From issue creation to release PR, auto-merge and deployment in one flow.
  - title: Versions and changelog
    details: Commit titles decide major/minor/patch, and release notes are generated automatically.
  - title: Agent Skills
    details: /pro-* Skills for Claude Code, Cursor, Gemini CLI and Codex CLI.
  - title: npx wizard
    details: Integrate or update the workflows in an existing project with npx projectops.
  - title: PR Preview
    details: Deploy a temporary server from a PR comment; it is cleaned up when the PR closes.
  - title: SSH + Docker deployment
    details: Deploy Docker containers to any server reachable over SSH, including zero-downtime options.
---

## What it looks like

Run `npx projectops` in your project folder. This is a **real run** on a sample Spring project (the wizard UI itself is currently Korean).

![npx projectops interactive wizard](../images/cli-wizard.gif)

This repository is operated with the same tool, from issue to release.

![Real screens from issue to release](../images/demo/demo.gif)
