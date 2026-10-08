# SSH + Docker deployment guide

A guide to the workflows that deploy an application automatically to any server reachable over SSH (Synology NAS, AWS EC2, GCP, a plain VPS, and so on).

---

## Overview

projectops provides deployment workflows built on the pattern "connect over SSH → pull the Docker image → replace the container". One set of workflows covers Synology, AWS EC2 and the rest. The only differences are `SSH_AUTH_METHOD` (password/key) and the path settings.

| Workflow | Project type | Purpose |
|-----------|-------------|------|
| `PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD` | Flutter | Build the APK, then upload it to the server over SMB |
| `PROJECT-SPRING-SIMPLE-CICD` | Spring Boot | Build and deploy a Docker image (default, single container) |
| `PROJECT-SPRING-NONSTOP-TRAEFIK-CICD` | Spring Boot | Zero-downtime deployment (Traefik Blue-Green, opt-in) |
| `PROJECT-SPRING-NONSTOP-NGINX-CICD` | Spring Boot | Zero-downtime deployment (Nginx Blue-Green, opt-in) |
| `PROJECT-SPRING-PR-PREVIEW` | Spring Boot | Create a preview environment for each PR automatically |
| `PROJECT-PYTHON-SIMPLE-CICD` | Python (FastAPI/Django) | Build and deploy a Docker image (single container) |
| `PROJECT-PYTHON-PR-PREVIEW` | Python (FastAPI/Django) | Create a preview environment for each PR automatically |

> **The server deployment workflows are included when `--deploy docker-ssh` (the default) is used.** They live in each type's `project-types/<type>/server-deploy/` folder, and choosing `--deploy vercel` or `--deploy none` excludes the whole folder.
> Library publishing is selected with `--publish nexus,npm,github-packages`, and Secret backup with `--secret-backup`. (The old `--nexus`/`--npm-publish` flags are deprecated and are interpreted as the new axes, with a warning.)
> The **zero-downtime options** ship alongside the default `SIMPLE-CICD` and are enabled only when you switch to them explicitly (their triggers are commented out).
>
> The Python deployment workflows use the **same SSH+Docker engine** as Spring's `SIMPLE-CICD` / `PR-PREVIEW`, with the same Secrets and env structure. Apply the Spring sections below as they are. Only the build step (Gradle → pip/uv) and the health check defaults (`/actuator/health` → `/docs`, log pattern `Uvicorn running on`) differ.

---

## Deploying multiple project types

When one repository holds several types (for example a Spring backend plus a Python AI service) and several CICD workflows are installed together, they all deploy to the same server. To avoid resource conflicts, set each workflow's env to **different values**.

- Separate `PROJECT_NAME`, `CONTAINER_NAME` and `DEPLOY_PORT` (or `PROJECT_DEPLOY_PORT`) per type in each workflow.
- You cannot deploy two containers on the same port of the same server (`port is already allocated`).
- Example: split the ports, such as `8096` for the Spring backend and `8092` for the Python AI service.

| Item | Spring backend | Python AI |
|------|--------------|-----------|
| `PROJECT_NAME` | `myapp-back` | `myapp-ai` |
| `DEPLOY_PORT` | `8096` | `8092` |

> With multiple types, the CI workflows (`*-CI.yaml`) all fire on a single develop push. Comment out the trigger or delete the file for any type whose CI you do not need. For type and path settings, see the [NPX wizard guide](../NPX-WIZARD.md).

---

## Prerequisites

### 1. Server setup (example: Synology NAS)

> The steps below are an example for Synology NAS (DSM). For other servers such as AWS EC2, GCP or a VPS, install Docker and enable SSH the way your OS requires. For AWS EC2 setup, see the "SSH authentication methods and deploying to other servers (AWS EC2 and others)" section at the bottom of this document.

#### Install the Docker package (for Spring Boot deployment)
1. DSM > Package Center > install Docker
2. Check that you have permission to manage Docker containers

#### Enable SSH
1. DSM > Control Panel > Terminal & SNMP > enable the SSH service
2. Port: the default 22 or a custom one (workflow default: 2022)
3. Allow SSH login for the administrator account

