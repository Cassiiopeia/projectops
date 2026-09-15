# 릴리스 버전 자동 승격을 시맨틱 버저닝으로 전환 (semver_auto)

작성일: 2026-09-15
상태: 설계 확정

## 문제

`PROJECT-COMMON-RELEASE-CHANGELOG.yaml`의 `bump_version` step이 릴리스마다
`version_manager.sh increment`를 호출하고, 이 명령은 **무조건 patch+1**이다.
major/minor는 사람이 `version.yml`을 직접 고쳐야만 올라간다.

실측: `origin/main` 릴리스 이력 **45회가 전부 patch**라서 현재 `4.2.45`다.
그 구간에 `: feat :` 커밋이 분명히 있었는데도 minor는 **45번 중 0번** 올라갔다.
버전 숫자만 보고 변화의 성격을 판단한다는 시맨틱 버저닝의 목적이 죽어 있고,
"minor 올리는 걸 사람이 기억해야 하는" 실패 모드가 고착됐다.

`version_code`(빌드 번호)는 현행대로 매 릴리스 +1이 맞다 — 변경 대상이 아니다.

## 참조 구현과 그 한계

`project-auto-wizard`가 같은 문제를 이미 풀어놨다:
`classify-bump` → `increment --bump {major|minor|patch}`.

다만 **그대로 복사하면 안 되는 차이가 두 가지** 있다.

### 1. 커밋 컨벤션이 다르다 — major 경로가 죽는다

auto-wizard의 실제 커밋은 순수 Conventional Commits다 (`feat: ...`, `chore(release): ...`).
줄 맨 앞에 타입이 오므로 표준 `!` 마커가 자연히 작동한다.

projectops 컨벤션은 `제목 : type : 내용 URL`이라 **줄 앞이 한글 제목**이다.
auto-wizard의 breaking 판정 정규식은 줄 맨 앞부터 `type!:`를 요구한다:

```python
_BREAKING_MARKER_RE = re.compile(r'^[a-zA-Z]+(\([^)]*\))?!:')
```

→ 우리 컨벤션에서는 **절대 매칭되지 않는다.** 이식만 하면 "문서에는 있는데
한 번도 안 도는 죽은 규칙"이 된다.

실증 (`project-auto-wizard/tests/py/test_classify_bump.py`):

| 입력 | 결과 | 비고 |
|---|---|---|
| `"로그인 기능 : feat : 소셜 로그인 추가"` | `minor` | **projectops 컨벤션 — 보장됨** |
| `"feat!: drop legacy config format"` | `major` | Conventional |
| `"feat(api)!: change response shape"` | `major` | Conventional |
| `"제목 : feat! : 내용"` | — | **테스트 자체가 없음** |

즉 **minor 판정은 우리 컨벤션에서 그대로 작동**하고(tier-1 정규식이 제목을 캡처),
major만 경로가 비어 있다.

참고로 auto-wizard에서도 `!` 마커 실사용 커밋은 **0건**이고 현재 버전은 `0.8.2`다.
major 자동 승격은 그쪽에서도 실전 발동 이력이 없는 경로다.

### 2. AI 호출 구조가 다르다

auto-wizard는 `call_openai_compatible`을 `changelog_manager.py`에 직접 들고 있다.
projectops는 AI 호출이 `changelog_providers/` 사다리로 분리돼 있어 같은 자리에 박을 수 없다.

## 설계

### 판정 규칙 (결정적 — AI 없음)

릴리스 구간은 `origin/main..HEAD` (deploy PR의 head = 개발 브랜치).
커밋 **제목 한 줄만** 본다 (본문 접근 불가 — Conventional Commits 조항 13에 따라
`!` 마커 단독으로도 표준을 만족하므로 표준이 허용하는 부분집합).

| 커밋 형태 | 판정 |
|---|---|
| `제목 : feat! : 내용` (**tier-1 확장 — 신설**) | `major` |
| `feat!:` / `fix(api)!:` (Conventional) | `major` |
| `제목 : feat : 내용` / `feat: 내용` | `minor` |
| fix·docs·chore·refactor·test, 자유형식, 미분류 | `patch` |
| `[skip ci]` 포함 / `Merge `로 시작 / 빈 줄 | 제외 |

한 구간에 섞이면 **가장 높은 것이 이긴다** (major > minor > patch).

### major를 수동 전용으로 두지 않는 이유

