# SSH + Docker 배포 가이드

SSH로 접속 가능한 모든 서버(Synology NAS·AWS EC2·GCP·일반 VPS 등)에 애플리케이션을 자동 배포하는 워크플로우 사용 가이드입니다.

---

## 개요

projectops은 "SSH 접속 → Docker 이미지 pull → 컨테이너 교체" 패턴의 배포 워크플로우를 제공합니다. 배포처가 Synology든 AWS EC2든 동일한 워크플로우 하나로 커버하며, 차이는 `SSH_AUTH_METHOD`(password/key)와 경로 설정뿐입니다.

| 워크플로우 | 프로젝트 타입 | 용도 |
|-----------|-------------|------|
| `PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD` | Flutter | APK 빌드 후 SMB로 서버 업로드 |
| `PROJECT-SPRING-SIMPLE-CICD` | Spring Boot | Docker 이미지 빌드 및 배포 (기본, 단일 컨테이너) |
| `PROJECT-SPRING-NONSTOP-TRAEFIK-CICD` | Spring Boot | 무중단 배포 (Traefik Blue-Green, opt-in) |
| `PROJECT-SPRING-NONSTOP-NGINX-CICD` | Spring Boot | 무중단 배포 (Nginx Blue-Green, opt-in) |
| `PROJECT-SPRING-PR-PREVIEW` | Spring Boot | PR별 Preview 환경 자동 생성 |
| `PROJECT-PYTHON-SIMPLE-CICD` | Python (FastAPI/Django) | Docker 이미지 빌드 및 배포 (단일 컨테이너) |
| `PROJECT-PYTHON-PR-PREVIEW` | Python (FastAPI/Django) | PR별 Preview 환경 자동 생성 |

> **서버 배포 워크플로우는 `--deploy docker-ssh`(기본값)일 때 포함**됩니다. 각 타입의 `project-types/<type>/server-deploy/` 폴더에 있으며, `--deploy vercel` 또는 `--deploy none`을 고르면 폴더째 제외됩니다.
> 라이브러리 publish는 `--publish nexus,npm,github-packages`, Secret 백업은 `--secret-backup`으로 선택합니다. (구 `--nexus`/`--npm-publish` 플래그는 deprecated이며 경고와 함께 신 축으로 해석됩니다.)
> **무중단 배포 옵션**은 기본 `SIMPLE-CICD` 와 함께 배포되며, 사용자가 명시적으로 전환할 때만 활성화됩니다 (트리거 주석 처리 상태).
>
> Python 배포 워크플로우는 Spring의 `SIMPLE-CICD` / `PR-PREVIEW`와 **동일한 SSH+Docker 엔진**을 쓰며 Secret과 env 구조도 같습니다. 아래 Spring 절의 설명을 그대로 적용하되, 빌드 단계(Gradle → pip/uv)와 헬스체크 기본값(`/actuator/health` → `/docs`, 로그 패턴 `Uvicorn running on`)만 다릅니다.

---

## 멀티 프로젝트 타입 배포 시

단일 레포에 여러 타입(예: Spring 백엔드 + Python AI)이 공존해 여러 CICD 워크플로우가 함께 설치된 경우, 같은 서버에 배포하므로 리소스 충돌을 막기 위해 각 워크플로우의 env를 **서로 다른 값**으로 설정해야 합니다.

- 각 워크플로우의 `PROJECT_NAME`, `CONTAINER_NAME`, `DEPLOY_PORT`(또는 `PROJECT_DEPLOY_PORT`)를 타입별로 분리합니다.
- 동일 서버에 같은 포트로 두 컨테이너를 배포할 수 없습니다 (`port is already allocated`).
- 예: Spring 백엔드 `8096`, Python AI `8092` 등으로 포트를 분리한 뒤 사용합니다.

| 항목 | Spring 백엔드 | Python AI |
|------|--------------|-----------|
| `PROJECT_NAME` | `myapp-back` | `myapp-ai` |
| `DEPLOY_PORT` | `8096` | `8092` |

