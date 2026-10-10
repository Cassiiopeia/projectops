# 6관점 리뷰 기준과 출력 형식

> 언제 읽나: 리뷰 2~4단계에서 관점별 Critical/Major/Minor 기준과 결과 템플릿이 필요할 때.

## 6가지 관점

### 🔒 보안 (Security)
**Critical**: SQL Injection, XSS, 민감 정보 하드코딩, 인증/인가 우회
**Major**: 취약한 의존성, 불충분한 입력 검증, 에러 메시지 민감 정보 노출
**Minor**: 보안 헤더 누락, 로깅 민감 정보, Rate limiting 미적용

### ⚡ 성능 (Performance)
**Critical**: N+1 쿼리, 메모리 누수, 무한 루프, 동기 blocking
**Major**: 불필요한 렌더링, 큰 번들, 비효율 알고리즘 O(n²), 캐싱 미활용
**Minor**: useMemo 미사용, 이미지 미최적화, Lazy loading 미적용

### 🐛 버그 및 로직
**Critical**: Null/undefined 참조, 타입 에러, 예외 처리 누락
**Major**: 엣지 케이스 미처리, Race condition, 비동기 오류
**Minor**: 에러 메시지 불명확, 폴백 부족

### 📐 코드 품질
**Major**: 100줄 이상 함수, DRY 위반, 순환 복잡도 > 10, 스타일 불일치
**Minor**: 불명확한 이름, 매직 넘버, 깊은 중첩 > 3단계

### 🏗️ 아키텍처
**Major**: 관심사 분리 부족, 의존성 순환, SOLID 위반
**Minor**: 불명확한 구조, 불필요한 의존성

### 🧪 테스트
**Major**: 핵심 로직 테스트 없음, 엣지 케이스 누락
**Minor**: 커버리지 < 70%, 깨지기 쉬운 테스트

## 우선순위 분류 (3단계)

```markdown
### 🚨 Critical (즉시 수정)
**파일:라인** — 문제 / 영향 / 해결

### ⚠️ Major (배포 전 수정)
**파일:라인** — 문제 / 영향 / 해결

### 💡 Minor (개선 권장)
**파일:라인** — 현재 / 제안 / 이유

### ✅ Positive (잘한 점)
- [칭찬할 부분]
```

## 종합 평가 (4단계)

```markdown
### 📊 리뷰 요약
**전체 평가**: [Approve / Request Changes / Comment]
**이슈 통계**: Critical X개 / Major Y개 / Minor Z개

**핵심 개선 사항**:
1. [가장 중요]
2. [두 번째]
3. [세 번째]
```