#### Set up an SMB shared folder (for Flutter APK upload)
1. DSM > Control Panel > Shared Folder > create a new shared folder
2. Enable the SMB service (Control Panel > File Services > SMB)
3. Port: the default 445 or a custom one (for example 44445)

### 2. Common GitHub Secrets

Secrets shared by every deployment workflow:

| Secret | Description | Example |
|--------|------|------|
| `SERVER_HOST` | Server IP or domain (for example Synology NAS, AWS EC2) | `192.168.1.100` or `nas.example.com` |
| `SERVER_USER` | SSH/SMB login user name | `admin` |
| `SERVER_PASSWORD` | SSH/SMB login password | `{PASSWORD}` |

---

## Flutter Android deployment (SMB)

### Workflow

**File**: `PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml`

**Triggers**:
- Push to the `main` branch
- Runs automatically after the CHANGELOG workflow completes
- Manual run (workflow_dispatch)

### Required GitHub Secrets

| Secret | Description |
|--------|------|
| `SERVER_HOST` | Synology NAS host |
| `SERVER_USER` | SMB login user name |
| `SERVER_PASSWORD` | SMB login password |
| `DEBUG_KEYSTORE` | Android debug keystore (Base64 encoded) |
| `ENV_FILE` | Contents of the Flutter .env file |
| `GOOGLE_SERVICES_JSON` | Contents of the Firebase google-services.json |

### Environment variables (edit in the workflow file)

```yaml
env:
  PROJECT_NAME: "your-project"      # Project name (used in the APK file name)
  FLUTTER_VERSION: "3.35.5"         # Flutter version
  JAVA_VERSION: "17"                # Java version
  SMB_PORT: "44445"                 # SMB port (default 445)
  SMB_SHARE: "web"                  # SMB shared folder name
  SMB_PATH_ANDROID: "/android/download"  # APK storage path
```

### Deployment process

```
1. Build the Flutter APK (Fastlane)
2. Rename the APK: {PROJECT_NAME}-v{VERSION}-{COMMIT_HASH}.apk
3. Upload to the Synology NAS over SMB
4. Update the build history JSON
```

### Deployment result

APK file path: `//{SERVER_HOST}/{SMB_SHARE}/{PROJECT_NAME}/android/download/`

History file: `{PROJECT_NAME}-android-cicd-history.json`

---

## Spring Boot simple deployment (Docker)

### Workflow

**File**: `PROJECT-SPRING-SIMPLE-CICD.yaml`

**Triggers**:
- Push to the `main` branch (production)
- Manual run (workflow_dispatch)

### Required GitHub Secrets

| Secret | Description |
|--------|------|
| `APPLICATION_PROD_YML` | Contents of the Spring Boot production config file |
| `DOCKERHUB_USERNAME` | DockerHub user name |
| `DOCKERHUB_TOKEN` | DockerHub access token |
| `SERVER_HOST` | Synology NAS host |
| `SERVER_USER` | SSH login user name |
| `SERVER_PASSWORD` | SSH login password |

### Environment variables (edit in the workflow file)

```yaml
env:
  PROJECT_NAME: "project"           # Project name
  DOCKER_IMAGE_PREFIX: "back-container"
  SPRING_PROFILE: "prod"
  JAVA_VERSION: "17"
```

### Deployment by branch

| Branch | Port | Container name |
|--------|-----|-----------|
| main | 8080 (default, `DEPLOY_PORT`) | `{PROJECT_NAME}-back-deploy` |

### Deployment process

```
1. Gradle build (tests skipped)
2. Build the Docker image and push it to DockerHub
3. Connect to the Synology NAS over SSH
4. Pull the Docker image
5. Remove the existing container, then start the new one
```

---

## Spring Boot zero-downtime deployment (Traefik Blue-Green)

> It uses the same Secrets as the default `SIMPLE-CICD`, and provides deployment without downtime by toggling Blue-Green through Traefik labels.

### Workflow

**File**: `PROJECT-SPRING-NONSTOP-TRAEFIK-CICD.yaml`

**Triggers** (disabled by default):
- `workflow_dispatch` (manual run)
- The push trigger is commented out (`# push: / #   branches: / #     - main`). To switch over, uncomment it so a push to `main` deploys, and at the same time comment out the push trigger of `SIMPLE-CICD` to prevent duplicate runs

