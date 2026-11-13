# CLI 레퍼런스

`npx projectops`는 기존 프로젝트에 워크플로우, 이슈·PR 템플릿, Agent Skills를 설치하고 업데이트하는 **유일한 공식 경로**입니다. Node.js 20.12 이상만 있으면 별도 설치 없이 실행됩니다. (macOS · Linux · Windows 공통)

## 한눈에 보기

| 하고 싶은 일 | 실행할 것 |
|--------------|-----------|
| 질문에 답하며 설치한다 | `npx projectops` |
| 질문 없이 한 줄로 설치한다 | `npx projectops --mode full --type spring --force` |
| Agent Skills만 설치한다 | `npx projectops --mode skills` |
| 설치 상태를 점검한다 (읽기 전용) | `npx projectops --mode doctor` |
| 모든 옵션을 한 번에 본다 (AI agent용 JSON) | `npx projectops --mode options --json` |

## 대화형 마법사

프로젝트 폴더에서 `npx projectops`만 실행하면 됩니다. 아래는 샘플 Spring 프로젝트에서 **실제로 실행한 화면**입니다.

![npx projectops 대화형 마법사 실행 화면](./images/cli-wizard.ko.gif)

마법사는 이 순서로 묻습니다. 대부분 기본값이 추천값이라 Enter만 눌러도 끝납니다.

| 순서 | 질문 | 무엇을 정하나 |
|------|------|---------------|
| 1 | 무엇을 설치할까요? | 전체 설치, 버전 관리, 워크플로우, 이슈·PR 템플릿, AI 스킬 중 선택 |
| 2 | (자동) 프로젝트 감지 | `build.gradle`, `pubspec.yaml` 같은 마커 파일로 타입(spring, flutter, react 등)과 버전, 브랜치를 알아냅니다 |
| 3 | 프로젝트 성격 | 서버·앱을 배포하는지, 라이브러리를 배포하는지에 따라 이후 질문을 줄입니다 |
| 4 | 실행물 배포 방식 | Docker + SSH 서버 배포(기본), Vercel, 배포 안 함 |
| 5 | PR 댓글 방식 | 변경 요약, 코드 리뷰(CodeRabbit), 둘 다, 사용 안 함 |
| 6 | 개발(릴리스 소스) 브랜치 | 개발을 모아 기본 브랜치로 올리는 브랜치(기본 `develop`). 없으면 만들고 원격 push까지 제안합니다 |
| 7 | Secret 서버 백업 워크플로우 | 포함 여부 |
| 8 | 배포 환경 값 | 서비스 이름, 도메인, JDK 버전 등. "기본값 그대로 전부 설치"를 고를 수 있습니다 |
| 9 | AI 에이전트 스킬 | Claude Code, Cursor, Gemini CLI, Codex CLI, GitHub Copilot, PI에 함께 설치할지 |

선택한 값은 전부 `version.yml`의 `metadata.template.options.*`에 저장되어, 다음 실행(업데이트) 때 다시 묻지 않습니다.

## 한 줄 실행 (비대화형)

CI나 스크립트에서는 `--force`로 모든 확인을 건너뛰고 기본값을 씁니다. 설치가 끝난 뒤 `--mode doctor`로 상태를 확인하는 흐름입니다.

![비대화형 설치와 doctor 진단 실행 화면](./images/cli-oneshot.ko.gif)

```bash
npx projectops --mode full --type spring,react --force
npx projectops --mode workflows --type flutter --paths "flutter=app"
npx projectops --deploy docker-ssh --publish nexus,npm
npx projectops --intent library
```

## 모드

`--mode` 값은 무엇을 설치하느냐를 정합니다. 생략하면 대화형으로 실행됩니다.

| 모드 | 하는 일 |
|------|---------|
| `full` | 워크플로우 + `version.yml` + 이슈·PR 템플릿 + Skills 전체 통합 |
| `version` | `version.yml`만 |
| `workflows` | 워크플로우만 |
| `issues` | 이슈·PR 템플릿만 |
| `skills` | Agent Skills만 |
| `doctor` | 통합 상태와 저장소 설정 진단 (읽기 전용, 아무것도 바꾸지 않음) |

