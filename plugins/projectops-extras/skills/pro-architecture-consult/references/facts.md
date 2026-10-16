# CLI 출력 읽는 법

> 언제 읽나: `arch_cli.py` 결과 JSON을 해석할 때. 수치는 후보이고, **판정은 원문을 읽고 한다.**

## 읽는 순서 (scan)

1. **`excluded`부터 본다.** 레포가 소유하지 않은 코드는 이미 빠져 있다: `tooling`(`.github/`·`.claude/` 등 설치물 — 원본 레포에서 고칠 일), `generated`(생성 머리 표식·gen-l10n), `vendored`(`vendor/`, 버전 머리가 있는 정적 JS, shadcn ui). 사람이 고친 shadcn 컴포넌트처럼 봐야 할 것이 섞였으면 `scan PATH --all`로 다시 본다 (항목에 `origin` 태그).
2. **`counts`는 운영 코드만이다.** 테스트 쪽은 `test_counts`. 항목에 `origin: "test"`가 붙은 것은 운영 항목 뒤에 온다. 테스트 이름·상수는 우선순위를 낮춘다.
3. **`review_order` 순서로 연다**: 동작 위험 > 공통화·단일 원본 > 구조 > 주석 > 이름·토큰. 수가 많은 범주가 큰 문제인 것이 아니다 (긴 주석 150건보다 다시 던지지 않는 catch 3건이 먼저다).
4. **`hotspots`로 원인을 묶는다.** 한 파일에 여러 범주가 몰리면 그 파일 하나가 원인이다 (분리 대상).
5. 목록은 심한 것 먼저, 같은 무게면 폴더마다 번갈아 나온다. `truncated`에 범주가 있으면 잘린 것이다 (값 = 전체 수). 범주 하나만 더 보려면 `--category X --limit 200`, 폴더 하나만 보려면 `--only app/` (하위 에이전트에 넘길 사실).

## scan 범주

| 범주 | 뜻 | 판단 단서 · 오탐이 나는 곳 |
|---|---|---|
| `unhandled_catch` | 본문이 있는데 throw·return·raise 없는 catch(`no_rethrow`), catch-all이 다른 예외로 바꿔 던짐(`rewrap_all`) | `no_rethrow`: 트랜잭션 안에서 흡수하면 high(롤백 표시만 남고 커밋 때 터진다), 롤백·보상 뒤에 흐름이 계속되면 high. `records_failure`(실패를 결과 목록에 담음)·`sets_error_state`(화면 오류 상태·에러 콜백·알림 — UI 경계의 정상 처리)는 낮다. 문제는 로그만 남기고 사용자에게 실패를 숨기는 경우. `rewrap_all`: `has_passthrough_before`(앞 catch가 업무 예외를 그대로 던짐)나 try 안에 업무 예외가 없는 checked→unchecked 변환은 정상. `try_body_throws`가 붙으면 try 안에서 직접 던진 예외가 있다는 뜻이라 사라지는지 먼저 본다. 안에서 던진 업무 예외 코드가 사라질 때만 문제 |
| `test_code_in_production` | `src/main` 아래 test·mock 폴더, `Test*Controller` 같은 파일 | 운영 노출 여부(보안 설정·프로필)를 원문으로 확인 |
| `swallowed_catch` | 빈 catch·`except: pass` | `has_reason_comment`가 참이면 이유가 적힌 정리 코드일 수 있다 |
| `hardcoded_urls` | 코드 줄의 `https?://` 리터럴 (스키마·example·localhost·텍스트 블록·`example=` 속성 제외) | 설정 원본으로 옮길 대상(허용 출처·외부 서비스 주소). 외부 공개 링크는 상수 한 곳이면 정상. 한 파일에 몰려 있으면 문서 예시일 수 있으니 원문을 연다 |
| `lint_disabled_files` | 파일 머리에서 린트 전체 끄기 (규칙 이름을 지정한 끄기는 제외) | `marker` 원문을 본다. 도달 불가 분기·중복 조건 같은 **버그를 알리는 규칙**을 끈 것은 high. 생성 코드가 아니면 끈 이유가 없는 경우가 대부분 |
| `bypassed_components` | 공통 폴더(`core`·`design`·`common`·`apis` 등)에 같은 원본 호출을 감싼 파일(`wrappers`)이 있는데 다른 곳이 직접 부름 | `wrappers`를 열어 진짜 래퍼인지 확인. 맞으면 "공통 지점이 문서에 없다"가 원인 |
| `common_call_candidates` | 래퍼 없이 3개 파일 이상이 같은 원본을 직접 부름 | 세 번째 원칙 후보 (공통 지점을 새로 만든다) |
| `duplicate_constants` | 같은 값 상수가 2개 파일 이상 (문자열은 값, 숫자는 이름+값으로 묶음) | 설정 키·접두사는 2곳이어도 단일 원본 대상. 우연히 같은 짧은 문자열은 무시 |
| `long_files` · `long_functions` | 300줄 초과(500 초과는 `must_split_files`) · 60줄 넘는 함수 | 데이터·상수 표 파일. 함수 길이는 중괄호·들여쓰기 기준 근사. UI 컴포넌트는 마크업이 길이를 부풀리니 150줄 이상이거나 데이터 조회·오류 처리가 섞인 것만 본다 |
| `file_type_mismatch` | Dart 파일명 ≠ 타입명, TSX 파일명 ≠ export 컴포넌트 (대소문자 무시) | 묶음 파일(`_parts` 등)과 최상위 함수가 주인인 파일은 이미 뺐다 |
| `history_comments` | 경위 문구 ("기존에는", "옮겼다", "~에서 전환", "previously") | 명사형 끝맺음("삭제함")과 사용자·관리자 동작·가정문은 이미 뺐다. 마이그레이션 로직 설명은 정상 |
| `commented_out_code` | 3줄 이상, 60% 이상이 코드 모양인 주석 블록 | conventions §7.7 "주석 처리한 옛 코드" — 지울 대상 |
| `long_comment_blocks` | 5줄 이상 주석. `kind`: `prose`(줄글) / `api_doc`(@param·HTML 태그 문서 주석) | `prose`가 먼저 나온다. `api_doc`이 80% 넘으면 팀 문화이니 한 줄로 요약하고 `prose`만 표본으로 판정한다. 라이선스 머리는 이미 뺐다 |
| `comment_heavy_files` | 주석 줄 > 코드 줄 | `is_declaration_only`(인터페이스·추상 클래스·`.d.ts`)는 정상인 경우가 많다 |
| `banner_comments` · `prose_ending_comments` | `// ====` 장식 · "~합니다" 문장체 | 낮은 우선순위. 파일 분리하면 배너는 사라진다 |
| `boolean_functions` | 질문형 아닌 boolean 반환 함수 | override·`exists`/`contains`/`equals`/`matches`·React 훅·함수 타입은 이미 뺐다. 성공 여부를 돌려주는 동작 함수는 이름보다 반환 설계(사유가 담긴 결과)를 본다 |
| `boolean_names` | is/has/can/should 없는 boolean | `contract` 태그(dto·설정 바인딩·JPA·직렬화)는 바꾸면 JSON·설정 키·컬럼이 깨진다 — "고칠 것"이 아니라 "이관 계획이 필요한 것"으로 분리 |
| `abbreviations` · `meaningless_names` | 약어 단어 · 단독 `data`·`result`·`info`·한 글자 지역 변수 | `memberInfo`·`JwtUtil` 같은 합성어는 허용(conventions §2.2). 도메인 용어(`repo`가 저장소 자체)와 타입 이름(`class Item`, 변수명=타입명)은 정상. 관례가 굳은 `result`(AOP·콜백)는 낮다 |
| `hardcoded_tokens` | 색·0 아닌 간격·글자 크기·자산 경로 직접 사용 | 토큰·테마 파일(`*_colors.dart`, `tailwind.config.*`)은 뺐다. 디자인 컴포넌트 안도 잡는다 (컴포넌트도 토큰을 써야 한다) |

