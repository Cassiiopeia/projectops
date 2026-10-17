# 아키텍처 감사: projectops (2026-10-18)

## 한 줄 결론
같은 값과 목록(옵션 키, 레포 주소, 스킬 개수, GitHub API 호출 코드)을 손으로 복사해 둔 곳이 많고, 그중 대조 테스트가 없는 곳에서 실제 버그 3건이 나왔다. 규칙 문서(CLAUDE.md·ARCHITECTURE.md)는 코드보다 늦게 고쳐지고, 동결 규칙은 표현 하나만 막아 같은 문제가 다른 말로 다시 들어온다.

## 수치 (scan · assets · deps · rule-docs)
> 이번 scan 은 `.github/` 를 tooling 으로 빼고 셌다(감사 스킬 결함, 아래). 지난 감사는 `.github/` 를 포함해 센 값이라 직접 비교할 수 없다. `.github/` 는 `scan --all --only .github` 로 따로 봤다.

| 항목 | 이번 (`.github` 제외) | 지난 감사 (`.github` 포함) |
|---|---|---|
| long_files | 22 | 52 |
| banner_comments | 61 (+ `.github/util` 211) | 327 |
| history_comments | 17 (운영 `예전에는` 0) | 17 |
| boolean_functions | 54 | 51 |
| abbreviations | 66 | 268 |
| meaningless_names | 126 | 97 |
| swallowed_catch | 55 | (skills 29) |
| 자산 사본 · 계층 역방향 import | 0 · 0 | 0 · 0 |
| 규칙 문서 없는 경로 참조 | 28 (진짜 1) | 31 |