## 옵션

| 옵션 | 설명 |
|------|------|
| `-m, --mode MODE` | 위 모드 중 하나. 기본은 대화형 |
| `-t, --type CSV` | 프로젝트 타입. 예: `spring,react,python`. 지원: `spring` `flutter` `react` `react-native` `react-native-expo` `node` `python` `basic` (`next`는 `react`로 흡수됨 — Next.js는 `react`) |
| `--project-version V` | 통합 대상의 초기 버전(예: `1.0.0`). 생략하면 자동 감지 |
| `--paths "t=p,..."` | 타입별 프로젝트 경로(모노레포). 예: `flutter=app,react=client` |
| `--intent KIND` | 프로젝트 성격: `app` `library` `both` `none` `manual`. 생략하면 `--deploy`/`--publish`에서 추정. `library`/`none`은 배포 질문을, `app`/`none`은 publish 질문을 건너뜁니다 |
| `--deploy TARGET` | 배포 방식 택1: `docker-ssh`(기본) `vercel` `none` |
| `--publish CSV` | publish 대상: `nexus,npm,github-packages` (기본 없음) |
| `--deploy-branch NAME` | 릴리스 PR의 head 브랜치(기본 `develop`). 기본(배포) 브랜치와는 별개입니다 |
| `--deploy-trigger-branch NAME` | push되면 배포 워크플로우가 도는 브랜치. 기본 브랜치와 다를 때만 지정 (기본: 기본 브랜치) |
| `--create-development-branch` | 비대화형 실행에서 개발 브랜치가 없으면 기본 브랜치에서 만들고 origin에 push. 이미 있으면 아무것도 하지 않고, push 때 자격 증명을 묻지 않아 로그인이 필요한 원격이면 기다리지 않고 바로 실패하며, push가 실패해도 실행은 계속되고 직접 실행할 명령을 안내합니다 (기본 꺼짐) |
| `--secret-backup` / `--no-secret-backup` | Secret 백업 워크플로우 포함 / 제외 |
| `--ai-summary` / `--no-ai-summary` | PR 변경 요약 워크플로우 포함 / 제외 |
| `--coderabbit` / `--no-coderabbit` | CodeRabbit PR 코드 리뷰 설정(`.coderabbit.yaml`) 설치 (`--mode full` 에서만). CodeRabbit GitHub 앱이 따로 필요하고, 이미 있는 파일은 `.bak` 으로 백업하고 덮어쓴다. 생략하면 꺼짐(`version.yml` 에 켜짐이 저장돼 있으면 유지). 릴리스 노트와는 무관 |
| `--projects-sync` / `--no-projects-sync` | GitHub Projects 상태 동기화 워크플로우 포함 / 제외 (신규 설치 기본 제외, 이미 설치돼 있으면 유지) |
| `--ci-minutes-saver` / `--no-ci-minutes-saver` | 비공개 레포의 Actions 사용 시간 절약: CI는 PR에서만 돌고 문서만 바뀐 변경은 건너뜀. iOS 빌드·Secret 백업은 수동 실행에서만 (기본 꺼짐) |
| `--language LANG` | 레포에 쓰이는 이슈/PR 템플릿·봇 문구 언어: `en` `ko`. 신규 설치 기본 `en`, 기존 설치는 저장값(없으면 `ko`) |
| `--label-style STYLE` | 상태 라벨 표기: `en`(`status: todo`) `ko`(기존 `작업전`). 신규 설치 기본 `en` |
| `--lang LANG` | **CLI 화면** 언어: `en` `ko`. 레포에 쓰이는 문구(`--language`)와 다르다. 기본은 시스템 언어, CI·`--force` 에서는 `en` |
| `--remove-legacy` | 은퇴한 구세대 배포 워크플로우를 `.bak`으로 치움 (기본은 목록·삭제 명령만 안내) |
| `--json` | `--mode options`와 함께 — 사람이 아닌 기계가 읽는 JSON 출력 |
| `--force`, `-y`, `--yes` | 모든 확인을 생략하고 비대화형 기본값 사용 |
| `-v, --version` | projectops 버전 출력 |
| `-h, --help` | 도움말 |

