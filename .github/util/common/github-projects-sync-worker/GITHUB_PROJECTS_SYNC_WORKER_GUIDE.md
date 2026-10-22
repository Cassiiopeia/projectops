# GitHub Projects Sync Worker Guide

A Cloudflare Worker that detects Status changes on GitHub Projects and keeps the issue labels in sync automatically.

---

## 📌 Overview

```
Move a card on the Projects board (Status change)
          │
          ▼
GitHub Webhook (projects_v2_item)
          │
          ▼
Cloudflare Worker (this module)
          │
          ▼
Issue label updated automatically
```

**What it does**: when the Projects Status changes, the issue's label follows it.

---

## 🚀 Quick start

### Prerequisites

- Node.js (v18 or later recommended)
- A Cloudflare account (free)
- A GitHub Personal Access Token (repo and project scopes)

### Step 1: Install dependencies

```bash
cd .github/util/common/github-projects-sync-worker
npm install
```

> **If you get an SSL error**:
> ```bash
> npm config set strict-ssl false
> npm install
> npm config set strict-ssl true  # turn it back on after installing
> ```

### Step 2: Log in to Cloudflare

```bash
export NODE_TLS_REJECT_UNAUTHORIZED=0  # avoids SSL errors
npx wrangler login
```

When the browser opens, log in with your Cloudflare account and grant access.

### Step 3: Set the secrets

```bash
# GitHub Personal Access Token
npx wrangler secret put GITHUB_TOKEN
# enter the token at the prompt

# Webhook secret
npx wrangler secret put WEBHOOK_SECRET
# enter the secret at the prompt (the same value you will set on the GitHub webhook)
```

### Step 4: Deploy

```bash
npx wrangler deploy
```

When the deploy finishes, the Worker URL is shown:
```
https://github-projects-sync-worker.<your-subdomain>.workers.dev
```

### Step 5: Set up the GitHub webhook

1. Open GitHub Organization Settings → Webhooks
2. Click **Add webhook**
3. Settings:
   - **Payload URL**: the Worker URL
   - **Content type**: `application/json`
   - **Secret**: the same value as the WEBHOOK_SECRET from Step 3
   - **Events**: "Let me select individual events" → check `Project v2 items`
4. Click **Add webhook**

---

## ⚙️ Customizing the settings

### wrangler.toml

```toml
[vars]
# Projects number (from the URL: /orgs/ORG_NAME/projects/NUMBER)
PROJECT_NUMBER = "6"

# Name of the Status field in Projects
STATUS_FIELD = "Status"

# Labels to sync (JSON array)
STATUS_LABELS = '["작업전","작업중","담당자확인","피드백","작업완료","보류","취소"]'

# Organization name
ORG_NAME = "your-org"
```

> `STATUS_LABELS` is data: it must match the label names and the Status column names exactly.
> The default is the legacy Korean label set (todo, in progress, needs review, feedback, done,
> on hold, cancelled). A repo that uses the English standard labels puts those names here instead
> (`"status: todo"`, `"status: in progress"`, and so on).

### Using it for another project

1. Edit the `[vars]` section of `wrangler.toml`
2. Change the `name` field (if you want a different Worker name)
3. Redeploy: `npx wrangler deploy`

---

## 🔧 Main commands

| Command | Description |
|--------|------|
| `npm install` | Install dependencies |
| `npx wrangler login` | Log in to Cloudflare |
| `npx wrangler deploy` | Deploy the Worker |
| `npx wrangler tail` | Stream live logs |
| `npx wrangler secret put <NAME>` | Set a secret |
| `npx wrangler secret list` | List secrets |
| `npx wrangler dev` | Run the local dev server |

---

## 📁 File layout

```
github-projects-sync-worker/
├── .gitignore              # files Git ignores
├── package.json            # dependencies
├── package-lock.json       # dependency lock
├── tsconfig.json           # TypeScript settings
├── wrangler.toml           # Cloudflare Worker settings
├── GITHUB_PROJECTS_SYNC_WORKER_GUIDE.md  # this guide
└── src/
    └── index.ts            # Worker main code
```

---

## 🔐 Required permissions

