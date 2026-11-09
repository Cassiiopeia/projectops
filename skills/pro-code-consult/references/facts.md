# How to read CLI output

> When to read: when you interpret the JSON returned by `arch_cli.py`. Numbers are candidates; **judge by reading the source.**

## Reading order (scan)

1. **Look at `excluded` first.** Code the repo does not own is already left out: `tooling` (installed files such as `.github/` and `.claude/` — fix them in the upstream repo. Copies of other repos, such as `.template_download_temp/` or a subfolder with its own `.git`, also land here), `generated` (generated-file header markers, gen-l10n), `vendored` (`vendor/`, static JS with a version header, shadcn ui). A `.github/` with its own tests is owned by this repo and stays in the audit (evidence in `owned_tooling`: test count and examples). If something you should look at is mixed in, such as a hand-edited shadcn component, re-run with `scan PATH --all` (items get an `origin` tag and are added to `counts`).
2. **`counts` covers production code only** (plus the included origins with `--all`). Test code is in `test_counts`. Items tagged `origin: "test"` come after production items. Give test names and constants lower priority.
3. **Open items in `review_order` order**: behavior risk > common code and single source > structure > comments > names and tokens. A category with many hits is not necessarily the big problem (3 catches that do not rethrow come before 150 long comments).
4. **Group causes with `hotspots`.** When many categories pile up in one file, that one file is the cause (a candidate for splitting).
5. Lists come worst first; at equal weight they alternate between folders. A category listed in `truncated` was cut off (value = full count). To see more of one category use `--category X --limit 200`; for one folder use `--only app/` (facts to hand to a subagent).

## scan categories