`--nexus`, `--npm-publish`(와 `--no-nexus`, `--no-npm-publish`)는 더 이상 쓰지 않는 옵션입니다. 각각 `--publish nexus`, `--publish npm`을 쓰세요.

> 모바일 앱 타입(`flutter`, `react-native`, `react-native-expo`)은 스토어 배포 워크플로우가 타입에 이미 포함돼 있어서 배포·publish 질문 자체를 건너뜁니다. 자세한 규칙은 [NPX 마법사 가이드](./NPX-WIZARD.md)를 보세요.

## 전체 옵션 레퍼런스

모든 플래그와 `version.yml` 키를 값·기본값과 함께 정리한 표입니다.
`src/core/options-schema.js`에서 생성합니다. `npx projectops --mode options --json`과 같은 원본입니다.
원본 설명이 영어라 아래 표도 영어입니다. 원본을 고치면 `node scripts/build_options_reference.mjs`로 다시 만듭니다.

<!-- generated: options -->
<!-- Do not edit by hand. Source: src/core/options-schema.js. Rebuild: node scripts/build_options_reference.mjs -->

### CLI flags

| Flag | `version.yml` key | Values / default | Description |
|---|---|---|---|
| `-m`, `--mode MODE` |  | values: `interactive` `full` `version` `workflows` `issues` `skills` `doctor` `options`; default: interactive | What to do. Agents and CI should always pass an explicit non-interactive mode together with --force. |
| `-t`, `--type CSV` |  | values: `spring` `flutter` `react` `react-native` `react-native-expo` `node` `python` `basic`; default: auto-detected | Project types, comma separated. The first one is the primary type. |
| `--project-version VERSION` |  | default: auto-detected | Initial version of the target project (x.y.z). |
| `--paths type=path,...` | `project_paths` | default: repo root | Per-type project folders for monorepos, e.g. flutter=app,react=client. |
| `--intent KIND` | `metadata.template.options.intent` | values: `app` `library` `both` `none` `manual`; default: inferred from --deploy/--publish | Project kind. Decides whether deploy and publish questions are asked. |
| `--deploy TARGET` | `metadata.template.options.deploy` | values: `docker-ssh` `vercel` `none`; default: docker-ssh | Where the app is deployed. Pick one. |
| `--publish CSV` | `metadata.template.options.publish` | values: `nexus` `npm` `github-packages`; default: none | Registries a library is published to. Several allowed. |
| `--deploy-branch NAME` | `metadata.development_branch` | default: develop | Development branch: the head of the release PR. Not the repository default branch. |
| `--deploy-trigger-branch NAME` | `metadata.template.options.deploy_trigger_branch` | default: the default branch | Branch whose push runs the deploy workflows. Only when it differs from the default branch. |
| `--create-development-branch` |  | default: off | Non-interactive runs: create the development branch from the default branch and push it to origin when it does not exist. |
| `--language LANG` | `metadata.template.options.language` | values: `en` `ko`; default: en for new installs, ko for existing installs | Language of issue/PR templates and bot messages written into the repo. |
| `--label-style STYLE` | `metadata.template.options.label_style` | values: `en` `ko`; default: en for new installs, ko for existing installs | Status label names: en = 'status: todo', ko = legacy Korean names. |
| `--secret-backup`, `--no-secret-backup` | `metadata.template.options.secret_backup` | default: excluded | Include / exclude the workflow that uploads GitHub Secrets to a server over SSH. |
| `--ai-summary`, `--no-ai-summary` | `metadata.template.options.code_review.ai_summary` | default: included | Include / exclude the workflow that comments an AI summary on work PRs. |
| `--coderabbit`, `--no-coderabbit` | `metadata.template.options.code_review.coderabbit` | default: off unless version.yml already says on | Install the CodeRabbit code review config (.coderabbit.yaml). Only --mode full installs it. |
| `--projects-sync`, `--no-projects-sync` | `metadata.template.options.projects_sync` | default: excluded for new installs; kept if already installed | Include / exclude the GitHub Projects status sync workflow. Needs a PAT secret and PROJECT_URL variable. |
| `--ci-minutes-saver`, `--no-ci-minutes-saver` | `metadata.template.options.ci_minutes_saver` | default: off | Cut GitHub Actions minutes for private repos: CI runs on PRs only and skips docs-only changes, the iOS (macOS) CI build runs only on manual dispatch, secret backup runs only on manual dispatch. |
| `--remove-legacy` |  | default: off | Rename retired old-generation workflows to .bak. Without it they are only listed in the summary and in doctor. |
| `-y`, `--yes`, `--force` |  | default: off | Skip every confirmation and use non-interactive defaults. Required for agents and CI. |
| `--lang LANG` |  | values: `en` `ko`; default: system language; pinned to en in CI and with --force | Language of the CLI screen. Not the language written into the repo (that is --language). |
| `--json` |  | default: off | With --mode options: print machine-readable JSON instead of a table. |
| `-v`, `--version` |  |  | Print the projectops package version and exit. |
| `-h`, `--help` |  |  | Print the human-readable help and exit. |
| `--nexus`, `--no-nexus` |  |  | (deprecated) Use --publish nexus. Also implies --deploy none. |
| `--npm-publish`, `--no-npm-publish` |  |  | (deprecated) Use --publish npm. |

