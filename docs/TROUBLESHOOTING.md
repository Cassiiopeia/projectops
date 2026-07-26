# 트러블슈팅

자주 발생하는 문제와 해결 방법을 정리했습니다.

---

## GitHub Actions 관련

### 워크플로우 실행 안됨

**증상**: 푸시해도 워크플로우가 트리거되지 않음

**확인 사항**:
```
1. Actions 탭에서 워크플로우 활성화 여부 확인
2. 브랜치 이름이 트리거 조건과 일치하는지 확인
3. paths-ignore에 해당 파일이 포함되어 있는지 확인
```

**해결**:
```
Settings → Actions → General
→ "Allow all actions and reusable workflows" 선택
```

---

### GitHub 토큰 권한 오류

**증상**:
```
remote: Permission to ... denied to github-actions[bot]
```

**원인**: `_GITHUB_PAT_TOKEN`이 없거나 권한 부족

**해결**:
```
1. GitHub → Settings → Developer settings
   → Personal access tokens (Classic)

2. 토큰 생성
   - Scopes: repo, workflow 체크

3. Repository Settings → Secrets and variables → Actions
   → New repository secret
   - Name: _GITHUB_PAT_TOKEN
   - Value: [생성한 토큰]
```

---

### PR 자동 머지 실패

**증상**: PR이 생성되었으나 자동으로 머지되지 않음

**확인 사항**:
```
1. Repository Settings → General → Pull Requests
   → "Allow auto-merge" 체크

2. Branch protection rule이 너무 엄격한지 확인
   (required reviews, status checks 등)

3. Organization 설정 확인
   Settings → Actions → General
   → "Allow GitHub Actions to create and approve pull requests" 체크
```

---

## 버전 관리 관련

### 버전 동기화 실패

**증상**: 여러 파일의 버전이 불일치

**해결**:
```bash
# 수동 동기화
.github/scripts/version_manager.sh sync
```

---

### Git 태그 중복

**증상**: `tag 'v1.0.0' already exists` 에러

**해결**:
```bash
# 원격 태그 삭제
git push origin :refs/tags/v1.0.0

# 로컬 태그 삭제
git tag -d v1.0.0

# 다시 푸시
git push
```

---

### 스크립트 권한 오류

**증상**: `bash: permission denied`

**해결**:
```bash
chmod +x .github/scripts/version_manager.sh
chmod +x .github/scripts/changelog_manager.py
git add .github/scripts/
git commit -m "fix: add execute permission to scripts"
```

---

## 체인지로그 관련

### 체인지로그 생성 안됨

**증상**: PR 머지 후에도 CHANGELOG가 업데이트 안됨

**확인 사항**:
```
1. 릴리스 PR이 develop → main 으로 열렸는지 확인
   (head가 develop이 아니면 파이프라인 전체가 스킵됩니다)

2. PR을 "새로 연" 게 맞는지 확인
   (트리거는 opened 뿐이라 기존 PR에 재푸시해도 재실행되지 않습니다)

3. version.yml의 changelog provider 확인
   - coderabbit(미설정 시 기본): CodeRabbit 앱 설치 + Summary 작성 여부
   - github-ai / openai 계열 / commit: 해당 provider 요구사항 충족 여부

4. Secret 설정 확인
   - _GITHUB_PAT_TOKEN (공통)
   - MODEL_API_KEY (openai/gemini/claude provider일 때)

5. Actions 로그에서 fallback-summary job이 어느 provider로 완주했는지 확인
```

