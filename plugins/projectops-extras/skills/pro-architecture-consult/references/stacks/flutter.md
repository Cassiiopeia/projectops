# Flutter 스택 규칙

> 언제 읽나: 대상에 `pubspec.yaml`(flutter)이 있을 때. audit·refactor·init 공통.

## 계층 지도

| 계층 | 폴더 | 들어가는 것 |
|---|---|---|
| 표현 | `features/<기능>/presentation/{pages,widgets,providers}` | 화면, 기능 전용 위젯, Riverpod 상태 |
| 응용 | `features/<기능>/application` 또는 `domain/usecases` | 유스케이스, 화면 밖 업무 규칙 |
| 도메인 | `features/<기능>/domain/models` | 순수 모델 (Flutter·dio import 없음) |
| 인프라 | `features/<기능>/data/{repositories,sources}`, `core/network` | dio, 저장소, 로컬 DB |
| 공통 | `core/` (설정·에러·포맷), `design/` 또는 `presentation/design/` (토큰·컴포넌트) | |

**계층 우선 구조**(`lib/presentation/{pages,widgets,providers}`, `lib/domain`, `lib/data`, `lib/core`)도 흔하다. 계층은 같고 폴더 순서만 다르다 — 규칙의 `paths`를 `lib/presentation/pages/,lib/presentation/widgets/`처럼 실제 폴더로 맞춘다 (`lib/features/`로 두면 0건 동결).
provider·notifier가 `data/`를 import하는 것(`deps`의 `from_role: "state"`)은 Riverpod 관례상 허용하는 팀이 많다. 레포 규칙에 없으면 위반이 아니라 "팀 결정 필요"로 적는다.

의존 방향: 표현 → 응용 → 도메인 ← 인프라. **화면이 `data/`·`core/network`를 직접 import하면 위반.**
`core/`·`shared/`가 `features/`를 import하는 것도 위반 (공통이 기능에 묶인다).

## 자주 나오는 AI 냄새

- 같은 기능 안에서 presentation → data 직접 import (`ref.watch(xxxRepositoryProvider)`를 화면에서 바로)
- 공통 컴포넌트 있는데 `CircularProgressIndicator(`·`CupertinoActivityIndicator(`·`showDialog(`·`SnackBar(` 직접 사용
- `Color(0x`·`Colors.xxx`·숫자 `EdgeInsets`·`fontSize:` 직접 사용 (토큰 우회)
- `Image.asset('...')` 경로 직접 (자산 상수·컴포넌트 우회)
- `bool loading`·`bool selected` (접두사 없음), 파일명 ≠ 클래스명
- 화면 파일 500줄+ (상태·위젯·업무 규칙이 한 파일)

## 첫 규칙 후보 (`docs/architecture/rules/`)

```
# no-direct-progress-indicator.rule
description=화면 코드에서 로딩 인디케이터 직접 사용 금지 (공통 로딩 컴포넌트 사용)
paths=lib/features/
extensions=.dart
pattern=\b(?:CircularProgressIndicator|CupertinoActivityIndicator)\(

# no-color-literal-in-features.rule
description=화면 코드에서 색 값 직접 사용 금지 (토큰 사용)
paths=lib/features/
extensions=.dart
pattern=\bColor\(0x|\bColors\.(?!transparent\b)[a-z]

# presentation-must-not-import-data.rule
description=표현 계층이 데이터 계층을 직접 import 금지 (provider·usecase 경유)
paths=lib/features/
extensions=.dart
pattern=^import .*/data/
```

마지막 규칙은 `paths`를 `presentation` 폴더로 좁힌다 (`lib/features/<기능>/presentation/`을 기능마다 쉼표로).
모노레포면 `paths` 앞에 앱 폴더를 붙인다 (`app/lib/features/`).

## 규칙 테스트

`install-tests PATH --stack flutter --module <앱 폴더>` → `test/architecture/architecture_rules_test.dart`.
`flutter test test/architecture`로 돈다. 순수 Dart 패키지면 import를 `package:test/test.dart`로 바꾼다.

## 모범 파일 지정

init에서 계층마다 하나씩 고른다: 상태 관리가 깔끔한 화면 1개, 토큰만 쓰는 위젯 1개, 저장소 1개.
`docs/architecture/stacks/flutter.md` 맨 아래 "모범 파일" 절에 경로와 한 줄 이유를 적는다.
