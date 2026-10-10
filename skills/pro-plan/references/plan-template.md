# plan 질문 포맷 · 산출물 템플릿 · 안티 패턴

> 언제 읽나: Phase 1 에서 질문을 만들 때, Phase 2 에서 plan 문서를 쓰기 직전, Phase 3 자체검토 때.

## 질문 포맷 (Phase 1)

```
[질문] {부족한 항목}이 무엇인가요?

후보:
  1) {옵션 A} — {한 줄 설명}
  2) {옵션 B} — {한 줄 설명}
  3) 직접 입력

추천: {기본값} (이유: {왜})
```

전문 용어 등장 시 한 줄 풀이 필수. 예: "MVC(Model-View-Controller, 화면/로직/데이터를 분리하는 구조)로 갈까요?"

## 산출 위치

`plan_cli.py get-output-path` 가 돌려주는 `path` 를 그대로 쓴다.
형태(참고): `{output_root}/plan/YYYYMMDD_{이슈번호}_{정규화된제목}.md`

- 이슈번호가 없으면 순번(`001`, `002`…)을, 제목 정규화(특수문자 제거, 공백→`_`, 50자 이내)를 CLI 가 처리한다.
- 3-layer 아키텍처: skill별 `_cli.py` 에서 `get-output-path` · `get-issue-number` · `normalize-title` 를 부른다.
  `commit_cli.py` 가 `get-issue-number`·`normalize-title`, `github_cli.py` 가 `normalize-title`·`create-branch-name`·`get-commit-template` 를 갖는다(pro-issue 통합으로 흡수).
  참조: `../../references/common-rules.md` §"skill별 py 분산 호출".
- 다음 순번 계산은 각 스킬 CLI 의 `get-output-path` 가 내부에서 처리하므로 agent 가 따로 호출하지 않는다.

## 템플릿

```markdown
# {제목}

작성일: {YYYY-MM-DD}
GitHub 이슈: {이슈 번호/링크 또는 "없음"}
대상 브랜치: {브랜치명 또는 "미정"}
우선순위/마감: {이슈 라벨 또는 "없음"}

## 1. 한 줄 요약
{무엇을 왜 한다 — HOW 없이 WHAT만}

## 2. 배경
{2~5줄. 왜 지금 필요한가, 어떤 문제를 풀고 있는가}

## 3. 사용자 시나리오 / 동작 정의
- 시나리오 1: {누가} {언제} {무엇을 하면} {무엇이 일어난다}
- (버그라면) 재현 단계 → 현재 결과 → 기대 결과

## 4. 요구사항
**필수 (Must)**:
- ...

**원함 (Should)**:
- ...

**선택 (Nice)**:
- ...

> Must/Should/Nice: Must=없으면 안 됨, Should=가능하면, Nice=여유 있을 때.

## 5. 제약
- 기술: {라이브러리/언어/프레임워크 제약}
- 환경: {내부망, OS, 런타임 버전}
- 일정: {마감, 의존 작업}

## 6. 성공 기준 (Definition of Done)
- [ ] {검증 가능한 기준 1}
- [ ] {검증 가능한 기준 2}

## 7. 가정 [ASSUMPTIONS]
- 가정 1: ... (다르면 알려주세요)

## 8. 미해결 질문
- ?: ... (없으면 "없음")

## 9. 다음 단계
- (단순 작업) → `/implement` 바로 호출
- (복잡 작업) → `/analyze`로 HOW 구체화 후 `/implement`

## 10. [REVIEW_LOG] — Architect 자기검증
> Devil's Advocate. Architect 시선으로 이 plan을 되돌아본다. 최소 1개 기록 (Stop-and-Think Gate — 비어 있으면 제출 불가).
- **리스크/놓친 시나리오**: {이 plan이 빗나간다면 어디서? 고려 못 한 사용자/실패 시나리오는?}
- **아키텍처 방향 대안**: {채택 방향 외 고려한 큰 방향 1개 + 왜 안 골랐나. 예: "동기 처리 vs 비동기 큐 — 트래픽 규모상 동기 채택"}
> ⚠ 여기서 대안은 **아키텍처 방향 수준**까지만. 파일/함수 단위 대안은 금지(→ `/analyze`).
> ⚡ Fast-Track: 단순 작업이면 "리스크 없음 — 단순 작업 (Fast-Track)" 한 줄로 갈음.
```

> ⛔ **이 템플릿에서 절대 추가 금지**: "변경 계획" 표, 파일 경로 + 함수명 조합, Before/After 코드
> (단 `[REVIEW_LOG]`의 아키텍처 방향 대안은 파일/함수 없는 큰 방향 서술이므로 허용)

## 안티 패턴

| ❌ | ✅ |
|---|---|
| "이 파일의 이 함수를 바꾸면 됩니다" | "→ `/analyze`에서 구체화" |
| 변경 계획 표 작성 | plan 문서에서 완전 제거 |
| GitHub 이슈 무시 | Phase -1에서 반드시 fetch 시도 |
| 4개 질문 한 번에 | 한 번에 하나, 추론 가능하면 가정 |
| 전부 Must 분류 | Must/Should/Nice 균형 |
| HOW 포함 plan 승인 | HARD-GATE — 수정 후 재제출 |
| `[REVIEW_LOG]` 비우고 제출 | Devil's Advocate — 리스크/대안 1개 이상 의무 기록 |
| 사용자 지시를 의심 없이 수용 | Intentional Doubt — 숨은 의도 1개 파고듦 |
