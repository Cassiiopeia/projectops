# Coding rules and clean code principles (shared by Flutter · Spring · Python · JavaScript)

This document gives one set of criteria for judging code on any stack.
There is one goal: **code where fixing one place fixes everything correctly, and where names alone show the meaning.**
An Apple-style redesign could be applied to dozens of screens at once because colors, spacing and components lived in one common place.
Apply the same approach to every area (design, API, config, assets, copy).

---

## 1. Three core principles

1. **Single Source of Truth**
   Keep the source of a value, rule or asset in one place only. Everything else references that source or is generated from it. Hand-made copies always drift apart eventually.
2. **Extract on the third (Rule of Three)**
   - Up to **2 places**, keep the code or value where it is. Premature abstraction is harder to read.
   - When a **3rd place** appears, extract it to a common point right away. Do not postpone.
   - Exception: brand assets (logo, colors, fonts), config values (URLs, key names, bundle IDs) and legal text get a single source from the start, **even at 2 places**. When they drift, users notice immediately or it causes an outage.
3. **The name is the explanation**
   The name alone must tell you what something is and what it does. Long names are fine. If a comment has to supplement a name, rename it.

---

## 2. Naming

### 2.1 Common rules
| Target | Rule | Good | Bad |
|---|---|---|---|
| Boolean variables, properties, getters | Start with `is` / `has` / `can` / `should` | `isDarkMode`, `hasUnreadNotification`, `canSubmitAnswer`, `shouldShowOnboarding` | `dark`, `flag`, `loaded`, `check` |
| Functions, methods | Start with a verb that says what it does | `fetchDailyQuestionSet`, `calculatePassReadinessPercent`, `saveSelectedThemeMode` | `data()`, `process()`, `handle()`, `doIt()` |
| Boolean-returning functions | Phrased as a question | `isAnswerCorrect(...)`, `hasExpiredToken()` | `checkAnswer(...)` (you cannot tell what it returns) |
| Collections | Plural, or `...List` / `...ById` | `questionSummaries`, `topicNameById` | `qList`, `data`, `arr` |
| Numbers with units | Unit as a suffix | `timeoutSeconds`, `bottomInsetPixels`, `retryDelayMilliseconds` | `timeout`, `delay` |
| Event handlers | `on` + event | `onThemeModeSelected`, `onSubmitButtonPressed` | `click`, `cb` |
| Conversion functions | `to...` / `from...` | `toQuestionDetailResponse`, `fromJson` | `conv`, `map2` |

### 2.2 Forbidden
- **No abbreviations.** Spell out `svc`, `repo`, `mgr`, `btn`, `idx`, `tmp`, `res`, `cnt`, `q`, `ctx` (except where it is a framework convention).
  - Only industry-standard abbreviations are allowed: `id`, `url`, `api`, `json`, `http`, `sql`, `ui`, `dto`, `jwt`, `uuid`.
- No meaningless names: `data`, `info`, `item`, `value`, `temp`, `result`, `manager`, `helper`, `util`. Do not use them alone; say what of what (`questionDetailData` → `questionDetail`).
- No negative booleans: use `isVisible` instead of `isNotVisible`, and negate at the call site.
- Names that show ownership only through a prefix (`AppButton`) are for design system components only. Everywhere else, use a name that shows the role.

### 2.3 Files and types
- One main type per file. **Name the file after the main type** (`question_detail_page.dart` ↔ `QuestionDetailPage`, `QuestionService.java`, `question_service.py` ↔ `QuestionService`).
- Use role suffixes consistently.

| Role | Flutter | Spring | Python |
|---|---|---|---|
| Screen | `...Page` | — | — |
| Reusable UI | `...Widget` / design system `App...` | — | — |
| State | `...Provider` / `...Notifier` | — | — |
| Request entry point | — | `...Controller` | `..._router` |
| Business rules | `...Service` / `...UseCase` | `...Service` | `..._service` |
| Storage access | `...Repository` | `...Repository` | `..._repository` |
| External system calls | `...Client` / `...Api` | `...Client` | `..._client` |
| Request/response shapes | `...Request` / `...Response` | `...Request` / `...Response` | `...Request` / `...Response` |

### 2.4 Per-language casing
- Flutter/Dart: types `UpperCamelCase`, members `lowerCamelCase`, files `snake_case.dart`, constants also `lowerCamelCase`.
- Spring/Java: types `UpperCamelCase`, members `lowerCamelCase`, constants `UPPER_SNAKE_CASE`, packages lowercase.
- Python: types `UpperCamelCase`, functions and variables `snake_case`, constants `UPPER_SNAKE_CASE`, booleans also start with `is_...` / `has_...`.

