# 버전 관리 시스템

정상 릴리스는 `develop → main` PR에서 RELEASE-CHANGELOG이 버전을 확정합니다. VERSION-CONTROL은 **main 직접 푸시 시 patch 버전을 자동 증가시키는 안전망**입니다.

---

## 개요

| 기능 | 설명 |
|------|------|
| **자동 증가 (안전망)** | main 직접 푸시 시 patch 버전 +1 (1.0.0 → 1.0.1). 릴리스 PR 머지(version.yml 변경 포함)인 경우는 건너뜁니다 |
| **버전 확정 (정상 릴리스)** | `develop → main` PR에서 RELEASE-CHANGELOG이 버전을 확정하고 CHANGELOG를 스탬프합니다 |
| **멀티 파일 동기화** | version.yml ↔ 프로젝트 파일 양방향 동기화 |
| **충돌 해결** | 버전 불일치 시 "높은 버전 우선" 정책 |
| **Git 태그** | 버전 변경 시 자동 태그 생성 |

---

## version.yml

모든 프로젝트의 버전 정보는 `version.yml`에서 중앙 관리됩니다.

```yaml
version: "2.4.3"              # 버전 (자동 관리)
version_code: 94              # 빌드 번호 (자동 증가)
project_types: ["spring"]     # 프로젝트 타입 배열 — 첫 항목이 primary

metadata:
  last_updated: "2026-01-06 08:23:20"
  last_updated_by: "username"
```

### `project_types` (배열 — 유일한 소스)

단일 레포에 여러 타입이 공존하는 경우를 위해 `project_types` 배열 키를 사용합니다.

```yaml
project_types: ["spring", "react", "python"]   # 첫 항목이 primary
```

- 단일 타입도 배열 형태로 통일됩니다 (`project_types: ["basic"]`).
- primary 타입(버전 파일 결정 기준)은 배열의 **첫 항목**입니다.
- 단수 `project_type` 키는 **v4.1.0에서 제거**되었습니다. 단수 키만 있는 v4.0 이전 형식은 `version_manager.sh`가 명시적으로 실패하며 전환 절차를 안내합니다 (`project_type: "spring"` → `project_types: ["spring"]`).
- `version_manager.sh`가 배열을 순회하여 모든 타입의 버전 파일을 동기화합니다.

### `project_paths` (모노레포 경로 맵)

타입별 프로젝트가 서브폴더에 있는 모노레포는 `project_paths` 맵(타입 → 레포 루트 기준 상대경로)으로 위치를 지정합니다.

```yaml
project_types: ["flutter", "react"]
project_paths:
  flutter: "app"       # app/pubspec.yaml을 동기화
  react: "client"      # client/package.json을 동기화
```

- 키가 없는 타입은 **레포 루트 기준**으로 동작합니다 (기존 동작 100% 유지).
- `npx projectops` 통합 시 마커 파일(`pubspec.yaml`·`package.json`·`pyproject.toml`·`build.gradle` 등)을 자동 감지해 후보를 제안하며, 비대화형은 `--paths "flutter=app,react=client"`로 지정합니다 ([NPX 마법사 가이드](NPX-WIZARD.md) 참조).
- `version_manager.sh`가 이 경로를 따라 서브폴더 버전 파일을 동기화하므로, `PROJECT-COMMON-VERSION-CONTROL` 워크플로우는 수정 없이 모노레포를 지원합니다.

---

## 프로젝트 타입별 버전 파일

| 타입 | 버전 파일 | 버전 위치 |
|------|----------|----------|
| `spring` | `build.gradle` | `version = '1.0.0'` |
| `flutter` | `pubspec.yaml` | `version: 1.0.0+1` |
| `react` (Next.js 포함) | `package.json` | `"version": "1.0.0"` |
| `node` | `package.json` | `"version": "1.0.0"` |
| `python` | `pyproject.toml` | `version = "1.0.0"` |
| `react-native` | `Info.plist` + `build.gradle` | iOS/Android 분리 |
| `react-native-expo` | `app.json` | `"version": "1.0.0"` |
| `basic` | `version.yml` 만 | - |

---

## version_manager.sh 사용법

