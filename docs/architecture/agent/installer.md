# 설치기(npx CLI) 규칙

> **언제 읽나:** `src/` 의 CLI · 마법사 · 옵션 · 실행 기록, breaking changes, 문서 언어, 한글 줄 예산을 건드릴 때
> `CLAUDE.md` 에서 옮긴 정본입니다. `CLAUDE.md` 에는 요약과 이 문서로 가는 링크만 있습니다.

### 옵션 정본은 한 곳이다 (agent 필독)

CLI 플래그와 `version.yml` 옵션의 이름·값·기본값은 **`src/core/options-schema.js`** 한 곳에 있고,
`npx projectops --mode options --json`이 그대로 출력한다. AI agent는 문서를 뒤지지 않고 이 명령으로 확인한다.

- 새 플래그(`src/cli/args.js`)나 `version.yml` 옵션(`parseTemplateOptions`)을 추가하면 **정본에도 반드시 추가한다.**
  `test/options-schema.test.js`가 코드와 정본을 대조해 어긋나면 실패한다.
- 문서에 옵션 표를 새로 복제하지 않는다 — 복제본은 낡는다. 문서는 정본을 가리킨다.
- `src/core/options-schema.js`를 고치면 `node scripts/build_options_reference.mjs`로 `docs/en/cli.md`·`docs/CLI.md`의 생성 표(`<!-- generated: options -->`)를 다시 만든다. `--check`는 쓰지 않고 최신인지만 본다.
- **옵션 값(플래그 > 저장값 > 기본값)은 `src/core/resolve-options.js` 한 곳에서 정한다 (#851).** `index.js`(비대화형)는 결과를 그대로 쓰고, `interactive.js`는 초기값으로 쓴 뒤 사용자가 답한 것만 덮어쓴다. 진입점에 기본값을 다시 적지 않는다 — 두 경로가 갈라져 대화형에서 PR 요약 선택이 버려진 적이 있다.
- 사용자 레포에는 `.github/.projectops/AGENT-GUIDE.md`가 설치된다(`src/core/agent-guide.js`). 옵션 값은 박지 않고 명령만 안내한다.
- 이 레포의 `AGENTS.md`·`GEMINI.md`·`llms.txt`는 템플릿 전용이라 `exclusions.js`와 `template_initializer.py` 양쪽에서 제외된다.

### 문서·데모 GIF는 읽는 언어를 따른다 — 기본은 영어 (#976)

| 대상 | 영어 (기본) | 한국어 |
|---|---|---|
| 문서 사이트 URL | `/projectops/<slug>` ← `docs/en/<slug>.md` | `/projectops/ko/<slug>` ← `docs/<SLUG>.md` |
| 데모 GIF | `docs/images/<이름>.gif` | `docs/images/<이름>.ko.gif` |
| 쓰는 곳 | `README.md`, ja·zh-CN README, `docs/en/` | `docs/i18n/README.ko.md`, `docs/*.md` |

- **파일은 옮기지 않고 URL만 바꾼다.** 규칙은 `site/.vitepress/locale-paths.mts` 한 곳(`rewrites`와 옛 URL 리다이렉트가 같이 쓴다). 두 언어 slug가 같아야 언어 전환이 같은 쪽으로 간다 — 한국어 문서를 추가하면 같은 slug의 영어 문서도 만든다.
- **GIF는 손으로 찍지 않는다.** `docs/recording/`의 스크립트로 언어별로 다시 찍는다 (`README.md` 참고). 시스템 언어가 새지 않게 `PROJECTOPS_LANG`/`--language`를 명시하고, npm 배포본이 아니라 작업 트리 CLI·템플릿으로 찍는다.
- 마법사 배포 환경값 문구(`.github/config/wizard-prompts.yml`)는 `label`=영어, `label_ko`=한국어다. 새 키는 두 언어를 함께 넣는다.

### 영문 표면의 한글 줄은 줄기만 한다 (#769)

- `scripts/tests/test_korean_line_budget.py`가 skills·src·워크플로·스크립트·마법사·README 등에서 **주석·docstring을 뺀 한글 줄 수**를 파일별로 세어 동결 장부 `scripts/tests/korean_line_budget.json`과 대조한다. 장부에 없는 파일은 0이어야 하고, 있는 파일은 장부 숫자를 넘으면 실패한다.
- 한글을 걷어 내 숫자가 줄면 테스트가 "장부를 낮춰라"로 실패한다 → `python3 scripts/tests/test_korean_line_budget.py --update` (줄어든 숫자만 반영, 절대 올리지 않음).
- 사용자에게 보이는 문구는 영어로 쓰고 한국어는 i18n ko 사전에 넣는다. 세는 파일에 한글을 새로 넣으려면 **코드가 대조하는 데이터**(한글 라벨 `작업전` 같은 것)처럼 강한 이유가 있어야 하고, 그때만 장부 숫자를 손으로 올리고 리뷰에서 이유를 밝힌다.
- 제외 범위(ko 사전·`docs/`·테스트·pro-launch troubleshooting 등)와 사유는 테스트 파일의 `EXCLUDED_PATTERNS`가 정본이다.

### 실행 기록 3계층 (#493·#494·#561 — agent 필독)

마법사(full/workflows)가 끝나면 **대상 레포**의 `.github/.projectops/logs/`에 실행 기록을 남긴다.
`docs/` 아래였던 위치를 #561에서 옮겼다 — 사람이 읽는 문서가 아니라 **Agent가 원인을 짚는 진단 자료**라
저장소 이력에 남을 이유가 없다.

| 계층 | 파일 | 내용 | 소스 모듈 |
|------|------|------|----------|
| 1 | `PROJECTOPS-MIGRATION-GUIDE.md` | 고정 헤더(AI 해석 가이드라인) + 실행 엔트리 append-only: 동적 체크리스트·통과한 breaking 전문·yaml 메타(`schema` 버저닝) | `src/core/migration-guide.js` |
| 2 | `{stamp}_v{from}_to_v{to}.jsonl` | 구조화 이벤트 (파일명 grep으로 인과 추적) | `src/core/run-trace.js` |
| 3 | `{stamp}_..._.log` | **서버 로그 형식** — 내부 이벤트 + 터미널 출력이 시간순 병합 | 〃 |

**건너뛴 워크플로의 새 템플릿은 `incoming/`에 남긴다 (#654).** 사용자가 수정한 워크플로는 덮어쓰지 않고
`skipped-conflict`로 유지하는데, 무엇이 다른지 알 방법이 없었다. 그래서 새 템플릿(env·브랜치 치환 적용본)을
`.github/.projectops/incoming/<파일명>`에 저장하고, 종료 화면·`skipped-conflict` 이벤트 detail(`incoming`,
`added`, `removed`)·MIGRATION-GUIDE 체크리스트에 비교 명령(`diff -u`, `git diff --no-index`)을 남긴다.

- **`logs/`와 같은 패턴**: 폴더가 자체 `.gitignore`(`*` + `!.gitignore`)를 들고 다니므로 루트 `.gitignore`는 건드리지 않는다.
- **`.github/workflows/`에는 절대 쓰지 않는다** — 거기 생긴 파일은 GitHub이 실제 워크플로로 실행한다.
- **실패해도 마법사를 죽이지 않는다** — 저장·diff 실패는 `incoming-failed` 이벤트와 경고 한 줄로 흡수한다. 종료 코드는 그대로다.
- 코드: `src/core/incoming.js`, 호출은 `copy/workflows.js`의 `applyDecision`.

**추적 제외는 폴더가 스스로 들고 다닌다.** `logs/.gitignore`(`*` + `!.gitignore`)를 매 실행마다 보장하므로
루트 `.gitignore`를 건드리지 않는다. 형제인 `.github/.projectops/baseline.json`(#557)은 팀원 공유
자산이라 **계속 추적된다** — 폴더를 나눈 이유가 이것이다.

**로그 레벨** (`levelOf`): `ERROR`(실패) / `WARN`(두면 실패하거나 판단 필요) / `INFO`(단계 경계·확정된 판단) /
`DEBUG`(건별 상세). **DEBUG도 파일에는 전부 남긴다** — 문제가 터진 뒤에 "그때 켰더라면"은 소용없다.

- 엔진(copy/env/legacy/orphan)은 `hooks.trace` / `ctx.trace`로 **null-safe emit** — trace 미주입 경로(기존 테스트)는 무영향.
- **단계는 `trace.step(name, fn)` / `stepAsync`로 감싼다** — 진입·종료·소요 ms·실패가 자동 기록된다.
  개별 호출부에 start/done을 흩뿌리면 반드시 빠뜨리는 자리가 생긴다.
- 가이드의 워크플로우 목록·env 값은 trace events에서 **파생**한다 (단일 소스). 새 엔진 동작을 추가하면 이벤트 emit도 함께 추가할 것.
- **호출은 `trace.event(phase, action, target, detail)`이다.** `emit`은 존재하지 않는다 —
  optional chaining(`?.`) 때문에 오타가 예외 없이 조용히 무시되어 기록이 통째로 사라진 적이 있다(#561).
- 민감값(PAT·token·secret·password·credential 키)은 `scrubDetail`이 이벤트에서 자동 제거 — **우회 금지**.
  값이 비밀이 아닌데 키 이름이 걸리면(`token` → `placeholder`처럼) **키 이름을 바꾼다**.
- **어떤 경로로 끝나도 기록이 남아야 한다**: 정상 완주·중간 취소·예외는 `finally`의 `trace.finalize()`(멱등),
  강제 종료(Ctrl+C)는 `trace.armSignals()`가 처리한다. 새 종료 경로를 만들면 이 계약을 확인할 것.
- **완료 화면 출력은 `try` 안에, `finalize()`는 `finally`에만 둔다 (#561).** `finally`는 try를 빠져나온
  직후 돌기 때문에, 완료 화면을 try 밖에 두면 기록이 먼저 닫혀 **그 화면이 `.log`에서 통째로 빠진다.**
  실제로 사용자 실행 로그가 `step/done install-full`에서 끊겨 "로그에 아무 안내가 없다"는 신고로 돌아왔다.
  `finalize()`는 멱등이라 뒤늦게 다시 불러도 복구되지 않는다 — 순서가 곧 계약이다.

### Breaking Changes
호환성 문제 변경 시 `.github/config/breaking-changes.json`에 등록:
```json
{
  "버전": {
    "severity": "critical | warning",
    "title": "English title",
    "message": "English details and action steps",
    "title_ko": "제목 (선택)",
    "message_ko": "상세 설명 및 조치 방법 (선택)"
  }
}
```

> **`title`/`message`는 영어가 정본이고 필수다 (#988).** 구버전 CLI는 `main`의 이 파일을 받아 이 두 키만 읽으므로
> 키 이름·형식을 바꾸지 않는다. 한국어는 선택 키 `title_ko`/`message_ko`에 넣고, CLI 화면 언어(`--lang`·`resolveLang`)가
> `ko`일 때만 보인다. 없으면 영어로 폴백한다 (`src/core/breaking.js` `localizeBreakingEntry`).
> 마이그레이션 가이드(실행 기록)에는 영어 원문이 남는다.
> (모든 항목에 영어 `title`/`message`), 한글 줄 감시는 `*_ko` 키 줄만 세지 않는다.
