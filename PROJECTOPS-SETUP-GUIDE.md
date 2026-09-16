# 🚀 projectops 빠른 시작 가이드

> **지금 당장 해야 하는 것은 하나뿐입니다.** 나머지는 나중에 필요해지면 하세요.

설치는 이미 끝났습니다. 아래 표만 보고 필요한 것을 고르세요.

| | 해야 하나? | 안 하면 | 걸리는 시간 |
|---|---|---|---|
| **① 개발 브랜치 만들기** | **네, 지금** | 릴리스를 못 합니다 | 10초 |
| ② AI 요약 키 등록 | 아니오 (선택) | 릴리스 노트가 커밋 목록 정리본으로 나옵니다 | 2분 |
| ③ PAT 등록 | 아니오 (선택) | 브랜치 보호 규칙이 있으면 자동 머지가 막힐 수 있습니다 | 3분 |
| ④ CodeRabbit | 통합 때 골랐다면 | PR에 코드 리뷰 댓글이 안 달립니다 | 2분 |

**①만 하면 바로 쓸 수 있습니다.**

> 💰 **기본 구성은 전부 무료이며 한도가 없습니다.** 릴리스 노트는 커밋 내용을 분석해
> 만들기 때문에 외부 서비스를 쓰지 않습니다. ②·④는 품질을 올리고 싶을 때만 선택하세요.

---

## ① 개발 브랜치 만들기 (필수)

```bash
git checkout -b develop
git push -u origin develop
git checkout main
```

**왜 필요한가**: 이 템플릿은 `develop`에 개발을 모았다가 `develop → main` PR로 릴리스합니다.
그 PR이 만들어지는 순간 버전 확정·릴리스 노트 생성·자동 머지가 돌아갑니다.
`develop`이 없으면 그 흐름이 시작되지 않습니다.

> 다른 이름을 쓰고 싶으면 `version.yml`의 `metadata.deploy_branch`를 바꾸세요.

---

## ② AI 요약 키 등록 (선택)

**등록하지 않아도 릴리스 노트는 나옵니다.** 커밋 메시지를 분석해 이렇게 만듭니다.

```
**새 기능**
* 소셜 로그인 버튼 추가

**버그 수정**
* 카드 중복 청구 문제 해결
```

AI가 다듬은 문장을 원할 때만 아래를 따르세요.