---

## 3. Architecture: layers and dependency direction

### 3.1 Four layers (a concept shared by every stack)
```
Presentation           →  Application          →  Domain          ←  Infrastructure
screens·controllers·routers  use cases·services   rules·models       DB·HTTP·files·external APIs
```
- Dependencies point **from outside to inside only**. The domain knows nothing.
- The presentation layer does not call infrastructure (DB, HTTP client) directly. It always goes through the application layer.
- Data crossing a layer is converted to that layer's shape. API response JSON does not travel all the way down to a screen widget.

| Concept | Flutter | Spring | Python (FastAPI) |
|---|---|---|---|
| Presentation | `presentation/pages`, `presentation/widgets` | `controller` | `routers` |
| State | `presentation/providers` (Riverpod) | — | — |
| Application | `domain/usecases` or `application` | `service` | `services` |
| Domain | `domain/models` | `domain` / `entity` | `domain` / `models` |
| Infrastructure | `data/repositories`, `data/sources`, `core/network` | `repository`, `client`, `config` | `repositories`, `clients`, `config` |
| Common | `core/` (config, errors, formatting), `presentation/design/` (design system) | `common/` (responses, exceptions, validation) | `core/` (config, exceptions, logging) |

### 3.2 Cross-cutting concerns live in one place
Do not implement these per screen or per feature. Put them in one common point from the start.
- **Error handling**: `@RestControllerAdvice` in Spring, an exception handler in FastAPI, a network-layer interceptor plus one common error converter in Flutter.
- **Response format**: one shape for success and failure responses.
- **Auth tokens**: attach and refresh them in one place, the HTTP client.
- **Loading / error / empty-state UI**: one common widget reused by every screen.
- **Date, number and time formatting**: one formatter.
- **Logging**: one logger configuration.

### 3.3 Size and responsibility
- A file or class has one responsibility. Over **300 lines**, consider splitting; over 500 lines, always split.
- A function does one thing. If its description needs "and", split it in two.
- Do not put business rules (score calculation, sort criteria, validation) in a screen file. Move them to the application layer.

---

## 4. Design system (stacks with UI)

This is the structure that let the Apple-style redesign change everything at once. All UI code follows it.

1. **Tokens**: define colors, spacing, font sizes, corner radii, shadows and animation durations in one place (`design/tokens`).
   - Define light and dark values together inside the token.
2. **Theme**: combine tokens into light/dark themes. Decide dark mode only through one common getter (for example `context.isDark`).
3. **Components**: UI used 3 or more times, such as buttons, cards, list rows, sheets and logos, becomes a design system component.
4. **Screens** only combine tokens and components.

**Forbidden**
- Do not write color values (`Color(0xFF...)`, `#FFFFFF`, `Colors.white`), numeric spacing (`EdgeInsets.all(13)`) or font sizes directly in screen code. If the token you need does not exist, add the token first.
- Do not load assets (logos, icons) by path directly in screens (`Image.asset('assets/logo.png')`). Go through a component (`AppLogo`).

---

### 4.1 Enforce rules with tests
A rule that exists only in a document will break at least once. When you create a common point, block code that bypasses it with an **architecture rule test**.
- Example: forbid direct use of `showModalBottomSheet(`, `ListTile(`, `Color(0x`, `Image.asset(` in screen (feature) code. Allow only the common components (`showAppBottomSheet`, `GroupedListRow`, tokens, `AppLogo`).
- Exceptions exist only as an **explicit list** inside the test. Each exception gets a comment with the reason.
- Enforce layer dependency direction the same way: ArchUnit for Spring, an import-check test (or import-linter) for Python, a source-scan test for Flutter.
- Thanks to these tests, new screens and features follow the same structure automatically.

### 4.2 Format of an extraction proposal
When you propose extracting common code or refactoring, show it in this order and get approval.
1. **Repeated pattern survey**: what repeats, in how many places, and how the copies differ, with evidence
2. **Layer**: the folder structure for the common code
3. **New common components**: what each one handles in one place
4. **Name table**: current name, new name, what the name alone tells you
5. **Scope**: keep behavior the same and change structure only, using existing tests as the safety net
6. **Rule test**: what to forbid and what to allow as exceptions
7. **Documents**: architecture documents and decision records
8. **Not doing**: state excessive tooling and out-of-scope work

