# 7차 점검 (2026-11-14)

기준: v4.104.0 이후 `develop`. 운영 파일 622개, 테스트 9개(생성 파일 4개 제외). 6차(2026-11-13, `d8a628fe`) 이후 98개 파일이 바뀌었다(README 개편, 자동 보고 버그 14건, 문서 사이트). 변경분은 `diff --base d8a628fe`로 따로 봤고, `scan` 수치는 후보일 뿐이라 열어서 확인한 것만 문제로 적었다.

**한 줄 결론:** 구조는 건강하다. 이번에 고칠 것은 이름 3곳과 긴 함수 설명 2곳뿐이었고 모두 고쳤다. 남은 판단거리는 출력 옵션(`--brief`·`--field(s)`) 처리가 세 벌로 늘어난 것 하나다.

## 잘 되어 있는 것

- 역방향 의존 0건, 저장소 직접 접근 0건 (`deps`). 이미지·글꼴 사본 충돌 0건 (`assets`). README 이미지 16장을 추가했는데도 그렇다.
- 동결 규칙 8개 위반 0건, 변경분의 새 동결 위반 0건.
- 새 README 이미지가 HTML 원본과 렌더 스크립트로 관리된다 (`docs/recording/readme_assets/`). 이름을 바꾼 뒤 다시 렌더링한 결과가 이전과 똑같아 원본과 산출물이 맞물려 있음을 확인했다. 옵션 레퍼런스(`scripts/build_options_reference.mjs --check`)도 같은 방식의 단일 원본이다.
- 이슈 14건이 모두 원인 단위로 고쳐졌다. 예: #1184는 보고된 원인(지운 경로)이 아니라 zsh의 `$P` 미분할이 원인이었고, 같은 수정으로 빈 `--root`가 엉뚱한 레포에 커밋하던 위험(#1187)까지 막았다.

## 6차 항목 재판정

| 6차 항목 | 지금 | 근거 |
|---|---|---|
| 설치기의 한국어 직출력 5건 | 그대로, 입문 이슈 #1170 대기 | 동결 규칙은 만들지 않기로 한 결정 유지 |
| 300줄 넘는 비마법사 파일 32개 | 33개 | 새로 넘은 것: `skills/pro-ssh/scripts/windows_script.py` 301, `pro-launch/.../render_scaffold.py` 320, `web/actions/open.py` 347. 셋 다 한 가지 책임이라 지금 나누지 않고, 다음에 기능을 더할 때 나눈다 |
| `main` 기준 포크 PR squash 문제 | 해결 | CONTRIBUTING에 확인 절차, 번역 점검이 버전 줄만 바뀐 커밋은 무시 |

## 이번에 확인하고 고친 것

| 문제 | 근거 | 조치 |
|---|---|---|
| 의미 없는 이름 | `docs/recording/readme_assets/assets.js:14` `value` | `localizedText` |
| 약어 | `scripts/build_options_reference.mjs:13` `repoRoot` | `repositoryRoot` |
| boolean 접두사 없음 | `pro-launch/.../runtime/android_device.py:163,196` `retried` | 내부 변수는 `has_retried`. JSON 응답 키 `retried`는 계약이라 그대로 |
| 긴 함수 설명 (규칙 2줄 이내) | `pro-commit/scripts/commit_cli.py:146` 5줄, `web/actions/wait.py:47` 5줄 | 2줄로 줄임 |

## 그대로 둔 것 (판단)

- **모듈 머리 주석 4개(5~9줄)**: `render_readme_assets.py`, `build_options_reference.mjs`, `windows_script.py`, `android_device.py:178`. 실행 예시와 반환 모양을 담은 도움말 역할이라 줄이면 정보가 사라진다.
- **`emit.py` `configure_output(brief=...)`**: 여러 CLI가 키워드로 넘기는 공용 인자라 이름을 바꾸면 호출부 전체가 바뀐다.
- **`windows_script.py`의 `emit`**: 공용 코드를 쓰지 않는 독립 CLI(`disk_cli.py`, `tunnel_cli.py`와 같은 방식)라 자기 출력 함수를 갖는 것이 맞다.
- **오래된 주석 의심 9건**: 열어 봤다. 바뀐 코드의 동작과 어긋난 주석은 없었다 (`render.py:85` 레포 밖 거절, `wait.py:58` 등).

## 결정이 필요한 것

- **출력 옵션 처리가 세 벌**: `scripts/common/cli_parser.py:75` `_extract_output_options`, `pro-launch/.../cli.py:71` `_pop_output_options`, `pro-image/scripts/image_cli.py:39` `_extract_output_options`(#1181). 세 번째에 공통화한다는 규칙에 걸린다. 다만 pro-launch는 자체 런타임이고, pro-image는 Windows 콘솔에서 한글 경로를 지키려고 공용 코드를 일부러 쓰지 않는다. 공통화한다면 `proc.py`처럼 원본 하나를 두고 `sync_extras.py` 방식의 생성 사본을 쓰는 안이 맞다. **판단: 합치지 않는다.** 40줄 남짓에 실행 환경이 셋 다 달라 생성 사본 체계를 두는 비용이 더 크다. 대신 `docs/architecture/agent/skills.md`에 세 곳을 함께 고치라는 규칙과 위치를 적었다 (규칙 원본은 `output-schemas.md`).

## 동결 후보

없음 (불필요한 CI는 두지 않는다는 결정).

## 확인하지 못한 것

- #1175·#1186 실기기 설치: 호스트 메모리 부족으로 새 에뮬레이터를 띄우지 못했다.
- #1189 Windows 서버의 간헐 인증 실패 원인.
