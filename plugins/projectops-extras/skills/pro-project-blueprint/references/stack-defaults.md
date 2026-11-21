# Stack defaults and coding conventions

> When to read: scaffolding a stack in a new project, or reviewing whether new code follows the owner's conventions.

Use these choices without asking. Check the installed version's docs before using an API (Expo, Spring and libraries
change per release); do not write from memory.

## React Native (`mobile/`)

- Expo + TypeScript + Expo Router (file = screen, `src/app/` holds routes only and stays thin).
- Reanimated for motion, `react-native-svg` for vector art, TanStack Query for server state.
  Add Zustand only when real client state appears.
- No paid EAS build: Android and iOS build on GitHub Actions (projectops `react-native-expo` workflows).
- Add packages with `npx expo install <name>` (matches the SDK).
- Layers: `src/core` (config, error, format) <- `src/data` (models, sources) <- `src/features` and `src/design`
  (tokens, theme, components, one `index.ts` entry) <- `src/app`. Architecture tests in `tests/architecture/` and
  ESLint enforce the direction and ban raw colors, sizes and durations in screens.
- Verify: `npx tsc --noEmit`, `npx eslint .`, `npx jest`.

## Spring (`server/`)

- Java 21, Gradle multi-module, dependencies from mavenCentral only.
- Modules, dependencies flow upward only:

| Module | Holds |
|---|---|
| `<PFX>-Common` | `ErrorCode`, `CustomException`, standard responses, `BaseEntity` |
| `<PFX>-Domain-<Name>` | One module per domain (entities, repositories, domain services) |
| `<PFX>-Application` | Use cases that combine domains |
| `<PFX>-Web` | Entry point, controllers, global exception handler, schedulers, Flyway migrations |

- PostgreSQL + Flyway; `ddl-auto: validate`, schema changes only through migration files.
- One exception type: `CustomException(ErrorCode)`; no per-domain exception classes. Success responses through one
  wrapper, failures built by the global handler.
- Secrets only through environment placeholders in `application.yml` (`public-repo-secrets.md`).
- Logs in English with a fixed feature prefix: `[feature action] rejected 400 : reason`; sanitize external input first.
- Verify: `./gradlew compileJava`, then only the tests that target the change.

## Coding conventions (short form)

The owner keeps a personal conventions document; this is its core.

1. **Single source of truth** - each value, rule or asset has one original; others reference or generate from it.
   Brand assets, config values and legal text are single-sourced from the first copy.
2. **Rule of three** - two copies may stay; the third copy is extracted into a shared place at once.
3. **Names explain** - verbs for functions, `is/has/can/should` for booleans, units as suffixes (`timeoutSeconds`),
   no abbreviations beyond industry-standard ones (`id`, `url`, `api`, `dto` ...), one main type per file named after it.
4. **Layers** - presentation > application > domain < infrastructure; screens never call HTTP or the database directly.
   Cross-cutting concerns (errors, response shape, auth token, loading/empty/error UI, formatting, logging) live in one place.
5. **Design system** - tokens (color, spacing, type, radius, motion, light and dark) > theme > components > screens.
   Screens use tokens and components only.
6. **Rules are enforced by tests** - architecture tests ban bypasses; exceptions are an explicit list with reasons.
7. **Size** - review a file over 300 lines, split it over 500. One function, one job.
8. **Comments** - short phrases, not prose: a one-line summary per method (`validate > run > compare > save`), a header
   per logic block, the meaning of codes and units next to them, the why only when code cannot show it. No change
   history in comments.
9. **Copy** - user-facing text follows the product's tone rules; error screens show an error code.
