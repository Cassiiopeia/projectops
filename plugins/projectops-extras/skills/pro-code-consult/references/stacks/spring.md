# Spring stack rules

> When to read: when the target has a Spring Gradle/Maven project. Shared by audit, refactor and init.

## Layer map

| Layer | Location | What goes in |
|---|---|---|
| Presentation | `controller` (+ `*ControllerDocs` Swagger interfaces) | Only receiving requests, validation and response conversion |
| Application | `service` (the Application module in a multi-module build) | Business rules, transactions, combining several domains |
| Domain | `entity`, `domain` | Entities, value objects, domain rules |
| Infrastructure | `repository`, `client`, `config` | JPA, external APIs, cache keys |
| Common | `common` (`ErrorCode` enum + one exception type + `@RestControllerAdvice`) | |

Dependency direction: controller → service → domain ← repository. **A controller importing a repository is a violation.**
Multi-module builds are one-way `Common ← Domain-* ← Application ← Web`. When domain modules tangle with each other through `api project(...)`, look at the Gradle edges and cycles in `deps`.

## Common AI smells

- Controllers calling repositories directly, responses exposing entities or `Page<Entity>` as is
- Error responses that bypass `ErrorCode`, such as `Map.of("error", ...)`; a catch-all handler that returns `e.getMessage()` as is
- Redis keys and config key strings scattered across services (no key registry)
- The same owner or status check block copied into every method
- Banners like `// ===== existing methods =====`, history comments like `added in (#123)`, multi-line Javadoc bullets
- `Boolean enabled`, `sslEnabled` (no prefix), services or Docs files of 1000+ lines

## First rule candidates

```
# controller-must-not-import-repository.rule
description=Controllers must not import repositories directly (go through services)
paths=src/main/java/
extensions=Controller.java
pattern=^import [\w.]+\.repository\.

# no-raw-error-map.rule
description=No error responses that bypass ErrorCode
paths=src/main/java/
extensions=.java
pattern=Map\.of\(\s*"error"
```

In a multi-module build, list the module folders in `paths`, comma-separated (`Web/src/main/java/,Application/src/main/java/`).
For dependencies a pattern cannot express (package cycles, etc.), **propose** ArchUnit — it is a new dependency, so only after the user approves.

## Rule tests

`install-tests PATH --stack spring --module <module>` → `src/test/java/architecture/ArchitectureRulesTest.java`.
Uses JUnit 5 only (included in `spring-boot-starter-test`). Gradle runs tests from the module folder, so the test walks upward to find the rules folder.

## Choosing model files

1 controller (Docs split out, request validation only), 1 service (flow visible through step comments and private methods), 1 repository.
