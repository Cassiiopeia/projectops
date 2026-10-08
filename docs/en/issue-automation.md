# Issue automation

When an issue is created, the template suggests a branch name and commit message, and a comment can create a QA issue.

---

## Overview

| Feature | Trigger | Description |
|---------|---------|-------------|
| **Issue Helper** | Issue created | Suggests a branch name and commit message |
| **QA bot** | `@projectops create qa` comment | Creates a QA issue |
| **Label sync** | `issue-labels.yml` changed | Syncs GitHub labels |

---

## Issue Helper

When an issue is created, it posts a comment with a recommended branch name and commit message.

### How it works

```
1. An issue is created
2. The Issue Helper workflow runs
3. A branch name and commit message are built from the issue title
4. The guide is posted as a comment
```

### Example of the generated comment

```markdown
<!-- Guide by SUH-LAB (marker for old workflow versions, not visible on screen) -->

Guide by ProjectOps
---

### Branch
```
20260112_#145_add_login_feature
```

### Commit message
```
feat : add login feature https://github.com/user/repo/issues/145
```

### Command
```bash
git checkout -b 20260112_#145_add_login_feature
```
```

### Branch name rule

```
YYYYMMDD_#issue-number_issue-title-summary
```

- Date: the issue creation date
- Issue number: in the form `#145`
- Title: spaces become underscores, special characters are removed

### Workflow

**File**: `PROJECT-COMMON-SUH-ISSUE-HELPER.yaml` (logic: `.github/scripts/issue_helper.py`, built in since v4.3.0, no external action dependency)

```yaml
on:
  issues:
    types: [opened, edited]
```

**Customization**: `version.yml` → `metadata.template.options.issue_helper`
(branch_prefix / max_branch_length / timezone / commit_template / commit_type_map / comment_marker / guide_signature / show_guide. Defaults apply if the section is missing. The default `guide_signature` is `Guide by ProjectOps`.)

---

## QA bot

Write an `@projectops create qa` comment on an issue or PR and a QA issue is created.

### Usage

```
@projectops create qa
```

### How it works

```
1. Comment @projectops create qa on an issue or PR
2. The QA-ISSUE-CREATION-BOT workflow runs
3. A new issue is created from the QA issue template
4. A link comment is posted on the original issue or PR
```

### The generated QA issue

```markdown
## QA request

**Source**: #145 (link)
**Requested by**: @username

### Test items
- [ ] Feature test
- [ ] UI/UX test
- [ ] Edge case test

### Test environment
- [ ] Local
- [ ] Dev server
- [ ] Staging
```

### Workflow

**File**: `PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml`

```yaml
on:
  issue_comment:
    types: [created]
```

**Trigger conditions**:
- The comment contains `@projectops create qa`
- Both issues and PRs are supported

---

## Label sync

Editing `issue-labels.yml` syncs the GitHub labels automatically.

### Label file location

```
.github/config/issue-labels.yml
```

### Label file format

```yaml
- name: "priority: urgent"
  from_name: 긴급          # renaming the old Korean label keeps the issues that carry it
  color: "d73a4a"
  description: "Urgent work"

- name: "status: in progress"
  from_name: 작업중
  color: "74D7CB"
  description: "Work in progress"
```

### Label naming: English standard and Korean (`label_style`)

`metadata.template.options.label_style` in `version.yml` sets how label names are written.

| Value | Meaning | When |
|---|---|---|
| `en` | English standard (`status: todo`, etc.) | **Default for new installs** |
| `ko` | Existing Korean (`작업전`, etc.) | Repos that are already installed keep this if the key is missing |

To switch to English, run `npx projectops --label-style en` (the interactive update offers it once). The label sync workflow renames the Korean labels in place using `from_name`, so labels already attached to issues move over unchanged. Projects sync and the skills recognize both names.

### Built-in labels

| English standard | Existing Korean | Purpose |
|------|------|------|
| `priority: urgent` | 긴급 | Needs urgent handling |
| `documentation` | 문서 | Documentation |
| `status: todo` | 작업전 | Ready, work not started |
| `status: in progress` | 작업중 | Work in progress |
| `status: needs review` | 담당자확인 | Needs assignee confirmation, waiting |
| `status: feedback` | 피드백 | Needs changes after assignee review |
| `status: done` | 작업완료 | Work done |
| `status: on hold` | 보류 | Work paused |
| `status: cancelled` | 취소 | Work cancelled |

### Completed issues are closed when a release ships (`close_on_release`)

The label (`status: done` or `작업완료`) marks completion. Closing is done by the `PROJECT-COMMON-CLOSE-ISSUES-ON-RELEASE` workflow when the release is merged. It closes only issues whose URL is referenced by a commit in the release range and that carry a done label. It runs only when `version.yml` has `close_on_release: true`. **Only new installs have it on. Existing installs have no key, so it stays off.**

### Workflow

**File**: `PROJECT-COMMON-SYNC-ISSUE-LABELS.yaml`

```yaml
on:
  push:
    paths:
      - '.github/config/issue-labels.yml'
```

---

## Issue templates

Four issue templates are installed automatically.

| Template | File | Purpose |
|--------|------|------|
| Bug report | `bug_report.md` | Report a bug |
| Feature request | `feature_request.md` | Add or improve a feature |
| Design request | `design_request.md` | UI/UX design |
| QA request | `qa_request.md` | Request testing |

### Template location

```
.github/ISSUE_TEMPLATE/
├── bug_report.md
├── feature_request.md
├── design_request.md
├── qa_request.md
└── config.yml          # template chooser settings
```

---

## Troubleshooting

### No Issue Helper comment

**Check**:
1. The `PROJECT-COMMON-SUH-ISSUE-HELPER.yaml` workflow and `.github/scripts/issue_helper.py` exist
2. The workflow is enabled in the Actions tab
3. If a private repo needs chained triggers, set the `_GITHUB_PAT_TOKEN` secret (GITHUB_TOKEN is enough for ordinary comments)

### QA issue not created

**Check**:
1. The comment contains exactly `@projectops create qa`
2. Workflow permissions (Issues write permission)

### Labels not syncing

**Check**:
1. The YAML syntax of `.github/config/issue-labels.yml`
2. Label names contain no special characters

---

## Related docs

- [PR Preview](../PR-PREVIEW.md) - the `@projectops server` command
- [Flutter build trigger](../FLUTTER-TEST-BUILD-TRIGGER.md) - the `@projectops build app/apk build/ios build` commands
- [Troubleshooting](./troubleshooting.md)
