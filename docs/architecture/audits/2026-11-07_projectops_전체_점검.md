# 4차 점검 (2026-11-07)

기준: v4.89.2 이후 `develop`. 운영 파일 539개. `scan` 수치는 후보이고, 이번에 직접 열어 확인한 것만 문제로 적었습니다.

**한 줄 결론:** 의존 방향과 동결 규칙은 건강합니다. 위험은 큰 마법사 파일과, 여러 곳을 함께 고쳐야 하는 약속에 있습니다. 이번 사고(`RESOLVER_REVISION` 누락)도 후자입니다.

## 잘 되어 있는 것

- 역방향 의존 0건, 저장소 직접 접근 0건, 이미지·글꼴 사본 충돌 0건
- 동결 규칙 8개 위반 0건

## 확인한 문제와 이번 조치

| 문제 | 근거 | 조치 |
|---|---|---|
| 스킬 표를 바꿔도 고정 진입점이 갱신되지 않음 | #1086 | 수정, CLAUDE.md에 약속 기록 |
| `ui_design_cli`, `launch_cli`가 진입점 갱신을 안 함 | 재현함 | 수정 |
| 경위 주석 규칙의 빈틈 | #1059 | 규칙 확대, 주석 5곳 수정 |
| `pro-ui-design` 내부 상수 중복 | `tokens.css` 3곳 | `settings.py`로 통합 (`server.py`는 독립 실행이라 예외) |

## 오탐으로 판단

- `rule-docs` 누락 경로 23건: 직접 확인한 결과 `build.gradle`, `.github/.projectops/` 등 **사용자 레포 쪽 경로**를 설명한 것입니다. 고칠 것이 없습니다.
- `duplicate_constants`의 `"projectops"`, `"ui-design"` 등: 표 항목과 식별자라 공통화해도 얻는 것이 없습니다.

## 승인이 필요해 손대지 않은 것

수치만으로 고치면 동작을 깨뜨릴 위험이 커서, 항목별 제안과 승인 후 진행합니다.

| 순위 | 대상 | 이유 |
|---|---|---|
| 1 | `playstore-wizard.py`(1804줄), `playstore-wizard.js`(1735줄), `projects-sync-wizard.js`(1339줄), `version_manager.py`(1029줄), `testflight-wizard.py`(1007줄) | 450줄 기준 초과. 앱 배포 경로라 실제 실행 대조 없이 나누면 위험 |
| 2 | `unhandled_catch` 242, `swallowed_catch` 87 | 대부분 직접 확인 전. `records_failure` 표시가 없는 것부터 표본 확인 필요 |
| 3 | 긴 주석 블록 455, 배너 주석 350 | 동작 위험은 없지만 수정량이 큼. 파일을 분할할 때 함께 처리 권장 |
| 4 | `CLAUDE.md` 1146줄 | 에이전트가 매번 읽는 비용. 주제별 문서 분리 검토 |

## 동결 후보

`SKILL_CLIS` 변경 시 `RESOLVER_REVISION` 증가를 검사하는 감시 검사. 프로젝트 규칙상 감시 검사 추가는 소유자와 상의 대상입니다.

## 제안: `playstore-wizard.py` 정리 (승인 전, 코드 변경 없음)

1. **반복 패턴:** 함수 41개, 1804줄. 가장 긴 함수는 `cmd_apply` 189줄, `patch_build_gradle` 146줄, `create_keystore` 112줄. 출력, 쓰기 게이트, gradle 패치, 키 파일, Fastfile 생성, 환경 감지가 한 파일에 있습니다.
2. **계층:** 같은 폴더에 `playstore_wizard/`를 두고 `output`, `gates`, `gradle_patch`, `signing`, `fastlane_files`, `detect` 모듈로 나눕니다. 진입 파일 이름과 인자는 그대로입니다.
3. **새 공통 코드:** 없음. `testflight`와 쓰기 게이트 블록을 글자 단위로 맞추는 약속(`check-consistency.py`)이 있어 이 블록은 진입 파일에 남겨야 합니다.
4. **이름 변경:** 없음. 동작 변경 없이 위치만 옮깁니다.
5. **적용 범위와 안전망:** 마법사 HTML이 `python .github/util/flutter/playstore-wizard/playstore-wizard.py`로 부르므로 호출은 유지합니다. 임시 Flutter 프로젝트에서 `setup`, `apply`, `detect-app-id`를 `--dry-run`과 실제 실행으로 전후 돌려 산출물 해시를 대조합니다.
6. **규칙 테스트:** 추가하지 않습니다 (감시 검사 5개 원칙).
7. **문서:** 파일 머리글의 "단일 파일" 문구와 `version.json` 이력을 수정합니다.
8. **하지 않는 것:** 문구, 검증 순서, 종료 코드 변경.

**판단:** 이 파일은 일부러 단일 파일로 합친 것이고 스킬의 450줄 규칙 대상도 아닙니다. 앱 배포에 쓰이며 최근 버그가 이 구조 때문에 난 것도 아닙니다. **나누는 이득이 위험보다 작아 지금은 하지 않는 것을 권합니다.** 다음에 이 파일을 고칠 때 `cmd_apply`만 함수로 나누면 충분합니다.

## E2E 트레이스백 추가 확인

첫 실행 1회 뒤 재현 시도를 11회 더 했고 모두 통과했습니다 (CI 제외).

**원인 확인 (2026-11-08):** 세션 기록에서 첫 실행(2026-11-07 10:56–10:57)의 트레이스백을 전부 다시 봤습니다. 모두 검증용 셸 파이프라인의 인라인 `python3 -c` 파서에서 났고, projectops 파일에서 난 것은 없습니다.

| 트레이스백 | 원인 |
|---|---|
| `JSONDecodeError: Expecting value` | zsh 변수에 명령을 담아 불러 `no such file or directory`로 실행 자체가 안 됨, 빈 출력을 파싱 |
| `JSONDecodeError: Invalid control character` | `echo`가 JSON 안의 `\n`을 실제 줄바꿈으로 바꿈 |
| `KeyError: 'count'` | 파서가 응답에 없는 키를 읽음 |

도구 결함이 아니므로 고칠 것은 없습니다. 검증 스크립트는 함수로 감싸고 `printf`나 파일로 넘깁니다.