> CI 워크플로우(`*-CI.yaml`)는 멀티타입에서 develop 푸시 한 번에 모두 발화합니다. 필요 없는 타입의 CI는 트리거를 주석 처리하거나 파일을 삭제하세요. 타입·경로 설정은 [NPX 마법사 가이드](NPX-WIZARD.md)를 참고하세요.

---

## 사전 준비

### 1. 서버 설정 (예: Synology NAS)

> 아래는 Synology NAS(DSM) 기준 예시입니다. AWS EC2·GCP·VPS 등 다른 서버는 해당 OS에 맞게 Docker 설치·SSH 활성화를 진행하세요. AWS EC2 설정은 문서 하단 "다른 서버(AWS EC2 등) 배포" 섹션을 참고하세요.

#### Docker 패키지 설치 (Spring Boot 배포용)
1. DSM > 패키지 센터 > Docker 설치
2. Docker 컨테이너 관리 권한 확인

#### SSH 활성화
1. DSM > 제어판 > 터미널 및 SNMP > SSH 서비스 활성화
2. 포트: 기본 22 또는 커스텀 (워크플로우 기본값: 2022)
3. 관리자 계정 SSH 접속 허용

#### SMB 공유 폴더 설정 (Flutter APK 업로드용)
1. DSM > 제어판 > 공유 폴더 > 새 공유 폴더 생성
2. SMB 서비스 활성화 (제어판 > 파일 서비스 > SMB)
3. 포트: 기본 445 또는 커스텀 (예: 44445)

### 2. GitHub Secrets 공통 설정

모든 배포 워크플로우에서 공통으로 사용하는 Secrets:

| Secret | 설명 | 예시 |
|--------|------|------|
| `SERVER_HOST` | 서버 IP 또는 도메인 (예: Synology NAS, AWS EC2) | `192.168.1.100` 또는 `nas.example.com` |
| `SERVER_USER` | SSH/SMB 접속 사용자명 | `admin` |
| `SERVER_PASSWORD` | SSH/SMB 접속 비밀번호 | `{PASSWORD}` |

---

## Flutter Android 배포 (SMB)

### 워크플로우

**파일**: `PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD.yaml`

**트리거**:
- `main` 브랜치 푸시
- CHANGELOG 워크플로우 완료 후 자동 실행
- 수동 실행 (workflow_dispatch)

### 필수 GitHub Secrets

| Secret | 설명 |
|--------|------|
| `SERVER_HOST` | Synology NAS 호스트 |
| `SERVER_USER` | SMB 접속 사용자명 |
| `SERVER_PASSWORD` | SMB 접속 비밀번호 |
| `DEBUG_KEYSTORE` | Android Debug Keystore (Base64 인코딩) |
| `ENV_FILE` | Flutter .env 파일 내용 |
| `GOOGLE_SERVICES_JSON` | Firebase google-services.json 내용 |

### 환경변수 설정 (워크플로우 파일 내 수정)

```yaml
env:
  PROJECT_NAME: "your-project"      # 프로젝트명 (APK 파일명에 사용)
  FLUTTER_VERSION: "3.35.5"         # Flutter 버전
  JAVA_VERSION: "17"                # Java 버전
  SMB_PORT: "44445"                 # SMB 포트 (기본 445)
  SMB_SHARE: "web"                  # SMB 공유 폴더명
  SMB_PATH_ANDROID: "/android/download"  # APK 저장 경로
```

### 배포 프로세스

```
1. Flutter APK 빌드 (Fastlane)
2. APK 파일명 변경: {PROJECT_NAME}-v{VERSION}-{COMMIT_HASH}.apk
3. SMB로 Synology NAS에 업로드
4. 빌드 히스토리 JSON 업데이트
```

### 배포 결과

APK 파일 경로: `//{SERVER_HOST}/{SMB_SHARE}/{PROJECT_NAME}/android/download/`

