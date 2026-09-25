# Figma MCP 읽기 규칙이 pro-figma-verify 안에만 있어 다른 스킬이 같은 방식으로 읽을 수 없다

## 개요

Figma MCP를 제대로 읽는 규칙과 상태를 세는 규칙을 `pro-figma-verify` 밖의 공용 참조(`skills/references/`)로 올렸다. 새로 만들 `pro-design-brief`도 Figma 링크를 같은 규칙으로 읽어야 하는데, 지금 구조로는 규칙을 복사할 수밖에 없었다. 복사본은 한쪽만 고쳐져 어긋난다. 세는 스크립트(`coverage` · `assets`)는 옮기지 않았다. 다른 스킬은 지금처럼 스크립트로 부른다.

## 변경 사항

### 공용 참조
- `skills/references/figma-mcp.md`: `pro-figma-verify/references/mcp.md`를 `git mv`로 옮겼다. 파일 전체가 MCP 읽기 규칙이라, figma-verify에만 해당하는 문단(대조·conform)은 원래 없었다. 앞에 붙인 것은 두 가지다.
  - "§0 읽는 순서 요약": 링크 인자 → 두 번 나눠 받기 → 공통 컴포넌트 먼저 → 파일로 두고 스크립트로 세기 → 상태 세기
  - "공통 컴포넌트를 화면보다 먼저 본다" 절(figma-verify SKILL.md에서 올림)
  
  끝에는 "§4 다른 스킬에서 세는 도구를 부르는 법"을 붙였다. `coverage` · `assets` 호출 예와 부르는 쪽별 용도를 적었다.
- `skills/references/design-states.md`(신규): figma-verify SKILL.md의 "상태를 다 세었는가"와 "시안은 한 가지 내용으로만 그려져 있다"를 올렸다. 여기에 pro-design-brief 설계 §4.2와 같은 **5축 상태 표**(데이터·입력·환경·사람·표시)와, 코드 상태 × 시안 상태 **빈틈 표**를 더했다.

### pro-figma-verify
- `SKILL.md`: "딸린 문서" 표를 새 경로 두 개로 바꿨다. Phase 0의 "공통 컴포넌트 먼저 · 링크 인자 · 두 번 나눠 받기" 세 절은 **요지 표 + 링크**로 줄였다. Phase 1의 상태 두 절도 요약 + 링크로 바꿨다.

## 주요 구현 내용

- **옮긴 뒤에도 figma-verify 흐름(Phase 0~7)은 그대로 따라간다.** 요지 표에 순서와 이유가 남아 있고, 자세한 실측은 공용 문서 한 곳에 있다. `coverage` 호출 블록과 효과·분류 절차는 figma-verify에 그대로 두었다. 대조 전용 내용이기 때문이다.
- **"시안에 없는 상태는 대조 대상이 아니라 요청 대상"이라는 연결을 문서에 넣었다.** 두 스킬의 역할 경계가 여기서 갈린다(`figma-verify` = 그려진 것을 다 옮겼나, `design-brief` = 안 그려진 것을 요청).
- **시안끼리 어긋난 곳은 고치지 않고 질문으로 올린다**는 규칙을 빈틈 표에 적었다(설계 4.1.1).

### 검증

- 옛 경로 `references/mcp.md`를 가리키는 곳: **0**(`grep -rn` 확인)
- `pytest skills/ scripts/tests/` 320 통과, `npm test` 402 통과. 문서 참조 경로 검사(`test_skill_doc_reference_paths_exist`)도 통과했다.

## 주의사항

- 공용 문서의 호출 예는 `{FIGMA_SCRIPTS}` 자리표시를 쓴다. 부르는 스킬이 `common-rules.md` 표준 블록을 `SKILL=pro-figma-verify`로 돌려 경로를 얻는다.
- `rendering.md`(찍는 법)는 이번에 건드리지 않았다. #633에서 pro-launch로 일원화한다.
