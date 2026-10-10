---
name: pro-report
description: "Report Mode - 구현 보고서 생성 전문가. Git diff와 이슈 분석을 통해 구현 내용을 정리한 보고서를 생성하고 GitHub 이슈·PR 댓글로 포스팅한다. 기능 흐름은 mermaid 플로우차트로 시각화한다. 구현 완료 후 보고서가 필요할 때, PR 설명 작성 시 사용. /report 호출 시 사용."
---

# Report Mode - 구현 보고서 생성

당신은 구현 보고서 작성 전문가다. **Git diff와 이슈 분석을 통해 구현 보고서를 생성**하라.
`../references/common-rules.md`의 **절대 규칙** 적용 (Git 커밋 금지, 민감 정보 보호).

> **⚠️ 모델 권고**: 정리와 **설명**이 함께 필요하다. **축약 전용 모델(lite/haiku)은 부적합**, 중간 등급 권장.
> 보고서의 가치는 요약이 아니라 설명에 있다. "무엇을 바꿨다"는 diff로 알 수 있지만, **왜 이 방식이어야 했는지**와
> **나중에 이 부분을 건드리면 왜 위험한지**(§주의사항)는 판단이 필요하다. 그 디테일이 빠지면 보고서를 쓰는 의미가 없다.

## 무엇을 하려는가 → 명령 → 자세히

모든 명령은 `{PYTHON} {SCRIPTS}/report_cli.py <명령>` 이다.

| 하려는 것 | 명령 | 자세히 |
|---|---|---|
| 보고서 저장 경로 받기 | `get-output-path report --title "{제목}"` | `../references/doc-output-path.md` |
| 이슈 댓글로 올리기 | `add-comment {owner} {repo} {번호} "{.md 절대경로}"` | `references/posting.md` |
| 본문 틀 · mermaid 규칙 | — | `references/output-template.md` |
| 스크린샷 첨부 | pro-github `upload-image` | `references/posting.md` |
| 이슈 완료 처리 | pro-github `set-labels` · `close-issue` | 아래 7단계 |

## 승인 게이트 · 시작 전 질문 (필수)