### Prerequisites

#### 1. Install the Traefik reverse proxy

```bash
docker network create traefik-network

docker run -d \
  --name traefik \
  --network traefik-network \
  -p 80:80 -p 8079:8079 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  traefik:v2.10 \
  --providers.docker=true \
  --entrypoints.web.address=:8079
```

#### 2. DSM reverse proxy mapping

```
${PRODUCTION_DOMAIN}:443 → localhost:${TRAEFIK_INTERNAL_PORT}  (default 8079)
```

### Required GitHub Secrets

Same as `SIMPLE-CICD`.

| Secret | Description |
|--------|------|
| `APPLICATION_PROD_YML` | Contents of application-prod.yml |
| `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` | DockerHub authentication |
| `SERVER_HOST` / `SERVER_USER` / `SERVER_PASSWORD` | SSH login |

### Main env settings

```yaml
env:
  PROJECT_NAME: "mapsy-back"
  PRODUCTION_DOMAIN: "example.com"
  TRAEFIK_NETWORK: "traefik-network"
  TRAEFIK_ENTRYPOINT: "web"
  TRAEFIK_INTERNAL_PORT: "8079"
  EXTRA_NETWORKS: ""                 # Example: "selenium-chrome-network"
  HEALTHCHECK_PATH: "/"
  HEALTHCHECK_ACCEPT_CODES: "200|301|302|308"
  HEALTHCHECK_MAX_RETRIES: "36"
  HEALTHCHECK_RETRY_INTERVAL: "5"
  IN_FLIGHT_WAIT: "10"
```

### Deployment process

```
1. Gradle build + Docker image build & DockerHub push
2. Connect to Synology over SSH → find the container with Traefik labels → determine the active color
3. Start the new container in the opposite color (blue/green) (Traefik labels are registered automatically)
4. If EXTRA_NETWORKS is set, run an additional docker network connect
5. Health check with a GET call through Traefik (passes when it matches HEALTHCHECK_ACCEPT_CODES)
   On failure the new container is kept and the old one stays as it is → effectively an automatic rollback
6. After IN_FLIGHT_WAIT seconds, remove the old container and clean up dangling images
```

### Resource naming

| Item | Format |
|------|------|
| Container | `{PROJECT_NAME}-blue` / `{PROJECT_NAME}-green` |
| Image | `{DOCKERHUB_USERNAME}/{PROJECT_NAME}:{ref_name}` |
| Traefik router/service | `{PROJECT_NAME}` |

---

## Spring Boot zero-downtime deployment (Nginx Blue-Green)

> It uses the same Secrets as the default `SIMPLE-CICD`, and provides Blue-Green zero-downtime deployment by toggling the `proxy_pass` port in the nginx config. Use it in environments without Traefik.

### Workflow

**File**: `PROJECT-SPRING-NONSTOP-NGINX-CICD.yaml`

**Triggers** (disabled by default):
- `workflow_dispatch` (manual run)
- The push trigger is commented out (`# push: / #   branches: / #     - main`). To switch over, uncomment it so a push to `main` deploys, and at the same time comment out the push trigger of `SIMPLE-CICD` to prevent duplicate runs

### Prerequisites

#### 1. nginx installed and a sites-enabled config present

The server block of the config must contain the following line:

```nginx
server {
    listen 443 ssl;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;   # BLUE_PORT (or GREEN_PORT)
        # ...
    }
}
```

#### 2. SSH user permissions

- Can run `sudo nginx -t`, `sudo systemctl reload nginx` and `sudo docker ...`
- Has write permission on the nginx config file and the backup directory

### Required GitHub Secrets

Same as `SIMPLE-CICD`.

### Main env settings