| Category | Meaning | Judgment hints · where false positives appear |
|---|---|---|
| `unhandled_catch` | A catch with a body but no throw, return or raise (`no_rethrow`); a catch-all that rethrows as a different exception (`rewrap_all`) | `no_rethrow`: swallowing inside a transaction is high (only a rollback mark remains and it blows up at commit); continuing the flow after a rollback or compensation is high. `records_failure` (puts the failure in a result list) and `sets_error_state` (screen error state, error callback, notification — normal handling at a UI boundary) are low. The problem is logging only while hiding the failure from the user. `rewrap_all`: normal when `has_passthrough_before` (an earlier catch rethrows business exceptions as is) or when it converts checked → unchecked with no business exception inside the try. `try_body_throws` means an exception is thrown directly inside the try; check first whether it gets lost. It is a problem only when a business exception code thrown inside is lost |
| `test_code_in_production` | test or mock folders under `src/main`, files such as `Test*Controller` | Check in the source whether it is exposed in production (security config, profiles) |
| `swallowed_catch` | Empty catch, `except: pass` | If `has_reason_comment` is true, it may be cleanup code with a stated reason |
| `hardcoded_urls` | `https?://` literals on code lines (schemas, example, localhost, text blocks and `example=` attributes excluded) | Candidates to move to the config source (allowed origins, external service addresses). A public external link in one constant is fine. If they cluster in one file it may be documentation examples, so open the source |
| `lint_disabled_files` | Linting turned off entirely at the file head (disabling a named rule is excluded) | Read the `marker` text. Turning off rules that **report bugs**, such as unreachable branches or duplicate conditions, is high. Unless it is generated code, there is usually no reason to turn it off |
| `bypassed_components` | A common folder (`core`, `design`, `common`, `apis`, etc.) has a file wrapping the same underlying call (`wrappers`), but other places call it directly | Open `wrappers` to confirm it is a real wrapper. If so, the cause is "the common point is not documented" |
| `common_call_candidates` | 3 or more files call the same underlying call directly with no wrapper | Rule-of-three candidates (create a new common point) |
| `duplicate_constants` | Constants with the same value in 2 or more files (strings grouped by value, numbers by name + value) | Config keys and prefixes need a single source even at 2 places. Ignore short strings that are equal by chance |
| `long_files` · `long_functions` | Over 300 lines (over 500 is `must_split_files`) · functions over 60 lines | Data and constant-table files. Function length is approximated from braces and indentation. Markup inflates UI components, so only look at those of 150+ lines or that mix data fetching and error handling |
| `file_type_mismatch` | Dart file name ≠ type name, TSX file name ≠ exported component (case-insensitive) | Bundle files (`_parts`, etc.) and files owned by top-level functions are already excluded |
| `history_comments` | History wording ("previously", "no longer", "used to", "migrated from"; Korean: "기존에는", "옮겼다", "~에서 전환") | Noun-form endings (Korean "삭제함", "deleted"), user and admin actions, and conditionals are already excluded. Explaining migration logic is fine |
| `commented_out_code` | Comment blocks of 3+ lines where 60%+ looks like code | conventions §7.7 "commented-out old code" — delete it |
| `long_comment_blocks` | Comments of 5+ lines. `kind`: `prose` / `api_doc` (doc comments with @param or HTML tags) | `prose` comes first. If `api_doc` is over 80%, it is team culture: summarize it in one line and sample only `prose`. License headers are already excluded |
| `comment_heavy_files` | Comment lines > code lines | `is_declaration_only` (interfaces, abstract classes, `.d.ts`) is often fine |
| `banner_comments` · `prose_ending_comments` | `// ====` decoration · full-sentence endings (Korean "~합니다" style) | Low priority. Banners disappear when you split the file |
| `boolean_functions` | Boolean-returning functions not phrased as questions | override, `exists`/`contains`/`equals`/`matches`, React hooks and function types are already excluded. For action functions that return success, look at the return design (a result carrying the reason) rather than the name |
| `boolean_names` | Booleans without is/has/can/should | `contract` tags (dto, config binding, JPA, serialization) break JSON, config keys or columns if renamed — put them under "needs a migration plan", not "to fix" |
| `abbreviations` · `meaningless_names` | Abbreviated words · bare `data`, `result`, `info`, single-letter local variables | Compounds such as `memberInfo` and `JwtUtil` are allowed (conventions §2.2). Domain terms (`repo` meaning a repository itself) and type names (`class Item`, variable name = type name) are fine. Conventional `result` (AOP, callbacks) is low |
| `hardcoded_tokens` | Direct use of colors, non-zero spacing, font sizes, asset paths | Token and theme files (`*_colors.dart`, `tailwind.config.*`) are excluded. It also flags design components (components must use tokens too) |

## Before trusting totals (check for false-positive clusters)

- If `excluded` lists files dropped as generated or external library code, **open 2–3 of them** and check that the header marker is real. If owned code was dropped, re-run with `scan --all`
- If one category **clusters in one file or folder**, it may be a false-positive cluster (`hotspots`) — compare the first 3 samples with the source before judging the whole category
- `unclassified_directories` (deps) are areas with no layer classification, where **violations hide**. If folder names differ from conventions, understand how the areas are organized first
- If zero rule documents are found, look in README, agent config folders and `docs/` yourself. Check that the documents you find **do not contradict** the code and build config (sometimes the dependency direction is written backwards)

## What scan cannot see (the audit agent checks these directly)

The CLI collects facts with regexes. There are no facts for the items below, so confirm them in the source and note it under "how it was verified" in the report.

