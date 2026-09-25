📝 현재 문제점
---

- Figma MCP를 **제대로 읽는 규칙**이 `pro-figma-verify` 안에만 있다 (`references/mcp.md` 251줄, `SKILL.md` "두 번에 나눠 받는다", "공통 컴포넌트를 화면보다 먼저 본다", "상태를 다 세었는가").
  - 링크의 `node-id`가 화면이라는 보장이 없다 (실측 SECTION, 108만 자 응답)
  - 스타일이 참조로만 오고, 한 문자열에 그림자가 여러 줄 뭉쳐 온다
  - 시안은 한 컴포넌트를 여러 상태로 그려 두는데 기본 상태만 보고 만든다
- 새로 만들 `pro-design-brief`도 사용자가 Figma 링크를 주면 같은 규칙으로 읽어야 한다. 시안에 그려진 상태와 빠진 상태를 가려 **빠진 상태를 디자이너에게 요청**하기 위해서다. 지금 구조면 규칙을 복사하게 되고, 복사본은 한쪽만 고쳐져 어긋난다.

🛠️ 해결 방안 / 제안 기능
---

- MCP 읽기 규칙과 상태 세기 규칙을 **공용 참조**(`skills/references/`)로 올리고, 두 스킬이 링크로 같이 쓴다.
- 스크립트(`figma_verify_cli.py coverage` / `assets`)는 옮기지 않는다. 다른 스킬은 지금처럼 **스크립트로 부른다** (발견 스니펫 `SKILL=pro-figma-verify`).
- 설계: `docs/superpowers/specs/2026-09-25-pro-design-brief-design.md` §4.1.1

⚙️ 작업 내용
---

- [ ] `skills/pro-figma-verify/references/mcp.md` → `skills/references/figma-mcp.md`로 옮긴다. figma-verify에만 해당하는 문단(대조·conform)은 원래 자리에 남긴다
- [ ] `SKILL.md`의 "두 번에 나눠 받는다", "링크에서 인자를 뽑는다", "공통 컴포넌트를 먼저 본다"를 공용 참조로 올리고, figma-verify에는 요약 + 링크만 남긴다
- [ ] "상태를 다 세었는가", "시안은 한 가지 내용으로만 그려져 있다"를 `skills/references/design-states.md`로 올린다. 상태 축(데이터·입력·환경·사람·표시) 표를 함께 둔다. pro-design-brief §4.2와 같은 표다
- [ ] figma-verify SKILL.md · references 안의 옛 경로 참조를 전부 새 경로로 바꾼다
- [ ] `coverage` / `assets`를 다른 스킬이 스크립트로 부르는 호출 예를 공용 참조에 적는다
- [ ] 문서 링크 검사: 옛 경로 `references/mcp.md`를 가리키는 곳이 0이 되게 한다

**완료 기준**
- [ ] figma-verify의 기존 흐름(Phase 0~7)이 공용 참조만 보고도 그대로 따라가진다
- [ ] `pytest skills/pro-figma-verify/tests scripts/tests` 통과

🙋‍♂️ 담당자
---

- 백엔드: 
- 프론트엔드: 
- 디자인: 