## 5. Brand assets, config and copy: a single source across platforms

If the same logo lives separately in Flutter assets, the iOS launch screen, Android resources, the web, the admin page and store images, you will always miss the rest when you fix one.

- **Keep one source folder** (for example `brand/` at the repo root). Keep the logo sources (transparent background, light and dark), icon sources and color definitions only here.
- Make each platform copy with **a script that generates it from the source**. Never edit copies by hand.
  - Example: `brand/generate_platform_assets.py` → Flutter `assets/`, iOS `LaunchImage` and `AppIcon`, Android `mipmap`, web `favicon`.
- Config values (API address, bundle ID, app name, version) also have one source. Each platform reads that value.
- Legal text (terms of service, privacy policy) and the API contract (request/response shapes, error codes) also have one source. Generate client types from the server's OpenAPI spec.

---

## 6. Constants and magic values
- Give meaningful numbers and strings a named constant (`maximumDailyQuestionCount = 3`).
- Put a constant where its scope fits.
  - Used only inside one class: put it in that class.
  - Used in several places: put it in a common constants file.
  - Used across platforms: put it in the single source from chapter 5.
- Manage string identifiers such as storage keys, event names and route paths in one constants place (`AppRoutes`, `StorageKeys`).

---

## 7. Comments

Comments hold **only the needed information, not prose**. Write them in the project's working language, and end them with a noun phrase or short phrase, not a full sentence (no "This method will ..." style; in Korean, no "~합니다" or "~하기 위해서는" endings).
Skimming the code top to bottom, **the comments alone should show the processing flow**.

### 7.1 Method and class doc comments: a one-line summary
- Say what it does in one line. If there are steps, write the flow with `>`.
- Write conversions and mappings as `input > output`.
```java
/**
 * Grade one answer: validate > run in sandbox > compare results > save score
 */
/**
 * Difficulty code (1, 2, 3) > display name (easy, normal, hard)
 */
/**
 * Clean a value for logging (control chars and non-ASCII > ?, 100-char limit)
 */
```

- Keep class doc comments to two lines. The first line is `target: responsibility1, responsibility2, responsibility3`; the second is one line on how it works.
```java
/**
 * External integration API common: usage condition check, token issue, token validation
 * 3 usage conditions (site, usage option, allowed IPs) > settings read per request
 */
```
- When there are several conditions or targets, give the count and the list: `3 conditions: A, B, C`
- State what it does not do as a scope line: `other states not recorded`

### 7.2 Step comments inside logic: a header per block
- Put a one-line header before each meaningful block. Reading only these in order gives the algorithm.
- **List what it handles** in parentheses.
```java
// Validate request (required fields, allowed characters, size, duplicates)
// Process each item
// Refresh cache once if anything was saved
// Restore backup on failure
```

### 7.3 The meaning of values and codes, right next to them
- Write the meaning of code values, status values and flags in place.
```java
// mode required: 1 practice, 2 exam, 3 all
// is_applied: 1 if used by a policy, otherwise 0
```
- Give constants their purpose and unit: `// maximum upload file size (10MB)`
- Put the unit in the name when possible: `TOKEN_VALID_SECONDS`, `MAX_UPLOAD_BYTES`
- For config key constants, write **where the value lives, what it is, and what its values mean**.
```java
// app_settings: external API enabled (1: on, 0: off)
private static final String SETTING_KEY_EXTERNAL_API_ENABLED = "externalApiEnabled";
// app_settings: allowed caller IPs (comma-separated)
private static final String SETTING_KEY_EXTERNAL_API_ALLOWED_IPS = "externalApiAllowedIps";
private static final String ALLOWED_IP_DELIMITER = ",";
```
- Keep related constants together, side by side (a key, then the delimiter for its value, and so on).
- For paths and formats, give the real shape as an example: `// backup: {home}/backup/{fileName}_{yyyyMMddHHmmss}`

### 7.4 Order and exception conditions
- Note order and conditions such as "always runs" in short parentheses: `(private key first)`, `(success and failure)`, `(recorded even on exception)`.
- Write comparisons as `A <-> B`: `// certificate public key <-> public key computed from the private key`

### 7.5 WHY and linked locations
- Write a reason only when the code alone cannot show it. Even then, one line.
- For values tied to another place that must change together, write that location: `// build.gradle.kts reads this relative to android/app`
- Leave the issue number behind the decision: `(#453)`

