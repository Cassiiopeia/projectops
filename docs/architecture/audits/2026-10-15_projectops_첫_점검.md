# 아키텍처 감사: projectops (2026-10-15)

## 한 줄 결론

계층 방향과 자산 사본은 깨끗하다. 문제는 **크기와 주석**이다 — CLI 하나에 서브커맨드를 계속 붙여 1,000줄 넘는 파일이 쌓였고, 이유를 "예전에는 ~했다" 경위로 적는 주석 습관이 11개 파일에 퍼져 있다.

## 수치 (scan · assets · deps · rule-docs)

| 항목 | 값 | 지난 감사 |
|---|---|---|
| 스캔 파일 | 405 (JS·Python) | — |
| 300줄 초과 / 500줄 초과 | 52 / 27 | — |
| 경위 주석 | 25 (운영 코드 11개 파일) | — |
| 장식 배너 | 327 (`.github/util` 231) | — |
| 삼키는 catch·`except: pass` | 54 (skills 29) | — |
| 접두사 없는 boolean 변수 / 질문형 아닌 boolean 함수 | 47 / 51 | — |
| 약어 · 뜻 없는 이름 | 268 · 95 | — |
| 계층 역방향 import · 모듈 순환 | 0 · 0 | — |
| 자산 사본 · 같은 이름 다른 내용 | 0 · 0 | — |
| 규칙 문서 줄글 주석 유도 | 0 | — |

## Top 10