- **Security exposure**: whether paths open without auth (permitAll in security config, test APIs) are on in the production profile (with or without a profile restriction), code that disables certificate or hostname verification (trust all certificates), and secrets in code or logs
- **Token and session handling in several places**: whether interceptors, header functions and direct storage access are mixed (`sessionStorage/localStorage` in `bypassed_components` is a hint)
- **Cross-stack drift**: server enum ↔ client constants, API response ↔ hand-written types
- **Near duplicates**: similar components or services that differ only in name (the same code in 3 places)
- **Comment ↔ code mismatch**: during an audit, pick 10 samples and read whether the comment matches the current code
- **Unsupported languages**: the CLI reads only Dart, Java, Kotlin, Python, JS and TS. Other sources (Go, Rust, Swift, C#, PHP, etc.) appear only as file counts in `not_analyzed_languages`. If the count is large, do not read "scan found 0" as "no problems"; sample that code directly
- **Code inside strings**: multi-line strings, text blocks and `example` blocks (scripts in other languages, sample API JSON) are excluded from name, URL and token checks. Look at real problems inside them yourself
- **HTML, CSS and templates**: not scanned. Check inline scripts in admin templates and CSS size yourself
- **Contradictions inside rule documents**, and **which documented rules the existing rule tests do not enforce**

## deps

- `layer_violations`: imports in a forbidden direction. Classification order: Java/Kotlin file suffix (`*Controller`, `*ExceptionHandler` > presentation, `*Repository` > infrastructure, `*Service` > application) > exception and constant folders (`common` — outside the direction rules) > folder name > Next `app/` router (presentation). If folder names differ from conventions, look at the whole picture in `layer_edges` first
- `from_role: "state"`: a Flutter provider or notifier imports the data layer. Whether that is allowed is a team decision (`stacks/flutter.md`)
- `test_violation_count`: number of violations in test files (not listed)
- `cross_module_repository_imports`: direct imports of another Gradle module's Repository. Violation candidates come first in the list, and the summary count covers candidates only
  - `is_to_common_module`: a repository in a common module — usually fine
  - `is_from_aggregator_module`: an application or entry-point module that combines several domains — using domain repositories may be by design. Judge against the repo's module documents and build dependency direction
  - Real candidates are **domain ↔ domain** and **presentation → repository**. If one file injects many repositories from several modules, the problem is too much responsibility rather than boundaries
- `unclassified_directories`: areas with no layer classification (source file count). Reverse imports inside these folders do not appear in `layer_violations`
- `gradle_modules.cycles`: production dependency cycles (test-scope dependencies are in `test_edges`). High if present
- If the repo has an existing layer exception list (`detect.allowlists`), compare against it. Do not report edges the existing mechanism allows as violations

## assets

- Ignored (gitignore) files are not counted (`ignored_assets` is that count). `identical_copies`: the same content in several places. Hand copies across areas come first. `is_generated_icon_set` (flutter_launcher_icons output) and `is_reference_copy` (`docs/`, Figma exports) are low
- `same_name_different_content`: the same name and extension (same pixels for PNG) with different content per area — candidates for **a stale copy where only one side was updated**. Look at these first
- `format_variants`: the same name in different formats, such as svg and png (web font format sets excluded) — one side may be an unused copy (search for references to confirm)

## rule-docs

- `missing_references`: paths not found in the document's folder, any ancestor folder, or by matching the path tail. Look at missing paths that instructions point to (rules that cannot be followed) before old paths in "do not use" lists. `in_code_block` may be a tree diagram or an example
- `ignored_references`: gitignored paths (such as secret config files — it may be normal that they are missing. Check whether the document says so)
- `prose_comment_inducing`: phrases that invite prose comments ("comment every function", "detailed comments"; Korean "주석 필수", "자세히". "WHY 중심" ("focus on WHY") alone matches conventions §7.5 and is not flagged)
- `duplicate_documents`: copies of rule documents with the same content — if only one side is updated, they contradict

## diff · ledger · conventions

- diff: see the table in `references/check.md`. New files are excluded from the stale-comment and rewritten-comment checks
- ledger `check`: per rule, `new` (new violations — fix the code), `fixed` (fixed — remove from the list with `tighten`), `verdict`. `freeze` refuses with `allow_exists` when an `.allow` exists (there is no command that adds lines to the list)
- conventions: `same` · `outdated` (the source changed) · `locally_modified` (the project changed it — respect it as that project's rules) · `missing`