```yaml
env:
  PROJECT_NAME: "mapsy-back"
  DOMAIN_NAME: "example.com"                                  # Must match the nginx server_name
  BLUE_PORT: "8080"
  GREEN_PORT: "8081"
  NGINX_RP_CONF: "/etc/nginx/sites-enabled/example.conf"
  NGINX_BACKUP_DIR: "/volume1/project/nginx/backups"
  NGINX_BACKUP_KEEP: "10"
  HEALTHCHECK_PATH: "/actuator/health"
  HEALTHCHECK_MAX_RETRIES: "120"
  HEALTHCHECK_RETRY_INTERVAL: "1"
  DOMAIN_CHECK_RETRIES: "10"
  DOMAIN_CHECK_INTERVAL: "2"
  IN_FLIGHT_WAIT: "5"
```

### Deployment process

```
1. Gradle build + Docker image build & DockerHub push
2. Connect over SSH → back up the nginx config file (NGINX_BACKUP_DIR)
3. Parse the proxy_pass port in the nginx config with awk → determine the current active port
4. Start the new container on the inactive port
5. Container health check (HTTP call to HEALTHCHECK_PATH)
6. Toggle the proxy_pass port in the nginx config to the new port with awk
7. Verify with `nginx -t`, then reload (on failure, restore the backup + remove the new container → automatic rollback)
8. Domain access check (call https://${DOMAIN_NAME} DOMAIN_CHECK_RETRIES times)
9. After IN_FLIGHT_WAIT seconds, remove the old container and clean up dangling images
10. Keep the latest NGINX_BACKUP_KEEP nginx backup files
```

### Resource naming

| Item | Format |
|------|------|
| Container | `{PROJECT_NAME}-blue` / `{PROJECT_NAME}-green` |
| Image | `{DOCKERHUB_USERNAME}/{PROJECT_NAME}:{ref_name}` |
| nginx backup file | `${NGINX_BACKUP_DIR}/server.ReverseProxy.conf.{TIMESTAMP}.bak` |

### Automatic rollback scenarios

| Failed step | Behavior |
|----------|------|
| Container health check fails | Remove the new container, keep the old one as it is |
| `nginx -t` verification fails | Restore the nginx config from the backup file + remove the new container |
| `systemctl reload/restart nginx` fails | Restore the backup, retry restart, and remove the new container if that fails |
| Domain access check fails | Warning only, the deployment continues (DNS propagation may be delayed) |

---

## Spring Boot PR Preview (Traefik)

### Workflow

**File**: `PROJECT-SPRING-PR-PREVIEW.yaml`

**Triggers**:
- Enter `@projectops pr build/destroy/status` in a PR comment
- Deleted automatically when the PR is closed

### Prerequisites

#### 1. Install the Traefik reverse proxy

```bash
# Create the Docker network
docker network create traefik-network

# Run the Traefik container
docker run -d \
  --name traefik \
  --network traefik-network \
  -p 80:80 -p 8079:8079 -p 8080:8080 \
  -v /var/run/docker.sock:/var/run/docker.sock \
  traefik:v2.10 \
  --api.dashboard=true \
  --providers.docker=true \
  --entrypoints.web.address=:8079
```

#### 2. Wildcard DNS setup

```
*.pr.suhsaechan.kr → Synology NAS IP
```

### Required GitHub Secrets

| Secret | Description |
|--------|------|
| `APPLICATION_PROD_YML` | Spring Boot production config file |
| `DOCKERHUB_USERNAME` | DockerHub user name |
| `DOCKERHUB_TOKEN` | DockerHub access token |
| `SERVER_HOST` | Synology NAS host |
| `SERVER_USER` | SSH login user name |
| `SERVER_PASSWORD` | SSH login password |

### Environment variables (edit in the workflow file)

```yaml
env:
  PROJECT_NAME: "suh-project-utility"
  JAVA_VERSION: '17'
  GRADLE_BUILD_CMD: './gradlew clean build -x test -Dspring.profiles.active=prod'
  JAR_PATH: 'Suh-Web/build/libs/*.jar'
  APPLICATION_YML_PATH: 'Suh-Web/src/main/resources/application-prod.yml'
  DOCKERFILE_PATH: './Dockerfile'
  INTERNAL_PORT: '8080'
  TRAEFIK_NETWORK: 'traefik-network'
  PREVIEW_DOMAIN_SUFFIX: 'pr.suhsaechan.kr'
  PREVIEW_PORT: '8079'
```

### Usage

Enter these commands in a PR comment:

