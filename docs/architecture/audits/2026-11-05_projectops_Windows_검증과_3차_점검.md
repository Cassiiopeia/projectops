# 3차 점검: Windows 실측과 코드 감사 (2026-11-05)

기준 커밋 `5495c73c`. 운영 파일 525개. 생성 파일로 빠진 2개(`changelog_providers/_common.py`, `release_tools.py`)는 문자열 상수 때문에 걸린 오탐이고 직접 쓴 코드다.

**한 줄 결론:** 코드 품질은 나아졌지만, 위험은 scan이 못 보는 곳에 있었다. 워크플로의 권한 게이트, 동결 규칙을 돌리지 않는 CI, 일반 Windows 사용자 환경에서만 드러나는 크래시다.

## 이전 감사 재판정

| 항목 | 판정 | 근거 |
|---|---|---|
| 거대 스킬 CLI | 해결 | 스킬 `.py` 최대 458줄 (상한 450에 8줄 초과) |
| 마법사 거대 파일 | 일부 개선 | playstore.js 1735줄, testflight.js 994줄, playstore.py 1804줄 |
| 경위 주석 | 일부 개선 | 규칙이 `에서 옮겼다`만 봐서 `로 옮겼다`가 통과 |
| 삼키는 예외 | 변화 없음 | 89건, 표본 대부분은 정리용이고 실해는 2건 |
| 테스트 비대 | 해결 | 소유자 결정으로 가드 5개만 유지 |
| 동사형 bool | 변화 없음 | `kill_browser`는 True가 "아직 살아 있음" |
| store_locales 중복, `--mode version`, `os.kill` | 해결 | 규칙 위반 0 |
| REST 6벌 | 해결 | `.github/scripts/github_api.py`로 공통화 |
| 규칙이 CI에서 막음 | 악화했다가 이번에 해결 | 규칙 테스트를 지운 뒤 아무도 안 돌렸다 |

## 이번에 고친 것

| 이슈 | 원인 | 내용 |
|---|---|---|
| #1049 | Node 22 이상 `fs.cpSync` | Windows 비ASCII 경로에서 메시지 없이 프로세스 종료. 직접 재귀 복사로 교체, 규칙 `no-fs-cpsync` |
| #1049 | `subprocess(text=True)` | cp949로 UTF-8 git 출력을 읽어 `stdout`이 `None`. 49곳 수정, 규칙 `no-subprocess-text-without-errors` |
| #1050 | Windows 안내 명령의 `&&` | PowerShell 5.1 파싱 오류 |
| #1051 | CI 공백 | 스모크를 Node 20과 24, 비ASCII 경로로 확장 |
| #1052 | 워크플로 게이트 | 릴리스 자동 머지에 출처 레포 확인, 프리뷰와 QA 봇에 작성자 권한 검사, 규칙 `no-unguarded-release-target` |
| #1053 | 숨은 실패 | 설치기와 마법사의 실패 원인 표시, doctor CRLF 오탐, ledger를 CI에서 판정 |

**개발 PC가 결함을 가렸다.** 이 PC에는 `PYTHONUTF8=1`과 전역 `core.longpaths`가 켜져 있어, 그대로 돌리면 위 크래시가 재현되지 않는다. 검증 방법은 `CLAUDE.md`에 기록했다.

## 남은 것 (소유자 판단 필요)

- **pro-ssh 호스트 키:** `ssh_connect.py`는 `AutoAddPolicy`로 어떤 호스트 키든 수락한다. pro-launch는 `accept-new`를 쓴다. 고치면 키가 바뀐 서버의 접속이 막힌다.
- **긴 함수:** `runInteractive` 444줄, `runCore` 319줄, `printSummary` 308줄. 제안서를 먼저 쓸 대규모 작업이다.
- **`kill_browser` 반환값:** 결과 객체로 바꾸는 편이 맞다.
- **마이그레이션 이관 결과:** `obsolete-workflows.js`의 `carried`를 읽는 곳이 없어 이관 성공과 실패가 모두 안 보인다.
- **스크립트 출력:** `.github/scripts`의 Actions 전용 스크립트는 이모지 출력을 그대로 둔다. Actions 러너가 UTF-8이라 실해가 없다.

## 동결 후보 규칙 (미적용)

- `no-auto-add-host-key`: `AutoAddPolicy\(`. 현재 위반 2건이라 동결 목록이 필요하다.
- `no-silent-catch-in-ide-adapters`: `src/core/ide/`의 이유 없는 catch, 10건.
- `no-history-comment-variants` 패턴을 `(에서|으로|로) 옮겼다`로 확장, 5건.

## 잘 되어 있는 것

- 인코딩 없는 `open`, `read_text`, `write_text`가 0건이고, Python `shell=True`도 없다.
- 워크플로가 댓글과 브랜치명을 env로 받는다.
- `changelog_manager.py`, `apply_build_profile.py`, `paths.py`는 깨진 파일을 덮어쓰지 않고 멈춘다.
- 계층 역방향 import와 자산 사본이 0건이다.

## 확인하지 못한 것

- 포크 PR을 실제로 열어 본 재현. 게이트는 코드로만 확인했다.
- 약어, 뜻 없는 이름, boolean 범주와 `commented_out_code` 5건.
- 마법사 HTML 전체와 `github-projects-sync-worker`.
