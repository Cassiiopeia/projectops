---
name: pro-design-brief
description: "시안보다 먼저 만든 화면을 디자이너에게 넘길 요청서를 만든다. 실제 화면을 상태별로 찍고(빈 목록·실패·긴 글자·글자 크기·작은 폰), 배치 대안 3~5안을 실제 컴포넌트로 렌더하고, 문구 후보·UI 요소 후보·꼭 지킬 것(브랜드 규격·레포 디자인 원칙·합의된 예외)을 모아 보드(HTML → 주제별 PNG)로 조립한 뒤 디자인 이슈·HTML 한 장·md 폴더 중 레포에 맞는 한 형식으로 넘긴다. Figma 링크가 있으면 시안에 그려진 상태와 빠진 상태를 가려 빈틈을 요청한다. 정답이 아니라 생각할 재료를 준다. '디자인 요청해줘', '시안 요청 올려줘', '디자이너한테 보낼 거 만들어줘', '이거 디자인 안 나왔는데 먼저 만들었어', '빈 화면이랑 에러 화면도 그려 달라고 해줘', '디자인 이슈 만들어줘' 같은 요청에 사용한다. 시안을 코드로 옮기고 대조하는 것은 pro-figma-verify, 버그를 찾는 것은 pro-agent-test 다."
---

# 디자인 요청서 — 시안보다 먼저 만든 화면

요즘 개발 흐름은 **화면이 먼저 만들어지고 시안은 나중에 온다.** 또는 디자이너가 "어떻게
그려야 할지 모르겠다"고 한다. 그때 넘기는 요청서를 이 스킬이 만든다.

**디자이너는 보통 기본 화면만 그린다.** 목록이 있을 때만 그리고, 비었을 때·실패했을 때·
글자가 길 때는 빠진다. 손으로 만든 요청서도 이 부분을 자주 놓친다. 이 스킬은 그 빈자리를
먼저 채운다.

> **정답을 주지 않는다. 생각할 재료를 준다.** 대안·문구·요소를 넓게 펼치고, 개발 쪽
> 선호는 근거와 함께 한 줄만 적는다. 보드 맨 위에 "전부 바꿔도 된다"가 박힌다.

> **반드시 디자이너가 받아 보는 결과물로 끝난다** — 이미지가 든 이슈 / HTML 한 장 / md 폴더.
> "분석 결과를 채팅으로 말하기"로 끝나지 않는다. 산출물 실적이 없던 디자인 스킬은 지워졌다.

| 쓴다 | 쓰지 않는다 |
|---|---|
| 시안 없이 먼저 구현했다 → 시안 요청 | 시안이 있고 코드로 옮기는 중 → `pro-figma-verify` |
| 시안이 기본 화면만 있다 → 빠진 상태 요청 | 버그 찾기 → `pro-agent-test` |
| 디자이너가 방향을 못 잡는다 → 재료 제공 | 디자인 시스템을 새로 짠다 |

## 시작 전

`../references/common-rules.md` 의 **절대 규칙** 적용. 설정은 `../references/config-rules.md` §2~4,
승인 게이트는 `../references/approval-and-questions.md` 를 따른다.

인자: $ARGUMENTS

**대화에 이미 있는 것은 다시 조사하지 않는다.** 구현 직후에 부르면 무엇을 왜 만들었는지가
대화에 거의 다 있다. 특히 **"왜 이 자리를 골랐나"는 대화에만 있다** — 반드시 살린다.

## 스크립트 찾기

