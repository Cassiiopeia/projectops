# 아키텍처 규칙

규칙 하나 = 파일 두 개. 스택별 규칙 테스트(`architecture_rules_test.dart` · `ArchitectureRulesTest.java` ·
`test_architecture_rules.py` · `architecture.rules.test.mjs`)가 이 폴더를 읽어 CI에서 판정한다.

## `<id>.rule`

```
description=화면 코드에서 플랫폼 로딩 인디케이터 직접 사용 금지 (공통 컴포넌트 사용)
paths=app/lib/features/
extensions=.dart
exclude=app/lib/features/_generated/
pattern=CupertinoActivityIndicator\(
```

- `paths`·`exclude`: 레포 루트 기준 경로 접두사, 쉼표 구분. glob 아님
- `pattern`: 정규식 (여러 줄 모드). 첫 `=` 뒤 전부가 값
- `paths` 비우면 레포 전체

## `<id>.allow` (동결 목록)

- 규칙을 만들 때 있던 위반 파일 목록. 한 줄에 경로 하나, `#` 주석
- **줄을 지울 수만 있고 더할 수 없다.** 새 위반은 코드를 고친다
- 고친 파일이 목록에 남아 있으면 테스트가 실패한다 — 그 줄을 지운다

판정: 위반 − 목록 = 새 위반(실패), 목록 − 위반 = 고쳐진 항목(목록에서 지우라고 실패).
