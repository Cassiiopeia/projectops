# PR Preview

Deploy a temporary server with a single comment on an Issue or PR, and have it cleaned up automatically when you close it.

---

## Overview

PR Preview lets you test code that is still in development in a real server environment.

| Feature | Description |
|------|------|
| **Issue/PR support** | Works from comments on either an Issue or a PR |
| **Automatic cleanup** | The container is deleted automatically when the Issue/PR is closed |
| **Traefik integration** | Automatic SSL and domain routing |
| **Health Check** | Hybrid approach: HTTP + log pattern |

---

## Supported projects

| Type | Workflow |
|------|-----------|
| **Spring** | `PROJECT-SPRING-PR-PREVIEW.yaml` |
| **Python** | `PROJECT-PYTHON-PR-PREVIEW.yaml` |

> Both workflows provide the same commands and features.

---

## Usage

### Commands

Enter one of these commands as a comment on an Issue or PR.

| Command | What it does |
|--------|------|
| `@projectops server build` | Build and deploy the Preview server |
| `@projectops server destroy` | Delete the Preview server |
| `@projectops server status` | Check the current status |

### Usage scenarios

#### Using it on a PR
```
1. Create a PR
2. Comment: @projectops server build
3. → Build and deploy run
4. → The Preview URL is posted as a comment
5. Deleted automatically when the PR is closed
```

#### Using it on an Issue
```
1. Create an Issue
2. Issue Helper suggests a branch name automatically (comment)
3. Push code to that branch
4. Comment: @projectops server build
5. → The branch is detected automatically and the build runs
6. Deleted automatically when the Issue is closed
```

---

## Deployment result

When the deployment finishes, a comment like this is posted automatically.

```markdown
### Preview 환경
| 항목 | 값 |
|------|-----|
| **Preview URL** | http://project-pr-123.pr.domain.com:8079 |
| **API Docs** | http://project-pr-123.pr.domain.com:8079/docs/swagger |
| **컨테이너** | `project-pr-123` |
| **브랜치** | `feature/new-feature` |
| **커밋** | `abc1234` |
```

The bot writes these labels in Korean: `Preview 환경` (Preview environment), `항목` (Item), `값` (Value), `컨테이너` (Container), `브랜치` (Branch), `커밋` (Commit).

---

## Environment variable settings

Configure these for your project in the `[영역 1]` (Area 1) section of the workflow file.

### Per-project settings (edit these)

```yaml
env:
  PROJECT_NAME: my-project                 # Project name (used in container, image and domain)
  JAVA_VERSION: '21'                       # Spring only
  APPLICATION_YML_PATH: 'src/main/resources/application-prod.yml'
  DOCKERFILE_PATH: './Dockerfile'
  INTERNAL_PORT: '8080'                    # Port inside the container
  SSH_AUTH_METHOD: 'password'              # password | key
```

### Do not change after the environment is set up

```yaml
env:
  TRAEFIK_NETWORK: traefik-network
  PREVIEW_DOMAIN_SUFFIX: pr.suhsaechan.kr  # Preview domain suffix
  PREVIEW_PORT: '8079'                     # Externally exposed port
  SSH_PORT: '2022'                         # SSH port
```

> ⚠️ The base domain is `PREVIEW_DOMAIN_SUFFIX` and the external port is `PREVIEW_PORT`. The final URL is assembled as `{PROJECT_NAME}-pr-{PR number}.{PREVIEW_DOMAIN_SUFFIX}:{PREVIEW_PORT}`.

### Optional settings

```yaml
env:
  # Health Check
  HEALTH_CHECK_PATH: '/actuator/health'              # HTTP check path (empty: skip)
  HEALTH_CHECK_LOG_PATTERN: 'Started .* in [0-9.]+ seconds'  # Log pattern

  # API docs
  API_DOCS_PATH: '/docs/swagger'                     # Swagger path (empty: not shown)

  # Volume mount (empty means no mount)
  PROJECT_TARGET_DIR: ''                             # Data directory on the server
  PROJECT_MNT_DIR: ''                                # Mount path in the container

  # Issue Helper
  ISSUE_HELPER_MARKER: 'Guide by SUH-LAB'            # Marker used to extract the branch
```

