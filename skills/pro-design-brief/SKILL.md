---
name: pro-design-brief
description: "시안보다 먼저 만든 화면을 디자이너에게 넘길 요청서를 만든다. 실제 화면을 상태별로 찍고(빈 목록·실패·긴 글자·글자 크기·작은 폰), 배치 대안 3~5안을 실제 컴포넌트로 렌더하고, 문구 후보·UI 요소 후보·꼭 지킬 것(브랜드 규격·레포 디자인 원칙·합의된 예외)을 모아 보드(HTML → 주제별 PNG)로 조립한 뒤 디자인 이슈·HTML 한 장·md 폴더 중 레포에 맞는 한 형식으로 넘긴다. Figma 링크가 있으면 시안에 그려진 상태와 빠진 상태를 가려 빈틈을 요청한다. 정답이 아니라 생각할 재료를 준다. '디자인 요청해줘', '시안 요청 올려줘', '디자이너한테 보낼 거 만들어줘', '이거 디자인 안 나왔는데 먼저 만들었어', '빈 화면이랑 에러 화면도 그려 달라고 해줘', '디자인 이슈 만들어줘' 같은 요청에 사용한다. 시안을 코드로 옮기고 대조하는 것은 pro-figma, 버그를 찾는 것은 pro-agent-test 다."
---

# 디자인 요청서 — 시안보다 먼저 만든 화면

화면이 먼저 만들어지고 시안은 나중에 온다. **디자이너는 보통 기본 화면만 그린다** — 비었을 때·실패했을 때·
글자가 길 때가 빠진다. 이 스킬은 그 빈자리를 먼저 채운 요청서를 만든다.

> **정답을 주지 않는다. 생각할 재료를 준다.** 대안·문구·요소를 넓게 펼치고, 개발 쪽 선호는 근거와 함께 한 줄.
> **반드시 디자이너가 받아 보는 결과물로 끝난다** — 이미지가 든 이슈 / HTML 한 장 / md 폴더. 채팅 요약으로 끝내지 않는다.

| 쓴다 | 쓰지 않는다 |
|---|---|
| 시안 없이 먼저 구현했다 → 시안 요청 | 시안이 있고 코드로 옮기는 중 → `pro-figma` |
| 시안이 기본 화면만 있다 → 빠진 상태 요청 | 버그 찾기 → `pro-agent-test` |
| 디자이너가 방향을 못 잡는다 → 재료 제공 | 디자인 시스템을 새로 짠다 |

`../references/common-rules.md` 의 **절대 규칙** 적용. 설정은 `../references/config-rules.md` §2~4, 승인 게이트는
`../references/approval-and-questions.md`. **대화에 이미 있는 것은 다시 조사하지 않는다** — 특히 "왜 이 자리를 골랐나"는
대화에만 있으니 반드시 살린다. 인자: $ARGUMENTS

## 무엇을 하려는가 → 명령 → 자세한 문서

| 하려는 것 | 명령 | 자세히 |
|---|---|---|
| 출력 방식 · 디자이너 · 게시 전 확인 판정/저장 | `design_brief_cli.py config show\|set` | 아래 0단계 |
| Figma · 이미지 입력 읽기, 빈틈 표 | `mcp__figma__get_figma_data` · `figma_cli.py coverage` | `references/states-and-capture.md` |
| 상태 목록(5축) | — (코드를 읽는다) | `references/states-and-capture.md` · `../references/design-states.md` |
| 캡처 자리 · 실기기/브라우저/렌더 캡처 | `launch_cli.py get-output-path --skill design-brief` · `app shot` · `web route` · `render run` | `references/states-and-capture.md` |
| 렌더할 수 없는 상태 · 아직 없는 안 | `design_brief_cli.py ascii --spec` | `references/states-and-capture.md` |
| 대안 · 문구 · UI 요소 · 꼭 지킬 것 | `design_brief_cli.py copy-lint` | `references/content.md` |
| 보드 조립(HTML → 주제별 PNG · md) | `design_brief_cli.py get-output-path` → `board` | `references/publishing.md` |
| 게시(이슈 · HTML · md) | `github_cli.py upload-image` → `create-issue` | `references/publishing.md` |

## 스크립트 찾기 — 한 번만

