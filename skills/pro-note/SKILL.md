---
name: pro-note
description: "알아낸 것을 실행 가능한 기록으로 남기고, 막혔을 때 꺼내 쓴다. 빌드·배포 실패, 에러 발생, '뭔가 안 된다', 원인을 모르겠다 같은 상황이면 조사 전에 과거 기록을 먼저 검색한다. 어렵게 해결했거나 삽질 끝에 알아낸 것이 있으면 기록을 제안한다. 라이브러리 사용법, 프로젝트 관례, 도구 제약, 환경 설정처럼 다시 알아내는 데 시간이 드는 것도 대상이다. '/pro-note' 호출 시에도 사용."
---

# Note Mode

알아낸 것을 **AI 없이도 따라 할 수 있는 기록**으로 남기고, 막혔을 때 그것을 꺼내 쓴다.
기록의 독자는 **6개월 뒤 이 대화를 못 본 누군가**다 — 그 사람이 문서만 보고 같은 문제를 끝까지 해결할 수 있어야 한다.

## 무엇을 하려는가 → 명령 → 자세히

모든 명령은 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/note_cli.py <명령>` 이다.

| 하려는 것 | 명령 | 자세히 |
|---|---|---|
| 막혔을 때 과거 기록 찾기 (저장소 + 홈 양쪽) | `search "{키워드}" [--limit N]` | 아래 시점 1 |
| 저장 위치 판정 (project / home) | `resolve-scope [--scope project\|home]` | 아래 저장 위치 |
| 기록 파일 경로 받기 | `get-output-path {case\|fact} --title "{제목}" --scope {project\|home}` | 아래 기록 작성 |
| 기록 목록 | `list [--scope project\|home] [--limit N]` | — |
| 유형별 조사 체크리스트 | — | `references/investigation-checklists.md` |
| case/fact 템플릿 · 품질 자체검토 · 방법론 개선 제안 | — | `references/note-templates.md` |

## 스크립트 찾기 (한 번만)

Bash 도구는 호출마다 상태가 초기화된다. 한 번 찾은 뒤 **실제 경로를 이후 블록에 값으로 써넣는다.**

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-note; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS"
```

## 승인 게이트 · 시작 전 질문

`../references/approval-and-questions.md`를 따른다. 다만 **막혔을 때 검색은 묻지 않고 즉시 수행**한다 — 답을 기다리는 사용자에게 확인 질문은 방해다. 승인 규칙은 기록을 저장할 때만 적용된다.

## 언제 동작하나

### 시점 1. 막혔을 때 — 조사보다 검색이 먼저

"뭔가 안 된다", 빌드·배포 실패, 에러 로그 붙여넣기, 원인 불명이면 **조사를 시작하기 전에** 검색한다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/note_cli.py search "{증상 키워드}"
```

검색어는 사용자 표현이 아니라 **증상의 핵심 명사** 2~3개 조합이다 ("배포가 또 안 되네요" → `배포 실패 인증서`).

| 결과 | 행동 |
|---|---|
| 관련 기록 발견 | 그 문서를 읽고 **해결법이 지금 상황에 적용되는지 먼저 검증**한다. 맞으면 조사 없이 끝난다. 알리는 형식은 `references/note-templates.md` |
| 결과 없음 | 처음 겪는 문제다. 아래 조사 절차로 진행한다 |

> `github_cli actions show-run·joblog`와 `changelog_cli actions`가 실패를 보여 줄 때 맞는 기록이 있으면 응답에 `note_hits`(제목·경로·요약, 최대 2건)가 **저절로** 실린다. 있으면 `search` 전에 그 문서부터 읽고, 필드가 없으면 맞는 기록이 없는 것이다.

### 시점 2. 어렵게 알아냈을 때 — 기록을 제안

**고생한 흔적이 있을 때만** 제안한다. 한 번에 끝난 일은 남길 가치가 없고, 매번 물으면 방해다.

| 제안한다 | 제안하지 않는다 |
|---|---|
| 시도를 여러 번 반복했다 | 한 번에 끝났다 |
| 원인이 처음 예상과 달랐다 | 예상대로였다 |
| 조사가 여러 단계로 길어졌다 | 즉시 답이 보였다 |
| 검색해도 과거 기록이 없었다 | 기존 기록으로 해결했다 |
| 다시 만나면 또 헤맬 것 같다 | 사소하고 일회성이다 |

### 명시적 호출

`/pro-note`를 직접 부르면 검색 → 정리 → 기록 전체를 수행한다. 이미 해결한 것을 나중에 기록할 때는 **대화 맥락에서 조사 결과를 먼저 추출**하고 부족한 것만 보충한다 — 한 조사를 반복하지 않는다.

## 기록의 두 종류

| 종류 | 담는 것 | 파일명 | 갱신 |
|---|---|---|---|
| `case` | 무슨 일이 있었나 — 증상·조사·원인·조치·검증 | `YYYYMMDD_NNN_제목.md` | 사건마다 새로 |
| `fact` | 무엇을 알게 됐나 — 재사용 가능한 사실 | `주제.md` | 주제별 누적 갱신 (덮어쓰지 않고 해당 절만) |

**한 번의 사건이면 case, 앞으로 계속 참이면 fact.** ("7월 27일 배포가 인증서 만료로 실패" → case, "배포 인증서는 1년마다 갱신" → fact)

## 저장 위치 판정

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/note_cli.py resolve-scope
```