> provider 사다리(선택 provider → github-ai → commit) 덕분에 릴리스 노트가 완전히 비는 일은 없습니다. 상세는 [체인지로그 자동화](CHANGELOG-AUTOMATION.md#릴리스-노트-provider-사다리) 참조.

---

### Summary 파싱 실패

**증상**: `Could not parse CodeRabbit summary`

**해결**:
```
1. PR 댓글에서 CodeRabbit Summary 확인
2. HTML 형식이 깨지지 않았는지 확인
3. 수동으로 CHANGELOG 업데이트 가능:
   python3 .github/scripts/changelog_manager.py generate-md
```

---

## PR Preview 관련

### 빌드 실패

**증상**: `@projectops server build` 후 에러

**확인 사항**:
```
1. Actions 로그 확인
2. Dockerfile 경로 확인 (./Dockerfile 기본)
3. Secrets 설정 확인:
   - SERVER_HOST
   - SERVER_USER
   - SERVER_PASSWORD
   - DOCKER_REGISTRY_URL
   - DOCKER_USERNAME
   - DOCKER_PASSWORD
```

---

### Health Check 실패

**증상**: 배포 완료 후 "Health check failed"

**해결**:
```yaml
# 워크플로우에서 Health Check 설정 확인
env:
  HEALTH_CHECK_PATH: '/actuator/health'  # Spring
  # 또는
  HEALTH_CHECK_LOG_PATTERN: 'Started .* in [0-9.]+ seconds'
```

**Spring에서 Actuator 활성화**:
```gradle
// build.gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

---

### Issue에서 브랜치 못 찾음

**증상**: "브랜치를 찾을 수 없습니다"

**확인 사항**:
```
1. Issue Helper 댓글이 있는지 확인
2. 해당 브랜치가 푸시되었는지 확인:
   git branch -r | grep [브랜치명]
3. ISSUE_HELPER_MARKER 값이 올바른지 확인
```

---

### 컨테이너 삭제 안됨

**증상**: Issue/PR 닫아도 컨테이너가 남아있음

**수동 삭제** (Synology SSH):
```bash
# 컨테이너 삭제
docker stop project-pr-123
docker rm project-pr-123

# 이미지 삭제
docker rmi registry/project-pr-123:latest
```

---

## SSH + Docker 배포 관련

> 배포 엔진은 특정 벤더 전용이 아닙니다. Synology NAS, AWS EC2, 일반 Linux 등 SSH 접속이 가능한 서버라면 동일하게 동작합니다. 상세는 [SSH+Docker 배포 가이드](SSH-DOCKER-DEPLOYMENT-GUIDE.md) 참조.

### SSH 연결 실패

**증상**: `Connection refused` 또는 `Permission denied`

**확인 사항**:
```
1. 서버에서 SSH 서비스 활성화
   (Synology의 경우: 제어판 → 터미널 및 SNMP → SSH 서비스 활성화)

2. 인증 방식(SSH_AUTH_METHOD)과 Secret이 짝이 맞는지 확인
   - password → SERVER_PASSWORD
   - key      → SSH_KEY (.pem 파일 전체 내용)

3. Secrets 값 확인
   - SERVER_HOST: IP 또는 도메인
   - SERVER_USER: 접속 계정

4. 워크플로우의 SSH_PORT 값과 서버의 실제 SSH 포트가 일치하는지 확인
   (템플릿 기본값은 22가 아니라 2022입니다 — 서버에 맞게 수정하세요)

5. 방화벽에서 해당 SSH 포트 허용
```

---

### Docker 레지스트리 인증 실패

**증상**: `unauthorized: authentication required`

**해결**:
```bash
# 배포 서버에 SSH로 접속해 직접 로그인 테스트
docker login [REGISTRY_URL] -u [USERNAME] -p [PASSWORD]
```

DockerHub를 쓰는 워크플로우는 `DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN` Secret을 확인하세요.

---

## Flutter 관련

### iOS 빌드 실패

**증상**: Provisioning profile 오류

**확인 사항**:
```
1. APPLE_PROVISIONING_PROFILE_BASE64 값 확인
2. Profile이 만료되지 않았는지 확인
3. Bundle ID가 일치하는지 확인
```

---

### Android 서명 오류

**증상**: `keystore was tampered with`

**확인 사항**:
```
1. RELEASE_KEYSTORE_BASE64 인코딩 확인
   base64 -w 0 keystore.jks > keystore_base64.txt

2. 비밀번호가 올바른지 확인
   - RELEASE_KEYSTORE_PASSWORD
   - RELEASE_KEY_PASSWORD
```

---

## Organization 설정 체크리스트

Organization 저장소에서 자동화가 작동하지 않을 때:

```
Settings → Actions → General
├── ✅ Allow all actions and reusable workflows
├── ✅ Allow GitHub Actions to create and approve pull requests
└── ✅ Read and write permissions

Settings → General → Pull Requests
├── ✅ Allow auto-merge
├── ✅ Allow squash merging
└── ✅ Automatically delete head branches
```

---

## 디버깅 방법

### Actions 로그 확인

```
GitHub → Actions 탭 → 실패한 워크플로우 클릭
→ 각 Job 확장하여 상세 로그 확인
```

### 버전 파일 상태 진단

```bash
# 모든 버전 파일 상태 확인 (읽기만 하며 파일을 바꾸지 않음)
.github/scripts/version_manager.sh get

# 버전 형식 검증
.github/scripts/version_manager.sh validate 1.2.3

# 실제 동기화 (파일을 수정함 — 미리보기 옵션은 없습니다)
.github/scripts/version_manager.sh sync
```

> ⚠️ `version_manager`는 `--dry-run` 같은 옵션을 지원하지 않습니다. `sync`는 항상 실제로 파일을 수정하므로, 상태만 보고 싶으면 `get`을 사용하세요.

### 수동 워크플로우 실행

```
Actions → 해당 워크플로우 → Run workflow
→ 수동으로 트리거하여 테스트
```

---

## 도움 요청

문제가 해결되지 않으면:

1. [GitHub Issues](https://github.com/Cassiiopeia/projectops/issues) 에서 검색
2. 새 이슈 생성 시 다음 정보 포함:
   - 에러 메시지 전문
   - Actions 로그 (민감 정보 제거)
   - 프로젝트 타입
   - 재현 단계