---

## Health Check

Two methods are supported for confirming that the server has finished starting.

### 1. HTTP Health Check (preferred)

If `HEALTH_CHECK_PATH` is set, the check is done with an HTTP request.

```bash
# Spring Actuator example
GET http://localhost:8080/actuator/health
→ check for {"status":"UP"}
```

### 2. Log pattern (fallback)

If the HTTP check fails, the container logs are searched for a pattern.

```yaml
# Spring default pattern
HEALTH_CHECK_LOG_PATTERN: 'Started .* in [0-9.]+ seconds'

# Python/FastAPI pattern
HEALTH_CHECK_LOG_PATTERN: 'Uvicorn running on'
```

### Timeout

- Default: 120 seconds
- Checked every 5 seconds
- On failure, the logs are printed and a notification is sent

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    GitHub Actions                        │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   │
│  │ check-cmd   │──▶│ build-pr    │   │ build-issue │   │
│  │             │   │ (PR comment)│   │(Issue comm.)│   │
│  └─────────────┘   └─────────────┘   └─────────────┘   │
│         │                                               │
│         ▼                                               │
│  ┌─────────────┐   ┌─────────────┐                     │
│  │destroy-prev │   │ check-status│                     │
│  └─────────────┘   └─────────────┘                     │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│         Deployment server reachable over SSH             │
│    (Synology NAS · AWS EC2 · generic Linux, etc.)        │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   │
│  │   Docker    │◀──│   Traefik   │──▶│  Container  │   │
│  │  Registry   │   │  (Router)   │   │  project-   │   │
│  └─────────────┘   └─────────────┘   │  pr-123     │   │
│                                       └─────────────┘   │
└─────────────────────────────────────────────────────────┘
```

> The deployment engine is not tied to any one vendor. Choose `SSH_AUTH_METHOD` as `password` (Synology, generic servers) or `key` (.pem authentication, e.g. AWS EC2). See the [SSH+Docker deployment guide](./ssh-docker-deployment-guide.md) for details.

---

## Troubleshooting

### Build failure

**Symptom**: An error occurs after `@projectops server build`

**What to check**:
1. Check the GitHub Actions logs
2. Check the Dockerfile path (`DOCKERFILE_PATH`, default `./Dockerfile`)
3. Check the Secrets settings (`SERVER_HOST`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, etc.)

### Health Check failure

**Symptom**: Deployment finished, but a "Health check failed" error appears

**Fix**:
1. Check that the `HEALTH_CHECK_PATH` path is correct
2. Spring: check whether the Actuator dependency has been added
3. Configure `HEALTH_CHECK_LOG_PATTERN` as a fallback

### Branch not found on an Issue

**Symptom**: A "브랜치를 찾을 수 없습니다" (Cannot find the branch) error

**What to check**:
1. Check that the Issue Helper comment exists
2. Check that the branch has actually been pushed
3. Check that the `ISSUE_HELPER_MARKER` value is correct

### Container not deleted

**Symptom**: The container is still there after closing the Issue/PR

**Fix**:
```bash
# Manual deletion (after connecting to the deployment server over SSH)
docker stop project-pr-123
docker rm project-pr-123
docker rmi registry/project-pr-123:latest
```

---

## Required Secrets

| Secret | Description |
|--------|------|
| `SERVER_HOST` | Deployment server address |
| `SERVER_USER` | SSH username |
| `SERVER_PASSWORD` | SSH password (when `SSH_AUTH_METHOD: password`) |
| `SSH_KEY` | Full contents of the `.pem` private key (when `SSH_AUTH_METHOD: key`) |
| `DOCKERHUB_USERNAME` | DockerHub username (used for image push and pull) |
| `DOCKERHUB_TOKEN` | DockerHub access token |
| `APPLICATION_PROD_YML` (optional) | Contents of `application-prod.yml` |

> Depending on the value of `SSH_AUTH_METHOD`, you need **only one of** `SERVER_PASSWORD` and `SSH_KEY`.

---

## Related documents

- [SSH+Docker deployment guide](./ssh-docker-deployment-guide.md)
- [Troubleshooting](./troubleshooting.md)