## 총계를 믿기 전에 (오탐 묶음 확인)

- `excluded`에 **생성물·외부 라이브러리로 빠진 파일이 있으면 2~3개를 직접 열어** 머리 표식이 진짜인지 본다. 소유한 코드가 빠졌으면 `scan --all`로 다시 본다
- 한 범주가 **한 파일·한 폴더에 몰려 있으면** 오탐 묶음일 수 있다 (`hotspots`) — 첫 표본 3건을 원문과 대조한 뒤 범주 전체를 판정한다
- `unclassified_directories`(deps)는 계층 분류가 안 돼 **위반이 숨은 영역**이다. 폴더 이름이 관례와 다르면 영역 구성을 먼저 파악한다
- 규칙 문서가 0개로 나오면 README·에이전트 설정 폴더·`docs/`를 직접 찾는다. 찾은 문서는 코드·빌드 설정과 **서로 모순되지 않는지** 대조한다 (의존 방향이 뒤집혀 적힌 경우가 있다)

## scan이 보지 못하는 것 (감사 에이전트가 직접 본다)

CLI는 정규식 사실 수집이다. 아래는 사실이 없으니 원문으로 확인하고 보고서 "확인한 방법"에 적는다.

- **보안 노출**: 인증 없이 열린 경로(보안 설정의 permitAll·테스트 API)가 운영 프로필에서 켜지는지(프로필 제한 유무), 인증서·호스트명 검증을 끄는 코드(모든 인증서 신뢰), 비밀 값이 코드·로그에 있는지
- **토큰·세션 처리가 여러 곳**: 인터셉터·헤더 함수·저장소 직접 접근이 섞였는지 (`bypassed_components`의 `sessionStorage/localStorage`가 단서)
- **스택을 넘는 드리프트**: 서버 enum ↔ 클라이언트 상수, API 응답 ↔ 손으로 쓴 타입
- **근사 중복**: 이름만 다른 비슷한 컴포넌트·서비스 (같은 코드 3곳)
- **주석 ↔ 코드 불일치**: 감사에서는 표본 10개를 골라 주석이 지금 코드와 맞는지 읽는다
- **지원하지 않는 언어**: CLI는 Dart·Java·Kotlin·Python·JS·TS만 읽는다. 그 밖의 소스(Go·Rust·Swift·C#·PHP 등)는 `not_analyzed_languages`에 파일 수만 나온다. 수가 크면 "scan 0건"을 "문제 없음"으로 읽지 말고 그 언어 코드를 직접 표본으로 읽는다
- **문자열 안 코드**: 여러 줄 문자열·텍스트 블록·`example` 블록 안(다른 언어 스크립트, API 예시 JSON)은 이름·URL·토큰 검사에서 뺀다. 그 안의 실제 문제는 직접 본다
- **HTML·CSS·템플릿**: 스캔 대상이 아니다. 관리자 템플릿 인라인 스크립트·CSS 크기는 직접 본다
- **규칙 문서 내부 모순**과 **기존 규칙 테스트가 문서 규칙 중 무엇을 강제하지 않는지**

## deps

- `layer_violations`: 금지 방향 import. 분류 순서: Java·Kotlin 파일 접미사(`*Controller`·`*ExceptionHandler` > 표현, `*Repository` > 인프라, `*Service` > 응용) > 예외·상수 폴더(`common` — 방향 규칙 밖) > 폴더 이름 > Next `app/` 라우터(표현). 폴더 이름이 관례와 다르면 `layer_edges`로 전체 그림을 먼저 본다
- `from_role: "state"`: Flutter provider·notifier가 데이터 계층을 import. 허용 여부는 팀 결정이다 (`stacks/flutter.md`)
- `test_violation_count`: 테스트 파일의 위반 수 (목록에 넣지 않음)
- `cross_module_repository_imports`: 다른 Gradle 모듈의 Repository를 직접 import. 목록은 위반 후보 먼저이고, 요약의 건수도 후보만 센다
  - `is_to_common_module`: 공통 모듈 저장소 — 대개 정상
  - `is_from_aggregator_module`: 여러 도메인을 조합하는 응용·진입점 모듈 — 도메인 저장소를 쓰는 것이 설계일 수 있다. 레포의 모듈 문서·build 의존 방향과 대조해서 판정
  - 진짜 후보는 **도메인↔도메인**과 **표현 → 저장소**. 한 파일이 저장소를 여러 모듈에서 많이 주입하면 경계보다 책임 과다가 문제
- `unclassified_directories`: 계층 분류가 안 된 영역(소스 파일 수). 이 폴더 안의 역방향 import는 `layer_violations`에 나오지 않는다
- `gradle_modules.cycles`: 운영 의존 순환 (테스트 범위 의존은 `test_edges`). 있으면 high
- 레포에 기존 계층 예외 목록(`detect.allowlists`)이 있으면 그 목록과 대조한다. 기존 장치가 허용한 간선은 위반으로 쓰지 않는다

## assets

- 무시(gitignore) 대상 파일은 세지 않는다 (`ignored_assets`가 그 수). `identical_copies`: 같은 내용이 여러 곳. 영역을 넘는 손복사가 먼저 온다. `is_generated_icon_set`(flutter_launcher_icons 결과)·`is_reference_copy`(`docs/`·figma 내보내기)는 낮다
- `same_name_different_content`: 같은 이름·같은 확장자(PNG는 같은 픽셀)가 영역마다 다른 내용 — **한쪽만 고쳐진 낡은 사본** 후보. 가장 먼저 본다
- `format_variants`: 같은 이름이 svg·png처럼 형식만 다름 (웹폰트 형식 묶음은 제외) — 한쪽이 안 쓰이는 사본일 수 있다 (참조를 검색해 확인)

## rule-docs

- `missing_references`: 문서 폴더·조상 폴더·경로 꼬리 일치 어디에도 없는 경로. 지시문이 가리키는 없는 경로(따를 수 없는 규칙)를 "사용 금지" 목록 속 옛 경로보다 먼저 본다. `in_code_block`은 트리 그림·예시일 수 있다
- `ignored_references`: gitignore 대상 경로 (비밀 설정 파일 등 — 없는 게 정상일 수 있다. 문서가 그렇다고 적었는지 본다)
- `prose_comment_inducing`: 줄글 주석을 부르는 문구 ("주석 필수"·"자세히" 류. "WHY 중심" 단독은 conventions §7.5와 같아 잡지 않는다)
- `duplicate_documents`: 같은 내용 규칙 문서 사본 — 한쪽만 고쳐지면 모순이 생긴다

## diff · ledger · conventions

- diff: `references/check.md` 표 참고. 새 파일은 낡은 주석·고쳐 쓴 주석 검사에서 뺀다
- ledger `check`: 규칙별 `new`(새 위반 — 코드를 고친다), `fixed`(고쳐짐 — `tighten`으로 목록에서 지운다), `verdict`. `freeze`는 `.allow`가 있으면 `allow_exists`로 거부한다 (목록에 줄을 더하는 명령은 없다)
- conventions: `same` · `outdated`(정본이 바뀜) · `locally_modified`(프로젝트가 고침 — 그 프로젝트 규칙으로 존중) · `missing`