네 스킬의 스크립트를 쓴다. 한 번 찾고 **실제 경로를 기억해 이후 블록에 값으로 써넣는다.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
for SKILL in pro-design-brief pro-launch pro-github pro-figma-verify; do
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  [ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
    H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
    [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
  done
  [ -d "$ROOT/skills/$SKILL/scripts" ] || { echo "$SKILL 스크립트를 찾지 못했습니다"; exit 1; }
  echo "$SKILL=$ROOT/skills/$SKILL/scripts"
done
```

| 자리표시 | 스킬 | 쓰는 것 |
|---|---|---|
| `{SCRIPTS}` | pro-design-brief | `design_brief_cli.py` — config · get-output-path · board · copy-lint · ascii |
| `{LAUNCH}` | pro-launch | 캡처 · 렌더 · 상태 연출 |
| `{GITHUB}` | pro-github | 이미지 올리기 · 이슈 만들기 (`issue` 출력일 때) |
| `{FIGMA}` | pro-figma-verify | Figma 덤프 세기 (링크가 있을 때) |

## 흐름

```
0 설정 판정 → 1 입력 파악 → 2 상태 목록 → 3 캡처 → 4 대안·문구·UI 요소·꼭 지킬 것 → 5 보드 → 6 게시
```

## 0. 설정 판정 — 처음 한 번, 이후 자동

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/design_brief_cli.py config show --root {PROJECT_ROOT}
```

`resolved` 에 세 가지가 나온다. `missing` 에 있는 것만 **한 번에 하나씩** 묻는다. 권장안을 1번에 둔다.

| 정할 것 | 자동 판정 (`suggest`) | 물을 때 |
|---|---|---|
| 출력 방식 | GitHub 레포면 `issue` 제안, 아니면 `html` | "이 레포는 디자인 요청서를 어떻게 받으세요? 1) 디자인 이슈 (권장) 2) HTML 한 장 3) md 폴더" |
| 디자이너 | 이슈 템플릿의 `디자인:` 줄 (`designer_candidates`). 비면 최근 디자인 이슈 담당자를 `{GITHUB}` 로 본다 | "디자이너 GitHub 아이디(또는 이름)가 뭔가요?" |
| 게시 전 확인 | 기본은 확인받는다 | 첫 게시 때 승인 게이트 C 분기 |

답을 받으면 저장한다. **사용자에게 설정 키 이름·파일 경로를 보이지 않는다.**

```bash
{PYTHON} {SCRIPTS}/design_brief_cli.py config set --root {PROJECT_ROOT} --destination issue --designer {아이디}
#   --scope default  : 모든 레포 기본값으로 (사용자가 "앞으로 전부"라고 했을 때)
#   --auto-approve true : "다음부턴 확인 없이 올려줘"
```

"다음부턴 HTML 로 해줘" 같은 말도 같은 명령으로 바꾼다. GitHub 을 안 쓰는 레포는 경로로 맞춘다
(`github` 설정과 따로 두는 이유다).

## 1. 입력 파악

| 사용자가 준 것 | 하는 일 |
|---|---|
| 없음 | 코드 · 캡처 · 대화만으로 만든다 |
| **Figma 링크** | `../references/figma-mcp.md` 규칙으로 읽는다 (두 번 나눠 받기 · 공통 컴포넌트 먼저). 읽기에 실패하면 Figma 없이 진행하고 요약에 적는다 |
| 이미지 (스크린샷 · 참고 앱) | 보드 "현재 구현" 칸 옆에 넣고 무엇을 참고했는지 한 줄 적는다 |

구현 여부를 정한다: **구현됨 / 일부 / 아직 없음.** 아직 없으면 캡처 대신 ASCII 와 대안 목업이 중심이 된다.

**Figma 가 있으면 얻는 것**: 그려진 상태 vs 빠진 상태 **빈틈 표**(`../references/design-states.md` §4 —
빠진 상태가 곧 요청 목록), 토큰·컴포넌트(대안을 시안 언어로), 시안 export(보드에 `시안 | 현재 | 대안`).
**시안끼리 어긋난 곳은 고치지 않고 질문으로 올린다.**

## 2. 상태 목록 — 디자이너가 안 그리는 화면

`../references/design-states.md` 의 **5축**(데이터 · 입력 · 환경 · 사람 · 표시)에서 뽑는다.
**스크립트가 분기를 스캔하지 않는다 — 네가 코드를 읽고 적는다.**

- 상태마다 **구현됨 / 화면 임시 / 미구현** 을 적는다 (보드 데이터 `status`: `done` · `temp` · `none`).
- 상태마다 **지금 흐름에서 나오는가**를 적는다 (`reachable`: `yes` · `old_data` · `unknown`). 그 상태를 만드는
  **입력 경로(고르는 UI, 저장되는 값)가 지금도 있는지 코드로 본다.** 스펙·주석의 "임시", "나중에 교체"는
  쓴 시점의 이야기다. 예전 데이터에만 나오는 상태는 요청에서 빼거나 "예전 데이터에만"으로 따로 표시한다.
  > 실제로 고르는 UI 가 이미 없어진 상태를 스펙 문장만 믿고 요청해, 디자이너가 나오지도 않는 화면을 받았다.
- **서버가 내려주는 문구도 상태다** — 공지 팝업 · 약관 · 서버 오류 문구. 코드 검색에는 안 걸리므로
  운영 API·관리 화면에서 확인한다. (코드만 보고 "보이는 곳 6군데"라고 썼는데 공지 팝업까지 7군데였다.)
- **그 화면에 실제로 해당하는 축만** 넣는다. 억지로 채우지 않는다 (버전 표시에 "0건"은 없다).
- 표시 축(글자 200% · 작은 폰)은 거의 모든 화면에 해당한다. **여기서 깨지는 것이 자주 나온다** —
  요청 대상과 별개 문제면 "별개"라고 적어 섞지 않는다.

## 3. 캡처 — pro-launch 로

```bash
# 자리를 받는다 — 이 스킬의 자리 아래에 캡처가 쌓인다
{PYTHON} {LAUNCH}/launch_cli.py get-output-path --skill design-brief --title "{화면 이름}"
source "{env_file 값}"          # $SHOT_DIR · $RUN_DIR
```

**렌더는 상태를 연출하는 수단이고, "지금 앱은 이렇다"의 근거는 실기기다.** ⚠️

위젯 렌더만 보고 쓴 주장이 실기기와 7건 달랐다. 렌더 하네스에는 모달 가림막이 안 그려지고, 가짜
실패 객체는 실제 실패와 모양이 다르고, 가짜 provider 는 오프라인 우선 경로와 자동 재시도를 건너뛰고,
렌더 폭은 기기 폭과 다르고, 픽스처 값은 운영 값이 아니다. 반대로 실기기에서만 나오는 결함도 있다.

| 무엇을 보이려는가 | 무엇으로 |
|---|---|
| 지금 앱의 모습 · 동작 · 수치 (사실) | **실기기 · 운영 API · 운영 설정** — 렌더로 대신하지 않는다 |
| 만들기 어려운 상태 (빈 목록 · 실패 · 긴 글자) | 렌더 · 응답 바꿔치기 — 캡처에 **"렌더 · 가짜 데이터"** 표시 |
| 아직 없는 안 | 실제 컴포넌트 렌더 → 안 되면 ASCII |

- 지급량·한도 같은 **수치는 픽스처가 아니라 운영 API·설정에서** 읽는다.
- 캡처마다 출처를 적는다 (`source`: `render` · `device` · `server` · `design`). 보드가 표시를 단다.
- 요청서에 적는 "지금 앱은 이렇다" 문장은 `facts[]` 에 **근거와 함께** 적는다. 렌더만 근거인 문장은
  게시 전에 실기기로 확인하거나 뺀다 (`board` 의 `preflight` 가 짚는다).

순서: **코드 렌더 → 실기기·브라우저 → ASCII.** 연출한 상태 중 실기기로 재현할 수 있는 것은 실기기로도 한 번 찍는다.

| 무엇으로 | 명령 | 언제 |
|---|---|---|
| 코드 렌더 | `render snapshot` → 임시 렌더 코드 → `render run` | 엣지 상태·대안 목업. 레시피는 `../pro-launch/references/render.md` |
| 기기 | `app shot --clean-status` | 실제 화면 그대로 |
| 브라우저 | `web viewport` · `web route` · `web shot` | 웹 — 빈 목록·실패를 서버 없이 연출 |
| ASCII | `{SCRIPTS}/design_brief_cli.py ascii --spec '{...}'` | 렌더할 수 없는 상태·아직 코드가 없는 안. "렌더 실패" 라고 표시한다 |

- **대안 목업도 실제 컴포넌트로 렌더한다.** HTML 로 다시 그리면 글꼴·간격이 달라 디자이너가 헷갈린다.
  실제 화면 위에 실제 글자 토큰으로 자리만 옮기는 식이 가장 정확하다.
- **작은 요소는 확대 조각을 만든다** (4배, 가장 가까운 픽셀로). 10px 글자는 전체 화면에서 안 보인다.
- 캡처를 위해 **AI 생성 API 를 부르지 않는다** — 가짜 데이터로 채운다.
- `render run` 이 `residue` 를 내면 **지우지 않는다.** 네가 만든 것이면 네가 지우고, 모르는 변경이면 보고만 한다.

## 4. 대안 · 문구 · UI 요소 · 꼭 지킬 것

**① 배치 대안 — 모양이 아니라 축이 달라야 한다**

- 3~5안. 갈라지는 축: 위치 · 밀도 · 표현(글자·아이콘·배지) · 진입(그 자리·새 화면·시트).
- **항상 "현재 구현" 안과 "최소" 안을 포함한다.**
- 안마다 `장점 · 약점 · 개발 영향`. 개발 영향은 "이 안은 새 화면이 필요해 개발이 따로 든다" 같은 것.
- 추천은 **근거와 함께 한 줄.** 안 이름은 A·B·C 로 통일하고 이슈 본문과 같은 이름을 쓴다.

**② 문구 — `현재 → 후보 2~3 → 이유`**

| 짚는 것 | 예 |
|---|---|
| 번역투 · 딱딱함 | "~하실 수 있습니다", "~되었습니다" |
| 장황 · 반복 | 제목과 본문이 같은 말 |
| AI 문장부호 | em dash(—) · 가운뎃점(·) 남발 |
| 과장 | "혁신적인", "완벽한" |
| 레포 용어·말투 규칙 위반 | 루트·모듈 `CLAUDE.md`, `docs/*design*` 의 용어표 — **자동으로 읽는다** |

- **법적 문구(약관·동의)는 "바꾸면 안 됨"만 표시**하고 후보를 내지 않는다 (`legal: true`).
- 상태별 문구가 없으면 **"문구 필요"** (`needed: true`).
- 후보를 쓴 뒤 기계 검사를 돌린다. **좋은 문구를 만들어 주지는 않는다** — 걸린 것을 고치는 것은 네 일이다.

```bash
{PYTHON} {SCRIPTS}/design_brief_cli.py copy-lint --file {보드 데이터.json} --banned "아이,기기,서버"
#   --banned : 레포 용어표의 "쓰지 않는다" 칸 (쉼표 목록 또는 한 줄에 하나인 파일)
```

**③ UI 요소 후보 — 데이터 모양에서 고른다**

| 데이터 모양 | 후보 |
|---|---|
| 하나 고르기 | 라디오 · 세그먼트 · 드롭다운 · 카드 선택 |
| 여러 개 고르기 | 체크박스 · 칩 · 토글 목록 |
| 긴 내용 | 아코디언 · 더보기 · 바텀시트 |
| 확인 · 알림 | 팝업 · 토스트 · 그 자리 안내 |
| 목록 | 리스트 · 그리드 · 카드 |
| 읽기 전용 한 값 | 목록 줄 오른쪽 값 · 새 화면 · 길게 눌러 복사 |

**레포에 이미 있는 컴포넌트를 먼저** 쓴다 (`existing`). 없는 것은 "새 컴포넌트" (`new`).

**④ 꼭 지킬 것 — 자동 수집, 출처와 함께**

브랜드 규격(예: Apple 로그인 버튼), 최소 터치 크기·글자 크기(레포 디자인 원칙 문서), **이미 합의된 예외**.
합의된 예외는 **코드 주석에 있는 경우가 많다** — 요청 대상 화면 파일의 주석을 읽는다 ("일부러 뺐다",
"되살리지 않는다" 같은 말). 레포 원칙과 요청 대상이 부딪히면(예: 10px 글자 vs 최소 14) **결함이 아니라
질문으로** 올린다.

## 5. 보드 — HTML 한 장 → 주제별 PNG

모은 것을 **데이터 JSON** 하나로 적고 조립한다. 그림 경로는 데이터 파일 기준 상대경로로 쓴다.

```bash
{PYTHON} {SCRIPTS}/design_brief_cli.py get-output-path --title "{화면 이름}"   # 캡처와 같은 제목
{PYTHON} {SCRIPTS}/design_brief_cli.py board --data {run_dir}/board_data.json --out {run_dir}/board --png
#   --md : markdown 출력용 brief.md 도 만든다 (PNG 링크 · 표)
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

- 데이터에 없는 주제는 보드에 만들지 않는다. `states[].design` 을 적으면 "시안" 칸이 생긴다 (Figma 빈틈 표).
- **주제별로 PNG 를 나눈다** — 한 장에 다 넣으면 GitHub 에서 안 읽힌다. 폭은 2,900px 안팎(상한 3,400).
- 그림은 HTML 에 **한 번만** 실린다(같은 캡처를 여러 칸에 써도). 표시에 충분한 크기로 줄여 싣는다.
- PNG 는 **pro-launch 가 받아 둔 Chromium** 으로 찍는다. 없으면 `browser_missing` — 멈추지 않고
  HTML 또는 원본 캡처 + md 표로 낸다. 브라우저가 필요하면 먼저 사용자에게 묻고 `{LAUNCH} web setup`.
- **PNG 를 Read 로 열어 본다.** 글자가 잘리거나 겹친 곳이 있으면 데이터를 고쳐 다시 조립한다.
- 결과의 **`preflight` 가 비어야 게시한다.** 출처 없는 캡처 · 도달 가능성을 안 적은 상태 · 렌더만 근거인
  사실을 짚는다. 게시 직전에는 `--strict` 로 조립하면 남은 것이 있을 때 `ok:false` 로 멈춘다.

## 6. 게시 — 디자이너에게는 한 형식만

게시 직전 **승인 게이트**(`../references/approval-and-questions.md` §4 A/B/C)를 그대로 쓴다.
무엇을 어디에 올릴지(이슈 제목·담당자·첨부 장수)를 보여 주고 승인받는다. 자동 모드면 요약만 보이고 진행한다.

| 출력 | 디자이너가 받는 것 | 방법 |
|---|---|---|
| `issue` | 이슈 본문 + PNG | 아래 |
| `html` | `board/board.html` 한 파일 (그림 내장 · 탭으로 넘겨 본다) | 경로를 알려준다 |
| `markdown` | `board/brief.md` + PNG 폴더 | `board --md` 로 만든 것. 경로를 알려준다 |

**둘 다 주지 않는다** — 어느 쪽을 볼지 헷갈린다.

**`issue` 일 때** — `pro-github` 스크립트로 올린다. **순서를 지킨다** (본문을 먼저 올리면 그림 없는 글이 게시된다).

```bash
# ① 그림을 먼저 올려 URL 을 받는다
PYTHONIOENCODING=utf-8 {PYTHON} {GITHUB}/github_cli.py upload-image {owner} {repo} {run_dir}/board/*.png --prefix brief
# ② 받은 markdown 을 본문에 넣는다 — 레포의 디자인 요청 템플릿(🖌️ 요청 내용 · 🎯 기대 결과 · 📋 참고 자료 ·
#    💡 추가 요청 사항 · 🙋 담당자) 섹션에 맞춘다. 제목은 레포 이슈 제목 규칙을 따른다
# ③ 이슈를 만든다 — 담당자는 디자이너
PYTHONIOENCODING=utf-8 {PYTHON} {GITHUB}/github_cli.py create-issue {owner} {repo} "{제목}" "{본문 .md 경로}" "{라벨}" --assignees "{디자이너}"
# ④ 구현 이슈가 있으면 서로 링크한다
PYTHONIOENCODING=utf-8 {PYTHON} {GITHUB}/github_cli.py add-comment {owner} {repo} {구현 이슈} "{링크 댓글 .md}"
```

본문 뼈대 — 보드와 같은 이름·같은 순서로:

| 섹션 | 들어갈 것 |
|---|---|
| 🖌️ 요청 내용 | 무엇을·왜·지금 상태 표, **꼭 지킬 것**(출처와 함께), 현재 구현 PNG |
| 🎯 기대 결과 | 어떤 시안이 나오면 개발이 무엇을 하는지 |
| 📋 참고 자료 | 상태 PNG · 대안 PNG(A·B·C) · 문구표 · UI 요소. 개발 쪽 추천은 **한 줄** |
| 💡 추가 요청 사항 | 고르면 개발이 따로 드는 안 · 질문(원칙과 부딪히는 것, 시안끼리 어긋난 것) |
| 🙋 담당자 | 디자이너 |

**게시한 뒤 틀린 것을 발견하면** 본문을 고치고 **정정 댓글을 따로 단다.** 디자이너는 알림으로 옛 본문을
이미 봤을 수 있다 — 본문만 고치면 무엇이 바뀌었는지 모른다. 정정 댓글에는 "처음에 쓴 것 → 실제 → 근거"를
표로 적고, 실기기 캡처를 붙인다.

**private 레포는 그림이 렌더링되지 않는다** (`upload-image` 의 `private_warning`). 그때는 사용자에게
알리고 `html` 출력으로 바꿀지 묻는다.

## 실패 경로

| 상황 | 동작 |
|---|---|
| 브라우저 없음 | PNG 대신 HTML 또는 원본 캡처 + md 표로 낸다. 요약에 사유를 적는다 |
| 렌더 실패 | 그 상태만 ASCII 로 대체하고 "렌더 실패" 표시 (`render_failed: true`) |
| 업로드 실패 | 로컬 산출물로 남기고 경로를 알려준다 |
| Figma 읽기 실패 | Figma 없이 진행하고 요약에 적는다 |
| 디자이너 모름 | 담당자 없이 등록하고 알린다 (다음에 묻는다) |
| 대상 레포에 흔적 | pro-launch `residue` 를 그대로 보고하고 지우지 않는다 |
| 실기기로 확인할 수 없다 (기기·계정·비용) | 그 사실은 `facts` 에서 빼거나 근거 없음으로 두고, 요약에 "확인 못 함"으로 적는다. 렌더로 대신 단정하지 않는다 |

## 하지 않는 것

- 캡처를 위해 AI 생성 API 호출 — 가짜 데이터로
- Figma 에 그리기 — MCP 는 읽기 전용이다
- 디자이너 대신 결정 — 추천은 한 줄, 선택은 디자이너
- 법적 문구 후보 제안
- 요청 대상과 별개로 발견한 화면 결함을 요청서에서 고치기 — 상태 표에 "별개"로 적고 개발 쪽에 알린다
