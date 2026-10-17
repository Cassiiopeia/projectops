# Spring 스택 규칙

> 언제 읽나: 대상에 Spring Gradle/Maven 프로젝트가 있을 때. audit·refactor·init 공통.

## 계층 지도

| 계층 | 위치 | 들어가는 것 |
|---|---|---|
| 표현 | `controller` (+ `*ControllerDocs` Swagger 인터페이스) | 요청 받기·검증·응답 변환만 |
| 응용 | `service` (멀티모듈이면 Application 모듈) | 업무 규칙, 트랜잭션, 여러 도메인 조합 |
| 도메인 | `entity`·`domain` | 엔티티, 값 객체, 도메인 규칙 |
| 인프라 | `repository`·`client`·`config` | JPA, 외부 API, 캐시 키 |
| 공통 | `common` (`ErrorCode` enum + 예외 1종 + `@RestControllerAdvice`) | |

의존 방향: controller → service → domain ← repository. **controller가 repository를 import하면 위반.**
멀티모듈은 `Common ← Domain-* ← Application ← Web` 단방향. 도메인 모듈끼리 `api project(...)`로 얽히면 `deps`의 Gradle 간선·순환으로 본다.

## 자주 나오는 AI 냄새

- controller에서 repository 직접 호출, 응답에 엔티티·`Page<Entity>` 그대로 노출
- `Map.of("error", ...)`처럼 `ErrorCode`를 우회한 오류 응답, catch-all 핸들러가 `e.getMessage()`를 그대로 내보냄
- Redis 키·설정 키 문자열이 여러 서비스에 흩어짐 (키 등록부 없음)
- 같은 소유자·상태 검사 블록을 메서드마다 복사
- `// ===== 기존 메서드 =====` 같은 배너, `(#123) 에서 추가` 경위 주석, 여러 줄 Javadoc 불릿
- `Boolean enabled`·`sslEnabled` (접두사 없음), 1000줄+ 서비스·Docs 파일

## 첫 규칙 후보

```
# controller-must-not-import-repository.rule
description=컨트롤러가 저장소를 직접 import 금지 (서비스 경유)
paths=src/main/java/
extensions=Controller.java
pattern=^import [\w.]+\.repository\.

# no-raw-error-map.rule
description=ErrorCode 우회 오류 응답 금지
paths=src/main/java/
extensions=.java
pattern=Map\.of\(\s*"error"
```

멀티모듈이면 `paths`에 모듈 폴더를 쉼표로 나열한다 (`Web/src/main/java/,Application/src/main/java/`).
규칙이 패턴으로 표현이 안 되는 의존(패키지 순환 등)은 ArchUnit을 **제안**한다 — 새 의존성이라 사용자 승인 뒤에만.

## 규칙 테스트

`install-tests PATH --stack spring --module <모듈>` → `src/test/java/architecture/ArchitectureRulesTest.java`.
JUnit 5만 쓴다 (`spring-boot-starter-test`에 들어 있음). Gradle은 모듈 폴더에서 테스트를 돌리므로 위로 올라가며 규칙 폴더를 찾는다.

## 모범 파일 지정

컨트롤러 1개(Docs 분리·요청 검증만), 서비스 1개(단계 주석·private 메서드로 흐름이 보임), 저장소 1개.