## Top 10
| # | 심각도 | 문제 | 근거 | 원인 |
|---|---|---|---|---|
| 1 | high | 업데이트를 다시 돌릴 때마다 `store_locales_ios`·`store_locales_play` 키가 한 줄씩 늘어남 (YAML 키 중복) — **재현함** | `src/core/version-yml.js:426` `OWNED_OPTION` 에 두 키 없음. 생성기는 `:598-599` 에서 씀 | 생성기가 쓰는 키 목록을 손으로 따로 들고 있고 대조 테스트가 없음 |
| 2 | high | `--mode version` 이 `ai_summary`·`intent` 를 잃음 (`ai_summary: false` → `true`) | `src/commands/version.js:15-40` 이 두 값을 넘기지 않음. `full.js:57` 은 넘김 | 진입점마다 기본값·전달 목록을 다시 적음 (CLAUDE.md "진입점에 기본값을 다시 적지 않는다" 위반, 25곳) |
| 3 | high | Windows 에서 생존 확인이 프로세스를 **종료**시킴 | `scripts/common/state.py:104-106` `os.kill(pid, 0)`, 호출 `state.py:132` (옛 `browser.json` 이주 시) | OS 분기 단일 지점 `pro_launch/runtime/procs.py:33` 을 공용 코드가 우회 |
| 4 | med | GitHub REST 호출 함수 6벌, 서로 갈라짐 (인증 `token`/`Bearer` 혼용, `issue_helper._request` 는 timeout 없음 → 무한 대기 가능). 마커 댓글 갱신도 3벌 | `.github/scripts/` `changelog_notice.py:104` · `issue_helper.py:331` · `close_issues_on_release.py:56` · `pr_summary_comment.py:64` · `dispatch_downstream.py:121` · `store_deploy_config.py:190` | 파일 단위로 복사되는 구조라 공통 모듈을 두지 않음 |
| 5 | med | 규칙 문서가 코드보다 늦음 | `CLAUDE.md:810,829` personas 로드(로드하는 스킬 0개), `:933` 지운 analyze·plan CLI, `:779`·`README.md:132` extras 1종(실제 2종), `:651` 없는 `.github/workflows/test/`, `src/ARCHITECTURE.md:69` "두 경로가 기본값을 따로 고른다"(#851 과 모순) | 스킬 삭제·추가(#849, extras) 때 문서를 함께 고치는 장치 없음. 개수를 6곳에 손으로 적음 |
| 6 | med | 레포 주소 리터럴이 정본을 우회 | `src/core/paths.js:11` 정본, 직접 기재 9개 파일 (`ide/adapters/claude.js:10` 등) | 설정값 단일 원본(conventions §5) 미강제 |
| 7 | med | 동결 규칙을 다른 표현이 우회 | `종전에는`(`options-ask.js:335` 등 3), `옮겼다`(`run-trace.js:9`, `e2e_cli.py:4` 등), `예전 pro-commit 은`(`commit_style.py:4`). 검사 경로에 `.github/scripts`·`plugins/` 없음 | 패턴이 `예전(?:에는\|엔)` 하나 |
| 8 | med | 거대 파일 그대로 (지난 #1·#2) | e2e_cli 1956 · oss_cli 1269 · figma_cli 1264 · github_cli 1101 · gh_client 1053 / playstore-wizard.js 2360 · .py 1796 · testflight-wizard.js 1529 (줄 수 변화 거의 0) | 레포 규칙이 "skill 1개 = py 1개" 를 크기 상한 없이 표준으로 둠 — **팀 결정 필요** |
| 9 | med | 이유 없는 catch-all `pass` 12건, 설정 고장 무음 처리 | `scripts/common/paths.py:58` (깨진 config → `output.root` 기본값으로 조용히, #623 재발 위험), `web/actions/wait.py:54` (셀렉터 문법 오류를 "안 보임"으로) | 정리용 무시와 진짜 오류 무시가 구분되지 않음 |
| 10 | med | 마법사 dry-run 블록이 3종 사이에서 갈라짐, 검증기는 플래그 문자열만 봄 | `playstore-wizard.py:508,1225` ↔ `testflight-wizard.py:867`, firebase 블록 없음, `check-consistency.py:192-205` | 주석은 "동일성 검증"이라 하지만 실제 검사는 일부 |

## 스택별
### JavaScript (`src/` · `bin/` · `site/`)
- [high] #1 · #2
- [med] `src/core/ide/adapters/pi-common.js:45` — 사용자 `settings.json` 을 해석에 실패하면 `{}` 로 덮어써 다른 키를 지움 (JSONC 허용 여부 미확인)
- [med] `version-yml.js` 631줄, `interactive.js` 506줄, `runInteractive` 439줄 함수
- [low] `doctor.js:31` · `breaking-check.js:13` fetch 공통 지점 없음(타임아웃 한쪽만)
- 계층 방향(`src/cli` → `src/core`) 유지, `unhandled_catch` 4건 오탐(결과에 담아 표시)

### Python (`skills/` · `scripts/` · `plugins/`)
- [high] #3
- [med] `common/memory.py:150` `seen_today` 가 있는데 `journal.py:110-127` · `knowledge.py:~410` 이 다시 구현 (3곳째)
- [med] `skills/pro-launch/tests/test_launch_architecture.py:33` 이 `pro_launch/` 패키지만 봐서 `app_input.py` 461줄(상한 450), `browser_pick.py:29`·`stealth.py:65` 의 OS 분기를 못 잡음
- [med] 동사형 bool 반환 31건(skills) — `create_branch` · `kill_browser` · `delete_credential` · `clear_stale_locks`. 이름보다 실패 사유를 담은 결과로 바꿀 대상
- [med] 테스트 48개 파일이 각자 `sys.path.insert` (conftest 2개 스킬만)
- pro-launch 가 swallowed_catch 29 → 46, bool 반환 22 → 31 로 늘린 주범 (#904 등 대량 추가)

### `.github/` (템플릿 원본 — 사용자 레포로 복사되는 제품 코드)
- [med] #4 · #10
- [low-med] `dispatch_downstream.py:111` 워크플로 파싱 실패를 `continue` 로 넘겨 대상·미도달 어디에도 안 남음
- [low] 죽은 코드 `changelog_providers/github_ai.py` (복사 목록·사다리에서 빠짐, 테스트 2개만 붙잡음)
- [low] stdout UTF-8 재설정 5곳 2가지 형태
- shim 3쌍(`.sh` → `.py`) 위임 구조 유지, 정합성 검증기 통과, CLI 테스트 16/16

## 이전 감사 대비
| 이전 항목 | 지금 |
|---|---|
| 1 스킬 CLI 비대 | 그대로 |
| 2 마법사 거대 파일 | 그대로 |
| 3 경위 주석 | 고쳐짐 (운영 `예전에는` 0) — 단 다른 표현으로 남음(#7) |
| 4 삼키는 예외 | 악화 (skills 29 → 46, pro-launch) |
| 5 테스트 비대 | 그대로 |
| 6 bool 반환 동사형 | 악화 (skills 22 → 31) |
| 7 장식 배너 | 소폭 감소 (`.github/util` 231 → 211) |
| 8 접두사 없는 boolean | 그대로 (JS 옵션 필드는 외부 계약 — 이관 계획 대상) |
| 9 뜻 없는 이름 | 그대로 (대부분 테스트) |
| 10 규칙 문서 없는 경로 | **판정 정정** — 지난 감사는 "AGENTS 1건 확인 필요"였으나 그건 정상이고, 진짜는 `CLAUDE.md:651` 1건 + 내용 어긋남(#5). 경로 검사만으로는 내용 어긋남을 못 잡음 |

## 규칙 문서
- 코드와 모순: `CLAUDE.md:810,829,933,779`, `README.md:132`, `src/ARCHITECTURE.md:69,72-76`(옵션 추가 절차에 `OWNED_OPTION`·`resolve-options.js` 누락 — #1·#2 의 근본 원인)
- 없는 경로: `CLAUDE.md:651` `.github/workflows/test/` (같은 값이 `template_initializer.py:211` 에도)
- 없는 경로 28건 중 21건은 사용자 프로젝트 파일을 가리키는 정상 서술, 6건은 도구 오탐
- 레포 규칙 "skill 1개 = py 1개"(`CLAUDE.md:842,924`, `mcp-subcommand-rules.md:100`)가 크기 상한이 없어 #8 을 낳음 — 팀 결정 필요
- 팀 결정 필요: 이식 원본 줄번호 주석 132건(".sh L4557 등가") 유지 여부

## 감사 스킬(pro-architecture-consult) 결함
| 결함 | 원인 위치 |
|---|---|
| `skills/pro-launch/.../web/actions/setup.py` 를 Python 패키지 표식으로 오인 | `scripts/arch/detect.py:98` (위치 무관 `setup.py` 판정) |
| 지난 감사로 `docs/architecture/audits/…` 대신 스킬 자신의 `references/audit.md` 를 잡음 | `detect.py:17,44` (이름에 audit 포함만 봄, skills·plugins 미제외) |
| 이 레포의 원본인 `.github/` 를 tooling 으로 제외 | `origins.py:19,111` |
| `scan --all` 결과가 전부 `test_counts` 로 가고 `review_order` 가 빔 | (원인 미확인) |
| 지난 감사 보고서를 규칙 문서로 취급해 인용문을 "줄글 주석 유도"로 셈 | `detect.py:12` `RULE_DOCUMENT_DIRECTORY_PARTS` 에 `/docs/architecture/` |
| `$HOME` · 확장자 없는 모듈 경로를 없는 경로로 오판 | `rule_documents.py:94-101`, `BACKTICK_PATH_PATTERN` |
| `MUST_SPLIT_LINES=500` 두 곳 | `arch/scan.py:19`, `arch/scan_report.py:33` |

## 잘 되어 있는 것
- 정본 + 대조 테스트: `options-schema.js` ↔ `test/options-schema.test.js`, `resolve-options.js` ↔ `test/resolve-options.test.js`(두 경로 비교), `workflow-groups.js` 하나를 복사·고아 감지가 함께 읽음 — #1·#2·#6 을 막는 방법이 이미 레포 안에 있다
- 공통 워크플로 원본 ↔ 루트 복사본 바이트 동일(`test_common_workflow_copies.py`), 버전 동기화 대상 7개 정합
- `pro_launch/registry.py` 자동 수집 + `test_launch_architecture.py` 계층·크기 테스트 — 거대 CLI 분리(#8)의 모범
- `.github/util/flutter/_shared/` 공통 자산과 재정의 검출기, dry-run 메모리 오버레이
- changelog provider 사다리의 폴백 `except` 마다 이유 주석
- `no-history-comment` 가 CI 에서 실제로 새 위반을 막음

## 확인 못 한 것
- #2 실행 재현(코드 경로로만 확인), #3 Windows 실기 재현(Python 동작·`procs.py:33` 근거)
- `pi-common.js:45` — pi 의 `settings.json` 이 JSONC 를 허용하는지
- 마법사 HTML 3종 원문, `github-projects-sync-worker/src/index.ts`, `secrets-converter.js`, i18n 카탈로그
- JS 바인딩 없는 `catch {` 52건 전수, Python `boolean_names` 중 JSON 계약 필드 수
- `test/` 63개 · 스킬 테스트 본문은 크기만

## 동결 후보 규칙
| id | 금지하는 것 | 패턴 · 경로 | 현재 위반 수 |
|---|---|---|---|
| `no-history-comment` 확장 | 경위 서술 다른 표현 | `예전(?:에는\|엔)\|종전에는\|에서 옮겼다` · `src/`·`scripts/`·`skills/`·`plugins/`·`.github/scripts/` | 약 8 (오탐 정리 후 확정) |
| `no-os-kill-probe` | `os.kill(pid, 0)` 생존 확인 | `os\.kill\([^,]+,\s*0\)` · `scripts/`·`skills/` (`procs.py` 예외) | 1 |
| `no-repo-url-literal` | 레포 주소 직접 기재 | `github\.com/Cassiiopeia/projectops\|"Cassiiopeia/projectops"` · `src/` (`paths.js`·`i18n` 예외) | 9개 파일 |
| `no-catch-all-pass` | 이유 없는 `except Exception: pass` | `skills/*/scripts`·`scripts/common` | 12 |
| `no-raw-urllib-in-github-scripts` | `.github/scripts` 의 `urllib.request.Request(` 직접 호출 | `.github/scripts/*.py` | 9개 파일 |
| (테스트) `owned-option-keys` | `OWNED_OPTION` 손 목록 | 생성기가 쓰는 키와 대조 — #1 재발 방지 | — |
| (테스트) 스킬 개수 정합 | CLAUDE.md·README·marketplace 개수 ↔ 실제 폴더 | — | 2곳 어긋남 |
| (테스트) 크기 상한 확장 | pro-launch 450줄 상한을 `skills/*/scripts`·`scripts/` 로 | 초과 파일 동결 | 약 7 |
