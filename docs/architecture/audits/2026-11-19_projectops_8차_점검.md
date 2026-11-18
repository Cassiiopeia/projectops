# 8차 점검 (2026-11-19)

기준: v4.106.0 이후 `develop`. 운영 파일 625개, 테스트 10개(생성 파일 7개 제외). 7차(2026-11-14) 이후 바뀐 파일 92개를 `diff --base a5c0bc06`로 따로 봤다. 주요 변경은 iOS 27 SDK 대응(#1232), Ego Lite 로그인(#1231), 실패 응답의 다음 행동 안내(#1222), pro-remote-link(#1218)다. `scan` 수치는 후보일 뿐이라 열어서 확인한 것만 문제로 적었다.

**한 줄 결론:** 구조는 그대로 건강하다. 이번에 고칠 것은 500줄을 넘은 파일 1개와 동결 규칙 위반 1건이었고 둘 다 고쳤다.

## 잘 되어 있는 것

- 역방향 의존 0건, 모듈 간 저장소 직접 접근 0건 (`deps`). 이미지·글꼴 사본 충돌 0건 (`assets`).
- Xcode 선택(`select_xcode.py`), 빌드 번호(`build_number.py`), 업로드 오류 해석이 각각 한 곳에만 있다. iOS 27 대응도 이 원본만 고쳐 세 워크플로에 같이 들어갔다.
- 함께 바뀌는 문서 쌍(`troubleshooting.md` ↔ `troubleshooting/index.json`)은 생성 스크립트(`scripts/build_troubleshooting.py`)로 이어져 있어 손으로 맞추는 사본이 아니다.

## 7차 항목 재판정

| 7차 항목 | 지금 | 근거 |
|---|---|---|
| 출력 옵션 처리 세 벌 (합치지 않음) | 그대로 | 결정 유지. `skills.md`의 "세 곳을 함께 고치라" 규칙도 그대로 있음 |
| 300줄 넘는 비마법사 파일 | `ios_release.py` 709줄(500 초과) → 고침 | 아래 |
| 모듈 머리 주석 길이 | 그대로 | `select_xcode.py` 머리 주석 19줄도 사용법·반환 모양을 담은 도움말이라 유지 |

## 이번에 확인하고 고친 것

| 문제 | 근거 | 조치 |
|---|---|---|
| 500줄 초과 | `.github/scripts/ios_release.py` 709줄 (7차 673줄, #1232에서 36줄 늘어남) | 입출력 없는 규칙(버전 닫힘·다음 버전, 업로드 오류 분류, IPA 묶음 검사, 상태 표, 실패 사유 정리)을 `ios_release_rules.py`(222줄)로 옮김. `ios_release.py`는 실행 흐름만 남아 487줄. 옮기기 전후로 `classify-error` 4건·`--help`·함수 결과가 같음을 비교. 설치기 복사 목록(`src/core/copy/simple.js`)에 등록, 기본 브랜치 스크립트는 폴더째(`git archive .github/scripts`) 가져오므로 워크플로 수정 불필요 |
| 동결 규칙 위반 | `skills/pro-launch/scripts/pro_launch/runtime/ego_engine.py:69` `subprocess.run(text=True)`만 씀 (`no-subprocess-text-without-errors`) | `encoding="utf-8", errors="replace"` 추가. CI 감시 검사가 다시 통과 |
| 오래된 모듈 설명 | `ios_release.py` 머리 주석이 "오류 해석의 유일한 곳, 새 코드는 test_ios_release.py에 표본과 함께"라고 적음 (테스트 파일은 삭제됨) | 실행 흐름 설명으로 고치고 규칙 위치를 `ios_release_rules.py`로 안내 |

## 그대로 둔 것 (판단)

- **규칙 문서의 "없는 경로" 24건**: 사용자 레포에 생기는 파일(`pubspec.yaml`, `.github/.projectops/`, `decision.json` 등)이거나 예시 경로라 오탐.
- **숨은 결합 상위 쌍**: 한국어·영어 문서 쌍(`docs/*.md` ↔ `docs/en/*.md`), 생성 관계(`troubleshooting.md` ↔ `index.json`). 번역 쌍은 README 번역 점검처럼 따로 묶는 장치가 이미 있다.
- **변경분 오래된 주석 의심 11건**: 열어 봤다. 바뀐 코드와 어긋난 주석은 위 `ios_release.py` 머리 주석 하나뿐이었다.

## 동결 후보

없음 (불필요한 CI는 두지 않는다는 결정).

## 확인하지 못한 것

- Ego Lite 로그인(#1231) 실제 사이트 동작: 작업한 세션이 아직 이슈를 열어 두고 있다.