### 7.6 Comment problems AI often creates (forbidden)
- **Do not edit or rewrite existing comments on code you did not touch.** Touch only comments attached to code you changed.
- **When you change logic, check the comment above it and the enclosing function's doc comment.** A comment that describes old behavior is worse than none.
- Do not write a multi-line explanation for what fits in one line. If a comment is longer than the code, it is wrong.
- Do not comment every line. Use block headers (7.2) only.
- Do not leave work history in comments: `// previously X, now Y`, `// fixed the old bug`, `// refactored`. History belongs in commits and issues.
- Do not stress the obvious: `// Important!`, `// Note: this function saves the user`.
- Do not end comments in full-sentence style (in Korean, "~합니다/~입니다/~하기 위함" endings).

### 7.7 Comments not to write
- Comments that repeat the name: `// saves the user` above `saveUser()`
- Multi-line explanations, change history, authors, commented-out old code

### 7.8 Log messages
- Write logs in English with a fixed feature prefix: `[question grade] rejected 400 : answer is empty`
- For rejections and failures, include the status code and cause; sanitize external input before putting it in.
- For key changes, log before and after values: `replaced : serial A -> B`

---

## 8. How to spot refactoring targets

When you open a file and see any of the following, it is a refactoring target. Higher rows take priority.

| Signal | Change it like this |
|---|---|
| One method mixes several steps | Split each step into a named private method. The public method shows the flow through step calls alone (`validate > process > result` from 7.1) |
| Validation is scattered through the main logic | Gather it into a validation method at the start. Return immediately on failure (guard clause). Per-item validation returns a failure reason string to log |
| A check returns a boolean, so callers work out again why it was rejected | Make the check method return **a result that carries the rejection reason** (status code, reason enum, reason string). One success, failures distinguished by reason |
| Usage condition or permission checks are copied into several entry points | Gather them into one condition-check method that every entry point (issue, validate, etc.) goes through |
| A condition is so long you have to read it to get its meaning | Extract it into a method with a question-style name: `isValidFileName()`, `isPublicKeyPairMatched()`, `hasReplacedCertificate()` |
| Code-value conversion or mapping exists in several places | Gather it into one conversion method: `toDifficultyLabel(code)` |
| Work that must happen even on failure (audit log, temp file deletion) is only on the success path | Move it to `finally` and note `(success and failure)` in the comment |
| It can fail with only part of the change applied | Write the order explicitly: back up before the change > change > verify > restore on failure |
| External input goes straight into logs, file paths or commands | Route it through sanitize, path-traversal blocking and escaping methods |
| There are meaningful number or string literals | Make them named constants with a purpose and unit comment |
| The same code exists in 3 places | Extract it to a common point (the third principle in chapter 1) |
| Over 300 lines | Split classes by responsibility (3.3) |

Keep behavior the same and change only structure. Use existing tests as the safety net; if there are none, first write a test that pins the current behavior before refactoring.

## 9. Procedure for making changes (Claude Code working rules)

1. **Survey everything first.** Find every copy and every use of what you are fixing.
   - Before creating a new function, widget or class, search for similar names. If one exists, reuse it or fix it.
   - Read the model file of the same layer first (named in `docs/architecture/stacks/<stack>.md`) and follow its shape.
   - Search by the same name, the same value and the same file hash.
   - Do not look only at Flutter screens; include iOS and Android native code, the web, server static resources, store images and documents.
2. **Fix it at the source.** If a common point exists, fix it there. If not, and there are 3 or more uses, create the common point first.
3. **Check names.** Confirm that names you created or touched follow chapter 2 (especially the boolean `is` prefix and no abbreviations).
4. **Run it and look.** Run every affected screen in light and dark, on iOS and Android, and capture it. Passing tests alone does not mean done.
5. **Report remaining copies.** If there are copies you could not fix this time, list their locations in the completion report.

### Pre-completion checklist
- [ ] Comments above the changed logic describe the current behavior (no stale comments)
- [ ] No existing code is similar to what I created (if there is, reuse it)
- [ ] I did not add lines to a frozen list (`docs/architecture/rules/*.allow`)
- [ ] I found every copy and platform of the same target
- [ ] Screen code has no hard-coded colors, spacing or asset paths
- [ ] No code repeated 3 or more times remains
- [ ] Boolean names start with `is/has/can/should`
- [ ] No abbreviations or meaningless names
- [ ] I did not create new files over 300 lines
- [ ] Comments are one-line summaries, step headers and value meanings, not prose
- [ ] The processing flow is visible from the public methods alone (step-by-step private methods)
- [ ] I actually checked it in light and dark and on each platform