**1. 키 발급** — [Google AI Studio](https://aistudio.google.com/apikey) (무료, 신용카드 불필요)

> 결제 계정이 **연결되지 않은** 새 프로젝트로 키를 만들면 무료 등급입니다.
> 일 500회까지 쓸 수 있어 일반적인 릴리스 빈도에는 충분합니다.

**2. 저장소에 등록** — Settings → Secrets and variables → Actions → New repository secret

| Name | Secret |
|---|---|
| `GEMINI_API_KEY` | 발급받은 키 (`AIza...` 로 시작) |

**다른 서비스를 쓴다면** 이름만 바꿔 등록하세요. 등록한 것이 자동으로 쓰입니다.

| 서비스 | Secret 이름 | 무료 |
|---|---|---|
| Google Gemini | `GEMINI_API_KEY` | ✅ |
| Groq | `GROQ_API_KEY` | ✅ |
| Mistral | `MISTRAL_API_KEY` | ✅ |
| OpenAI | `OPENAI_API_KEY` | ❌ |
| Anthropic | `ANTHROPIC_API_KEY` | ❌ |

**동작 방식** — 설정은 이것뿐입니다. 나머지는 자동입니다.

```
릴리스 PR 생성
  → PR 본문에 릴리스 노트가 이미 있으면 그대로 사용
  → 없으면 등록한 키로 AI 요약 (키가 없으면 건너뜀)
  → 그래도 안 되면 커밋 내용으로 정리   ← 항상 성공한다
```

> **기본 경로에는 요금이 발생하는 요소가 없습니다.** 아무 설정도 하지 않으면
> 커밋 분석만 돌며, 이는 무제한·무료입니다.

어느 경로로 만들어졌는지는 **Actions 실행 요약**에 매번 기록됩니다.
AI를 하나도 쓰지 못한 경우에만 PR에 안내 댓글이 **한 번** 달립니다.

> 한도를 넘기거나 키가 잘못돼도 릴리스는 멈추지 않습니다. 커밋 분석으로 내려갈 뿐입니다.

---

## ③ GitHub Personal Access Token (선택)

**없어도 릴리스는 정상 동작합니다.** 브랜치 보호 규칙을 걸어둔 저장소에서
자동 머지가 막힐 때만 필요합니다.

#### 토큰 생성
1. **GitHub** → **Settings** → **Developer settings** → **Personal access tokens (Classic)**
2. **Generate new token (classic)** 클릭
3. 토큰 설정:
   - **Name**: `_GITHUB_PAT_TOKEN`
   - **Expiration**: 90 days (또는 조직 정책에 따라)
   - **Scopes**: ✅ `repo` (Full control), ✅ `workflow` (Update workflows)
4. **Generate token** 클릭 후 토큰 복사

#### Secret 등록
1. **프로젝트 저장소** → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret** 클릭
3. **Name**: `_GITHUB_PAT_TOKEN`
4. **Secret**: [위에서 복사한 토큰 값 붙여넣기]
5. **Add secret** 클릭

---

## ④ CodeRabbit 활성화 (통합 때 골랐다면)

| | 무료 | 유료 |
|---|---|---|
| 대상 | **공개 저장소만** | 비공개 포함 |
| 한도 | **시간당 3회** 리뷰 | 플랜에 따라 상향 |

공개 저장소는 영구 무료지만 시간당 3회 제한이 있습니다. PR을 연달아 올리면 리뷰가
밀릴 수 있습니다. **비공개 저장소는 무료 플랜이 없습니다.**

> CodeRabbit은 **코드 리뷰**만 담당합니다. 릴리스 노트는 위 ②의 사다리가 만들므로
> CodeRabbit이 느리거나 한도에 걸려도 릴리스는 기다리지 않고 진행됩니다.


통합 시 **CodeRabbit 코드 리뷰**를 선택한 경우에만 필요합니다.

1. [CodeRabbit 웹사이트](https://coderabbit.ai) 접속
2. GitHub 계정으로 로그인
3. 저장소 목록에서 프로젝트 선택하여 활성화
4. `.coderabbit.yaml` 파일이 프로젝트에 있으면 자동으로 설정 적용됨

**설명**: CodeRabbit은 AI 기반 코드 리뷰를 담당합니다. 이 단계를 건너뛰면 워크플로우가
켜져 있어도 PR에 리뷰 댓글이 달리지 않습니다.

---

## 🛠️ IDE 도구 (Skills) 설치 (선택)

npx projectops로 통합 시 자동 안내되지만, 수동으로도 설치할 수 있습니다.

| IDE | 설치 방법 | 사용 예시 |
|-----|----------|----------|
| **Claude Code** | 플러그인 마켓플레이스 (CLI) | `/pro-analyze`, `/pro-review` |
| **Cursor** | `.cursor/skills/` 폴더 복사 | Skills 패널에서 선택 |
| **Gemini CLI** | `gemini extensions install` | extension 명령 |
| **Codex CLI** | `codex plugin marketplace add` | `/plugins`에서 확인 |

### Claude Code

```bash
# 마켓플레이스 등록 + 플러그인 설치
claude plugin marketplace add Cassiiopeia/projectops
claude plugin install projectops@projectops-marketplace --scope user
```

### Cursor

`npx projectops` 실행 시 Cursor 설치를 선택하면 자동으로 `skills/` → `.cursor/skills/`로 복사됩니다.

---

## ✅ 제대로 됐는지 확인하기

언제든 아래 명령으로 현재 상태를 진단할 수 있습니다.

```bash
npx projectops --mode doctor
```

저장소 설정까지 보려면 토큰을 함께 넘기세요.

```bash
GITHUB_TOKEN=ghp_... npx projectops --mode doctor
```

### 첫 릴리스를 돌려보기

```bash
git checkout develop
git commit --allow-empty -m "첫 릴리스 테스트 : feat : 자동화 동작 확인"
git push origin develop
```

그다음 GitHub에서 `develop → main` PR을 만들면 자동으로 진행됩니다.

| 순서 | 일어나는 일 |
|---|---|
| 1 | 버전이 확정됩니다 (`feat`이 있으면 minor, 아니면 patch) |
| 2 | 릴리스 노트가 만들어져 PR 본문에 들어갑니다 |
| 3 | `CHANGELOG.md` · `CHANGELOG.json`이 갱신됩니다 |
| 4 | PR이 자동 머지됩니다 |

Actions 탭의 실행 요약에서 **릴리스 노트가 어떤 경로로 만들어졌는지** 확인할 수 있습니다.

---

## 🎉 완료!

**이제 코드를 푸시하면 모든 자동화가 작동합니다.**

- ✅ 버전 자동 증가 (1.0.0 → 1.0.1)
- ✅ README 버전 자동 업데이트
- ✅ Git 태그 자동 생성
- ✅ 체인지로그 자동 생성

---

## ✨ 자동으로 처리되는 것들

### 템플릿 사용 시 (GitHub "Use this template")

**프로젝트 생성 즉시 자동 실행**:
- ✅ `version.yml` 자동 생성 (v0.0.0, basic 타입)
- ✅ 공통 워크플로우 자동 설치 (주요 항목):
  - `PROJECT-COMMON-VERSION-CONTROL.yaml` (버전 자동 관리)
  - `PROJECT-COMMON-RELEASE-CHANGELOG.yaml` (체인지로그 생성)
  - `PROJECT-COMMON-README-VERSION-UPDATE.yaml` (README 업데이트)
  - `PROJECT-COMMON-SUH-ISSUE-HELPER-MODULE.yml` (이슈 브랜치/커밋 제안)
  - `PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml` (QA 이슈 자동 생성)
  - `PROJECT-COMMON-SYNC-ISSUE-LABELS.yaml` (라벨 동기화)
  - `PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml` (Projects 상태 동기화)
- ✅ README 버전 섹션 자동 추가
- ✅ 불필요한 템플릿 파일 자동 삭제
- ✅ Default 브랜치 자동 감지

---

### 원격 스크립트 사용 시 (기존 프로젝트에 통합)

```bash
# 대화형 모드 (권장)
npx projectops

# 비대화형 모드 (Spring Boot 전체 통합 예시)
npx projectops \
  --mode full --type spring --version 1.0.0 --force
```

**자동으로 수행되는 작업**:
- ✅ 프로젝트 타입 자동 감지 (Spring, Flutter, React, Node, Python 등) — 한 레포에 여러 타입이 섞인 모노레포는 멀티타입으로 함께 인식
- ✅ 현재 버전 자동 감지 (Git 태그, build.gradle, package.json 등)
- ✅ 프로젝트 타입에 맞는 워크플로우만 선택 복사
- ✅ `version.yml` 자동 생성
- ✅ README에 버전 섹션 자동 추가
- ✅ 버전 관리 스크립트 자동 설치

**지원하는 프로젝트 타입**:
- `spring` - Spring Boot / Java / Gradle
- `flutter` - Flutter / Dart
- `react` - React.js / Next.js
- `react-native` - React Native (iOS + Android)
- `react-native-expo` - Expo 기반 React Native
- `node` - Node.js / Express
- `python` - Python / FastAPI / Django
- `basic` - 기본 타입 (버전 관리만)

---

### 매 커밋마다 자동 실행

#### main 브랜치 푸시 시
- ✅ 커밋 메시지 분석 (`feat:`, `fix:`, `docs:` 등)
- ✅ 버전 자동 증가 (1.0.0 → 1.0.1)
- ✅ README 버전 자동 업데이트
- ✅ Git 태그 자동 생성 (`v1.0.1`)
- ✅ 프로젝트별 버전 파일 동기화:
  - Spring: `build.gradle` 또는 `pom.xml`
  - Flutter: `pubspec.yaml`
  - React/Node: `package.json`
  - React Native: `package.json`, `ios/Info.plist`, `android/build.gradle`
  - Python: `pyproject.toml`

#### develop → main 릴리스 PR 생성 시
- ✅ CodeRabbit AI 자동 코드 리뷰
- ✅ 체인지로그 자동 생성 (`CHANGELOG.json`, `CHANGELOG.md`)
- ✅ PR 자동 머지 (리뷰 통과 시)

---

## 🏢 Organization 사용 시 추가 설정

Organization 저장소에서는 아래 3가지 추가 설정이 필요합니다:

### 1. Actions 설정
```
Organization Settings → Actions → General
├── ✅ Allow GitHub Actions to create and approve pull requests
└── ✅ Allow GitHub Actions to merge pull requests
```

### 2. Repository 설정
```
Repository Settings → General → Pull Requests
├── ✅ Allow auto-merge
└── ✅ Allow squash merging
```

### 3. Member 권한 확인
```
Organization Settings → Member privileges
└── Personal access token expiration policy: 조직 정책에 맞게 설정
```

💡 **개인 저장소는 추가 설정 불필요합니다.**

---

## 🧪 동작 확인

### 첫 번째 테스트: 버전 자동 증가

```bash
# main 브랜치에 테스트 커밋
echo "# 테스트" >> TEST.md
git add TEST.md
git commit -m "test: 자동화 테스트"
git push origin main
```

**예상 결과** (GitHub Actions 탭에서 확인):
1. `PROJECT-COMMON-VERSION-CONTROL` 워크플로우 실행
2. 버전 자동 증가 (예: v0.0.0 → v0.0.1)
3. Git 태그 `v0.0.1` 자동 생성
4. README 버전 자동 업데이트

---

### 두 번째 테스트: 체인지로그 자동 생성

```bash
# feature 브랜치 생성 및 작업
git checkout -b feature/test-changelog
echo "# 체인지로그 테스트" >> TEST2.md
git add TEST2.md
git commit -m "feat: 체인지로그 테스트 기능"
git push origin feature/test-changelog

# GitHub에서 develop 브랜치로 PR 생성 (feature → develop)
# 이후 develop → main 릴리스 PR 생성 시 체인지로그가 자동 생성됩니다
```

**예상 결과**:
1. CodeRabbit AI 자동 리뷰
2. `CHANGELOG.json`, `CHANGELOG.md` 자동 생성
3. PR 자동 머지 (리뷰 통과 시)

---

## 🚨 자주 묻는 질문

### Q1: 워크플로우가 실행되지 않아요

**원인**: `develop` 브랜치에 워크플로우 파일이 없을 수 있습니다.

**해결**:
```bash
git checkout develop
ls .github/workflows/

# 파일이 없다면 main에서 복사
git checkout main
git checkout develop
git merge main
git push origin develop
```

---

### Q2: 토큰 권한 오류가 발생해요

**증상**:
```
remote: Permission to ... denied to github-actions[bot]
```

**해결**:
1. 토큰이 **Classic** 타입인지 확인 (Fine-grained 아님)
2. `repo`, `workflow` 권한 **모두** 체크되었는지 확인
3. Organization 설정에서 PAT 정책 확인
4. 토큰 만료 날짜 확인

---

### Q3: 버전이 동기화되지 않아요

**해결**: 수동 동기화 실행
```bash
# 현재 버전 상태 확인
.github/scripts/version_manager.sh get

# 모든 파일 동기화
.github/scripts/version_manager.sh sync

# 특정 버전으로 강제 설정
.github/scripts/version_manager.sh set 1.0.0
```

---

### Q4: CodeRabbit 리뷰가 동작하지 않아요

**확인 사항**:
1. `.coderabbit.yaml` 파일이 프로젝트 루트에 있는지 확인
2. CodeRabbit이 저장소에 액세스 권한이 있는지 확인
3. PR에 충분한 변경사항이 있는지 확인 (1줄 이상)

---

### Q5: Spring Boot 프로젝트인데 Nexus 배포 워크플로우가 없어요

**답변**: Nexus 워크플로우는 Spring 타입 선택 시 자동으로 복사됩니다:
- `PROJECT-SPRING-NEXUS-CI.yml`
- `PROJECT-SPRING-NEXUS-PUBLISH.yml`

**추가 설정 필요**:
1. GitHub Secrets에 Nexus 인증 정보 등록:
   - `NEXUS_USERNAME`
   - `NEXUS_PASSWORD`
   - `NEXUS_URL`
2. `gradle.properties` 또는 `build.gradle`에 Nexus 저장소 설정

---

## 📚 추가 문서

- [CONTRIBUTING.md](CONTRIBUTING.md) - 상세 기여 가이드 및 워크플로우 설명
- [CHANGELOG.md](CHANGELOG.md) - 전체 변경 이력
- [README.md](README.md) - 프로젝트 개요 및 빠른 시작

---

## 💡 다음 단계

### 프로젝트 타입 변경하려면?

```bash
# 원격 스크립트로 타입 변경 
npx projectops
```

### 고급 기능 활용

1. **수동 워크플로우 실행**: GitHub Actions 탭에서 `workflow_dispatch` 트리거 활용
2. **멀티 환경 배포**: `version.yml`에 환경별 설정 추가
3. **커스텀 워크플로우**: `.github/workflows/`에 프로젝트별 워크플로우 추가 가능

---

**🎉 축하합니다! 이제 완전 자동화된 DevOps 환경이 구축되었습니다.**

추가 질문이나 문제가 있다면 [이슈를 생성](https://github.com/Cassiiopeia/projectops/issues/new/choose)해 주세요.
