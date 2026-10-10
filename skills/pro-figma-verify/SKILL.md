---
name: pro-figma-verify
description: "Figma 시안을 코드로 옮기고, 옮긴 것이 시안과 같은지 센다. Figma MCP 응답의 허점(스타일이 참조로만 오는 것, 한 문자열에 그림자 여러 줄이 뭉쳐 오는 것, 아이콘 모양 정보가 아예 없는 것)을 알고 값을 복원해, 요소·효과(그림자·안쪽그림자·글로우·블러·배경블러)·스타일을 하나도 빠짐없이 나열해 작업 목록으로 삼는다. 아이콘·이미지 에셋을 중복 없이 안전한 파일명으로 내려받는 목록도 만들어 준다. 옮긴 뒤에는 시안 export 와 앱 렌더를 픽셀로 맞대 어긋난 자리를 덩어리로 짚는다. React·Flutter·React Native 를 가리지 않는다. 'figma 디자인 구현해줘', '시안대로 만들어줘', 'figma 코드로 바꿔줘', 'figma 에셋 받아줘', '아이콘 다운로드', '시안이랑 같은지 확인해줘', '디자인대로 됐는지 봐줘', 'figma 대조해줘', '그림자 빠진 거 없나', '모서리가 각진 것 같은데', '라운드 안 먹었어' 같은 요청에 사용한다. 앱을 밟아 동작 결함을 찾는 것은 pro-agent-test 다."
---

# 시안 → 코드 → 대조

**눈으로는 못 잡는다.** 효과 네 줄 중 안쪽 세 줄이 통째로 빠진 버튼이 전체 화면 골든을 통과해 배포됐고,
디자이너가 배포 **후에** 알려줬다. 값 단언도 단언하기로 생각한 것만 지킨다. 그래서 **세는 것**과 **그리는 것**
둘 다 한다 — 옮기는 일과 세는 일은 한 스킬이다(빠뜨림은 옮길 때 생기고 대조는 사후 확인일 뿐이다).

쓰는 때: 시안을 받아 화면을 만들 때(세는 것부터) · 만든 직후 배포 전 · "이거 다른데요"가 무엇인지 특정할 때 ·
기존 에셋·컴포넌트를 재사용했을 때. **쓰지 않는 때**: 앱을 밟아 동작 결함을 찾는 일(`pro-agent-test` — 접근성 트리에는
그림자·색·굵기가 없다), 시안이 없는 화면(대조할 기준이 없다 — 상태를 요청할 것이면 `pro-design-brief`).

`../references/common-rules.md` 의 **절대 규칙** 적용. 인자: $ARGUMENTS

## 무엇을 하려는가 → 명령 → 자세한 문서

| 하려는 것 | 명령 | 자세히 |
|---|---|---|
| 산출물 자리(증거 폴더 · 에셋 후보) | `figma_verify_cli.py get-output-path --title` | `references/counting.md` |
| Figma 를 읽는다(화면 목록 → 화면 하나) | `mcp__figma__get_figma_data` | `../references/figma-mcp.md` |
| 요소 · 효과 · 스타일을 **빠짐없이** 나열 | `figma_verify_cli.py coverage --dump --node` | `references/counting.md` |
| 상태(disabled · 빈 값 · 0건)를 다 세었나 | 상태별 노드마다 `coverage` | `../references/design-states.md` |
| 내려받을 에셋 묶기 → 받기 | `figma_verify_cli.py assets` → `mcp__figma__download_figma_images` | `references/assets.md` |
| 값을 코드로 옮기기 · 근사·생략 판단 | — | `references/conversion.md` · `references/framework-gaps.md` |
| 렌더를 시안과 같은 조건으로 찍기 | `launch_cli.py render run` · `app shot --keep-format` · `web shot --keep-format` | `references/rendering.md` |
| 속성으로 대조(모서리 · 칠 · 그림자) | `figma_verify_cli.py conform` | `references/comparing.md` |
| 픽셀로 맞대기(보조) | `figma_verify_cli.py diff` | `references/comparing.md` |
| 보고 · 함정 표 | — | `references/comparing.md` |

## 스크립트 찾기 — 한 번만