| Command | Description |
|--------|------|
| `@projectops pr build` | Build and deploy the PR Preview |
| `@projectops pr destroy` | Delete the Preview environment |
| `@projectops pr status` | Check the current state |

### Resource naming rules

| Item | Format | Example |
|------|------|------|
| Container name | `{PROJECT_NAME}-pr-{PR number}` | `suh-project-utility-pr-123` |
| Image tag | `{DOCKERHUB_USERNAME}/{PROJECT_NAME}:pr-{PR number}` | `user/suh-project-utility:pr-123` |
| Preview URL | `http://{PROJECT_NAME}-pr-{PR number}.{DOMAIN}:{PORT}` | `http://suh-project-utility-pr-123.pr.suhsaechan.kr:8079` |

### Progress notifications

While the build runs, the PR comment is updated live with:
- Project build status
- Docker image creation status
- Server deployment and health check status
- Elapsed time

---

## Troubleshooting

### Common problems

#### SSH connection failed
```
Error: ssh: connect to host xxx port 2022: Connection refused
```
**Fix**:
1. Check that the SSH service is enabled in Synology DSM > Control Panel > Terminal & SNMP
2. Check the port number (workflow default: 2022)
3. Allow the SSH port in the firewall

#### Docker permission problem
```
Error: permission denied while trying to connect to Docker daemon
```
**Fix**:
1. Check that the SSH user is in the docker group
2. Check that the workflow uses `sudo`

#### Port conflict
```
Error: port is already allocated
```
**Fix**:
1. Find the container using that port: `docker ps`
2. Change the port or stop the existing container

### Flutter specific

#### SMB connection failed
```
Error: session setup failed: NT_STATUS_LOGON_FAILURE
```
**Fix**:
1. Check the SMB user name and password
2. Check that the SMB service is enabled (DSM > Control Panel > File Services > SMB)
3. Check access permissions on the shared folder

#### SMB path error
```
Error: tree connect failed: NT_STATUS_BAD_NETWORK_NAME
```
**Fix**:
1. Check that the `SMB_SHARE` environment variable matches the shared folder name
2. Check that the `SMB_PATH` path exists

### Spring Boot specific

#### Health check failed
```
Error: Health check timeout after 60 seconds
```
**Fix**:
1. Check how long the application takes to start (increase MAX_RETRIES if it needs more than 60 seconds)
2. Check the health check endpoint (`/actuator/health` or `/`)
3. Check the container logs: `docker logs {container_name}`

#### Traefik routing failed (PR Preview)
```
Error: 404 page not found
```
**Fix**:
1. Check that the Traefik container is running
2. Check the Docker network connection: `docker network inspect traefik-network`
3. Check the router/service state in the Traefik dashboard

### Zero-downtime deployment specific

#### Traefik Blue-Green: temporary 404 on the new container's health check
- This is a race condition while the Traefik router re-registers. If the health check retry count (`HEALTHCHECK_MAX_RETRIES`) is large enough, the next attempt passes.
- In the workflow log, check that the `Host(\`${PRODUCTION_DOMAIN}\`)` label is escaped correctly in the `🔍 Traefik 라벨 확인:` output (Korean log text, "Checking Traefik labels:").

#### Nginx Blue-Green: failed to detect the active port
```
⚠️ 활성 포트를 찾지 못함 → 기본값(BLUE=8080)을 활성으로 간주
(Could not find the active port → assuming the default (BLUE=8080) is active)
```
**Fix**:
1. Check that the `NGINX_RP_CONF` path is correct
2. Check that the `server_name` line in the config matches `${DOMAIN_NAME}` exactly
3. Keep the `proxy_pass http://127.0.0.1:{PORT};` format in the config (port number of 2 to 5 digits)

#### Nginx Blue-Green: `nginx -t` failed → backup restore
- The workflow restores the backup file automatically and removes the new container.
- The backup file is kept at `${NGINX_BACKUP_DIR}/server.ReverseProxy.conf.{TIMESTAMP}.bak`.

---

## Integration with the npx projectops wizard

### Deployment workflows are included by default

The SSH+Docker deployment workflows (SIMPLE-CICD, NONSTOP-*, PR-PREVIEW) are **included automatically with no extra option** once you select the matching project type. Just run the integration wizard:

