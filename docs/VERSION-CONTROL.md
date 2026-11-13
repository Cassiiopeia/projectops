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
version_code: 94              # Android 릴리스 빌드 번호 (자동 증가)
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

`version_code`는 **Android 릴리스 전용**입니다. 매 릴리스마다 +1 되며 Play Store CICD와 Firebase CICD가 읽어 `versionCode`로 씁니다. 자체 서버(SMB) 배포는 `pubspec.yaml`의 `+N`을 씁니다.

**iOS와 테스트 빌드(iOS 테스트, Android 테스트 APK)에는 쓰이지 않습니다.** 이들은 `build_number.py`가 정하는 시각 기반 번호(2024-01-01 UTC부터 지난 초)를 씁니다 (#643). iOS 릴리스 번호도 더 이상 `version_code`와 같지 않습니다.

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
    ├─ 버전 +1 (semver_auto가 켜져 있으면 커밋 제목으로 major/minor/patch, 꺼져 있으면 patch)
    ├─ 프로젝트 파일 동기화
    ├─ Git 태그 생성 (v1.0.1)
    └─ 커밋 & 푸시
```

> VERSION-CONTROL은 PR을 생성하지 않습니다. 릴리스 머지로 인한 push(version.yml 변경 포함)는 감지해 건너뛰고, 그 외 main 직접 푸시에만 patch +1로 동작하는 안전망입니다.

---

## 배포 브랜치 분리 (선택)

기본은 기본 브랜치(`main`)에 푸시되면 배포가 돈다. develop → main → deploy 로 나눠서 배포 워크플로(앱스토어·서버·패키지 publish·Vercel)를
`deploy` 브랜치에서만 돌리고 싶으면 한 번만 정한다.

```bash
npx projectops --mode workflows --force --deploy-trigger-branch deploy
```

`version.yml` 에 `metadata.template.options.deploy_trigger_branch` 가 기록되고, 배포 워크플로의 `main` 만 `deploy` 로 바뀐다
(푸시 트리거, 체크아웃, `git pull`, 브랜치 조건). 버전 올림·README 버전·릴리스 노트·이슈 닫기는 기본 브랜치를 그대로 따른다.
이후 업데이트도 이 설정을 유지한다. `deploy` 브랜치는 먼저 만들어 둔다. 플래그를 안 주면 아무것도 바뀌지 않는다.

- 릴리스 PR(develop → main)은 지금처럼 버전 확정·릴리스 노트만 하고 배포하지 않는다. 배포는 main 을 `deploy` 로 올릴 때 돈다.
  `pro-changelog-deploy` 의 `detect-release-context` 가 이 구조를 `release_shape: three_tier` 로 알려 준다.
- 버전 올림·README 버전 커밋은 기본 브랜치에 남는다. `deploy` 는 main 을 받아 가므로 함께 간다.
- `.coderabbit.yaml` 의 `auto_review.base_branches` 처럼 레포가 직접 관리하는 파일은 바뀌지 않는다. 필요하면 `deploy` 를 직접 더한다.

## CI 사용 시간 절약 (선택)

비공개 레포는 Actions 사용 시간이 과금된다. 한 번 켜 두면 CI 워크플로가 시간을 덜 쓰는 모양으로 설치된다.

```bash
npx projectops --mode workflows --force --ci-minutes-saver
```

| 워크플로 | 켜면 |
|---|---|
| `PROJECT-FLUTTER-CI` | PR 에서만 돈다(개발 브랜치 push 제거), 문서만 바뀐 PR 은 건너뛴다, iOS(macOS 러너) 빌드는 수동 실행의 `enable_ios` 로만 |
| `PROJECT-PYTHON-CI` · `PROJECT-SPRING-NEXUS-CI` | PR 에서만 돈다, 문서만 바뀐 PR 은 건너뛴다 |
| `PROJECT-REACT-CI` | 문서만 바뀐 push 는 건너뛴다 |
| `PROJECT-COMMON-SECRET-FILE-UPLOAD` | 수동 실행만 |

`version.yml` 에 `metadata.template.options.ci_minutes_saver: true` 가 기록되고 이후 업데이트도 유지한다. 끄려면 `--no-ci-minutes-saver`.
개발 브랜치에 직접 push 한 커밋은 CI 가 돌지 않는다. CI 를 필수 상태 검사로 걸어 두었다면 문서만 바뀐 PR 이 그 검사를 계속 기다리므로 필수에서 빼야 한다.
이미 설치된 `PROJECT-COMMON-SECRET-FILE-UPLOAD` 는 업데이트가 덮어쓰지 않으므로(서버 폴더 이름이 들어 있다) 기존 레포는 `push:` 트리거를 직접 지운다.

## 버전 증가 규칙

승격 폭은 `version.yml`의 `metadata.template.options.semver_auto`가 정합니다.

**`semver_auto: true`** (신규 통합 기본값) — 릴리스 구간 커밋 제목으로 판정합니다.

| 버전 | 발동 조건 | 예시 |
|------|----------|------|
| **major** | 커밋 타입 뒤 `!` 마커 (`제목 : feat! : 내용`, `feat!:`) | 1.1.0 → 2.0.0 |
| **minor** | `feat` 타입 (`제목 : feat : 내용`, `feat:`) | 1.0.1 → 1.1.0 |
| **patch** | 그 외 (fix·docs·chore·refactor·test·자유형식) | 1.0.0 → 1.0.1 |

한 릴리스 구간에 섞이면 가장 높은 것이 이깁니다 (major > minor > patch).
`[skip ci]` 포함 커밋과 `Merge`로 시작하는 커밋은 판정에서 제외됩니다.

**`semver_auto: false`를 명시한 경우** — 항상 `patch +1`입니다. 키가 없으면 켜진 것으로 봅니다(업데이트가 키를 `true`로 기록하고 완료 화면에서 알려 줍니다).

| 버전 | 변경 방법 | 예시 |
|------|----------|------|
| **patch** | 자동 (develop → main 릴리스 PR, 또는 main 직접 푸시 안전망) | 1.0.0 → 1.0.1 |
| **minor** | 수동 (version.yml 직접 수정) | 1.0.1 → 1.1.0 |
| **major** | 수동 (version.yml 직접 수정) | 1.1.0 → 2.0.0 |

> **main 직접 푸시(VERSION-CONTROL)도 `semver_auto`를 따릅니다.** 켜져 있으면(키가 없으면 켜진 것으로 봅니다)
> 개발 브랜치 유무와 상관없이 push 구간 커밋 제목으로 major/minor/patch를 정하고, `semver_auto: false`로 명시했을 때만 항상 patch입니다.
> - `version.yml`의 설정만 바꾼 push는 릴리스로 보지 않습니다 — `version:` 값이 바뀐 경우만 건너뜁니다.
>
> 워크플로우는 `pull_request_target`으로 돌아 **base 브랜치(main)의 워크플로우 파일**로 실행됩니다.
> 워크플로우 자체를 고친 릴리스에는 구 로직이 적용되고, 머지된 **다음 릴리스부터** 새 로직이 반영됩니다.

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