> v4.2부터 실 로직은 `version_manager.py`(stdlib 전용 — yq/jq 불필요)에 있고 `.sh`는 Python 위임 shim입니다 (#448). Windows에서는 `python .github/scripts/version_manager.py get`처럼 .py를 직접 실행합니다.

### 기본 명령어

```bash
# 현재 버전 확인
.github/scripts/version_manager.sh get

# patch 버전 증가 (1.0.0 → 1.0.1)
.github/scripts/version_manager.sh increment

# 특정 버전으로 설정
.github/scripts/version_manager.sh set 2.0.0

# 버전 동기화 (충돌 해결)
.github/scripts/version_manager.sh sync

# 버전 형식 검증
.github/scripts/version_manager.sh validate 1.2.3
```

### version_code 관리

```bash
# 현재 빌드 번호 확인
.github/scripts/version_manager.sh get-code

# 빌드 번호 증가
.github/scripts/version_manager.sh increment-code
```

---

## 자동화 흐름

### 정상 릴리스 (develop → main PR)

```
develop → main PR 생성 (release)
    │
    ▼
RELEASE-CHANGELOG 워크플로우
    │
    ├─ 버전 확정 (PR 안에서 patch/minor/major 결정)
    ├─ CHANGELOG.json / CHANGELOG.md 스탬프
    └─ automerge
         │
         ▼
main 푸시 (릴리스 머지)
    │
    ├─ README-VERSION-UPDATE
    ├─ PLUGIN-VERSION-SYNC
    └─ CICD 배포
```

### main 직접 푸시 (안전망)

```
main 직접 푸시 (릴리스 PR이 아닌 경우)
    │
    ▼
VERSION-CONTROL 워크플로우
    │
    ├─ version.yml 버전 읽기
    ├─ patch 버전 +1
    ├─ 프로젝트 파일 동기화
    ├─ Git 태그 생성 (v1.0.1)
    └─ 커밋 & 푸시
```

> VERSION-CONTROL은 PR을 생성하지 않습니다. 릴리스 머지로 인한 push(version.yml 변경 포함)는 감지해 건너뛰고, 그 외 main 직접 푸시에만 patch +1로 동작하는 안전망입니다.

---

## 버전 증가 규칙

| 버전 | 변경 방법 | 예시 |
|------|----------|------|
| **patch** | 자동 (develop → main 릴리스 PR, 또는 main 직접 푸시 안전망) | 1.0.0 → 1.0.1 |
| **minor** | 수동 (version.yml 직접 수정) | 1.0.1 → 1.1.0 |
| **major** | 수동 (version.yml 직접 수정) | 1.1.0 → 2.0.0 |

### 수동 버전 변경

```bash
# 1. version.yml 직접 수정
version: "2.0.0"

# 2. 커밋 & 푸시 (자동 동기화됨)
git add version.yml
git commit -m "feat: v2.0.0 major release"
git push
```

---

## 동기화 정책

### 충돌 해결

여러 파일에서 버전이 다를 경우:

```
version.yml: 1.0.5
build.gradle: 1.0.3
```

→ **높은 버전 우선**: 모두 `1.0.5`로 동기화

### 동기화 방향

```
version.yml ←→ 프로젝트 파일
              (양방향)
```

- version.yml 변경 → 프로젝트 파일 업데이트
- 프로젝트 파일 변경 → version.yml 업데이트

---

## 워크플로우

### PROJECT-COMMON-VERSION-CONTROL.yaml

```yaml
on:
  push:
    branches: ["main"]
    paths-ignore:
      - 'CHANGELOG.md'
      - 'CHANGELOG.json'
      - 'version.yml'   # 무한 루프 방지
  workflow_dispatch:
```

**트리거 조건**:
- main 브랜치 푸시 (**main 직접 푸시 안전망** — 릴리스 PR 머지로 인한 push는 가드로 skip)
- CHANGELOG 2종과 `version.yml`만 바뀐 push는 제외 (`README.md`는 제외 대상이 **아닙니다**)
- 릴리스 머지 감지는 `paths-ignore`가 아니라 워크플로우 안의 **release 가드 스텝**이 담당합니다. push에 포함된 커밋이 `version.yml`을 변경했는지 확인해 버전 증가를 건너뜁니다

**실행 내용**:
1. 현재 버전 확인
2. patch 버전 증가
3. 프로젝트 파일 동기화
4. Git 태그 생성

> PR을 생성하지 않습니다. 정상 릴리스 버전 확정은 `develop → main` PR에서 `PROJECT-COMMON-RELEASE-CHANGELOG.yaml`(트리거: `pull_request_target opened, branches: [main]`)이 담당합니다.

---

## 트러블슈팅

### 버전 동기화 실패

**증상**: 여러 파일의 버전이 불일치

**해결**:
```bash
# 수동 동기화 실행
.github/scripts/version_manager.sh sync
```

### Git 태그 중복

**증상**: 태그가 이미 존재합니다 에러

**해결**:
```bash
# 원격 태그 삭제 후 재생성
git push origin :refs/tags/v1.0.0
git tag -d v1.0.0
```

### 스크립트 권한 오류

**증상**: permission denied

**해결**:
```bash
chmod +x .github/scripts/version_manager.sh
```

---

## 관련 문서

- [체인지로그 자동화](CHANGELOG-AUTOMATION.md)
- [트러블슈팅](TROUBLESHOOTING.md)