히스토리 파일: `{PROJECT_NAME}-android-cicd-history.json`

---

## Spring Boot 단순 배포 (Docker)

### 워크플로우

**파일**: `PROJECT-SPRING-SIMPLE-CICD.yaml`

**트리거**:
- `main` 브랜치 푸시 (운영 환경)
- 수동 실행 (workflow_dispatch)

### 필수 GitHub Secrets

| Secret | 설명 |
|--------|------|
| `APPLICATION_PROD_YML` | Spring Boot 운영 설정 파일 내용 |
| `DOCKERHUB_USERNAME` | DockerHub 사용자명 |
| `DOCKERHUB_TOKEN` | DockerHub 액세스 토큰 |
| `SERVER_HOST` | Synology NAS 호스트 |
| `SERVER_USER` | SSH 접속 사용자명 |
| `SERVER_PASSWORD` | SSH 접속 비밀번호 |

### 환경변수 설정 (워크플로우 파일 내 수정)

```yaml
env:
  PROJECT_NAME: "project"           # 프로젝트명
  DOCKER_IMAGE_PREFIX: "back-container"
  SPRING_PROFILE: "prod"
  JAVA_VERSION: "17"
```

### 브랜치별 배포

| 브랜치 | 포트 | 컨테이너명 |
|--------|-----|-----------|
| main | 8080 (기본, `DEPLOY_PORT`) | `{PROJECT_NAME}-back-deploy` |

### 배포 프로세스

```
1. Gradle 빌드 (테스트 제외)
2. Docker 이미지 빌드 및 DockerHub 푸시
3. SSH로 Synology NAS 접속
4. Docker 이미지 Pull
5. 기존 컨테이너 제거 후 새 컨테이너 실행
```

---

## Spring Boot 무중단 배포 (Traefik Blue-Green)

> 기본 `SIMPLE-CICD` 와 동일한 Secrets 를 사용하며, Traefik 라벨 기반 Blue-Green 토글로 다운타임 없는 배포를 제공합니다.

### 워크플로우

**파일**: `PROJECT-SPRING-NONSTOP-TRAEFIK-CICD.yaml`

**트리거** (기본 비활성):
- `workflow_dispatch` (수동 실행)
- push 트리거는 주석 처리됨 (`# push: / #   branches: / #     - main`) — 전환 시 주석 해제하면 `main` 브랜치 push 시 배포되며, 동시에 `SIMPLE-CICD` 의 push 트리거를 주석 처리해 중복 실행을 막아야 함

### 사전 요구사항

#### 1. Traefik 리버스 프록시 설치

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

#### 2. DSM 역방향 프록시 매핑

```
${PRODUCTION_DOMAIN}:443 → localhost:${TRAEFIK_INTERNAL_PORT}  (기본 8079)
```

### 필수 GitHub Secrets

`SIMPLE-CICD` 와 동일.

| Secret | 설명 |
|--------|------|
| `APPLICATION_PROD_YML` | application-prod.yml 내용 |
| `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` | DockerHub 인증 |
| `SERVER_HOST` / `SERVER_USER` / `SERVER_PASSWORD` | SSH 접속 |

### 주요 env 설정

```yaml
env:
  PROJECT_NAME: "mapsy-back"
  PRODUCTION_DOMAIN: "example.com"
  TRAEFIK_NETWORK: "traefik-network"
  TRAEFIK_ENTRYPOINT: "web"
  TRAEFIK_INTERNAL_PORT: "8079"
  EXTRA_NETWORKS: ""                 # 예: "selenium-chrome-network"
  HEALTHCHECK_PATH: "/"
  HEALTHCHECK_ACCEPT_CODES: "200|301|302|308"
  HEALTHCHECK_MAX_RETRIES: "36"
  HEALTHCHECK_RETRY_INTERVAL: "5"
  IN_FLIGHT_WAIT: "10"
```

### 배포 프로세스

