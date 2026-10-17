# init — 규칙을 프로젝트에 깔기

> 언제 읽나: "내 규칙 깔아줘", "새 프로젝트", "이 레포도 내 스타일로", audit 뒤 규칙 테스트가 없을 때.

목표: 이후 모든 에이전트 세션이 **말하지 않아도** 규칙을 따르고, 어기면 CI가 막는다.

## 1. 현재 상태

`detect PATH` → 스택, 기존 규칙 문서, 기존 규칙 테스트. `conventions PATH check --stack <s>...`로 설치 여부.

## 2. 규칙 문서 설치

```
conventions PATH install --stack flutter --stack spring
```

- `docs/architecture/CONVENTIONS.md`와 `docs/architecture/stacks/<스택>.md`가 생긴다 (기존 파일은 덮어쓰지 않는다)
- 상태가 `locally_modified`면 그 프로젝트가 규칙을 고친 것이다. 덮어쓰지 않고, 정본과 다른 점만 알려 준다
- `outdated`면 정본이 바뀐 것이다. 차이를 보여 주고 사용자가 원하면 `--force`

## 3. 에이전트 규칙 문서에 연결

`CLAUDE.md`(없으면 `AGENTS.md`)에 아래 문단을 넣는다. 이미 비슷한 절이 있으면 그 절을 고친다.

```markdown
## 코딩 규칙

코드를 쓰거나 고칠 때 `docs/architecture/CONVENTIONS.md`와 `docs/architecture/stacks/<스택>.md`를 따른다.
- 새로 만들기 전에 비슷한 것이 있는지 찾는다. 같은 계층의 모범 파일을 먼저 읽는다
- 주석은 한 줄 요약·단계 머리글·값의 뜻만. 경위·이슈 이력은 커밋에 남긴다
- 로직을 바꾸면 그 위 주석도 지금 동작에 맞춘다. 건드리지 않은 코드의 주석은 고치지 않는다
- `docs/architecture/rules/*.allow`(동결 목록)에 줄을 더하지 않는다
```

`rule-docs PATH`의 `prose_comment_inducing`(예: "코드 주석 필수 — WHY 중심")은 줄글 주석을 부른다.
위 문단의 주석 줄로 바꾸자고 제안한다. `missing_references`(없는 파일 참조)도 같이 고친다.

## 4. 모범 파일

스택 문서의 "모범 파일 지정" 기준으로 계층마다 하나씩 후보를 골라 사용자에게 보여 준다.
승인받으면 `docs/architecture/stacks/<스택>.md` 끝에 `## 모범 파일` 절로 `경로 — 한 줄 이유`를 적는다.

## 5. 규칙 테스트

```
install-tests PATH --stack flutter --module app
```

- 모듈마다 한 번. 이미 있으면 덮어쓰지 않는다
- 규칙이 0개여도 테스트는 통과한다. 첫 규칙은 audit 결과나 스택 문서의 "첫 규칙 후보"에서 고른다
- 새 테스트가 CI에서 실제로 도는지 확인한다 (그 레포의 테스트 명령으로 한 번 실행)
- ArchUnit·import-linter·dependency-cruiser는 더 정확하지만 새 의존성이다 — 제안만 한다

## 6. 마무리

`scan PATH --record`로 첫 기준선을 남기고, 바뀐 파일 목록을 보여 준 뒤 `/pro-commit` (타입 `chore`).
