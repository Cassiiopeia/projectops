# GitHub Projects sync guide

Syncs issue labels and GitHub Projects Status in both directions.

> **Optional install (#716).** A new install does not include this workflow. It only works after you register the secret `_GITHUB_PAT_TOKEN` and the variable `PROJECT_URL`, and in a repository that does not use Projects it would only pile up notifications every time a label changes.
> - Install: `npx projectops --projects-sync` (running the wizard again also works). The choice is saved as `projects_sync` in `version.yml`.
> - In a repository that already has it, an update does not remove or disable it.
> - To turn it off, run with `--no-projects-sync`. The remaining file is not deleted automatically. It is listed as a cleanup candidate.

---

## 📌 Overview

### Sync direction

| Direction | Handled by | Description |
|------|------|------|
| **Label → Status** | GitHub Actions | Updates the Projects Status when a label is added to an issue |
| **Status → Label** | Cloudflare Worker | Updates the issue label when the Status changes in Projects |

This page covers **Label → Status** sync (GitHub Actions). For Status → Label, see the [GitHub Projects Sync Wizard guide](./github-projects-sync-wizard.md).

### How it works

1. A status label is added or changed on an issue (for example `status: in progress`, or `작업중` in a Korean-label repository)
2. The `PROJECT-COMMON-PROJECTS-SYNC-MANAGER` workflow is triggered
3. The issue's Status in GitHub Projects is updated to match

---

## 🚀 Quick start

### Step 1: Configure the workflow

**You do not edit the workflow file.** You only register one variable in the repository settings.

`Settings` → `Secrets and variables` → `Actions` → `Variables` tab → `New repository variable`

| Field | Value |
|---|---|
| Name | `PROJECT_URL` |
| Value | Your Projects board URL (for example `https://github.com/orgs/MY-ORG/projects/3`) |

The workflow reads this variable automatically.

```yaml
env:
  STATUS_LABELS: '["작업전", "작업중", "담당자확인", "피드백", "작업완료", "보류", "취소", "status: todo", "status: in progress", "status: needs review", "status: feedback", "status: done", "status: on hold", "status: cancelled"]'
  PROJECT_URL: ${{ vars.PROJECT_URL }}   # injected from the repository variable (no file edit needed)
```

> If the variable is not registered, the workflow does not fail. It logs a hint and exits quietly. It does nothing until you set it up, so it is safe.
>
> ⚠️ **Do not write the URL directly in the workflow file.** A URL in the file gets committed, and when someone forks the repository or updates the template, another person's board address leaks in.

You also need to register the `_GITHUB_PAT_TOKEN` secret (scopes: `repo`, `project`).

### Step 2: Done!

Now, when you add a status label to an issue, it syncs to GitHub Projects automatically.

---

## 📎 Supported URL formats

Several URL formats are supported. Just copy and paste.

### Organization projects

```
https://github.com/orgs/{org}/projects/{number}
https://github.com/orgs/{org}/projects/{number}/views/{view_id}
```

**Examples:**
- `https://github.com/orgs/MapSee-Lab/projects/1`
- `https://github.com/orgs/TEAM-ROMROM/projects/6/views/2`

### User (personal) projects

```
https://github.com/users/{username}/projects/{number}
https://github.com/users/{username}/projects/{number}/views/{view_id}
```

**Examples:**
- `https://github.com/users/Cassiiopeia/projects/2`
- `https://github.com/users/Cassiiopeia/projects/2/views/2`

> **💡 Tip**: A `/views/{id}` path is parsed automatically too. Copy the URL as is.

---

## ⚠️ Notes for organization projects

When you use an organization project, **every repository must use the same labels**.

### Why do the labels need to be the same?

- An organization project manages issues from several repositories on one board.
- Each repository's issue labels have to match the Projects Status options.
- If the label names differ, the sync fails.

The workflow treats each English standard label and its legacy Korean label as the same status (`status: todo` = `작업전`, `status: in progress` = `작업중`, `status: needs review` = `담당자확인`, `status: feedback` = `피드백`, `status: done` = `작업완료`, `status: on hold` = `보류`, `status: cancelled` = `취소`). It prefers a board column with exactly the label's name and falls back to the column with the other name.

### How to sync labels

1. **Share the label config file**

   Keep `.github/config/issue-labels.yml` identical in every repository:

   ```yaml
   # Status labels (for Projects sync)
   # Korean-label repositories (label_style: ko) use the Korean name in the comment instead
   - name: "status: todo"          # 작업전
     color: "B8B8B8"
     description: "Not started yet"
   - name: "status: in progress"   # 작업중
     color: "1D76DB"
     description: "Work in progress"
   - name: "status: needs review"  # 담당자확인
     color: "5319E7"
     description: "Needs the assignee to confirm"
   - name: "status: feedback"      # 피드백
     color: "FBCA04"
     description: "Waiting for feedback"
   - name: "status: done"          # 작업완료
     color: "0E8A16"
     description: "Work is done"
   - name: "status: on hold"       # 보류
     color: "D93F0B"
     description: "Work on hold"
   - name: "status: cancelled"     # 취소
     color: "E4E669"
     description: "Work cancelled"
   ```

2. **Run the label sync**

   Sync the labels to GitHub with the `PROJECT-COMMON-SYNC-ISSUE-LABELS` workflow:

   - Manual run: Actions → "Sync Issue Labels" → Run workflow
   - Automatic run: triggered when `issue-labels.yml` changes

3. **Match the Projects Status options**

   In GitHub Projects, set the option names of the Status field to the same names as the labels:

   ```
   status: todo, status: in progress, status: needs review, status: feedback, status: done, status: on hold, status: cancelled
   ```

   In a Korean-label repository:

   ```
   작업전, 작업중, 담당자확인, 피드백, 작업완료, 보류, 취소
   ```

### Organization setup checklist

- [ ] Deploy the same `issue-labels.yml` to every repository
- [ ] Run the label sync workflow in each repository
- [ ] Check the GitHub Projects Status option names
- [ ] Register the `PROJECT_URL` repository variable in each repository (the same Projects URL)

---

## 🔧 Settings in detail

### Environment variables

| Variable | Description | Example |
|------|------|------|
| `STATUS_LABELS` | Status labels to sync (JSON array) | `'["작업전", "작업중", ..., "status: todo", ...]'` |
| `PROJECT_URL` | GitHub Projects URL (register it as a **repository variable**, not in the file) | `https://github.com/orgs/ORG/projects/1` |

### GitHub Secrets

| Secret | Description | Required scopes |
|--------|------|----------|
| `_GITHUB_PAT_TOKEN` | Personal access token | `repo`, `project` |

> **Scopes**: Settings → Developer settings → Personal access tokens → Tokens (classic)
> - `repo` (all)
> - `project` (all), for access to organization projects

---

## 🔍 Troubleshooting

The workflow logs these messages in Korean. Each one is shown as printed, followed by its meaning.

### PROJECT_URL errors

**Symptom**: `⚠️ PROJECT_URL이 설정되지 않았습니다.` (PROJECT_URL is not set.)

**Fix**:
1. Check that the `PROJECT_URL` variable is registered under `Settings` → `Secrets and variables` → `Actions` → `Variables` tab
2. Check that the URL format is correct (`/orgs/{org}/projects/{n}` or `/users/{user}/projects/{n}`)

---

**Symptom**: `❌ PROJECT_URL 형식이 올바르지 않습니다.` (The PROJECT_URL format is invalid.)

**Fix**:
- Check that the URL is a supported format:
  - Organization: `https://github.com/orgs/{org}/projects/{number}`
  - User: `https://github.com/users/{user}/projects/{number}`

### Project connection errors

**Symptom**: `⏭️ 이슈가 해당 프로젝트에 연결되어 있지 않습니다.` (The issue is not connected to the project.)

**Fix**:
1. Add the issue in GitHub Projects
2. Or open the issue sidebar → "Projects" → select the project

---

**Symptom**: `❌ 프로젝트에서 Status 필드를 찾을 수 없습니다.` (Cannot find the Status field in the project.)

**Fix**:
1. Check that GitHub Projects has a "Status" field
2. Check that the field name is exactly "Status" (case-sensitive)

---

**Symptom**: `❌ 프로젝트에 "작업중" Status 옵션이 없습니다.` (The project has no "작업중" Status option.)

**Fix**:
1. Add that option to the Status field in GitHub Projects
2. Or change the `STATUS_LABELS` environment variable to match your project

### Permission errors

**Symptom**: `❌ 프로젝트 정보를 가져오는데 실패했습니다.` (Failed to fetch project information.)

**Fix**:
1. Check that `_GITHUB_PAT_TOKEN` has the `project` scope
2. For an organization project, the token must belong to an account in that organization
3. If the project is private, check access permissions

---

## 📋 Customizing status labels

You can use labels that fit your project instead of the default ones.

### How to change them

1. **Edit the workflow file** (2 places)

   ```yaml
   env:
     STATUS_LABELS: '["To Do", "In Progress", "Review", "Done"]'

   jobs:
     sync-label-to-status:
       if: |
         github.event_name == 'workflow_dispatch' ||
         (github.event_name == 'issues' &&
          contains(fromJSON('["To Do", "In Progress", "Review", "Done"]'), github.event.label.name))
   ```

2. **Edit issue-labels.yml**

   ```yaml
   - name: "To Do"
     color: "B8B8B8"
   - name: "In Progress"
     color: "1D76DB"
   - name: "Review"
     color: "5319E7"
   - name: "Done"
     color: "0E8A16"
   ```

3. **Match the GitHub Projects Status options**

   Change the options of the Status field in the Projects settings to the same names

---

## 📚 Related docs

- [Issue automation guide](./issue-automation.md)
- [Version control](./version-control.md)
