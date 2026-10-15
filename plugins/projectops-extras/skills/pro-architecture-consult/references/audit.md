# audit — 전체 점검

> 언제 읽나: "전체적으로 봐줘", "점검", "엉망인 것 같은데", 동결 목록이 없는 상태의 "정리해줘".

목표: 문제를 근거와 함께 찾고, **지금 있는 위반을 동결해 더 늘지 않게** 만든다. 보고서로 끝내지 않는다.

## 1. 이어받을 것부터

`detect PATH`로 시작한다.

- `prior_audits`가 있으면 **읽고 항목마다 지금도 그런지 다시 판정한다** (고쳐짐 / 그대로 / 악화). 처음부터 다시 쓰지 않는다.
- `allowlists`·`rule_tests`가 있으면 그 레포가 이미 쓰는 강제 장치다. 같은 규칙을 `docs/architecture/rules/`에 중복으로 만들지 않고, 그 장치를 확장하는 쪽을 먼저 제안한다.
- `has_architecture_folder`가 참이면 `ledger PATH check`·`conventions PATH check`로 현재 상태를 본다.

## 2. 사실 수집

```
scan PATH --limit 50
assets PATH
deps PATH
rule-docs PATH
```

출력 해석은 `references/facts.md`. 수치는 후보일 뿐이다 — 원문을 열어 확인한 것만 문제로 쓴다.

## 3. 스택별 감사 (병렬)

스택(또는 모노레포 폴더)마다 읽기 전용 하위 에이전트를 하나씩 띄운다. 프롬프트에 반드시 넣는 것:

- 그 폴더의 `CLAUDE.md`·`AGENTS.md`·`.claude/rules`를 **먼저** 읽는다. 규칙 문서도 감사 대상이다 (코드와 모순, 없는 파일 참조)
- `references/conventions.md` 기준, `references/stacks/<스택>.md`의 "자주 나오는 AI 냄새"
- 2단계 사실 JSON 중 그 폴더 부분
- 요구: `file:line` 근거, 추측 금지, 심각도(high/med/low), "확인 못 한 것" 목록, 우선순위 top 10, 700단어 이내
- 잘한 것도 적게 한다 — 다른 폴더로 옮길 수 있는 패턴이다

스택을 넘는 것(자산 사본, 토큰 값 드리프트, 서버 enum ↔ 클라이언트 문자열, API 타입 손복사)은 감사 에이전트 하나를 따로 둔다.

## 4. 판정 기준

- **깐깐하게.** "AI 치고 괜찮다"가 기준이 아니다. 사람이 1년 유지보수할 코드인지 본다.
- 판정은 레포가 아니라 **구간** 단위다. 사람이 짠 레포에도 바이브코딩 구간이 섞인다.
- 같은 문제가 여러 곳이면 **원인 한 줄**로 묶는다 (예: "공통 로딩 컴포넌트가 문서에 없어서 12곳이 각자 만듦").
- 규칙 문서가 문제를 **유도**하면 그것이 근본 원인이다 (`rule-docs`의 `prose_comment_inducing`).

## 5. 보고서 · 동결 제안

1. `get-output-path PATH --title "<제목>"` → `references/report-template.md` 형식으로 쓴다
2. 반복 패턴마다 **동결할 규칙 후보**(`.rule` 초안)를 보고서 끝에 붙인다 — `references/stacks/<스택>.md`의 "첫 규칙 후보"에서 출발
3. 사용자에게 보고서 요약 + 동결 후보 목록을 보여 주고 **승인받은 규칙만** 만든다
4. 규칙마다 `ledger PATH freeze --rule <id>` → `ledger PATH check`가 pass인지 확인
5. 규칙 테스트가 아직 없으면 `install-tests`를 제안한다 (`references/init.md` 5단계)
6. `scan PATH --record`로 기준선 수치를 남긴다

다음 행동은 사용자에게 고르게 한다: "top 10 중 무엇부터 refactor할까요?"
