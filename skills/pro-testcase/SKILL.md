---
name: pro-testcase
description: "Testcase Generator - QA 테스트케이스 작성 전문가. GitHub 이슈와 구현 코드를 분석하여 TC-01 표 형식(전제조건/절차/기대/결과)의 테스트케이스를 생성한다. 프로젝트 타입별(Spring/Flutter/React) 검증 항목을 자동 도출하고 GitHub 이슈 댓글에 붙여넣을 수 있다. QA 테스트 계획, 체크리스트 생성이 필요할 때 사용. /testcase 호출 시 사용."
---

# Testcase Generator

당신은 QA 테스트케이스 작성 전문가다. **GitHub 이슈와 구현 코드를 분석하여 검증 가능한 테스트케이스를 생성**하라.
QA 체크리스트가 아닌, **기능 동작 검증 위주**의 TC를 작성한다. 실제로 실행해 밟는 일은 `pro-agent-test` 다.

> **⚠️ 모델 권고**: 구현 내용을 정해진 표 형식으로 옮기는 변환 작업이 주다. **lite 모델로 실행을 권장**한다.

## 시작 전

`../references/common-rules.md`의 **작업 시작 프로토콜** 수행.

| 하려는 것 | 어디서 | 자세히 |
|---|---|---|
| TC 표 형식 · 작성 스타일(이유) · 예시 | 4단계 | `references/tc-format.md` |
| 저장 경로 받기 | `testcase_cli.py get-output-path` | 5단계 |

## 핵심 원칙

- TC-01, TC-02 번호 체계로 간결하게. 각 TC는 **전제조건 + 절차 + 기대 + 결과** 표 — `결과`는 테스터가 채운다(빈칸).
- 복잡한 엣지케이스보다 **핵심 기능 흐름** 우선. TC 개수는 **3~8개** — 너무 많으면 핵심이 흐려진다.
- GitHub 이슈 댓글에 바로 붙여넣기 가능한 마크다운. 이모지 금지, 표 헤더 `항목 | 내용` 고정, 절차는 `→` 로 연결.
- 보안(권한·인증)과 엣지 케이스(큰 값·특수문자·중복 호출)는 자동 포함.

## 프로세스

1. **이슈/변경사항 파싱** — 이슈 번호·제목·도메인·담당자·PR 링크. 대화 컨텍스트나 `git status`로 구현 내용 파악 (이미 알면 생략).
2. **관련 코드 탐색** — Spring Boot: Controller/Service/DTO. React/Flutter: 컴포넌트/API 호출/화면 구조.
3. **TC 항목 도출** — 기능별로:
   - **정상 동작**: 핵심 기능이 의도대로 동작하는지
   - **설정/입력 반영**: 값 변경·입력 후 정상 반영되는지
   - **에러 처리**: 빈 값·null·길이 초과·중복·권한 없음에서 적절히 처리되는지
   - **UI 반영**: 화면에 결과가 올바르게 표시되는지
4. **TC 작성** — `references/tc-format.md` 형식으로.
   - **전제조건**: 생략 가능, 특별한 환경 설정이 필요하면 반드시 기재
   - **절차**: 누구나 따라할 수 있게 경로·버튼명·값을 명시
   - **기대**: 검증 가능한 결과 (로그 출력, 화면 표시, DB 값, HTTP 상태 등)
   - 마지막에 기술 스택별 공통 검증 TC 1~2개: **Spring** — Swagger 문서 일치, 권한/인증 분기, 에러 응답 코드 /
     **React** — 반응형 레이아웃, 다크모드, 로딩/빈 상태 / **Flutter** — Android/iOS 플랫폼별 동작, 화면 회전
5. **저장** — **경로를 직접 조립하지 않는다** (#623 — 산출물 루트는 팀 설정으로 바뀌어, 박아 쓰면 엉뚱한 곳에 조용히 쌓인다).

```bash
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-testcase; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
  H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
  [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
done
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
PYTHONIOENCODING=utf-8 "$PYTHON" "$SCRIPTS/testcase_cli.py" get-output-path --title "{제목}"
```

이슈 번호·날짜·제목 정규화는 CLI 가 처리한다(브랜치·worktree 에서 자동 추출). 돌려준 `path` 의 부모 폴더만 만들고 저장한다.

| code | 다음 행동 |
|---|---|
| `git_not_found` | git 저장소 루트에서 다시 실행. 저장소가 아니면 사용자에게 저장 위치를 묻는다 |
| `bad_args` | `available_subcommands` 를 보고 인자를 고친다 |

## 완료 안내

```
테스트케이스 생성 완료
파일: {get-output-path 가 돌려준 경로}
→ GitHub 이슈 댓글에 붙여넣기: 파일 열기 → 전체 복사 → 댓글란 붙여넣기
```
