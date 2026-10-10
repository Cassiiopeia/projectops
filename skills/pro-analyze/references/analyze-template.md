# analyze 산출물 템플릿 · 안티 패턴

> 언제 읽나: Phase 2 에서 analyze 문서를 쓰기 직전, 그리고 Phase 3 자체검토 때.

## 산출 위치

`analyze_cli.py get-output-path` 가 돌려주는 `path` 를 그대로 쓴다.
형태(참고): `{output_root}/analyze/YYYYMMDD_{이슈번호}_{정규화된제목}.md`

- 이슈번호가 없으면 순번(`001`, `002`…)을 CLI 가 붙인다.
- 제목 정규화(특수문자 제거, 공백→`_`, 50자 이내)도 CLI 가 한다.
- 3-layer 아키텍처: skill별 `_cli.py` 에서 `get-output-path` 를 부른다 (예: `report_cli.py`, `review_cli.py`, `note_cli.py`).
  참조: `../../references/common-rules.md` §"skill별 py 분산 호출".

## 병렬 태스크 식별

태스크 간 의존 관계를 확인한다.
- **순차**: 앞 태스크 결과에 의존 (예: 모델 변경 → 그걸 쓰는 서비스 변경)
- **병렬**: 독립적 (예: 서로 다른 모듈의 변경, 같은 파일 안 건드림) → 표에 `[병렬]` 표시

## 템플릿

````markdown
# {제목} — HOW 계획

작성일: {YYYY-MM-DD}
참조: {plan 산출물 경로}
GitHub 이슈: {이슈 번호 또는 없음}

## 1. 변경 파일 목록

| # | 파일 | 함수/위치 (라인) | 무엇을 | 실행 순서 |
|---|------|----------------|-------|---------|
| 1 | `path/to/File.java` | `methodName()` (L42~67) | A를 B로 교체 | 순차 |
| 2 | `path/to/Other.java` | `otherMethod()` (L88) | X 필드 추가 | [병렬] |

## 2. 태스크별 상세

### Task 1: {이름}

**파일**: `path/to/File.java`
**함수**: `methodName()` (line 42~67)
**변경 이유**: {plan Must 항목과 연결}

**Before**:
```java
// 현재 코드 (실제로 읽은 것)
public void methodName() {
    // 기존 로직
}
```

**After**:
```java
// 변경 후 코드
public void methodName() {
    // 새 로직
}
```

**검증**: {구체적 명령 또는 수동 확인 단계}
예: `mvn test -pl module-name -Dtest=ClassName#testMethodName`

---

### Task 2: {이름}
...

## 3. 현재 상태 (코드 인용)

실제로 읽은 파일/함수 요약:
- `path/to/File.java:42` — `methodName()`: 현재 X를 한다
- `path/to/Other.java:88` — `otherMethod()`: Y 역할

## 4. 위험 & 완화 [RISK]

- **[RISK]**: {Red Team이 찾은 결함/edge case. 예: 기존 호출자 영향, 동시성 경합} → **완화**: {예: 하위 호환 오버로드 추가}

## 5. 검증 방법

- [ ] {입력값 또는 시나리오} → {기대 결과}
- [ ] {회귀 확인 대상} — {확인 명령}
- [ ] {파괴적 검증: invalid input/경계값} → {기대되는 안전한 실패}

## 6. 다음 단계

구현 방식을 선택하세요:

**1. Subagent-Driven (권장)** — `/implement` 호출 시 태스크별 서브에이전트 + Self-Review 자동 진행
**2. Inline** — 현재 세션에서 순차 실행

병렬 태스크 있음: Task {N}, Task {M} → Subagent-Driven 선택 시 병렬 dispatch 가능.

## 7. [REVIEW_LOG] — Reviewer 적대적 검증
> Devil's Advocate. Reviewer 페르소나로 전환해 위 HOW 계획을 적대적으로 공격한다. 최소 1개 기록 (Stop-and-Think Gate — 비어 있으면 제출 불가).
- **[REVIEW_LOG]**: {이 계획의 결함/우회 가능 시나리오/극한 조건 실패 1개 이상. "정상 동작 확인"이 아니라 "어떻게 깨지는가". 발견 시 §1 표·§2 태스크에 반영했는가?}
> ⚡ Fast-Track: 단순 작업이면 "리스크 없음 — 단순 작업 (Fast-Track)" 한 줄로 갈음.

## 8. [ALTERNATIVES_CONSIDERED] — 기각한 대안
> 채택한 HOW 외에 고려했다가 기각한 구현 대안. 최소 1개 (Stop-and-Think Gate). analyze는 HOW 단계이므로 구현 수준 대안 비교가 정당하다.
- **기각 대안 1**: {대안 HOW} → **기각 이유**: {왜 채택안이 더 나은가}
> ⚡ Fast-Track: 단순 작업이면 "단일 자명 해법 — Fast-Track" 한 줄로 갈음.
````

## 안티 패턴

| ❌ | ✅ |
|---|---|
| "이 클래스를 수정하면 됩니다" (파일만, 함수/라인 없음) | `path/File.java:42` — `method()` 명시 |
| Before/After 없이 "X를 Y로 변경" | 실제 코드 블록 포함 |
| TBD/TODO 남기기 | 모르면 사용자에게 질문, 가정이면 명시 |
| plan.md 안 읽고 analyze 작성 | Phase 0에서 반드시 Read |
| 코드 안 읽고 영향 범위 추정 | Read/Grep으로 호출자 직접 확인 |
| 모든 태스크 순차로만 표시 | 독립 태스크는 `[병렬]` 표시 |
| `[REVIEW_LOG]`·`[ALTERNATIVES_CONSIDERED]` 비우고 제출 | Devil's Advocate — 결함 1개 + 기각 대안 1개 의무 |
| 자기 계획을 "잘 됐다"고 통과 | Red Team — "어떻게 깨지는가"로 적대 검증 |