판정 기준은 **저장소 파일이 바뀌었는가**다.

| 신호 | 판정 | 예시 |
|---|---|---|
| 저장소 파일 변경됨 | `project` | 이 프로젝트 코드·설정 수정 |
| 변경 없이 외부만 조치 | `home` | 인증서 갱신, 계정 설정, 로컬 런타임 설치 |
| git 저장소 밖 | `home` | — |

출력 `ask_user`가 `true`면 근거를 제시하고 **한 번만** 묻는다(형식은 `references/note-templates.md`). `false`면 묻지 않고 진행한다.
검색은 항상 양쪽을 조회한다 — 프로젝트 문제인지 환경 문제인지 미리 알 수 없다.

## 조사 절차

과거 기록이 없을 때 수행한다. 유형별 확인 항목은 `references/investigation-checklists.md`.
**실행한 명령과 출력을 그대로 보존**한다 — 기록의 핵심 재료이고, 나중에 재구성하면 명령이 부정확해진다.

```
1. 증상 확정      — 무엇이 안 되는가, 언제부터인가, 최근 무엇이 바뀌었나
2. 범위 좁히기    — 어디까지 정상이고 어디부터 실패하는가
3. 가설 → 검증    — 근거 있는 가설을 세우고 명령으로 확인한다
4. 원인 확정      — 증거로 뒷받침되는가. 아니면 (추정) 표기
5. 조치           — 되돌릴 수 없으면 백업 먼저
6. 검증           — 실제로 해결됐는지 확인하는 명령까지
```

## 기록 작성

경로는 직접 조립하지 않고 CLI에 받는다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/note_cli.py get-output-path case --title "{제목}" --scope {project|home}
# 응답에 related(비슷한 기존 기록, 점수 포함 최대 3건)가 있으면 읽어 보고 같은 지식이면 새로 만들지 말고 그 기록을 갱신한다. 저장을 막지는 않는다.
```

출력 JSON의 `path`에 저장한다(`dir`이 없으면 먼저 만든다). 본문은 `references/note-templates.md`의 case/fact 템플릿을 따르고,
**저장 직전 같은 문서의 품질 자체검토 체크리스트를 통과**시킨다. 민감 정보는 `../references/common-rules.md` 마스킹 규칙대로 플레이스홀더로 바꾼다.

같은 원인이 **3회 이상 반복**되면 조사 절차 개선을 제안할 수 있다 — 한 번 겪은 것은 넣지 않고, **승인 없이 이 `SKILL.md`를 수정하지 않는다** (형식·이유는 `references/note-templates.md`).

## 목록 조회

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/note_cli.py list --scope project
```