| # | 심각도 | 문제 | 근거 | 원인 |
|---|---|---|---|---|
| 1 | high | 스킬 CLI가 단일 파일로 비대 | `skills/pro-agent-test/scripts/e2e_cli.py` 1959줄, `pro-oss-consult/scripts/oss_cli.py` 1269, `pro-figma/scripts/figma_cli.py` 1264, `pro-github/scripts/github_cli.py` 1104 | "skill 1개 = py 1개" 표준(CLAUDE.md)이 크기 상한 없이 적용됨. `pro-launch`만 `pro_launch/commands/` 로 나눔 |
| 2 | high | 마법사 JS·PY 거대 파일 | `.github/util/flutter/playstore-wizard/playstore-wizard.js` 2360, `playstore-wizard.py` 1796, `testflight-wizard.js` 1529 | 공통 자산(`_shared/`)은 뽑았지만 마법사 본체는 단계별 분리 없음 |
| 3 | med | 경위 주석 ("예전에는 ~") | `src/core/options-ask.js:238`, `src/core/version-yml.js:143`, `scripts/common/gh_branch.py:174`, `skills/pro-agent-test/scripts/e2e_cli.py:314`, `skills/pro-github/scripts/github_cli.py:1084` 외 6개 파일 | 이유(WHY)를 과거 사건으로 서술하는 습관. 이유는 남기고 경위는 커밋·이슈로 (conventions §7.5·7.6) |
| 4 | med | 삼키는 예외 | skills 29건 (`pro-launch/scripts/app_input.py` 5건 등), `.github/util` 13, `scripts` 8 | 실패해도 되는 정리 코드와 진짜 오류 무시가 구분되지 않음 — 이유 주석이 없는 곳이 대상 |
| 5 | med | 테스트 파일 비대 | `skills/pro-agent-test/tests/test_e2e_cli.py` 1436, `pro-launch/tests/test_launch_cli.py` 1289, `pro-figma/tests/test_figma_cli.py` 1092 | CLI 비대(#1)를 그대로 따라감 |
| 6 | med | boolean 반환 함수가 동사형 | `scripts` 20건, `skills` 22건 (예 `create_branch -> bool`) | 성공 여부를 bool로 돌려주는 설계 — 이름보다 반환을 결과 객체로 바꾸는 쪽 (conventions §8 "거부 사유가 담긴 결과") |
| 7 | low | 장식 배너 | `.github/util` 231건 | 마법사 파일 구획용. 파일 분리(#2)하면 자연히 사라짐 |
| 8 | low | 접두사 없는 boolean 변수 | `src` 18건, `skills` 17건 | JS 옵션 객체 필드(`dryRun` 등)는 외부 계약이라 바꾸면 깨짐 — 내부 지역변수만 대상 |
| 9 | low | 뜻 없는 이름 `tmp`·`result`·`data` | 95건, 절반이 `test/` | 테스트 픽스처 변수 — 우선순위 낮음 |
| 10 | low | 규칙 문서의 없는 경로 참조 | `CLAUDE.md`의 `build.gradle`·`pubspec.yaml` 등 31건 | 대부분 **사용자 프로젝트 파일**을 가리키는 정상 서술 (오탐). `AGENTS.md`의 `.github/.projectops/`만 확인 필요 |

## 스택별

### JavaScript (`src/`, `bin/`)
- 계층: `src/cli` → `src/core` 단방향 유지, 역방향 0
- [high] 300줄 초과 8개 — `src/core/copy/workflows.js` 등. 단계 머리글 주석은 잘 되어 있음
- [med] 경위 주석 5개 파일 (`options-ask.js`, `version-yml.js`, `workflow-groups.js`, `resolve-options.js`, `commands/doctor.js`)

### Python (`skills/*/scripts`, `scripts/common`, `.github/scripts`)
- [high] CLI 4개가 1,000줄 초과 (#1)
- [med] `except: pass` 다수, boolean 반환 함수 이름

## 규칙 문서
- 코드와 모순: 확인한 범위에서는 없음. `CLAUDE.md`의 "skill 1개 = py 1개" 표준이 크기 문제의 원인 (#1)
- 줄글 주석 유도: 0 (레포 규칙 문서에는 없음. 소유자 전역 `~/.claude/CLAUDE.md`의 "코드 주석 필수 — WHY 중심"은 별도)

## 잘 되어 있는 것
- **규칙을 테스트로 강제하는 문화**: `test/options-schema.test.js`(정본 ↔ 코드), `test/workflow-groups.test.js`, `.github/scripts/test/test_workflow_permissions.py`, `skills/pro-launch/tests/test_launch_architecture.py`(계층 테스트). 다른 레포로 옮길 모범
- **단일 원본**: `src/core/options-schema.js`, `src/core/resolve-options.js`, `scripts/sync_extras.py` + 동기화 테스트
- **CLI 분할 모범**: `skills/pro-launch/scripts/pro_launch/commands/` — #1 리팩터링의 기준 파일
- `src/core/ide/adapter.js`는 주석이 코드보다 길지만 계약(typedef) 문서라 정상

## 확인 못 한 것
- 함수 단위 중복(같은 로직 3곳 이상) — CLI는 이름 유사도만 본다. 파일 분리 설계 때 직접 확인
- `.github/workflows/*.yaml` 내부 스크립트 블록 (scan 대상 아님)

## 동결 후보 규칙
| id | 금지하는 것 | 현재 위반 수 |
|---|---|---|
| `no-history-comment` | 운영 코드(`src/`·`scripts/`·`skills/*/scripts/`)의 `예전에는`·`예전엔` 경위 주석 | 11개 파일 |
| `no-silent-except-in-skill-scripts` | `skills/*/scripts`의 `except …: pass` (이유 없이 삼키기) | 29건 (파일 수는 freeze 때 확정) |

파일 크기(#1·#2)는 패턴 규칙으로 표현되지 않는다 — 리팩터링 때 `test_launch_architecture.py`처럼 줄 수 상한 테스트를 따로 둔다.

## 처리 기록

| # | 상태 | 내용 |
|---|---|---|
| 3 | 완료 | 운영 코드 12곳의 "예전에는/예전엔" 경위 서술을 현재형 이유로 교체 (이슈 번호 유지, 동작 변화 없음). 규칙 `no-history-comment` 추가 — 테스트 파일 3개는 동결 목록, `scripts/tests/architecture/`가 CI에서 새 위반을 막는다 |
