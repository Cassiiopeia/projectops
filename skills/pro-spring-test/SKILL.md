---
name: pro-spring-test
description: "Suh Spring Test Generator - Spring Boot 프로젝트용 테스트 코드를 자동 생성한다. suh-logger 의존성 유무에 따라 템플릿을 선택하고, 멀티모듈 프로젝트를 자동 감지한다. /spring-test 호출 시 사용."
---

# Suh Spring Test Generator

Spring Boot 프로젝트용 샘플 테스트 코드를 생성한다.

## 시작 전

`../references/common-rules.md`의 **절대 규칙** 적용 (Git 커밋 금지)

## 사용법

```
/spring-test                    # 현재 파일 기준
/spring-test UserService        # 특정 클래스
/spring-test @파일경로          # 특정 파일
```

인자: $ARGUMENTS

## 프로세스

### 1단계: 의존성 확인
- `build.gradle` 또는 `pom.xml`에서 `me.suhsaechan:suh-logger` 의존성 확인
- 멀티모듈 여부 (`settings.gradle`의 `include`)
- `testImplementation project(':상위모듈')` 존재 여부

### 2단계: Application 클래스 탐색 (멀티모듈)
- `@SpringBootApplication` 클래스의 FQCN 확인

### 3단계: 테스트 파일 생성
대상 클래스와 동일한 패키지 구조로 `src/test/java/` 하위에 생성

## 템플릿

### A: suh-logger 있을 때

```java
package {{PACKAGE}};

import static me.suhsaechan.suhlogger.util.SuhLogger.lineLog;
import static me.suhsaechan.suhlogger.util.SuhLogger.superLog;
import static me.suhsaechan.suhlogger.util.SuhLogger.timeLog;

import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
{{ADDITIONAL_IMPORTS}}

@SpringBootTest{{BOOT_CLASS}}
@ActiveProfiles("dev")
@Slf4j
class {{CLASS_NAME}}Test {

  {{AUTOWIRED_FIELDS}}

  @Test
  public void mainTest() {
    lineLog("테스트시작");

    lineLog(null);
    timeLog(this::{{TEST_METHOD_NAME}}_테스트);
    lineLog(null);

    lineLog("테스트종료");
  }

  public void {{TEST_METHOD_NAME}}_테스트() {
    // TODO: 테스트 로직 작성
    lineLog("테스트 실행중");
  }
}
```

### B: suh-logger 없을 때

```java
package {{PACKAGE}};

import lombok.extern.slf4j.Slf4j;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
{{ADDITIONAL_IMPORTS}}

@SpringBootTest{{BOOT_CLASS}}
@ActiveProfiles("dev")
@Slf4j
class {{CLASS_NAME}}Test {

  {{AUTOWIRED_FIELDS}}

  @Test
  public void mainTest() {
    log.info("============ 테스트시작 ============");

    {{TEST_METHOD_NAME}}_테스트();

    log.info("============ 테스트종료 ============");
  }

  public void {{TEST_METHOD_NAME}}_테스트() {
    // TODO: 테스트 로직 작성
    log.info("테스트 실행중");
  }
}
```

## 플레이스홀더

| 플레이스홀더 | 설명 | 예시 |
|-------------|------|------|
| `{{PACKAGE}}` | 패키지 | `com.example.service` |
| `{{CLASS_NAME}}` | 클래스명 | `UserService` |
| `{{TEST_METHOD_NAME}}` | 메서드명 (소문자) | `userService` |
| `{{BOOT_CLASS}}` | 멀티모듈 시 | `(classes = MyApplication.class)` |
| `{{ADDITIONAL_IMPORTS}}` | 추가 import | `import com.example.MyApplication;` |
| `{{AUTOWIRED_FIELDS}}` | 주입 필드 | `@Autowired UserService userService;` |

## 주의사항

- `application-dev.yml`이 `src/test/resources/`에 필요
- 멀티모듈에서는 상위 모듈 의존성 확인 필수
