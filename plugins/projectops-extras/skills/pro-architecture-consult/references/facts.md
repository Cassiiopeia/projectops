# CLI 출력 읽는 법

> 언제 읽나: `arch_cli.py` 결과 JSON을 해석할 때. 수치는 후보이고, **판정은 원문을 읽고 한다.**

공통: `truncated`에 범주가 있으면 목록이 잘린 것이다 (값 = 전체 수). `--limit`을 올리거나 범주별로 다시 본다.

## scan

| 범주 | 뜻 | 오탐이 나는 곳 |
|---|---|---|
| `long_files` | 300줄 초과 (`must_split_files`: 500 초과) | 데이터·상수 표 파일 |
| `comment_heavy_files` | 주석 줄 > 코드 줄 | 상수·설정 파일의 값 설명 (정상일 수 있음) |
| `long_comment_blocks` | 5줄 이상 연속 주석·docstring | 라이선스 머리, 공개 API 문서 |
| `history_comments` | "기존에는·바꿨다·previously" 같은 경위 문구 | 마이그레이션 로직 설명 |
| `banner_comments` | `// ====` 장식 | 문서 생성용 구분 |
| `prose_ending_comments` | "~합니다·~하기 위해" 문장체 | 사용자 노출 문구를 담은 주석 |
| `boolean_names` | is/has/can/should 없는 boolean 변수·필드·매개변수 | 외부 API·직렬화 필드명 (바꾸면 계약이 깨짐) |
| `boolean_functions` | 질문형 아닌 boolean 반환 함수 (`create_branch -> bool`) | 성공 여부를 돌려주는 동작 함수 — 이름보다 반환 설계를 본다 |
| `abbreviations`·`meaningless_names` | 약어 단어, 단독 `data`·`result` 같은 이름 | 도메인 용어 (`repo`가 저장소 자체를 뜻하는 곳) |
| `file_type_mismatch` | Dart 파일명 ≠ 타입명, TSX 파일명 ≠ export 컴포넌트 | 한 파일에 작은 타입 여러 개 |
| `hardcoded_tokens` | 색·간격·글자 크기·자산 경로 직접 사용 (토큰 정의 폴더 제외) | 테마 파일이 다른 이름 폴더에 있을 때 |
| `swallowed_catch` | 빈 catch·`except: pass` | 실패해도 되는 정리 코드 (이유 주석이 있어야 함) |

생성 파일(`*.g.dart`·`*.freezed.dart`·`*.min.js` 등)과 `build`·`node_modules` 같은 폴더는 처음부터 뺀다.

## assets

- `identical_copies`: 같은 내용이 여러 곳 — `areas`가 2개 이상이면 플랫폼을 넘는 손복사 후보. 생성 스크립트로 바꿀 대상
- `same_name_different_content`: 같은 이름(배율·크기 접미사 제거)이 영역마다 다른 내용 — **한쪽만 고쳐진 낡은 사본** 후보. 가장 먼저 본다

## deps

- `layer_violations`: 금지 방향 import (화면 → 인프라, 도메인 → 다른 계층 등). 계층은 폴더 이름으로 분류하므로, 폴더 이름이 관례와 다른 레포는 `layer_edges`로 전체 그림을 먼저 본다
- `gradle_modules.cycles`: 모듈 순환. 있으면 high
- import 해석은 레포 안 파일만 본다. 외부 패키지는 무시한다

## diff

`references/check.md` 표 참고. 새 파일은 낡은 주석·고쳐 쓴 주석 검사에서 뺀다 (모든 줄이 새 줄이라).

## rule-docs

- `missing_references`: 백틱 안 경로가 문서 폴더·레포 루트 어디에도 없음 (맨 파일명은 레포 어디든 있으면 통과)
- `prose_comment_inducing`: 줄글 주석을 부르는 문구. 코드 주석 과잉의 **원인**일 수 있다 ("주석 필수"·"자세히" 류. "WHY 중심" 단독은 conventions §7.5와 같으므로 잡지 않는다)

## ledger

- `check`: 규칙별 `new`(새 위반 — 코드를 고친다), `fixed`(고쳐짐 — `tighten`으로 목록에서 지운다), `verdict`
- `freeze`: `.allow`가 이미 있으면 `allow_exists`로 거부한다. 동결 목록에 줄을 더하는 명령은 없다 (의도된 설계)

## conventions

`same` · `outdated`(정본이 바뀜) · `locally_modified`(프로젝트가 고침 — 그 프로젝트 규칙으로 존중) · `missing`.
