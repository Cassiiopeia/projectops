# 체인지로그 자동화

main 브랜치로 PR(develop→main)이 생성되면 릴리스 노트 provider(기본: CodeRabbit, 신규 설치 기본: github-ai)가 체인지로그를 자동 생성합니다. provider가 실패해도 폴백 사다리(github-ai → commit)가 릴리스 노트를 끝까지 만들어냅니다 (#455).

---

## 개요

| 기능 | 설명 |
|------|------|
| **AI 분석** | 선택한 provider(coderabbit/github-ai/openai 계열/commit)가 변경사항 자동 분석 |
| **폴백 사다리** | provider 실패 시 github-ai → commit 순 폴백, 폴백 발생 시 PR 댓글 알림 |
| **카테고리 분류** | Features, Bug Fixes 등 자동 분류 |
| **이중 형식** | JSON (데이터) + Markdown (가독성) |
| **PR 제목 자동화** | `Deploy YYYYMMDD-vX.X.X` 형식으로 변경 |

---

## 자동화 흐름

```
develop 푸시
    │
    │  (워크플로우는 릴리스 PR을 자동 생성하지 않습니다)
    ▼
develop → main 릴리스 PR 생성  ← 사람 또는 /pro-changelog-deploy 스킬이 만듭니다
    │
    ▼
RELEASE-CHANGELOG 워크플로우 (pull_request_target: opened)
    │
    ├─ head 가드: PR head가 develop이 아니면 전체 스킵
    ├─ PR 제목을 "🚀 Deploy YYYYMMDD-vX.Y.Z" 형식으로 즉시 변경
    ├─ 릴리스 노트 확보 (provider 사다리)
    ├─ CHANGELOG.json 업데이트 / CHANGELOG.md 생성
    ├─ 버전 확정 커밋
    └─ PR 자동 머지
         │
         ▼
main 푸시 (릴리스 머지)
    │
    ├─ README-VERSION-UPDATE
    ├─ PLUGIN-VERSION-SYNC
    └─ CICD 배포
```

> **주의 — 흔한 오해 2가지**
> - `VERSION-CONTROL`은 **develop 푸시에 반응하지 않습니다.** main 직접 푸시 시에만 도는 안전망입니다 ([버전 관리](VERSION-CONTROL.md) 참조).
> - **릴리스 PR을 자동 생성하는 워크플로우는 없습니다.** develop을 푸시했다고 PR이 생기지 않으므로, `/pro-changelog-deploy` 스킬을 쓰거나 직접 PR을 열어야 합니다.

> 구명칭 이력: 이 워크플로우는 `PROJECT-COMMON-AUTO-CHANGELOG-CONTROL`에서 v4.3.0에 `PROJECT-COMMON-RELEASE-CHANGELOG`로 리네임되었습니다. 구 파일이 남아있으면 `npx projectops` 업데이트가 자동 무해화합니다 ([NPX 마법사 가이드](NPX-WIZARD.md) 참조).

---

## 릴리스 노트 provider 사다리

릴리스 노트 생성기는 `version.yml`의 `metadata.template.options.changelog.provider`로 선택합니다 (#455).

```yaml
metadata:
  template:
    options:
      changelog:
        provider: "github-ai"   # coderabbit | github-ai | openai | gemini | claude | ollama | commit
        # base_url: "http://localhost:11434/v1"   # ollama 전용 (필수)
```

| provider | 방식 | 요구사항 |
|----------|------|---------|
| `coderabbit` (미설정 시 기본 — 기존 동작 보존) | CodeRabbit Summary 폴링 | 저장소에 CodeRabbit 앱 설치 |
| `github-ai` (신규 설치 기본) | GitHub Models API (`github_ai.py`) | 없음 — job의 `permissions: models: read` + GITHUB_TOKEN만으로 동작 (API 키 불필요, 기본 모델 `openai/gpt-4o-mini`) |
| `openai` / `gemini` / `claude` | OpenAI 호환 API (`openai_compatible.py`) | `MODEL_API_KEY` secret |
| `ollama` | OpenAI 호환 API (자체 호스팅) | `changelog.base_url` 필수 (기본 모델 `qwen2.5`) |
| `commit` | 커밋 메시지 분석 (`commit.py`) | 없음 — AI·네트워크 무의존 최후 보루 |

**폴백 순서** (`.github/scripts/changelog_providers/ladder.py`):

- `commit` → commit만 실행
- `openai`/`gemini`/`claude`/`ollama` → 해당 provider → github-ai → commit
- `github-ai` → github-ai → commit
- `coderabbit` → Summary 폴링 무응답 시 github-ai → commit

폴백이 발생하면 어떤 provider로 대체됐는지 **PR 댓글로 알림**이 남습니다. commit provider가 항상 완주하므로 릴리스 노트가 비는 일은 없습니다.

테스트: `python -m pytest .github/scripts/test/test_changelog_providers.py`

---

## 출력 파일

### CHANGELOG.json

구조화된 데이터 형식으로, 프로그래밍적 접근이 가능합니다.

```json
{
  "versions": [
    {
      "version": "1.2.3",
      "date": "2026-01-12",
      "categories": {
        "Features": [
          "새로운 로그인 기능 추가"
        ],
        "Bug Fixes": [
          "회원가입 오류 수정"
        ]
      }
    }
  ]
}
```

### CHANGELOG.md

사람이 읽기 좋은 마크다운 형식입니다.

```markdown
# Changelog

## [1.2.3] - 2026-01-12

### Features
- 새로운 로그인 기능 추가

### Bug Fixes
- 회원가입 오류 수정
```

---

## changelog_manager.py 사용법

### 기본 명령어

```bash
# CodeRabbit Summary로 업데이트
python3 .github/scripts/changelog_manager.py update-from-summary

# Markdown 재생성
python3 .github/scripts/changelog_manager.py generate-md

# 특정 버전 릴리즈 노트 추출
python3 .github/scripts/changelog_manager.py export --version 1.2.3 --output release_notes.txt
```

> 지원 서브커맨드는 위 3종(`update-from-summary` / `generate-md` / `export`)이 전부입니다.

---

## 카테고리 분류

선택한 provider가 변경사항을 자동으로 분류합니다.

| 카테고리 | 설명 | 예시 키워드 |
|----------|------|------------|
| **Features** | 새로운 기능 | feat, add, new |
| **Bug Fixes** | 버그 수정 | fix, bug, resolve |
| **Documentation** | 문서 변경 | docs, readme |
| **Performance** | 성능 개선 | perf, optimize |
| **Refactoring** | 코드 리팩토링 | refactor, clean |
| **Tests** | 테스트 추가/수정 | test, spec |
| **Chores** | 기타 작업 | chore, build |

---

## PR 제목 자동 포맷팅

**워크플로우가** develop → main PR 제목을 자동으로 변경합니다 (CodeRabbit이 아니라 워크플로우 스텝이 수행하며, provider 선택과 무관하게 항상 동작합니다).

**Before**:
```
develop에서 main으로 병합
```

**After**:
```
🚀 Deploy 20260112-v1.2.3
```

- 형식: `🚀 Deploy {YYYYMMDD}-v{버전}` — 로켓 이모지가 포함되며 뒤에 요약 문구는 붙지 않습니다.

---

## 워크플로우

### PROJECT-COMMON-RELEASE-CHANGELOG.yaml

```yaml
on:
  pull_request_target:
    types: [opened]
    branches: ["main"]
```

**트리거 조건**:
- main 브랜치로 PR이 **열릴 때만** 실행됩니다. `synchronize`(PR에 추가 푸시)는 트리거가 아니므로, **PR을 다시 푸시해도 재실행되지 않습니다.**
- 재실행이 필요하면 PR을 닫고 새로 열거나 `/pro-changelog-deploy`의 재트리거를 사용하세요.
- `pull_request`가 아니라 `pull_request_target`이므로 base(main) 기준으로 실행되며 secret에 접근할 수 있습니다.
- **head 가드**: PR head 브랜치가 `develop`이 아니면 전체 파이프라인이 스킵됩니다. main이 default 브랜치라 feature PR의 base가 실수로 main이 되는 경우를 막기 위한 장치입니다.

**실행 내용**:
1. version.yml에서 changelog provider 판독 (미설정 시 coderabbit)
2. provider=coderabbit이면 Summary 요청·폴링 / 아니면 폴링 생략
3. Summary가 없으면 fallback-summary job이 provider 사다리(ladder.py) 실행
4. Summary/릴리스 노트 파싱 → CHANGELOG.json 업데이트 → CHANGELOG.md 생성
5. 변경사항 커밋 (버전 확정 커밋)
6. PR 자동 머지

---

## CodeRabbit 연동 (provider=coderabbit일 때)

### 필수 조건

1. 저장소에 CodeRabbit 앱 설치
2. `.coderabbit.yaml` 설정 (선택)

### Summary 형식

CodeRabbit이 PR에 남기는 Summary 형식:

```markdown
## Summary by CodeRabbit

### Changes
- Added new login feature
- Fixed signup validation bug

### Files Changed
- src/auth/login.ts
- src/auth/signup.ts
```

---

## 이중 파싱 전략

레거시 및 최신 CodeRabbit 형식 모두 지원합니다.

### 최신 형식
```markdown
## Summary by CodeRabbit
<details>
  <summary>Changes</summary>
  ...
</details>
```

### 레거시 형식
```markdown
**Summary**
- Change 1
- Change 2
```

---

## 트러블슈팅

### 체인지로그 생성 안됨

**증상**: PR 머지 후에도 CHANGELOG가 업데이트 안됨

**확인 사항**:
1. `version.yml`의 `options.changelog.provider` 값 확인 (coderabbit이면 CodeRabbit이 Summary를 남겼는지 확인)
2. `_GITHUB_PAT_TOKEN` Secret 설정 확인 (openai 계열 provider는 `MODEL_API_KEY`도 확인)
3. Actions 로그에서 fallback-summary job이 어느 provider로 완주했는지 확인 (`PROVIDER=<승자>` 출력)

### Summary 파싱 실패

**증상**: "Could not parse CodeRabbit summary" 에러

**해결**:
1. PR 댓글에서 CodeRabbit Summary 형식 확인
2. HTML 태그가 깨지지 않았는지 확인

### PR 자동 머지 실패

**증상**: 체인지로그는 생성되었으나 PR이 머지 안됨

**확인 사항**:
1. Branch protection rule 확인
2. PAT 토큰 권한 확인 (repo, workflow)
3. Repository Settings → Actions 권한 확인

---

## 수동 업데이트

자동화가 실패한 경우 수동으로 업데이트할 수 있습니다.

```bash
# 1. CHANGELOG.json 직접 수정
# 2. Markdown 재생성
python3 .github/scripts/changelog_manager.py generate-md

# 3. 커밋 & 푸시
git add CHANGELOG.json CHANGELOG.md
git commit -m "docs: update changelog"
git push
```

---

## 릴리스 버전 확정 커밋과 후속 워크플로우 트리거

`RELEASE-CHANGELOG`이 develop→main 릴리스 PR을 automerge하며 만드는 **버전 확정 커밋**은
`[skip ci]`를 **포함하지 않는다**. 이 커밋이 main HEAD가 되므로, main push 트리거 워크플로우
(`NPM-PUBLISH`·`README-VERSION-UPDATE`·`PLUGIN-VERSION-SYNC` 및 각 프로젝트 배포 CICD)가
**릴리스 시 자동으로 트리거**되어야 하기 때문이다. (default 브랜치 push = 배포 트리거)

무한 루프가 없는 이유:

- `VERSION-CONTROL` 안전망은 `paths-ignore(version.yml)` + `release_guard`(커밋에 version.yml
  변경이 포함됐는지 감지)로 이 릴리스 커밋을 인식해 **재bump를 건너뛴다**.
- `README-VERSION-UPDATE`·`PLUGIN-VERSION-SYNC`는 자신이 만드는 후속 커밋에 `[skip ci]`를
  유지하므로 서로 재트리거하지 않는다.
- `RELEASE-CHANGELOG`은 `pull_request_target: [opened]` 트리거라 자신이 만드는 커밋으로
  재실행되지 않는다 (`synchronize`가 트리거가 아니다).

> 참고: develop을 push 트리거로 쓰는 워크플로우는 존재한다 (`PROJECT-TEMPLATE-CI`,
> `PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC`, `PROJECT-FLUTTER-CI`, `PROJECT-REACT-CI`,
> `PROJECT-SPRING-NEXUS-CI`). 다만 전부 **CI(검증)일 뿐 버전·CHANGELOG를 건드리지 않으므로**
> 릴리스 루프와 무관하다.

> 버전 확정 커밋에 `[skip ci]`를 다시 붙이면 릴리스마다 배포·동기화가 전부 멈춘다. 붙이지 않는다.

---

## 관련 문서

- [버전 관리](VERSION-CONTROL.md)
- [트러블슈팅](TROUBLESHOOTING.md)