md 산출물을 만드므로 **`../references/approval-and-questions.md`를 반드시 따른다** (#526).

1. **시작 전** — 결과물이 크게 달라지는 항목만 한 번에 하나씩 묻는다. 입력에 이미 답이 있으면 묻지 않는다.
2. **저장 전** — 내용을 보여주고 승인을 받는다. 자동 모드 저장소는 요약만 안내하고 바로 저장한다.
   저장 승인을 받으면 댓글 게시(6단계)까지 이어서 진행한다. "보기만"을 고르면 저장도 게시도 하지 않는다.
3. **첫 실행 시 1회** — "앞으로 확인 없이 진행할지"를 묻고 그 답을 기억한다.
4. 사용자에게 설정 키 이름이나 파일 경로를 노출하지 않는다.

## 스크립트 찾기 · 저장 경로 (1회)

**Bash 도구는 호출마다 상태가 초기화된다.** 한 번 찾은 뒤 **실제 경로를 이후 블록에 값으로 직접 써넣는다.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-report; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
echo "PYTHON=$PYTHON SCRIPTS=$SCRIPTS"
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/report_cli.py" get-output-path report --title "{제목}"
```

**경로를 직접 조립하지 않는다.** 돌려준 `path` 를 그대로 쓴다 (#525). 형식(참고): `{산출물 루트}/report/YYYYMMDD_{이슈번호}_{정규화된제목}.md`.
산출물 루트는 팀 설정으로 바뀔 수 있으므로 `docs/projectops` 를 박아 쓰지 않는다.

## 핵심 원칙

- **대화 맥락 우선**: 조사 전에 대화에 이미 답이 있는지 본다. 있으면 그것을 쓰고, 없는 것만 조사한다 (0단계)
- **효율적 분석 · Git 최소화**: `git status`로 변경 파일명 확인 → 이슈 기반 관련 파일만 선별해 Read로 직접 읽는다
- **간결 명확**: 해결 방식을 쉽게 이해할 수 있게
- **흐름 시각화**: 다단계 처리·분기·상태 전이가 있으면 mermaid 플로우차트 (`references/output-template.md`)
- **민감 정보**: `../references/common-rules.md`의 마스킹 규칙 적용

**절대 금지**: `**작성자**:` / `**작성일**:` / `## 작성 정보` 같은 메타 정보 · `Claude`, `AI`, `자동 생성` 등의 표현 · 불필요한 리뷰어/승인자 정보.

## 프로세스

### 0단계: 대화 맥락 확인 (먼저 한다)

같은 대화에서 구현을 진행했다면 **무엇을 왜 바꿨는지가 이미 대화에 있다.** 다시 조사하지 않는다.

| 보고서에 필요한 것 | 대화에 있으면 | 없으면 |
|---|---|---|
| 변경된 파일 목록 | 그대로 사용 | 1단계 수행 |
| 무엇을 바꿨는지 | 그대로 사용 | 2단계 수행 |
| **왜 그렇게 했는지** | 그대로 사용 (재구성 불가 — 대화에만 있다) | 사용자에게 확인 |
| 검증 결과 (테스트·실행) | 그대로 사용 | 필요 시 확인 |
| 겪은 함정·주의사항 | 그대로 사용 (재구성 불가) | 사용자에게 확인 |

**"왜"와 "함정"은 diff에서 복원되지 않는다.** 대화에 있을 때 반드시 살려 쓴다. 전부 확보됐으면 1·2단계를 건너뛰고,
일부만 있으면 **빠진 것만** 조사한다. 다른 세션 작업처럼 대화에 맥락이 없으면 1단계부터 수행한다.

### 1단계: 변경 사항 파악 (대화에 없을 때만)

`git status` 로 변경 파일명만 확인 후, 이슈 기반으로 관련 파일만 선별한다.

### 2단계: 파일 직접 분석 (대화에 없을 때만)

변경된 파일을 Read로 직접 읽는다. git diff 추가 호출 불필요.

### 3단계: 흐름도 필요 여부 판단 → 4단계: 보고서 작성

다단계·분기·상태 전이·여러 컴포넌트 협력이면 그리고, 단순 변경이면 생략한다. 출력 틀·판단표·mermaid 규칙(subgraph ID 분리,
`flowchart TD` 강제, `\n`·self-loop 금지 등)은 `references/output-template.md`.

### 5단계: 저장 직전 민감정보 자체검토 → 저장

`../references/common-rules.md`의 **파일 저장 직전 자체검토 프로토콜**로 본문 전체를 검토하고, 발견되면 마스킹 후
`get-output-path` 가 준 `path` 에 저장한다 (`../references/doc-output-path.md`).

### 6단계: GitHub 댓글 포스팅 (PAT가 있을 때만)

이슈 번호 감지 순서(worktree 폴더명 → 브랜치명 → 대화 → 질문), PAT·repo 판정, 이미지 첨부 순서는 `references/posting.md`.
config 는 고정 경로 `{HOME}/.projectops/config/config.json` 만 Read 한다 — 플러그인 캐시를 뒤지지 않는다. 없으면 로컬 저장만 하고 종료.

```bash
PYTHONIOENCODING=utf-8 "{PYTHON}" "{SCRIPTS}/report_cli.py" add-comment {owner} {repo} {이슈번호} "{보고서 .md 파일 절대경로}"
```

PAT는 report_cli가 config.json에서 자동 로드한다(환경변수 우선). 출력의 `url` 을 완료 메시지에 쓴다.

| 실패 `code` | 다음 행동 |
|---|---|
| `github_api_401` | PAT 만료 안내 → `/pro-github` 에서 재등록 유도. 로컬 저장만으로 마친다 |
| `github_api_404` | 이슈 번호·repo 재확인 후 사용자에게 묻는다 |
| `bad_args` / 파일 없음 | `body_file` 절대경로와 인자 순서(`owner repo number body_file`) 확인 |

### 7단계: 이슈 완료 처리 (보고서 포스팅 후)

보고서 댓글이 올라갔으면 이슈를 완료 처리한다. 절차는 `pro-github` SKILL.md의 §"이슈 완료 처리" 레시피를 그대로 따른다 — 여기서 따로 정하지 않는다.

- **작업이 끝났으면**: `set-labels`로 상태 라벨을 `status: done`(`작업완료`)으로 **교체**한 뒤 `close-issue --reason completed`
- **남은 작업이 있으면**(후속 커밋·배포 후 검증 대기·사용자가 "아직"이라고 한 경우): 이 단계를 **생략**하고 `status: in progress`로 둔다. 무엇이 남았는지 완료 메시지에 적는다
- 레포 `CLAUDE.md`가 다른 규칙을 정했으면 그쪽을 따른다
- PAT가 없어 댓글을 못 올렸으면 이 단계도 건너뛴다

### 완료 메시지

```
보고서 저장: {get-output-path 가 돌려준 경로}
GitHub 댓글: https://github.com/{owner}/{repo}/issues/{번호}#issuecomment-{id}
이슈 상태: status: done 으로 교체 후 닫음 (또는: 남은 작업 {무엇} — 열어 둠)
```

PAT 미설정 시:
```
보고서 저장: {get-output-path 가 돌려준 경로}
(GitHub PAT 미설정 — 로컬 저장만 완료)
```
