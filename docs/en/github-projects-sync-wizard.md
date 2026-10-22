# GitHub Projects Sync Wizard guide

A complete guide to setting up **two-way real-time sync** between GitHub Projects Status and issue labels.

---

## Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Using the wizard](#using-the-wizard-4-simplified-steps)
4. [Manual setup](#manual-setup)
5. [Troubleshooting](#troubleshooting)
6. [Maintenance](#maintenance)
7. [FAQ](#faq)

---

## Overview

### The problem

GitHub Actions does not support the `projects_v2_item` event as a trigger.

```yaml
# ❌ this does not work
on:
  projects_v2_item:
    types: [edited]
```

So when you change a Status on the Projects board, the issue label is not synced automatically.

### The solution

A **Cloudflare Worker** receives the GitHub organization webhook directly and handles it.

| Sync direction | Handled by | Trigger |
|------------|------|--------|
| Label → Status | GitHub Actions | Issue label change |
| Status → Label | Cloudflare Worker | Projects Status change |

---

## Architecture

### Overall flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                      GitHub Projects Board                          │
│                                                                     │
│   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌──────────┐   ┌───────┐│
│   │ 작업전  │ → │ 작업중  │ → │ 피드백  │ → │담당자확인│ → │작업완료││
│   └─────────┘   └─────────┘   └─────────┘   └──────────┘   └───────┘│
│                      │                                              │
│                      │ drag a card (Status change)                  │
└──────────────────────┼──────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                  GitHub Organization Webhook                         │
│   Event: projects_v2_item                                            │
│   Action: edited                                                     │
└──────────────────────────────────────────────────────────────────────┘
                       │
                       │ HTTPS POST (with X-Hub-Signature-256)
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    Cloudflare Worker (Edge)                          │
│                                                                      │
│   Processing order:                                                  │
│   1. Verify the webhook secret (HMAC-SHA256)                         │
│   2. Filter events (only projects_v2_item + edited)                  │
│   3. Read the current Status with the GraphQL API                    │
│   4. Sync the issue label with the REST API                          │
└──────────────────────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────────┐
│                         GitHub Issue                                 │
│   Labels: [enhancement] [작업 중] ← changed automatically!            │
└──────────────────────────────────────────────────────────────────────┘
```

The board columns above use the default Korean labels (작업전 = `status: todo`, 작업중 = `status: in progress`, 피드백 = `status: feedback`, 담당자확인 = `status: needs review`, 작업완료 = `status: done`).

### Two-way sync

```
┌─────────────┐                           ┌─────────────┐
│ Issue Label │ ◀───────────────────────▶ │  Projects   │
│             │      always in sync       │   Status    │
└──────┬──────┘                           └──────┬──────┘
       │                                         │
       │ on label change                         │ on Status change
       ▼                                         ▼
┌─────────────┐                           ┌─────────────┐
│   GitHub    │                           │  Cloudflare │
│   Actions   │                           │   Worker    │
└─────────────┘                           └─────────────┘
```

---

## Using the wizard (4 simplified steps)

### Step 1: Enter the information in the wizard

Open `.github/util/common/projects-sync-wizard/projects-sync-wizard.html` in a browser, then:

1. **Enter the GitHub Projects URL:**
   ```
   https://github.com/orgs/YOUR-ORG/projects/1
   ```
   When you enter the URL, the organization name and project number are extracted automatically.

2. **Set the worker name** (default: `github-projects-sync-worker`)
   - If the name collides during deploy, the script lets you enter a new one.

3. **Check or customize the status labels** (defaults come from issue-labels.yml)
   - 작업전, 작업중, 담당자확인, 피드백, 작업완료, 보류, 취소
   - **Important:** the label names must **exactly match** the Status column names in GitHub Projects. If your repository uses the English standard labels (`status: todo`, `status: in progress`, `status: needs review`, `status: feedback`, `status: done`, `status: on hold`, `status: cancelled`), enter those names here and use them as the column names.

4. **Webhook secret** (generated automatically)

5. Click **"Worker 파일 ZIP 다운로드"** (download the worker files as ZIP)

### Step 2: Run the script once

```bash
# unzip and move into the folder
cd github-projects-sync-worker

# Mac/Linux
./projects-sync-worker-setup.sh

# Windows PowerShell
.\projects-sync-worker-setup.ps1
```

What the script does automatically:
1. Installs npm dependencies (handles SSL errors automatically)
2. Logs in to Cloudflare (opens the browser automatically)
3. Deploys the worker (you can enter a new name if it collides)
4. Asks for the GITHUB_TOKEN
5. Sets WEBHOOK_SECRET automatically
6. Prints the worker URL

### Step 3: Set up the GitHub webhook by hand

1. Go to Organization Settings → Webhooks
   ```
   https://github.com/organizations/YOUR-ORG/settings/hooks
   ```
2. Click "Add webhook"
3. Enter the settings:
   - **Payload URL:** the worker URL printed by the script
   - **Content type:** `application/json`
   - **Secret:** the webhookSecret value in config.json
   - **Events:** "Let me select individual events" → check "Project v2 items"
4. Click "Add webhook"

### Step 4: Test

1. On the GitHub Projects board, move an issue card to another Status column
2. On the issue page, check that the label changed automatically
3. If something goes wrong, check the worker log: `npx wrangler tail`

---

## Manual setup

How to set everything up without the wizard.

### Cloudflare Worker manual setup

#### 1. Create wrangler.toml

```toml
name = "github-projects-sync-worker"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[vars]
PROJECT_NUMBER = "1"
STATUS_FIELD = "Status"
STATUS_LABELS = '["작업전","작업중","담당자확인","피드백","작업완료","보류","취소"]'
ORG_NAME = "YOUR-ORG"
```

#### 2. Set the secrets

```bash
npx wrangler secret put GITHUB_TOKEN
# enter a GitHub PAT (repo, project scopes)

npx wrangler secret put WEBHOOK_SECRET
# enter any secret key (for example: openssl rand -hex 32)
```

### GitHub Actions workflow

Edit the environment variables in `PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml`:

```yaml
env:
  STATUS_LABELS: '["작업전", "작업중", "담당자확인", "피드백", "작업완료", "보류", "취소"]'
  PROJECT_NUMBER: '1'
  ORG_NAME: 'YOUR-ORG'
```

---

## Troubleshooting

### SSL error (UNABLE_TO_GET_ISSUER_CERT_LOCALLY)

**Cause:** a company or school network proxy, or security software

**Fix:**

```bash
# for npm install
npm config set strict-ssl false
npm install
npm config set strict-ssl true

# for wrangler commands
export NODE_TLS_REJECT_UNAUTHORIZED=0  # Mac/Linux
$env:NODE_TLS_REJECT_UNAUTHORIZED=0    # Windows PowerShell
```

### Cloudflare email verification error

**Error:** `You need to verify your email address to use Workers. [code: 10034]`

**Fix:**
1. Open the [Cloudflare dashboard](https://dash.cloudflare.com)
2. Check the email verification banner at the top
3. Open the email and click the verification link

### Subdomain conflict

**Error:** `Subdomain is unavailable, please try a different subdomain`

**Fix:** use a different subdomain name (for example `my-org-sync`, `project-sync`)

### Webhook 401 error

**Cause:** the webhook secret does not match

**Fix:**
1. Check the secret in the GitHub webhook settings
2. Check that it is the same as WEBHOOK_SECRET in the Cloudflare Worker
3. If they differ, reset both to the same value

```bash
npx wrangler secret put WEBHOOK_SECRET
```

### Labels do not sync

**Checklist:**
1. Check the worker log: `npx wrangler tail`
2. Check webhook deliveries: Organization Settings → Webhooks → Recent Deliveries
3. Check that the issue is connected to the project
4. Check that the label exactly matches the project's Status column name

---

## Maintenance

### When the GitHub PAT expires

```bash
cd github-projects-sync-worker
export NODE_TLS_REJECT_UNAUTHORIZED=0
npx wrangler secret put GITHUB_TOKEN
# enter the new token
```

### When you add or change status labels

1. Edit `STATUS_LABELS` in `wrangler.toml`
2. Redeploy the worker

```bash
npx wrangler deploy
```

3. Make the same change to `STATUS_LABELS` in the GitHub Actions workflow

### Updating the worker code

```bash
cd github-projects-sync-worker
export NODE_TLS_REJECT_UNAUTHORIZED=0
npx wrangler deploy
```

### Checking the worker log

```bash
npx wrangler tail
```

---

## FAQ

### Q: Does it cost anything?

**A:** It is completely free on the Cloudflare Workers free tier.
- 100,000 requests per day
- Typical usage is under 100

### Q: Can I use it with a personal repository instead of an organization?

**A:** No. GitHub Projects V2 supports webhooks only at the organization level.
Projects in personal repositories cannot be synced this way.

### Q: Can I use it with several projects?

**A:** Deploy a separate worker for each project, or extend the worker code to handle several projects.

### Q: Can it cause an infinite loop?

**A:** No. The worker code includes infinite loop prevention.
If the same label is already there, it skips the update.

### Q: Does it apply to PRs too?

**A:** Yes. The worker code supports both issues and pull requests.

---

## Related files

| File | Description |
|------|------|
| `.github/util/common/projects-sync-wizard/` | Wizard UI folder |
| `.github/workflows/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml` | Label → Status sync |

---

## Version history

| Version | Date | Changes |
|------|------|---------|
| 2.0.0 | 2026-01-21 | Simplified to 4 steps, added a one-click setup script |
| 1.0.0 | 2026-01-21 | Initial release |