```
1. Gradle 빌드 + Docker 이미지 빌드 & DockerHub Push
2. SSH 로 Synology 접속 → Traefik 라벨 부착 컨테이너 검색 → active 색 판별
3. 반대 색(blue/green) 으로 신규 컨테이너 기동 (Traefik 라벨 자동 등록)
4. EXTRA_NETWORKS 가 있으면 추가 docker network connect
5. Traefik 통한 GET 호출로 헬스체크 (HEALTHCHECK_ACCEPT_CODES 매칭 시 통과)
   실패 시 신규 컨테이너 유지 + old 그대로 → 사실상 자동 롤백
6. IN_FLIGHT_WAIT 초 후 old 컨테이너 제거 + dangling 이미지 정리
```

### 리소스 네이밍

| 항목 | 형식 |
|------|------|
| 컨테이너 | `{PROJECT_NAME}-blue` / `{PROJECT_NAME}-green` |
| 이미지 | `{DOCKERHUB_USERNAME}/{PROJECT_NAME}:{ref_name}` |
| Traefik router/service | `{PROJECT_NAME}` |

---

## Spring Boot 무중단 배포 (Nginx Blue-Green)

> 기본 `SIMPLE-CICD` 와 동일한 Secrets 를 사용하며, nginx config 의 `proxy_pass` 포트 토글로 Blue-Green 무중단 배포를 제공합니다. Traefik 미설치 환경에서 사용합니다.

### 워크플로우

**파일**: `PROJECT-SPRING-NONSTOP-NGINX-CICD.yaml`

**트리거** (기본 비활성):
- `workflow_dispatch` (수동 실행)
- push 트리거는 주석 처리됨 (`# push: / #   branches: / #     - main`) — 전환 시 주석 해제하면 `main` 브랜치 push 시 배포되며, 동시에 `SIMPLE-CICD` 의 push 트리거를 주석 처리해 중복 실행을 막아야 함

### 사전 요구사항

#### 1. nginx 설치 + sites-enabled config 존재

config 의 server 블록에 다음 라인이 존재해야 합니다:

```nginx
server {
    listen 443 ssl;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:8080;   # BLUE_PORT (또는 GREEN_PORT)
        # ...
    }
}
```

#### 2. SSH 사용자 권한

- `sudo nginx -t`, `sudo systemctl reload nginx`, `sudo docker ...` 실행 가능
- nginx config 파일 및 백업 디렉토리 쓰기 권한

### 필수 GitHub Secrets

`SIMPLE-CICD` 와 동일.

### 주요 env 설정