**Bash 도구는 호출마다 상태가 초기화된다.** 한 번 찾은 뒤 **실제 경로를 이후 블록에 값으로 직접 써넣는다.**

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
for SKILL in pro-figma-verify pro-launch; do
  ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
  [ -d "$ROOT/skills/$SKILL/scripts" ] || for B in ~/.claude/plugins/cache ~/.codex/plugins/cache ~/.gemini/extensions ~/.pi/agent/git; do
    H=$(find "$B" -maxdepth 8 -type d -path "*/projectops/*skills/$SKILL/scripts" 2>/dev/null | sort -V | tail -1)
    [ -n "$H" ] && { ROOT="${H%/skills/$SKILL/scripts}"; break; }
  done
  [ -d "$ROOT/skills/$SKILL/scripts" ] || { echo "$SKILL 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
  echo "$SKILL=$ROOT/skills/$SKILL/scripts"
done
echo "PYTHON=$PYTHON PROJECT_ROOT=$PROJECT_ROOT"
```

`pro-figma-verify=` 값이 `{SCRIPTS}`, `pro-launch=` 값이 `{LAUNCH}` 다. **찍는 것은 pro-launch 가 한다**(`../pro-launch/SKILL.md`).

## 공통 규칙

- **JSON 하나를 돌려준다.** `ok` · `code` · `summary` · `next` 를 보고 다음 수를 정한다. **판단은 네가 한다** —
  스크립트는 세고 나열하고 그릴 뿐이다.
- **화면 하나씩 본다.** `--node` 없이 파일 전체를 넘기면 수천 개가 나와 분류할 수 없다. **공통 컴포넌트를 화면보다 먼저.**
- **효과를 가장 먼저, 따로 본다.** `effect_counts` → `effects` 한 줄씩. `boxShadow[0]`·`[1]`… 번호만큼 코드에도 있어야 한다.
  블러(자기가 흐려짐)와 배경 블러(뒤가 흐려짐)를 바꿔 쓰지 않는다.
- **분류는 셋 중 하나**: 구현 · 근사(사유 필수) · 생략(사유 필수). 근사·생략은 **코드 주석에도** 사유를 남긴다.
- **에셋은 증거 폴더(`run_dir`)에 받지 않는다** — `asset_dir_candidates` 중 하나(커밋돼야 하는 파일). 후보가 비면 묻는다.
- **대조용 캡처는 원본 PNG**(`--keep-format`). pro-launch 기본(긴 변 1200 WebP)으로 줄이면 픽셀이 뭉개진다.
- **픽셀 100% 일치를 요구하지 않고, 기본으로 CI 게이트를 걸지 않는다.** 퍼센트·덩어리 수를 결함 수로 읽지 않는다.
- 기준은 언제나 **시안 export** 다. 구현자가 만든 골든은 기준이 아니다.
  시안 export 는 화면 노드를 `download_figma_images` 로 받되 `pngScale` 을 기기 배율(3배 기기면 3)에 맞춘다 — `references/comparing.md` "시안 export 받기".

## 순서 — 단계별 결정 규칙

**Phase 0 — 자리를 받고 Figma 를 읽는다.**

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_verify_cli.py get-output-path --title "{화면 이름}"
```

덤프·export·렌더·차이 그림은 `run_dir` 아래(추적 제외), 앱이 쓸 에셋은 `asset_dir_candidates`(추적).
Figma 는 `depth: 2` 로 화면 목록 → 고른 화면 하나를 **`depth` 없이** 받아 **파일로** 둔다(`depth` 로 자르면 잘렸다는 표시가 없다).
링크의 node-id(`238-1846` → `238:1846`)가 화면이라는 보장은 없다. 노드 id 를 모르면 묻는다.

**Phase 1 — 빠짐없이 분류한다.**

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_verify_cli.py coverage --dump {덤프 파일} --node {노드 id}
```

요소(`elements` — 화면에 있나) · 효과(`effects` — 한 줄도 안 빠졌나) · 스타일(`items`)을 **하나도 남기지 않고** 분류한다.
`styles_resolved` 가 참조를 몇 개 이어 붙였는지 알려준다. 상태별 노드마다 돌리고, 시안에 **없는** 상태는 요청할 것으로 넘긴다.

**Phase 2 — 에셋을 받는다.** `get_figma_data` 는 그림을 주지 않는다(`IMAGE-SVG` 노드에 모양 정보가 없다).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_verify_cli.py assets --dump {덤프 파일} --node {노드 id}
```

돌려준 `nodes` 를 **그대로** `download_figma_images` 의 `nodes` 에, `localPath` 는 고른 에셋 폴더의 절대경로.
받은 뒤 `rename_me` · `certain: false` · 0 바이트 · 개수를 확인한다. `baked_effect` 항목은 **더 크게 온다** —
코드에서 효과를 빼고 받은 크기 그대로 도형 중심에 둔다. 넣은 뒤 `fill`/`stroke` 값을 전수로 훑어 토큰에 없는 색을 찾는다.

**Phase 3 — 옮긴다.** 분류표가 곧 작업 목록이다. 이미 있는 토큰·컴포넌트를 먼저 쓴다(`references/conversion.md`).
프레임워크가 그대로 못 받는 자리(안쪽 그림자 · 글로우 등)는 `references/framework-gaps.md`.

**Phase 4 — 속성으로 대조한다(픽셀보다 먼저).**

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_verify_cli.py conform --dump {덤프} --render {앱 렌더.png} --node {화면 노드 id}
#   --check corners,fills,shadows   좁히기     --fail-on high   그 이상이면 종료코드 1 (기본 none)
```

`[high] … 좌상 r=16 → 렌더가 각졌다` 처럼 단정으로 나온다. **각졌다고 나오면 반지름을 다시 주지 말고 자식이 덮었는지**
본다(Flutter `clipBehavior: Clip.antiAlias` · CSS/RN `overflow: hidden`). `INSTANCE` 가 스타일 없이 `componentId` 만 가지면
컴포넌트 노드를 따로 받는다.

**Phase 5 — 픽셀로 맞댄다(보조).** 같은 논리 크기 · 같은 안전영역 · 시안과 같은 내용으로 렌더한다(`references/rendering.md`).

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py render snapshot --root {레포}
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py render run --root {레포} --cmd "{렌더 명령}" --collect "{렌더 결과 글롭}" --cleanup {임시 폴더}
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py app shot --device "$DEV" --keep-format --out render   # 또는 기기에서 그대로
PYTHONIOENCODING=utf-8 {PYTHON} {LAUNCH}/launch_cli.py web shot --keep-format --out render
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/figma_verify_cli.py diff --render {앱 렌더.png} --design {시안 export.png} --out {차이.png} \
  --mask-top {상태바 높이} --mask-bottom {홈 인디케이터 높이}
```

덩어리가 여럿이면 **`shift_probe` 부터** — `looks_shifted: true` 면 컨테이너 하나가 밀린 것이다. 글자 자리 덩어리는 대개 무해,
도형·여백·배경 자리는 실제로 틀린 것. 시안 모서리가 투명하면 `--bg RRGGBB`.

**Phase 6 — 컴포넌트를 3배로 따로 본다.** 그림자·발광·1px 테두리는 1배 전체 화면에서 사라진다. pro-launch 브라우저는
1배 고정이라 3배는 임시 렌더 코드를 `render run` 으로 돌린다(`references/rendering.md`).

**Phase 7 — 보고한다.** **생략·근사를 맨 위에**, 그다음 속성 대조, 마지막에 픽셀 대조. 값은 다시 셀 수 있게(좌표 · 크기 · 평균차),
무엇과 맞댔는지 노드 id 를 남긴다. 형식과 함정 표는 `references/comparing.md`.

## 실패 code → 다음 행동

| code | 다음 행동 |
|---|---|
| `dump_not_found` · `dump_unreadable` | 덤프를 파일로 다시 저장한다(JSON·YAML). MCP 응답을 그대로 붙여 넣지 않는다 |
| `node_not_found` | `--node` 가 덤프 안에 없다. `depth: 2` 목록에서 화면 노드를 다시 고르거나 그 노드를 받아 온다 |
| `no_style_found` | 스타일 항목이 0건이다. 노드 id 가 맞는지, 덤프가 스타일을 포함하는지(`depth` 없이 받았는지) 본다 — 0건 통과는 대조를 안 한 것이다 |
| `render_not_found` · `image_not_found` · `image_unreadable` | 렌더·시안 PNG 경로를 확인한다. WebP 로 줄였으면 `--keep-format` 으로 다시 찍는다 |
| `imaging_missing` | 이미지 라이브러리(Pillow)가 없다. 설치를 사용자에게 제안한다 |
| `unknown_check` | `--check` 는 `corners` · `fills` · `shadows` 만 받는다 |
| `bad_bg` · `bad_mask` | `--bg` 는 `auto` 또는 `RRGGBB` · `--mask-top`+`--mask-bottom` 은 0 이상이고 시안 높이보다 작아야 한다 |
| `conformance_failed` | `--fail-on` 이상 항목이 있다. 출력 항목을 고치거나 근사·생략 사유를 남긴다 |
| `mkdir_failed` | 산출물 자리를 못 만들었다. 권한·`--root` 를 확인한다 |
| `bad_args` | 서브커맨드·필수 인자(`--dump` · `--render` · `--design` · `--title`)를 확인한다 |
