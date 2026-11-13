# 6차 점검 (2026-11-13)

기준: v4.103.0 이후 `develop`. 운영 파일 617개, 테스트 9개(생성 파일 4개 제외). 5차(2026-11-10) 항목을 지금 상태로 다시 판정하고, 오늘 바뀐 166개 파일을 `diff --base 75d2f538`으로 따로 봤다. `scan` 수치는 후보이고, 직접 열어 확인한 것만 문제로 적었다.

**한 줄 결론:** 구조는 여전히 건강하다. 오늘 새로 확인된 실제 문제는 두 가지다. 설치기가 번역 카탈로그를 거치지 않고 한국어를 바로 출력하는 곳 5곳, 그리고 `main` 기준 외부 PR을 `develop`으로 대상만 바꿔 squash할 때 릴리스 커밋이 딸려 오는 절차상 구멍이다.

## 잘 되어 있는 것

- 역방향 의존 0건, 저장소 직접 접근 0건 (`deps`)
- 동결 규칙 8개 위반 0건 (`ledger check`)
- 오늘 변경분: 새 동결 위반 0건, boolean 이름 지적 0건
- 모의 테스트가 실제 결함 2건을 배포 전에 잡았다. 깨진 템플릿 리터럴, `context.repo`를 잘못 바꾼 이름 일괄 변경. 둘 다 `scripts/issue_assignment.cjs`이다. 로직을 `scripts/`에 따로 두고 시험한 방식이 효과를 냈다.

## 5차 항목 재판정

| 5차 항목 | 지금 | 근거 |
|---|---|---|
| `CLAUDE.md` 1146줄 (결정 필요) | **해결** | 294줄. 영역 규칙을 `docs/architecture/agent/*.md`로 옮기고 "건드리기 전에 읽을 문서" 표로 연결했다. `AGENTS.md`에 영어 요약을 추가했다 (#1140) |
| 300줄 넘는 비마법사 파일 33개 | 32개, 그대로 | 릴리스 경로(`version_manager.py` 1049줄, `ios_release.py`, `changelog_manager.py`)는 실행 대조 없이 나누지 않는다는 판단을 유지한다 |
| `swallowed_catch` · `unhandled_catch` | 문제 없음 유지 | 5차 때 보지 못한 JS(`src/`) 표본 6건을 열었다. 모두 실패를 기록하거나 결과에 실어 돌려준다 (`src/core/copy/workflows.js:162,311`, `src/core/orphan-workflows.js:83`, `src/core/migrations/index.js:41`) |
| 큰 마법사 파일 | 그대로, 의도됨 | 소유자 결정 유지 |

## 이번에 확인한 문제

| 문제 | 근거 | 조치 |
|---|---|---|
| 설치기가 한국어를 직접 출력 (영어 사용자에게 한국어가 보임) | `src/core/copy/workflows.js:102,164`, `src/core/ide/legacy.js:36,39` (`src/core/ide/adapter.js:33`은 개발자용 검증 오류) | 입문 이슈 #1170으로 올림. 동결 규칙 후보 (아래) |
| `main` 기준 포크 PR을 `develop`으로 대상만 바꿔 squash하면 `main` 전용 릴리스 커밋이 딸려 옴 | #1145 머지 커밋 `a1f991ca`가 README 버전 줄, 플러그인 매니페스트, `package.json`까지 바꿈 | CONTRIBUTING(영·한) 메인테이너 절에 "squash 전 Files changed 확인"을 추가. 번역 점검이 버전 줄만 바뀐 커밋은 무시하게 함 |
| 오늘 만든 파일의 긴 머리 주석과 약어 | `scripts/check_readme_translations.py:2`, `scripts/issue_assignment.cjs:1`, `repo` 약어, `src/core/ci-minutes-sub.js` `m` | 고침 (두 줄 요약, `repository`, `pushBlock`) |

## 오탐으로 판단

- `rule-docs` 빠진 경로 24개: 설명 문장에 나오는 사용자 레포 파일(`build.gradle`, `pubspec.yaml`, `.github/.projectops/` 등)과 거르는 대상 이름(`conftest.py`)이다. 이 레포에 없는 것이 맞다.
- `history_comments` 25개: 상위 25개를 열었다. 대부분 지금 동작을 설명하는 문장이거나 출처 표기(`stealth.py:3`)다. 경위 서술은 마법사 파일 안 3건(`playstore-wizard.py:7,15`, `testflight-wizard.py:36`)뿐이고 마법사는 손대지 않는다는 결정에 따른다.
- `hidden_coupling`: `CLAUDE.md`와 pro-figma, 생성 파일 쌍(`troubleshooting.md` ↔ `index.json`), 한·영 문서 쌍, Android·iOS 워크플로 쌍. 규칙상 함께 고치는 쌍이다. `pro-skill-bug`의 `excerpt.py` ↔ `transcript.py`는 생산자와 소비자 관계(이벤트 사전 모양)라 정상이다.
- 새 정의 유사 이름: `release_commit_range`(PR base 범위)와 `close_issues_on_release.release_range`(push 전후 범위)는 하는 일이 다르다. `readable_cwd` 두 벌은 서로 import할 수 없는 단일 파일 진입점이라 의도된 사본이다 (사본 2개).

## 동결 후보

`no-korean-message-in-installer`(설치기의 한국어 직출력 금지)를 검토했으나 **만들지 않기로 했다** (소유자 결정, 2026-11-13: 불필요한 CI는 두지 않는다). 남은 5건은 입문 이슈 #1170으로 고친다.

## 확인하지 못한 것

- `browser_attach_failed`(#1154)의 실제 발생: CDP가 응답하면서 붙기는 실패하는 상황을 만들지 못해 코드만 읽었다.
- 문서 사이트 빌드에서의 깨진 링크: 문서 수정 작업이 진행 중이라 그 결과로 확인한다.