**Bash 도구는 호출마다 상태가 초기화된다.** 한 번 찾고 **실제 경로를 이후 블록에 값으로 써넣는다.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
for SKILL in pro-design-brief pro-launch pro-github pro-figma; do
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  [ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
    H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
    [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
  done
  [ -d "$ROOT/skills/$SKILL/scripts" ] || { echo "$SKILL 스크립트를 찾지 못했습니다"; exit 1; }
  echo "$SKILL=$ROOT/skills/$SKILL/scripts"
done
```

자리표시: `{SCRIPTS}` = pro-design-brief(config · get-output-path · board · copy-lint · ascii), `{LAUNCH}` = pro-launch(캡처 · 렌더 · 상태 연출),
`{GITHUB}` = pro-github(이미지 · 이슈), `{FIGMA}` = pro-figma(Figma 덤프 세기 — 링크가 있을 때).

## 공통 규칙

- 흐름: `0 설정 → 1 입력 → 2 상태 목록 → 3 캡처 → 4 대안·문구·UI·꼭 지킬 것 → 5 보드 → 6 게시`.
- **"지금 앱은 이렇다"의 근거는 실기기·운영 API 다.** 렌더는 상태를 연출하는 수단이다(렌더만 보고 쓴 주장이 실기기와 7건 달랐다).
  캡처마다 `source`, 사실 문장은 `facts[]` 에 `basis` 와 함께. 수치는 픽스처가 아니라 운영 값.
- 상태는 **네가 코드를 읽고** 적는다. 상태마다 `status`(done · temp · none) 와 `reachable`(yes · old_data · unknown) —
  입력 경로가 지금도 있는지 코드로 본다. 서버가 내려주는 문구(공지 · 약관 · 오류)도 상태다.
- 기기 화면 이동은 **요소로 누른다**(`app tap --text|--id|--desc`, 모르면 `app tree`). 좌표 눈대중 · 호스트 마우스 금지.
- 대안은 **축이 다른 3~5안**, "현재 구현"·"최소" 안을 항상 포함. 법적 문구는 후보를 내지 않는다(`legal: true`).
- 캡처를 위해 AI 생성 API 를 부르지 않는다. `residue` 는 네가 만든 것만 지운다. 디자이너 대신 결정하지 않는다.
- **사용자에게 설정 키 이름·파일 경로를 보이지 않는다.**

## 0. 설정 판정 — 처음 한 번, 이후 자동

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py config show --root {PROJECT_ROOT}
```

`resolved` 에 세 가지가 나온다. `missing` 에 있는 것만 **한 번에 하나씩**, 권장안을 1번에 두고 묻는다.

| 정할 것 | 자동 판정 (`suggest`) | 물을 때 |
|---|---|---|
| 출력 방식 | GitHub 레포면 `issue`, 아니면 `html` | "디자인 요청서를 어떻게 받으세요? 1) 디자인 이슈 (권장) 2) HTML 한 장 3) md 폴더" |
| 디자이너 | 이슈 템플릿의 `디자인:` 줄(`designer_candidates`). 비면 최근 디자인 이슈 담당자를 `{GITHUB}` 로 | "디자이너 GitHub 아이디(또는 이름)가 뭔가요?" |
| 게시 전 확인 | 기본은 확인받는다 | 첫 게시 때 승인 게이트 C 분기 |

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py config set --root {PROJECT_ROOT} --destination issue --designer {아이디}
#   --scope default      : 모든 레포 기본값으로 ("앞으로 전부")    --auto-approve true : "다음부턴 확인 없이 올려줘"
```

"다음부턴 HTML 로 해줘"도 같은 명령이다. GitHub 을 안 쓰는 레포는 경로로 맞춘다(`github` 설정과 따로 두는 이유).

## 1~4. 입력 · 상태 · 캡처 · 재료

구현 여부(구현됨 / 일부 / 아직 없음)를 정하고, Figma 가 있으면 그려진 상태 vs 빠진 상태 빈틈 표를 만든다.
5축(데이터 · 입력 · 환경 · 사람 · 표시)에서 **그 화면에 해당하는 상태만** 뽑는다. 순서는 `references/states-and-capture.md`.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py get-output-path --skill design-brief --title "{화면 이름}"
source "{env_file 값}"          # $SHOT_DIR · $RUN_DIR · $DEV
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV" --out 01_현재 --clean-status
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py ascii --spec '{"title":"…","rows":["…","---"],"width":24}'
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py copy-lint --file {보드 데이터.json} --banned "아이,기기,서버"
```

캡처 순서는 **코드 렌더 → 실기기·브라우저 → ASCII**. 대안 · 문구(`현재 → 후보 2~3 → 이유`) · UI 요소(레포에 있는 것 먼저) ·
꼭 지킬 것(브랜드 규격 · 디자인 원칙 · 코드 주석의 합의된 예외 — 부딪히면 질문으로)은 `references/content.md`.

## 5. 보드 — HTML 한 장 → 주제별 PNG

모은 것을 **데이터 JSON** 하나로 적고 조립한다(그림 경로는 데이터 파일 기준 상대경로).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py get-output-path --title "{화면 이름}"   # 캡처와 같은 제목
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py board --data {run_dir}/board_data.json --out {run_dir}/board --png
#   --md : brief.md 도 만든다    --strict : preflight 가 남으면 ok:false 로 멈춘다 (게시 직전)
```

```json
{
  "title": "{화면} — 디자인 요청서",
  "summary": {"what": "", "why": "", "status": "", "recommend": "A안 — 근거 한 줄", "note": "",
              "must_keep": [{"rule": "", "source": "파일·이슈·문서"}]},
  "facts": [{"claim": "주간 지급량은 50개다", "basis": "device|server|code|design", "ref": "GET /api/credit · 캡처 파일"}],
  "current": [{"label": "로그인 (iOS)", "image": "screenshots/login_ios.png", "source": "device"},
              {"label": "버전 4배", "image": "screenshots/zoom.png", "zoom": true, "source": "device"}],
  "states": [{"axis": "데이터", "name": "0건", "status": "done|temp|none", "reachable": "yes|old_data|unknown",
              "image": "", "source": "render|device|server", "ascii": "",
              "copy": "", "copy_needed": false, "design": true, "render_failed": false}],
  "alternatives": [{"id": "A", "name": "", "image": "", "source": "render", "zoom": "", "ascii": "",
                    "recommended": true, "pros": [], "cons": [], "dev_impact": ""}],
  "copy": [{"where": "", "current": "", "candidates": [], "reason": "", "legal": false, "needed": false}],
  "ui": [{"shape": "목록", "candidates": [], "existing": [], "new": []}],
  "impact": [{"choice": "B안", "work": "따로 필요한 개발"}]
}
```

**PNG 를 Read 로 열어 본다.** **`preflight` 가 비어야 게시한다.** 조립 규칙은 `references/publishing.md`.

## 6. 게시 — 디자이너에게는 한 형식만

게시 직전 승인 게이트(`approval-and-questions.md` §4 A/B/C) — 제목·담당자·첨부 장수를 보이고 승인받는다.
`html` 은 `board/board.html`, `markdown` 은 `board/brief.md` + PNG 폴더 경로를 알려준다. **둘 다 주지 않는다.**
`issue` 면 **그림 먼저**(본문을 먼저 올리면 그림 없는 글이 게시된다):

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {GITHUB}/github_cli.py upload-image {owner} {repo} {run_dir}/board/*.png --prefix brief
PYTHONIOENCODING=utf-8 {PYTHON} {GITHUB}/github_cli.py create-issue {owner} {repo} "{제목}" "{본문 .md 경로}" "{라벨}" --assignees "{디자이너}"
PYTHONIOENCODING=utf-8 {PYTHON} {GITHUB}/github_cli.py add-comment {owner} {repo} {구현 이슈} "{링크 댓글 .md}"   # 구현 이슈와 서로 링크
```

본문은 레포 디자인 요청 템플릿(🖌️ 요청 내용 · 🎯 기대 결과 · 📋 참고 자료 · 💡 추가 요청 사항 · 🙋 담당자)에 보드와 같은
이름·순서로 맞춘다. 게시 뒤 틀린 것은 본문 수정 + **정정 댓글**(처음 → 실제 → 근거). `references/publishing.md`.

## 실패 경로 → 다음 행동

| code · 상황 | 동작 |
|---|---|
| `browser_missing` · `png_failed` | PNG 대신 HTML 또는 원본 캡처 + md 표로 낸다. 요약에 사유. 브라우저가 필요하면 묻고 `launch_cli.py web setup` |
| `preflight_failed` | 출처 없는 캡처 · `reachable` 없는 상태 · 렌더만 근거인 사실을 고치거나 뺀다 |
| `candidate_issues` (copy-lint) | 걸린 후보를 네가 고친다 |
| `bad_data` · `bad_file` · `bad_spec` | JSON 형식을 고친다(ascii 는 `title` · `rows` · `width` · `caption` 만) |
| `bad_destination` · `nothing_to_set` | `--destination issue\|html\|markdown`, 바꿀 값을 하나 이상 준다 |
| 렌더 실패 | 그 상태만 ASCII 로 대체하고 `render_failed: true` |
| 업로드 실패 · `private_warning` | 로컬 산출물 경로를 알린다. private 이면 `html` 로 바꿀지 묻는다 |
| Figma 읽기 실패 · 디자이너 모름 | 없이 진행하고 요약에 적는다(담당자 없이 등록 → 다음에 묻는다) |
| 대상 레포에 흔적(`residue`) | 그대로 보고하고 지우지 않는다(네가 만든 것만 지운다) |
| 실기기로 확인할 수 없다(기기·계정·비용) | 그 사실은 `facts` 에서 빼거나 근거 없음으로 두고 "확인 못 함"으로 적는다. 렌더로 대신 단정하지 않는다 |