> **Exception: Nexus library projects**: A Spring project integrated with `--nexus` (library publish) is not deployed to a server, so the server deployment workflows above are **excluded automatically**. (In the Spring source these workflows are grouped in the `spring/server-deploy/` folder, and the whole folder is skipped for a Nexus project.)

```bash
# Same on macOS / Linux / Windows
npx projectops
```

### Optional workflows (Nexus / Secret backup)

Only two workflows of a different nature are opt-in:

- **Nexus library publish** (`spring/nexus/`): publishes a library/module to a Maven repository. It is for library projects, not server deployment
- **Secret server backup** (`common/secret-backup/`): uploads GitHub Secret files to the server over SSH and keeps their history

```bash
# Recommended: npx (same options on every OS)
npx projectops --nexus --secret-backup

# Non-interactive: include both
npx projectops --publish nexus --secret-backup
```

If you run it without options, it asks interactively when the matching folder exists. The prompts are Korean wizard output, shown here with English glosses:

```
📦 Nexus 라이브러리 publish 워크플로우를 발견했습니다. (2개 파일)
   (Found the Nexus library publish workflows. (2 files))
   Nexus 라이브러리 publish 워크플로우를 포함할까요? (예/아니오)
   (Include the Nexus library publish workflows? (yes/no))

🔐 Secret 서버 백업 워크플로우를 발견했습니다. (1개 파일)
   (Found the Secret server backup workflow. (1 file))
   Secret 서버 백업 워크플로우를 포함할까요? (예/아니오)
   (Include the Secret server backup workflow? (yes/no))
```

### Saved settings

The options you choose are saved in `version.yml`:

```yaml
metadata:
  template:
    options:
      nexus: false          # Whether Nexus publish is included
      secret_backup: false  # Whether Secret backup is included
```

On re-integration, the previous settings are detected and applied automatically.

---

## Related documents

- [TEMPLATE-INTEGRATOR.md](../TEMPLATE-INTEGRATOR.md) - Template integration script guide
- [flutter-cicd-overview.md](./flutter-cicd-overview.md) - Full Flutter CI/CD guide

---

## SSH authentication methods and deploying to other servers (AWS EC2 and others)

These deployment workflows are not Synology-only. They are a general-purpose engine that deploys Docker containers to **any server reachable over SSH**. The server type is decided by the `SSH_AUTH_METHOD` environment variable and the Secrets you register.

### Choosing the authentication method (`SSH_AUTH_METHOD`)

Choose the authentication method with the `SSH_AUTH_METHOD` value in the workflow `env` (the integration wizard asks about it, and the default is `password`).

| Value | Secret used | sudo handling | Suited for |
|----|-------------|-----------|-------------|
| `password` | `SERVER_PASSWORD` | `echo $PW \| sudo -S` | Synology NAS, general servers that need a sudo password |
| `key` | `SSH_KEY` (.pem contents) | passwordless `sudo` | AWS EC2, GCP, VPS with passwordless sudo configured |

### Deploying to AWS EC2

1. Set `SSH_AUTH_METHOD: "key"` in the workflow `env` (or choose `key` in the integration wizard).
2. Register these GitHub Secrets:
   - `SERVER_HOST`: the EC2 public IP or domain
   - `SERVER_USER`: `ubuntu` (Ubuntu AMI) or `ec2-user` (Amazon Linux)
   - `SSH_KEY`: paste the **entire contents** of the EC2 key pair `.pem` file as it is
   - `SSH_PORT`: usually `22` (set SSH_PORT in the workflow env to 22)
3. Allow SSH access from GitHub Actions in the EC2 security group, and Docker must be installed on the server.
4. Databases (PostgreSQL/Redis/Mongo and so on) are assumed to be running on the server already. This workflow replaces **only the app container**.

### Adding a new server type

`SSH_AUTH_METHOD` supports two values, `password` and `key`. If the new server uses one of those two, **you do not need to duplicate the workflow**. Just set that value and the Secrets. If you need server-specific logic beyond authentication and paths, add a branch on the `SSH_AUTH_METHOD` value in the `script:` body.