### `version.yml` keys

| Key | Type | Values / default | Set by | Description |
|---|---|---|---|---|
| `version` | string |  | workflow-managed | Project version (x.y.z). The single source of truth; workflows sync it into build files. |
| `version_code` | integer |  | workflow-managed | App build number. +1 on every release. Android release only; iOS and test builds use build_number.py. |
| `project_types` | string[] |  | wizard | Project types; the first is primary. Do not change after setup. |
| `project_paths` | map |  | wizard (--paths) | Per-type project folder relative to the repo root (monorepo). |
| `metadata.default_branch` | string | default: main | wizard | Repository default (production) branch. Pushes here deploy. |
| `metadata.development_branch` | string | default: develop | wizard (--deploy-branch) | Development branch: head of the release PR. Old name deploy_branch is still read and written with the same value. |
| `metadata.template.options.intent` | enum | values: `app` `library` `both` `none` `manual` | wizard (--intent) | Project kind; derives the deploy and publish questions. |
| `metadata.template.options.deploy` | enum | values: `docker-ssh` `vercel` `none`; default: docker-ssh | wizard (--deploy) | Where the app is deployed. |
| `metadata.template.options.publish` | enum[] | values: `nexus` `npm` `github-packages`; default: `[]` | wizard (--publish) | Library registries. |
| `metadata.template.options.secret_backup` | boolean | default: `false` | wizard (--secret-backup) | Secret-to-server upload workflow installed. |
| `metadata.template.options.semver_auto` | boolean | default: `true` | by hand | Decide the release bump from commit titles: 'type!:' = major, 'feat:' = minor, anything else = patch. Applies both to the release PR and to direct pushes to the default branch. |
| `metadata.template.options.close_on_release` | boolean | default: true for new installs; missing for existing installs | by hand | A release merge closes issues that carry the done label and are referenced by a release commit. |
| `metadata.template.options.language` | enum | values: `en` `ko` | wizard (--language) | Issue/PR template and bot message language. |
| `metadata.template.options.deploy_trigger_branch` | string | default: the default branch | wizard (--deploy-trigger-branch) | Branch whose push runs the deploy workflows (app store, server, package publish). |
| `metadata.template.options.ci_minutes_saver` | boolean | default: `false` | wizard (--ci-minutes-saver) | Install the CI workflows in their Actions-minutes-saving form (PR-only CI, docs-only changes skipped, iOS CI build and secret backup on manual dispatch only). |
| `metadata.template.options.label_style` | enum | values: `en` `ko` | wizard (--label-style) | Status label names. |
| `metadata.template.options.projects_sync` | boolean |  | wizard (--projects-sync) | Projects status sync workflow installed. |
| `metadata.template.options.app_release` | boolean |  | by hand | Releases go through App Store / Play Store review. Release notes get a review warning banner. Never auto-enabled. |
| `metadata.template.options.excluded_workflows` | string[] |  | by hand | Workflow file names the update must never install. Deleted files are also not restored; a copy is kept in .github/.projectops/incoming/. |
| `metadata.template.options.store_locales` | string[] |  | by hand | Store release-note languages, first is the default (for example ["ko-KR", "en-US", "ja-JP", "zh-CN"]). Missing = one text for every store language, as before. Per-language text comes from store_notes in CHANGELOG.json; a language without text gets the default-language text (the stores reject an empty What's New). |
| `metadata.template.options.store_locales_ios` | string[] |  | by hand | Only when the App Store languages differ from store_locales: the App Store uses this list instead. fastlane deliver ACTIVATES every language folder the app version does not have yet, so a language the App Store listing lacks must not be in this list. |
| `metadata.template.options.store_locales_play` | string[] |  | by hand | Only when the Play languages differ from store_locales: Google Play uses this list instead. |
| `metadata.template.options.code_review.coderabbit` | boolean |  | wizard | CodeRabbit config installed. |
| `metadata.template.options.code_review.ai_summary` | boolean | default: `true` | wizard (--ai-summary) | AI PR summary workflow installed. |
| `metadata.template.options.changelog.provider` | enum | values: `copilot` `coderabbit` `openai` `gemini` `claude` `groq` `mistral` `ollama` `commit`; default: commit | by hand | Release note generator. 'commit' is free and always works; AI keys are picked up automatically when registered as secrets. |
| `metadata.template.options.changelog.base_url` | string |  | by hand | Only for provider ollama. |

<!-- /generated -->

## 진단 — `doctor`

`--mode doctor`는 파일을 쓰지 않고 상태만 점검합니다.

- 이 폴더에 템플릿이 설치돼 있는지, 설치된 워크플로우가 몇 개인지
- 치환되지 않은 값(`__APPLICATION_YML_DIR__` 같은 자리)이 남아 배포 때 실패할 곳은 없는지
- 자동으로 실행되는(push, 라벨 등) 워크플로우에 예시 값(`your-...`, `example.com`)이 남아 실행될 때마다 실패할 곳은 없는지
- 설치된 워크플로우가 요구하는 Secret 목록
- 워크플로우 `permissions` 선언 여부

`GITHUB_TOKEN` 환경변수를 주면 저장소 설정(권한, 머지 방식, Secret)까지 점검합니다.

```bash
GITHUB_TOKEN=ghp_... npx projectops --mode doctor
```

## 다시 실행하면 (업데이트)

이미 통합한 프로젝트에서 다시 실행하면 업데이트로 동작합니다.

- **내가 고친 워크플로우는 덮어쓰지 않습니다.** 건너뛰고, 새 템플릿을 `.github/.projectops/incoming/`에 저장한 뒤 비교 명령을 안내합니다.
- **실행 기록이 남습니다.** `.github/.projectops/logs/`에 로그와 이벤트, 마이그레이션 가이드가 쌓이고 이 폴더는 git 추적에서 자동으로 제외됩니다. 문제가 생기면 AI 에이전트에게 "실행 로그 확인해줘"라고 요청하면 됩니다.
- 이름이 바뀐 옛 워크플로우는 자동으로 정리됩니다. 자세한 정책은 [NPX 마법사 가이드](./NPX-WIZARD.md)의 마이그레이션 절을 보세요.

> 구 `template_integrator.sh` / `.ps1`은 지원이 종료되어 저장소에서 제거됐습니다. `npx projectops`를 쓰세요. ([상세](./TEMPLATE-INTEGRATOR.md))