이식하면 breaking 판정 정규식이 어차피 딸려온다. 그대로 두면 죽은 규칙이 되어
나중에 버그로 오해받는다. 반면 tier-1 정규식에 `!`를 여는 비용은
**정규식 한 글자 + 테스트 2줄**이고, `/pro-commit`은 사용자가 타입을 직접 고르는
구조(`skills/pro-commit/SKILL.md:201`)라 선택지에 `feat!`을 한 줄 더하면 끝이다.

`!`는 **사람이 의도적으로 칠 때만** 발동하므로 실질 안전성은 수동과 동일하고,
"major 올려야 하는데 version.yml 고치는 걸 깜빡"하는 실패 모드가 사라진다.
minor가 45번 동안 0번 올라간 것과 정확히 같은 실패 모드다.

### `classify_commits()` 전체를 이식하지 않는다

auto-wizard의 `classify_commits()`는 bump 판정용이 아니라 **릴리스 노트 렌더링용**이다
(제목·설명 병합, 말미 URL 제거, 버킷별 마크다운 생성). projectops는 그 일을
`changelog_providers/` 사다리가 이미 하므로, 통째로 들이면 릴리스 노트 생성 경로가
둘로 갈라져 드리프트가 난다.

→ `classify_bump_level()`을 **정규식 3개짜리 자급자족 함수**로 새로 쓴다.
각 줄에서 타입과 `!` 유무만 뽑아 판정하고, 버킷 구성·렌더링은 하지 않는다.

### 하위호환 — 신규 ON / 기존 OFF

`version.yml`의 `metadata.template.options.semver_auto`로 제어한다.

| 상태 | 동작 |
|---|---|
| 키 없음 (**기존 통합 레포 전부**) | `patch` 고정 — 현행 무변화 |
| `semver_auto: true` | 규칙 승격 |
| `semver_auto: false` | `patch` 고정 |

신규 통합 시 `true`로 기록한다. **이미 배포된 레포(RomRom-BE/FE 등)의 버전이
예고 없이 튀지 않게 하는 것**이 이 기본값의 목적이다. 기존 레포는 사용자가
`version.yml`을 직접 고쳐 켠다.

## 변경 파일

| 파일 | 변경 |
|---|---|
| `.github/scripts/version_manager.py` | `increment_version(v, bump)` 추가, CLI `increment [--bump major\|minor\|patch]`. `increment_patch()`는 호출처 보존을 위해 유지 |
| `.github/scripts/version_manager.sh` | **무수정** — `exec ... "$@"` 통과 shim |
| `.github/scripts/changelog_manager.py` | `classify_bump_level()` + `classify-bump --commits-file` 서브커맨드 |
| `.github/workflows/PROJECT-COMMON-RELEASE-CHANGELOG.yaml` | 커밋 수집 step, `semver_auto` 읽기, bump 전달 |
| `.github/workflows/project-types/common/PROJECT-COMMON-RELEASE-CHANGELOG.yaml` | 위와 **동일 유지** (CLAUDE.md 규칙) |
| `PROJECT-COMMON-VERSION-CONTROL.yaml` | **무변경** (아래 근거) |
| `src/core/version-yml.js` | `parseTemplateOptions`에 `semverAuto` 파싱, `buildVersionYml`에 기록 |
| `version.yml` (이 레포) | `semver_auto: true` |
| `.github/scripts/test/test_classify_bump.py` | 신설 |
| `.github/scripts/test/test_version_manager.py` | bump 케이스 추가 |
| `CLAUDE.md`, 문서 | `!` 마커 규칙, `semver_auto` 설명 |

### 안전망 워크플로우(VERSION-CONTROL)를 건드리지 않는 이유

이 워크플로우는 **릴리스 PR을 거치지 않은 main 직접 push**에만 발동한다.
그 경로의 커밋은 컨벤션 준수를 신뢰할 수 없고, 애초에 비권장 경로다.
auto-wizard도 안전망은 patch로 유지한다.

## 안 하는 것 (YAGNI)

- **AI 보조 판정** — 같은 커밋이 릴리스마다 다른 버전을 내는 비결정성을 들이지 않는다.
  우리 레포는 컨벤션 준수율이 높아(최근 60커밋 중 미분류 사실상 없음) 얻는 게 적다.
- **마법사 질문 추가** — #485가 "질문 부담 축소" 방향으로 정리한 흐름을 거스른다.
  `version.yml` 직접 편집으로 충분하다.
- **안전망 워크플로우 semantic화**
- **`version_code` 로직 변경** — 매 릴리스 +1 유지

## 검증

```bash
python3 -m pytest .github/scripts/test/test_classify_bump.py
python3 -m pytest .github/scripts/test/test_version_manager.py
npm test
```

두 RELEASE-CHANGELOG 파일이 동일한지 diff로 확인한다.