```yaml
env:
  PROJECT_NAME: "mapsy-back"
  DOMAIN_NAME: "example.com"                                  # nginx server_name 과 일치
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

### 배포 프로세스

```
1. Gradle 빌드 + Docker 이미지 빌드 & DockerHub Push
2. SSH 접속 → nginx config 파일 백업 (NGINX_BACKUP_DIR)
3. nginx config 의 proxy_pass 포트 awk 파싱 → 현재 active 포트 판별
4. 비활성 포트로 신규 컨테이너 기동
5. 컨테이너 헬스체크 (HEALTHCHECK_PATH HTTP 호출)
6. nginx config 의 proxy_pass 포트를 신규 포트로 awk 토글
7. `nginx -t` 검증 후 reload (실패 시 백업 복구 + 신규 컨테이너 제거 → 자동 롤백)
8. 도메인 접근 검증 (DOMAIN_CHECK_RETRIES 회 https://${DOMAIN_NAME} 호출)
9. IN_FLIGHT_WAIT 초 후 old 컨테이너 제거 + dangling 이미지 정리
10. nginx 백업 파일 최신 NGINX_BACKUP_KEEP 개 보존
```

### 리소스 네이밍

| 항목 | 형식 |
|------|------|
| 컨테이너 | `{PROJECT_NAME}-blue` / `{PROJECT_NAME}-green` |
| 이미지 | `{DOCKERHUB_USERNAME}/{PROJECT_NAME}:{ref_name}` |
| nginx 백업 파일 | `${NGINX_BACKUP_DIR}/server.ReverseProxy.conf.{TIMESTAMP}.bak` |

### 자동 롤백 시나리오

| 실패 단계 | 동작 |
|----------|------|
| 컨테이너 헬스체크 실패 | 신규 컨테이너 제거 — old 그대로 유지 |
| `nginx -t` 검증 실패 | 백업 파일로 nginx config 복구 + 신규 컨테이너 제거 |
| `systemctl reload/restart nginx` 실패 | 백업 복구 후 restart 재시도, 실패 시 신규 컨테이너 제거 |
| 도메인 접근 검증 실패 | 경고만 — 배포는 진행 (DNS 전파 지연 가능성) |

---

## Spring Boot PR Preview (Traefik)

### 워크플로우

**파일**: `PROJECT-SPRING-PR-PREVIEW.yaml`

**트리거**:
- PR 코멘트에 `@projectops pr build/destroy/status` 입력
- PR 종료 시 자동 삭제

### 사전 요구사항

#### 1. Traefik 리버스 프록시 설치

```bash
# Docker 네트워크 생성
docker network create traefik-network

# Traefik 컨테이너 실행
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

#### 2. 와일드카드 DNS 설정

```
*.pr.suhsaechan.kr → Synology NAS IP
```

### 필수 GitHub Secrets

| Secret | 설명 |
|--------|------|
| `APPLICATION_PROD_YML` | Spring Boot 운영 설정 파일 |
| `DOCKERHUB_USERNAME` | DockerHub 사용자명 |
| `DOCKERHUB_TOKEN` | DockerHub 액세스 토큰 |
| `SERVER_HOST` | Synology NAS 호스트 |
| `SERVER_USER` | SSH 접속 사용자명 |
| `SERVER_PASSWORD` | SSH 접속 비밀번호 |

### 환경변수 설정 (워크플로우 파일 내 수정)

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

### 사용법

PR 코멘트에 다음 명령어 입력:

| 명령어 | 설명 |
|--------|------|
| `@projectops pr build` | PR Preview 빌드 및 배포 |
| `@projectops pr destroy` | Preview 환경 삭제 |
| `@projectops pr status` | 현재 상태 확인 |

### 리소스 네이밍 규칙

| 항목 | 형식 | 예시 |
|------|------|------|
| 컨테이너명 | `{PROJECT_NAME}-pr-{PR번호}` | `suh-project-utility-pr-123` |
| 이미지 태그 | `{DOCKERHUB_USERNAME}/{PROJECT_NAME}:pr-{PR번호}` | `user/suh-project-utility:pr-123` |
| Preview URL | `http://{PROJECT_NAME}-pr-{PR번호}.{DOMAIN}:{PORT}` | `http://suh-project-utility-pr-123.pr.suhsaechan.kr:8079` |

### 진행 상황 알림

빌드 중 PR에 실시간 댓글 업데이트:
- 프로젝트 빌드 상태
- Docker 이미지 생성 상태
- 서버 배포 및 Health Check 상태
- 소요 시간 표시

---

## 트러블슈팅

### 공통 문제

#### SSH 연결 실패
```
Error: ssh: connect to host xxx port 2022: Connection refused
```
**해결**:
1. Synology DSM > 제어판 > 터미널 및 SNMP > SSH 서비스 활성화 확인
2. 포트 번호 확인 (워크플로우 기본값: 2022)
3. 방화벽에서 SSH 포트 허용

#### Docker 권한 문제
```
Error: permission denied while trying to connect to Docker daemon
```
**해결**:
1. SSH 사용자가 docker 그룹에 포함되어 있는지 확인
2. 워크플로우에서 `sudo` 사용 확인

#### 포트 충돌
```
Error: port is already allocated
```
**해결**:
1. 해당 포트를 사용 중인 컨테이너 확인: `docker ps`
2. 포트 변경 또는 기존 컨테이너 중지

### Flutter 특화

#### SMB 연결 실패
```
Error: session setup failed: NT_STATUS_LOGON_FAILURE
```
**해결**:
1. SMB 사용자명/비밀번호 확인
2. SMB 서비스 활성화 확인 (DSM > 제어판 > 파일 서비스 > SMB)
3. 공유 폴더 접근 권한 확인

#### SMB 경로 오류
```
Error: tree connect failed: NT_STATUS_BAD_NETWORK_NAME
```
**해결**:
1. `SMB_SHARE` 환경변수가 공유 폴더명과 일치하는지 확인
2. `SMB_PATH` 경로가 존재하는지 확인

### Spring Boot 특화

#### 헬스체크 실패
```
Error: Health check timeout after 60 seconds
```
**해결**:
1. 애플리케이션 기동 시간 확인 (60초 이상 필요 시 MAX_RETRIES 증가)
2. 헬스체크 엔드포인트 확인 (`/actuator/health` 또는 `/`)
3. 컨테이너 로그 확인: `docker logs {container_name}`

#### Traefik 라우팅 실패 (PR Preview)
```
Error: 404 page not found
```
**해결**:
1. Traefik 컨테이너 실행 중인지 확인
2. Docker 네트워크 연결 확인: `docker network inspect traefik-network`
3. Traefik 대시보드에서 라우터/서비스 상태 확인

### 무중단 배포 특화

#### Traefik Blue-Green: 새 컨테이너 헬스체크 일시적 404
- Traefik 라우터 재등록 race condition. 헬스체크 재시도(`HEALTHCHECK_MAX_RETRIES`)가 충분히 크면 다음 시도에서 통과합니다.
- 워크플로우 로그의 `🔍 Traefik 라벨 확인:` 출력에서 `Host(\`${PRODUCTION_DOMAIN}\`)` 라벨이 정상 escape 되었는지 확인.

#### Nginx Blue-Green: 활성 포트 탐지 실패
```
⚠️ 활성 포트를 찾지 못함 → 기본값(BLUE=8080)을 활성으로 간주
```
**해결**:
1. `NGINX_RP_CONF` 경로가 정확한지 확인
2. config 의 `server_name` 라인이 `${DOMAIN_NAME}` 과 정확히 일치하는지 확인
3. config 의 `proxy_pass http://127.0.0.1:{PORT};` 형식 유지 (포트 번호 2~5자리)

#### Nginx Blue-Green: `nginx -t` 실패 → 백업 복구
- 워크플로우가 자동으로 백업 파일로 복구하고 신규 컨테이너를 제거합니다.
- 백업 파일은 `${NGINX_BACKUP_DIR}/server.ReverseProxy.conf.{TIMESTAMP}.bak` 에 보존됩니다.

---

## npx projectops 마법사 연동

### 배포 워크플로우는 기본 포함

SSH+Docker 배포 워크플로우(SIMPLE-CICD, NONSTOP-*, PR-PREVIEW)는 해당 프로젝트 타입을 선택하면 **별도 옵션 없이 자동 포함**됩니다. 통합 마법사를 그냥 실행하면 됩니다:

> **예외 — Nexus 라이브러리 프로젝트**: `--nexus`(라이브러리 publish)로 통합하는 Spring 프로젝트는 서버에 배포하지 않으므로, 위 서버 배포 워크플로우가 **자동으로 제외**됩니다. (Spring 원본에서 이 워크플로우들은 `spring/server-deploy/` 폴더로 묶여 있고, Nexus 프로젝트일 때 폴더째 건너뜁니다.)

```bash
# macOS / Linux / Windows 공통
npx projectops
```

### 선택 워크플로우 (Nexus / Secret 백업)

성격이 다른 두 워크플로우만 opt-in입니다:

- **Nexus 라이브러리 publish** (`spring/nexus/`): 라이브러리/모듈을 Maven 저장소에 배포 — 서버 배포가 아니라 라이브러리 프로젝트용
- **Secret 서버 백업** (`common/secret-backup/`): GitHub Secret 파일을 SSH로 서버에 업로드·이력관리

```bash
# 권장 — npx (OS 공통, 옵션 동일)
npx projectops --nexus --secret-backup

# 비대화형 — 둘 다 포함
npx projectops --publish nexus --secret-backup
```

옵션 없이 실행하면, 해당 폴더가 있을 경우 대화형으로 질문이 표시됩니다:

```
📦 Nexus 라이브러리 publish 워크플로우를 발견했습니다. (2개 파일)
   Nexus 라이브러리 publish 워크플로우를 포함할까요? (예/아니오)

🔐 Secret 서버 백업 워크플로우를 발견했습니다. (1개 파일)
   Secret 서버 백업 워크플로우를 포함할까요? (예/아니오)
```

### 설정 저장

선택한 옵션은 `version.yml`에 저장됩니다:

```yaml
metadata:
  template:
    options:
      nexus: false          # Nexus publish 포함 여부
      secret_backup: false  # Secret 백업 포함 여부
```

재통합 시 이전 설정이 자동으로 감지되어 적용됩니다.

---

## 관련 문서

- [TEMPLATE-INTEGRATOR.md](TEMPLATE-INTEGRATOR.md) - 템플릿 통합 스크립트 가이드
- [FLUTTER-CICD-OVERVIEW.md](FLUTTER-CICD-OVERVIEW.md) - Flutter CI/CD 전체 가이드

---

## SSH 인증 방식과 다른 서버(AWS EC2 등) 배포

이 배포 워크플로우는 Synology 전용이 아니라, **SSH로 접속 가능한 모든 서버**에 Docker 컨테이너를 배포하는 범용 엔진이다. 서버 종류는 `SSH_AUTH_METHOD` 환경변수와 등록하는 Secret으로 결정된다.

### 인증 방식 선택 (`SSH_AUTH_METHOD`)

워크플로우 `env`의 `SSH_AUTH_METHOD` 값으로 인증 방식을 고른다 (통합 마법사가 질문하며, 기본값은 `password`).

| 값 | 사용 Secret | sudo 처리 | 적합한 서버 |
|----|-------------|-----------|-------------|
| `password` | `SERVER_PASSWORD` | `echo $PW \| sudo -S` | Synology NAS, sudo 비밀번호가 필요한 일반 서버 |
| `key` | `SSH_KEY` (.pem 내용) | passwordless `sudo` | AWS EC2, GCP, passwordless sudo 설정된 VPS |

### AWS EC2에 배포하기

1. 워크플로우 `env`에서 `SSH_AUTH_METHOD: "key"`로 설정 (또는 통합 마법사에서 `key` 선택).
2. GitHub Secrets에 다음을 등록:
   - `SERVER_HOST`: EC2 퍼블릭 IP 또는 도메인
   - `SERVER_USER`: `ubuntu` (Ubuntu AMI) 또는 `ec2-user` (Amazon Linux)
   - `SSH_KEY`: EC2 키페어 `.pem` 파일의 **전체 내용**을 그대로 붙여넣기
   - `SSH_PORT`: 보통 `22` (워크플로우 env의 SSH_PORT를 22로 조정)
3. EC2 보안 그룹에서 GitHub Actions의 SSH 접근을 허용하고, 서버에 Docker가 설치돼 있어야 한다.
4. DB(PostgreSQL/Redis/Mongo 등)는 서버에 미리 떠 있다고 가정한다. 이 워크플로우는 **앱 컨테이너만** 교체한다.

### 새로운 서버 유형을 추가하려면

`SSH_AUTH_METHOD`는 `password`/`key` 두 가지를 지원한다. 새 서버가 둘 중 하나의 인증을 쓴다면 **워크플로우를 복제할 필요 없이** 해당 값과 Secret만 설정하면 된다. 인증·경로 외에 서버별 특수 로직이 필요하면 `script:` 본문에서 `SSH_AUTH_METHOD` 값으로 분기를 추가한다.