### GitHub Personal Access Token

These scopes are needed:
- `repo` - repository access
- `project` - Projects access (read/write)

Create a token: https://github.com/settings/tokens

### Cloudflare

A free account is enough. Email verification is required.

---

## ⚠️ Troubleshooting

### SSL certificate error

**Error**: `UNABLE_TO_GET_ISSUER_CERT_LOCALLY`

**Fix**:
```bash
# when installing with npm
npm config set strict-ssl false
npm install
npm config set strict-ssl true

# when running wrangler commands
export NODE_TLS_REJECT_UNAUTHORIZED=0
npx wrangler <command>
```

### Cloudflare email verification required

**Error**: `You need to verify your email address to use Workers. [code: 10034]`

**Fix**: open https://dash.cloudflare.com → finish email verification

### Webhook 401 error

**Cause**: WEBHOOK_SECRET does not match

**Fix**:
1. Check the Secret value on the GitHub webhook
2. Check that it matches the Worker's WEBHOOK_SECRET
3. If they differ, set it again: `npx wrangler secret put WEBHOOK_SECRET`

### The Worker does nothing

1. **Check the logs**: `npx wrangler tail`
2. **Check webhook delivery**: GitHub Webhook → Recent Deliveries
3. **Check the content type**: it must be `application/json`
4. **Check the event**: `Project v2 items` must be checked

---

## 🧪 How to test

### 1. Webhook connection test

When you create the GitHub webhook, a `ping` event is sent automatically.
Check for a `200 OK` response under Recent Deliveries.

### 2. Real behavior test

1. Start watching the logs with `npx wrangler tail`
2. Move an issue card to another Status column on the Projects board
3. Follow the processing in the logs
4. Check the label change on the issue page

### Expected log

The two label lines come from the Worker as they are: `제거됨` means "removed" and `추가됨` means "added".

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 GitHub Projects Sync Worker
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Webhook signature verified
📌 Event type: projects_v2_item
📌 Action: edited
📌 Processing item: PVTI_xxx
📌 Issue: acme-org/acme-app#123
📌 Current Labels: enhancement, 작업전
📌 New Status: "작업중"
🗑️ Labels to remove: 작업전
  ✅ Label "작업전" 제거됨
➕ Adding label: "작업중"
  ✅ Label "작업중" 추가됨
🎉 Label sync completed!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 📊 Cost

| Item | Cloudflare Free Tier |
|------|---------------------|
| Requests per day | 100,000 |
| CPU time per request | 10ms |
| **Monthly cost** | **Free** |

At typical usage (tens to hundreds of requests a day) it is completely free.

---

## 🔄 Maintenance

### Renewing the GitHub token

When the token expires:
```bash
npx wrangler secret put GITHUB_TOKEN
# enter the new token
```

### Changing the status labels

After editing `STATUS_LABELS` in `wrangler.toml`:
```bash
npx wrangler deploy
```

### Deploying after a code change

```bash
npx wrangler deploy
```

---

## 📚 Related docs

- [Cloudflare Workers docs](https://developers.cloudflare.com/workers/)
- [Wrangler CLI docs](https://developers.cloudflare.com/workers/wrangler/)
- [GitHub Webhooks docs](https://docs.github.com/en/webhooks)
- [GitHub Projects API](https://docs.github.com/en/graphql/reference/objects#projectv2item)

---

## 🏗️ Architecture

### How it works

1. **Receive the webhook**: on a `projects_v2_item` event, GitHub sends a POST request to the Worker
2. **Verify**: check the HMAC-SHA256 signature in the `X-Hub-Signature-256` header
3. **Filter events**: handle only the `edited` action (Status change)
4. **GraphQL lookup**: fetch the item's current Status and the issue details
5. **Sync labels**: remove the old status label → add the new status label
6. **Loop guard**: skip when the same label is already there

### Security

- **HMAC-SHA256**: verifies that the webhook request is genuine
- **Timing-safe comparison**: prevents timing attacks
- **Encrypted secrets**: stored safely by Cloudflare

---

## 📝 Change history

| Date | Version | Change |
|------|------|----------|
| 2026-01-20 | 1.0.0 | Initial version |
