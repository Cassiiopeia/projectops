// projectops 옵션 정본 (AI agent·사람·문서가 같은 표를 본다).
//
// 왜 필요한가: 옵션 설명이 문서 6곳(NPX-WIZARD, VERSION-CONTROL, ISSUE-AUTOMATION ...)에 흩어져 있어
// agent가 "이 옵션이 있나, 기본값이 뭔가"를 확인하려면 문서를 뒤져야 했다. 이제 한 호출로 읽는다:
//   npx projectops --mode options --json
//
// 이 표는 손으로 쓰되, test/options-schema.test.js 가 실제 코드와 대조한다.
//   - args.js 의 모든 CLI 플래그가 flags 에 있어야 한다
//   - parseTemplateOptions 가 읽는 모든 키가 versionYml 에 있어야 한다
// 새 플래그·옵션을 추가하고 여기에 안 쓰면 테스트가 실패한다.
//
// 설명은 영문이다 — 기계가 읽는 표이고, 화면 언어(i18n)와 무관하게 같아야 한다.

import { DEPLOY_TARGETS, PUBLISH_TARGETS, INTENT_VALUES, LABEL_STYLES, CHANGELOG_PROVIDERS } from "./constants.js";
import { REPO_LANGUAGES } from "./repo-language.js";
import { VALID_TYPES } from "../context.js";
import { SUPPORTED_LANGS } from "../i18n/index.js";

export const SCHEMA_VERSION = 1;

export const MODES = [
  { name: "interactive", description: "Default. Asks questions in the terminal. Do not use from an agent or CI." },
  { name: "full", description: "Install everything: version.yml, workflows, scripts, templates, setup guide." },
  { name: "version", description: "Only version.yml, README version section and version scripts." },
  { name: "workflows", description: "Only GitHub Actions workflows (+ scripts, config, util). Existing version.yml is kept." },
  { name: "issues", description: "Only issue and discussion templates." },
  { name: "skills", description: "Install or update agent skills for supported IDEs." },
  { name: "doctor", description: "Read-only diagnosis of the install and repository settings. Safe to run any time." },
  { name: "options", description: "Print this option table (add --json for machine-readable output). Read-only, no network." },
];

// 프로젝트 타입은 context.js 의 VALID_TYPES 와 같아야 한다 (테스트가 대조).
export const FLAGS = [
  { flag: "--mode", alias: "-m", value: "MODE", values: MODES.map((m) => m.name), default: "interactive",
    description: "What to do. Agents and CI should always pass an explicit non-interactive mode together with --force." },
  { flag: "--type", alias: "-t", value: "CSV", default: "auto-detected",
    description: "Project types, comma separated. The first one is the primary type.",
    values: [...VALID_TYPES] },
  { flag: "--project-version", value: "VERSION", default: "auto-detected",
    description: "Initial version of the target project (x.y.z)." },
  { flag: "--paths", value: "type=path,...", default: "repo root",
    description: "Per-type project folders for monorepos, e.g. flutter=app,react=client.", versionYml: "project_paths" },
  { flag: "--intent", value: "KIND", values: [...INTENT_VALUES], default: "inferred from --deploy/--publish",
    description: "Project kind. Decides whether deploy and publish questions are asked.", versionYml: "metadata.template.options.intent" },
  { flag: "--deploy", value: "TARGET", values: [...DEPLOY_TARGETS], default: "docker-ssh",
    description: "Where the app is deployed. Pick one.", versionYml: "metadata.template.options.deploy" },
  { flag: "--publish", value: "CSV", values: [...PUBLISH_TARGETS], default: "none",
    description: "Registries a library is published to. Several allowed.", versionYml: "metadata.template.options.publish" },
  { flag: "--deploy-branch", value: "NAME", default: "develop",
    description: "Development branch: the head of the release PR. Not the repository default branch.", versionYml: "metadata.deploy_branch" },
  { flag: "--language", value: "LANG", values: [...REPO_LANGUAGES], default: "en for new installs, ko for existing installs",
    description: "Language of issue/PR templates and bot messages written into the repo.", versionYml: "metadata.template.options.language" },
  { flag: "--label-style", value: "STYLE", values: [...LABEL_STYLES], default: "en for new installs, ko for existing installs",
    description: "Status label names: en = 'status: todo', ko = legacy Korean names.", versionYml: "metadata.template.options.label_style" },
  { flag: "--secret-backup", negation: "--no-secret-backup",
    description: "Include / exclude the workflow that uploads GitHub Secrets to a server over SSH.", default: "excluded",
    versionYml: "metadata.template.options.secret_backup" },
  { flag: "--ai-summary", negation: "--no-ai-summary",
    description: "Include / exclude the workflow that comments an AI summary on work PRs.", default: "included",
    versionYml: "metadata.template.options.code_review.ai_summary" },
  { flag: "--coderabbit", negation: "--no-coderabbit",
    description: "Install the CodeRabbit code review config (.coderabbit.yaml). Only --mode full installs it.",
    default: "off unless version.yml already says on", versionYml: "metadata.template.options.code_review.coderabbit" },
  { flag: "--projects-sync", negation: "--no-projects-sync",
    description: "Include / exclude the GitHub Projects status sync workflow. Needs a PAT secret and PROJECT_URL variable.",
    default: "excluded for new installs; kept if already installed", versionYml: "metadata.template.options.projects_sync" },
  { flag: "--remove-legacy",
    description: "Rename retired old-generation workflows to .bak. Without it they are only listed in the summary and in doctor.", default: "off" },
  { flag: "--force", alias: "-y", aliases: ["-y", "--yes"], description: "Skip every confirmation and use non-interactive defaults. Required for agents and CI.", default: "off" },
  { flag: "--lang", value: "LANG", values: [...SUPPORTED_LANGS], default: "system language; pinned to en in CI and with --force",
    description: "Language of the CLI screen. Not the language written into the repo (that is --language)." },
  { flag: "--json", description: "With --mode options: print machine-readable JSON instead of a table.", default: "off" },
  { flag: "--version", alias: "-v", description: "Print the projectops package version and exit." },
  { flag: "--help", alias: "-h", description: "Print the human-readable help and exit." },
  // 지원 종료 예정 — 새 설정에는 쓰지 않는다
  { flag: "--nexus", negation: "--no-nexus", deprecated: "Use --publish nexus. Also implies --deploy none." },
  { flag: "--npm-publish", negation: "--no-npm-publish", deprecated: "Use --publish npm." },
];

// version.yml 의 키. path 는 파일 안의 위치, parserKey 는 parseTemplateOptions 가 돌려주는 이름.
export const VERSION_YML = [
  { path: "version", type: "string", description: "Project version (x.y.z). The single source of truth; workflows sync it into build files.", edit: "workflow-managed" },
  { path: "version_code", type: "integer", description: "App build number. +1 on every release. Android release only; iOS and test builds use build_number.py.", edit: "workflow-managed" },
  { path: "project_types", type: "string[]", description: "Project types; the first is primary. Do not change after setup.", edit: "wizard" },
  { path: "project_paths", type: "map", description: "Per-type project folder relative to the repo root (monorepo).", edit: "wizard (--paths)" },
  { path: "metadata.default_branch", type: "string", default: "main", description: "Repository default (production) branch. Pushes here deploy.", edit: "wizard" },
  { path: "metadata.deploy_branch", parserKey: "deployBranch", type: "string", default: "develop",
    description: "Development branch: head of the release PR. Despite the name it is NOT where deploys run.", edit: "wizard (--deploy-branch)" },
  { path: "metadata.template.options.intent", parserKey: "intent", type: "enum", values: [...INTENT_VALUES],
    description: "Project kind; derives the deploy and publish questions.", edit: "wizard (--intent)" },
  { path: "metadata.template.options.deploy", parserKey: "deploy", type: "enum", values: [...DEPLOY_TARGETS], default: "docker-ssh",
    description: "Where the app is deployed.", edit: "wizard (--deploy)" },
  { path: "metadata.template.options.publish", parserKey: "publish", type: "enum[]", values: [...PUBLISH_TARGETS], default: [],
    description: "Library registries.", edit: "wizard (--publish)" },
  { path: "metadata.template.options.secret_backup", parserKey: "secretBackup", type: "boolean", default: false,
    description: "Secret-to-server upload workflow installed.", edit: "wizard (--secret-backup)" },
  { path: "metadata.template.options.semver_auto", parserKey: "semverAuto", type: "boolean",
    default: true,
    description: "Decide the release bump from commit titles: 'type!:' = major, 'feat:' = minor, anything else = patch. Applies both to the release PR and to direct pushes to the default branch.",
    edit: "by hand" },
  { path: "metadata.template.options.close_on_release", parserKey: "closeOnRelease", type: "boolean", default: "true for new installs; missing for existing installs",
    description: "A release merge closes issues that carry the done label and are referenced by a release commit.", edit: "by hand" },
  { path: "metadata.template.options.language", parserKey: "language", type: "enum", values: [...REPO_LANGUAGES], description: "Issue/PR template and bot message language.", edit: "wizard (--language)" },
  { path: "metadata.template.options.label_style", parserKey: "labelStyle", type: "enum", values: [...LABEL_STYLES], description: "Status label names.", edit: "wizard (--label-style)" },
  { path: "metadata.template.options.projects_sync", parserKey: "projectsSync", type: "boolean", description: "Projects status sync workflow installed.", edit: "wizard (--projects-sync)" },
  { path: "metadata.template.options.app_release", parserKey: "appRelease", type: "boolean",
    description: "Releases go through App Store / Play Store review. Release notes get a review warning banner. Never auto-enabled.", edit: "by hand" },
  { path: "metadata.template.options.excluded_workflows", parserKey: "excludedWorkflows", type: "string[]",
    description: "Workflow file names the update must never install. Deleted files are also not restored; a copy is kept in .github/.projectops/incoming/.",
    edit: "by hand" },
  { path: "metadata.template.options.store_locales", parserKey: "storeLocales", type: "string[]",
    description: "Store release-note languages, first is the default (for example [\"ko-KR\", \"en-US\", \"ja-JP\", \"zh-CN\"]). Missing = one text for every store language, as before. Per-language text comes from store_notes in CHANGELOG.json; a language without text gets the default-language text (the stores reject an empty What's New).",
    edit: "by hand" },
  { path: "metadata.template.options.store_locales_ios", parserKey: "storeLocalesIos", type: "string[]",
    description: "Only when the App Store languages differ from store_locales: the App Store uses this list instead. fastlane deliver ACTIVATES every language folder the app version does not have yet, so a language the App Store listing lacks must not be in this list.",
    edit: "by hand" },
  { path: "metadata.template.options.store_locales_play", parserKey: "storeLocalesPlay", type: "string[]",
    description: "Only when the Play languages differ from store_locales: Google Play uses this list instead.",
    edit: "by hand" },
  { path: "metadata.template.options.code_review.coderabbit", parserKey: "codeReviewCoderabbit", type: "boolean", description: "CodeRabbit config installed.", edit: "wizard" },
  { path: "metadata.template.options.code_review.ai_summary", parserKey: "aiPrSummary", type: "boolean", default: true, description: "AI PR summary workflow installed.", edit: "wizard (--ai-summary)" },
  { path: "metadata.template.options.changelog.provider", parserKey: "changelogProvider", type: "enum",
    values: [...CHANGELOG_PROVIDERS], default: "commit",
    description: "Release note generator. 'commit' is free and always works; AI keys are picked up automatically when registered as secrets.", edit: "by hand" },
  { path: "metadata.template.options.changelog.base_url", parserKey: "changelogBaseUrl", type: "string", description: "Only for provider ollama.", edit: "by hand" },
];

// ── agent 가 읽고 스스로 판단하게 하는 상세 설명 ───────────────────────────────────────────────
// 짧은 description 만으로는 "언제 쓰나 · 쓰면 레포에서 정확히 무엇이 바뀌나 · 안 쓰면 어떻게 되나"를 알 수 없다.
// 사람 없이 이 CLI 를 부르는 AI agent 가 추측하지 않도록 항목마다 적는다.
//   when    : 이 값을 직접 정해야 하는 상황 / 그냥 둬도 되는 상황
//   effect  : 레포에서 실제로 바뀌는 것 (어떤 파일이 생기고 사라지는지, 어떤 워크플로가 도는지)
//   omitted : 안 주면 어떻게 정해지는가
//   example : 그대로 실행할 수 있는 명령
//   caution : 되돌리기 어렵거나 놓치기 쉬운 것
// test/options-schema.test.js 가 모든 (폐기 아닌) 플래그·옵션에 when·effect 가 있는지 검사한다 — 새 항목은 여기에도 적는다.
export const FLAG_DETAILS = {
  "--mode": {
    when: "Always pass it explicitly from an agent or CI. Without it the CLI opens interactive questions.",
    effect: "Chooses which parts are installed. full = everything; workflows = only .github/workflows (+ scripts, config, util); version = only version.yml + README version section; issues = only issue/PR templates; skills = IDE agent skills; doctor and options never write anything.",
    omitted: "interactive: asks questions in the terminal and fails without a TTY.",
    example: "npx projectops --mode full --force",
    caution: "Any mode other than interactive decides every option from flags, version.yml and defaults — it does not ask. Without a TTY, --force is also required.",
  },
  "--type": {
    when: "Pass it when auto-detection is wrong or the repo has several stacks (a monorepo).",
    effect: "Selects which project-types/<type>/ workflows are installed and which build file version_manager keeps in sync (pubspec.yaml, package.json, build.gradle, pyproject.toml ...).",
    omitted: "Detected from marker files in the repo root (pubspec.yaml → flutter, build.gradle → spring, package.json → node/react ...). Nothing detected → basic (version.yml only).",
    example: "npx projectops --mode full --force --type spring,react",
    caution: "The first type is the primary one. Do not change types after setup.",
  },
  "--project-version": {
    when: "Only for a repo that has no version.yml yet and where the detected version is wrong.",
    effect: "Sets the starting version written into version.yml.",
    omitted: "Read from the build file (pubspec.yaml, package.json ...); an existing version.yml value is always kept.",
    example: "npx projectops --mode full --force --project-version 1.0.0",
  },
  "--paths": {
    when: "Monorepos where a stack lives in a subfolder (app/, client/ ...).",
    effect: "Writes project_paths into version.yml; version_manager then syncs the version file inside that folder and workflow path filters point at it.",
    omitted: "Every type is assumed to be at the repo root.",
    example: 'npx projectops --mode full --force --type flutter,react --paths "flutter=app,react=client"',
    caution: "Each folder must exist inside the repo. Absolute paths and '..' are rejected.",
  },
  "--intent": {
    when: "Rarely needed. It only matters for interactive questions and for deriving --deploy / --publish.",
    effect: "app → deploy asked, publish skipped; library → publish asked, deploy forced to none; both → both asked; none → neither; manual → both asked one by one. Stored as options.intent.",
    omitted: "Inferred from --deploy and --publish (or from the stored version.yml values).",
    example: "npx projectops --mode full --force --intent library --publish npm",
  },
  "--deploy": {
    when: "Set it when the app is deployed by this repo. Library repos use --publish instead.",
    effect: "docker-ssh installs the SSH + Docker server deploy workflows (SIMPLE-CICD, NONSTOP-*, PR-PREVIEW for spring/python; CICD for react). vercel installs the Vercel deploy workflow. none installs no deploy workflow. Mobile types (flutter, react-native*) ignore it — their store deploy workflows are part of the type.",
    omitted: "docker-ssh for server stacks, none for mobile apps and library repos.",
    example: "npx projectops --mode full --force --type spring --deploy vercel",
    caution: "docker-ssh workflows need server secrets (SERVER_HOST, SERVER_USER, SERVER_PASSWORD or SSH_KEY, DOCKERHUB_*). Until they are registered the workflows fail — the completion summary lists the missing secrets.",
  },
  "--publish": {
    when: "Set it when the repo is a library published to a package registry.",
    effect: "nexus installs NEXUS-CI and NEXUS-PUBLISH (spring); npm installs NODE-NPM-PUBLISH (needs NPM_TOKEN); github-packages installs GITHUB-PACKAGES-PUBLISH (spring). Several values are allowed.",
    omitted: "No publish workflow.",
    example: "npx projectops --mode workflows --force --type node --publish npm",
  },
  "--deploy-branch": {
    when: "Only if your development branch is not named develop.",
    effect: "Writes metadata.deploy_branch and rewrites the branch name inside the installed workflows (release PR head, CI triggers, PR summary base). The branch is NOT created by this flag.",
    omitted: "develop.",
    example: "npx projectops --mode full --force --deploy-branch dev",
    caution: "Despite the name this is the development branch (head of the release PR), not the branch that deploys. The deploying branch is the repository default branch.",
  },
  "--language": {
    when: "Set it only to change the language of an existing repo or to start a new repo in Korean.",
    effect: "Chooses the language of the issue/PR templates and bot comments written into the repo, and of the comments inside version.yml.",
    omitted: "New installs: en. Existing installs keep the stored value (ko if none was stored).",
    example: "npx projectops --mode full --force --language ko",
    caution: "This is not the language of the CLI screen — that is --lang.",
  },
  "--label-style": {
    when: "Only when the repo already uses one label naming and you must keep it.",
    effect: "Writes the label definitions (.github/config/issue-labels.yml) and the label names used inside the installed workflows in that style: en = 'status: todo', 'status: done'; ko = the legacy Korean names (작업전, 작업완료). Workflows and skills accept both. Labels are created in GitHub by running the PROJECT-COMMON-SYNC-ISSUE-LABELS workflow once.",
    omitted: "New installs: en. Existing installs keep ko unless a value is stored.",
    example: "npx projectops --mode full --force --label-style ko",
  },
  "--secret-backup": {
    when: "Only if you want GitHub Secrets copied to your own server over SSH.",
    effect: "Installs PROJECT-COMMON-SECRET-FILE-UPLOAD, which runs on pushes to the development branch and needs SERVER_HOST, SERVER_USER and SERVER_PASSWORD.",
    omitted: "Not installed.",
    example: "npx projectops --mode workflows --force --secret-backup",
  },
  "--ai-summary": {
    when: "Leave the default unless you want no automatic PR comment.",
    effect: "Installs PROJECT-COMMON-AI-PR-SUMMARY, which comments a change summary on work PRs into the development branch. It works with no extra setup; registering an AI key (GEMINI_API_KEY, GROQ_API_KEY, ...) makes the wording better.",
    omitted: "Installed (or kept as stored).",
    example: "npx projectops --mode workflows --force --no-ai-summary",
  },
  "--coderabbit": {
    when: "Pass --coderabbit only if the team uses CodeRabbit for pull request code review.",
    effect: "Copies .coderabbit.yaml to the repo root. Only --mode full installs it. If the file already exists it is overwritten and the old one is saved as .coderabbit.yaml.bak. This is the PR review bot only; release notes are generated separately (PR body → AI key → commit analysis) and do not need it.",
    omitted: "Off, unless version.yml already stores code_review.coderabbit: true (a stored choice is kept). The wizard asks interactively; non-interactive runs never turn it on by themselves.",
    example: "npx projectops --mode full --force --coderabbit",
    caution: "CodeRabbit needs its GitHub app installed and granted access to the repo (https://coderabbit.ai). Without the app the file does nothing and no review comments appear.",
  },
  "--projects-sync": {
    when: "Only if the repo uses a GitHub Projects board whose Status column should follow issue labels.",
    effect: "Installs PROJECT-COMMON-PROJECTS-SYNC-MANAGER. It needs the secret _GITHUB_PAT_TOKEN and the repository variable PROJECT_URL; without them it fails on every label change.",
    omitted: "Not installed for new installs; kept if it is already installed.",
    example: "npx projectops --mode workflows --force --projects-sync",
  },
  "--remove-legacy": {
    when: "After an update printed 'retired workflows are still installed' (or doctor listed them) and the new workflow is working.",
    effect: "Renames retired old-generation workflows (for example PROJECT-SPRING-SYNOLOGY-*, PROJECT-COMMON-RELEASE-PUBLISH) to *.yaml.bak so they stop running. Delete the .bak to restore.",
    omitted: "Retired workflows are left in place and only listed in the completion summary and in doctor. Plain renames that have an identical replacement are neutralised automatically; deploy pipelines are never touched without this flag.",
    example: "npx projectops --mode workflows --force --remove-legacy",
    caution: "Old deploy workflows may be the repo's only live deployment. Check that the replacement works first.",
  },
  "--force": {
    when: "Always, from an agent or CI.",
    effect: "Skips every confirmation (including the breaking-changes warning) and uses defaults for anything not given as a flag. Files you modified are NOT overwritten: they are kept and a copy of the new template is saved in .github/.projectops/incoming/ for you to diff.",
    omitted: "Confirmation prompts appear when a TTY is attached; without a TTY the command stops with an error asking for --force.",
    example: "npx projectops --mode workflows --force",
    caution: "Idempotent: running it again changes nothing that is already current.",
  },
  "--lang": {
    when: "Rarely. Only to force the language of the terminal output.",
    effect: "Changes the language of CLI messages (not of files written into the repo).",
    omitted: "System language; en in CI and whenever --force is given.",
    example: "npx projectops --mode doctor --lang ko",
  },
  "--json": {
    when: "With --mode options, whenever a program or agent reads the output.",
    effect: "Prints the full option table as JSON instead of text. No files are written.",
    omitted: "Human-readable text.",
    example: "npx projectops --mode options --json",
  },
  "--version": { when: "To learn which projectops release is running.", effect: "Prints the package version and exits. Writes nothing.", omitted: "-", example: "npx projectops --version" },
  "--help": { when: "To read the short human help.", effect: "Prints the help text and exits. Writes nothing. For agents, --mode options --json is more complete.", omitted: "-", example: "npx projectops --help" },
};

export const KEY_DETAILS = {
  "version": { when: "Read it to know the current version. Edit by hand only when asked to change the version.", effect: "version_manager syncs this value into pubspec.yaml / package.json / build.gradle / pyproject.toml ...", omitted: "Created from the build file at install." },
  "version_code": { when: "Do not edit.", effect: "Build number. +1 on every release; used by Android release builds (iOS and test builds use build_number.py).", omitted: "1" },
  "project_types": { when: "Set by the wizard. Do not change after setup.", effect: "Decides which type workflows run and which build files are synced. The first entry is primary.", omitted: "Detected at install." },
  "project_paths": { when: "Monorepos only.", effect: "Maps a type to its subfolder so version sync and workflow path filters look there.", omitted: "Every type at the repo root." },
  "metadata.default_branch": { when: "Do not edit unless the repository default branch was renamed.", effect: "The branch whose pushes deploy and publish. Workflows trigger on it.", omitted: "main" },
  "metadata.deploy_branch": { when: "Only if the development branch is not develop.", effect: "Head of the release PR; workflows rewrite their develop references to this name.", omitted: "develop", caution: "Not the deploying branch, despite the name." },
  "metadata.template.options.intent": { when: "Leave as is.", effect: "Remembers the project kind so a re-run does not ask the deploy questions again.", omitted: "Inferred from deploy and publish." },
  "metadata.template.options.deploy": { when: "Edit via --deploy, not by hand.", effect: "Which deploy workflow family is installed on the next update (docker-ssh, vercel, none).", omitted: "docker-ssh for server stacks." },
  "metadata.template.options.publish": { when: "Edit via --publish.", effect: "Which registry publish workflows are installed on the next update.", omitted: "[]" },
  "metadata.template.options.secret_backup": { when: "Edit via --secret-backup.", effect: "Whether the secret backup workflow is installed.", omitted: "false" },
  "metadata.template.options.semver_auto": { when: "Set false only if you want every release to be a patch bump.", effect: "true: the release PR and direct pushes to the default branch pick the bump from commit titles ('type!:' major, 'feat:' minor, otherwise patch). false: always patch.", omitted: "true (also for existing installs when the key is missing).", caution: "A repo that switches from patch-only to true can jump a minor version on its next release; the update summary warns about it." },
  "metadata.template.options.close_on_release": { when: "Set false to keep finished issues open after a release.", effect: "A release merge closes issues that carry the done label and are referenced by a release commit.", omitted: "true for new installs; off (key missing) for existing installs." },
  "metadata.template.options.language": { when: "Edit via --language.", effect: "Language of issue/PR templates, bot comments and version.yml comments.", omitted: "en for new installs, ko for existing ones." },
  "metadata.template.options.label_style": { when: "Edit via --label-style.", effect: "Status label names (en 'status: todo' or legacy ko).", omitted: "en for new installs, ko for existing ones." },
  "metadata.template.options.projects_sync": { when: "Edit via --projects-sync.", effect: "Whether the Projects status sync workflow is installed.", omitted: "false for new installs; kept if installed." },
  "metadata.template.options.app_release": { when: "Set true by hand for repos whose releases go through App Store / Play Store review.", effect: "The deploy skill (pro-changelog-deploy) treats releases as going through store review: release notes get a review warning banner and are checked more strictly, and the release PR always waits for manual approval instead of automerging.", omitted: "Not set. Never enabled automatically.", caution: "Do not set it on repos that do not ship to a store." },
  "metadata.template.options.excluded_workflows": { when: "Add a file name to stop the update from ever installing that template workflow.", effect: "Listed files are skipped on install and update. Files you deleted yourself are also not restored; a copy of the template is kept in .github/.projectops/incoming/.", omitted: "[]", example: 'excluded_workflows: ["PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml"]' },
  "metadata.template.options.store_locales": { when: "Set it when the store listing has several languages and release notes must not be one Korean text copied into all of them.", effect: "Turns on per-language store release notes (Play Console 'Release notes', App Store 'What's New'). The first entry is the default language. Each other language uses the text in store_notes[<language>] of that version in CHANGELOG.json; a language without text gets the default-language text, because the stores reject an empty What's New.", omitted: "Off: the same text is used for every store language, as before.", example: 'store_locales: ["ko-KR", "en-US", "ja-JP", "zh-CN"]' },
  "metadata.template.options.store_locales_ios": { when: "Set it only when the App Store listing has a different set of languages than Google Play.", effect: "The App Store uses this list instead of store_locales (same rules: first entry is the default language, a language without text gets the default-language text). Needed because fastlane deliver ACTIVATES every language folder the app version does not have, so a language the App Store listing lacks would be added to the app.", omitted: "The App Store uses store_locales.", example: 'store_locales_ios: ["ko-KR", "en-US"]' },
  "metadata.template.options.store_locales_play": { when: "Set it only when Google Play has a different set of languages than the App Store.", effect: "Google Play uses this list instead of store_locales (same rules).", omitted: "Google Play uses store_locales.", example: 'store_locales_play: ["ko-KR", "en-US", "ja-JP"]' },
  "metadata.template.options.code_review.coderabbit": { when: "Edit via --coderabbit / --no-coderabbit.", effect: "Whether .coderabbit.yaml is installed by --mode full. PR review bot only; unrelated to release notes.", omitted: "false" },
  "metadata.template.options.code_review.ai_summary": { when: "Edit via --ai-summary.", effect: "Whether the AI PR summary workflow is installed.", omitted: "true" },
  "metadata.template.options.changelog.provider": { when: "Leave the default. Set only to force one generator.", effect: "Release notes: the PR body is used as is when it already has notes; otherwise a registered AI key (GEMINI_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY) is used; otherwise the commit analysis, which always works and costs nothing. 'copilot' consumes Copilot premium requests, so it is only used when set here.", omitted: "commit (an AI key is still picked up automatically)." },
  "metadata.template.options.changelog.base_url": { when: "Only with provider ollama.", effect: "Base URL of the Ollama server (OpenAI-compatible, ending in /v1).", omitted: "" },
};

// 자주 하는 일 → 그대로 실행할 명령. agent 가 옵션을 조합하다 틀리지 않게 한다.
export const RECIPES = [
  { goal: "Install everything in a new repo (stack auto-detected)", command: "npx projectops --mode full --force", note: "Add --type spring,react for several stacks." },
  { goal: "Update an existing install to the newest templates", command: "npx projectops --mode full --force", note: "Files you modified are kept; read .github/.projectops/incoming/ and the completion summary for what was skipped." },
  { goal: "Refresh only the workflows, scripts and config", command: "npx projectops --mode workflows --force", note: "version.yml is not rewritten." },
  { goal: "See the state of an install and the repository settings (read-only)", command: "npx projectops --mode doctor", note: "Add GITHUB_TOKEN=... to also check repository settings." },
  { goal: "Read every option with values, defaults and effects", command: "npx projectops --mode options --json" },
  { goal: "Install the CodeRabbit PR review config", command: "npx projectops --mode full --force --coderabbit", note: "Needs the CodeRabbit GitHub app; overwrites an existing .coderabbit.yaml (backup saved as .bak)." },
  { goal: "Never install a template workflow again", command: "Add its file name to metadata.template.options.excluded_workflows in version.yml", note: "Delete the installed file too; the update will not bring it back." },
  { goal: "Stop retired workflows from running next to their replacements", command: "npx projectops --mode workflows --force --remove-legacy", note: "Run only after the new workflow is working." },
  { goal: "Keep every release a patch bump", command: "Set metadata.template.options.semver_auto: false in version.yml" },
  { goal: "Install a library publish workflow", command: "npx projectops --mode workflows --force --type node --publish npm", note: "Needs the NPM_TOKEN secret." },
];

// 이 CLI 를 사람 없이 쓰는 agent 가 지킬 규칙
export const AGENT_RULES = [
  "Always pass an explicit --mode and --force. Without --force and without a TTY the command stops; with --mode interactive it needs a human.",
  "Read before you write: run --mode doctor (state) and --mode options --json (this table). Both are read-only and need no network.",
  "Only flags you pass, the stored version.yml values and the defaults decide anything — nothing is asked. Check the 'omitted' text of a flag before relying on its default.",
  "Your edits are safe: a workflow you changed is kept as is, and a copy of the new template goes to .github/.projectops/incoming/. Compare with: diff -u .github/workflows/<file> .github/.projectops/incoming/<file>.",
  "After a run read the completion summary on stderr: it lists kept files, retired workflows still installed, workflows not installed, placeholders that still need a value (__NAME__) and secrets that must be registered.",
  "Every run is recorded in .github/.projectops/logs/ (.log for people, .jsonl for programs). Read the newest .log to see why something was decided. Never edit those files.",
  "Exit code 0 means the run completed (doctor also returns 0 when it finds things to look at). 1 means invalid arguments or a failed run; the message says which.",
  "Never delete .github/.projectops/baseline.json: it is how the next update tells your edits from template changes.",
];

export const OUTPUT_FILES = [
  { path: "version.yml", written_by: "full, version", note: "Regenerated on every full/version run from the stored values plus flags. Options and top-level keys the wizard does not generate itself (for example options.issue_helper) are kept verbatim, comments included; legacy keys (nexus, npm_publish, synology, project_type) are converted to their new form and not kept; a malformed block is dropped rather than copied. workflows mode does not touch version.yml." },
  { path: ".github/workflows/PROJECT-*.yaml", written_by: "full, workflows", note: "Installed per type and options. A file you modified is kept." },
  { path: ".github/scripts/, .github/config/, .github/util/", written_by: "full, workflows", note: "Helper scripts used by the workflows." },
  { path: ".github/ISSUE_TEMPLATE/, PULL_REQUEST_TEMPLATE.md", written_by: "full, issues", note: "Language follows options.language." },
  { path: ".coderabbit.yaml", written_by: "full (only with --coderabbit)", note: "Overwritten with a .bak backup if present." },
  { path: ".github/.projectops/AGENT-GUIDE.md", written_by: "full, version, workflows", note: "Short guide for AI agents working in the repo. Regenerated on every update." },
  { path: ".github/.projectops/baseline.json", written_by: "full, workflows", note: "Hashes of what was installed. Tracked by git; do not delete." },
  { path: ".github/.projectops/incoming/", written_by: "full, workflows", note: "New template copies of files that were kept or not installed. Not tracked by git." },
  { path: ".github/.projectops/logs/", written_by: "full, workflows", note: "Run log and event trace. Not tracked by git." },
];

export function buildSchema(packageVersion = "") {
  return {
    tool: "projectops",
    packageVersion,
    schemaVersion: SCHEMA_VERSION,
    usage: "npx projectops --mode <mode> [--type csv] [--force] ...   (agents: always pass --force and an explicit --mode)",
    modes: MODES,
    flags: FLAGS.map((f) => ({ ...f, ...(FLAG_DETAILS[f.flag] || {}) })),
    versionYml: VERSION_YML.map((k) => ({ ...k, ...(KEY_DETAILS[k.path] || {}) })),
    agentRules: AGENT_RULES,
    recipes: RECIPES,
    outputFiles: OUTPUT_FILES,
    related: {
      diagnose: "npx projectops --mode doctor",
      optionsJson: "npx projectops --mode options --json",
      docs: "https://cassiiopeia.github.io/projectops/",
    },
  };
}

// 사람이 읽는 표 — JSON 이 아닐 때 출력한다.
export function renderText(schema) {
  const lines = [`projectops ${schema.packageVersion} — options (schema v${schema.schemaVersion})`, "", schema.usage, "", "MODES"];
  for (const m of schema.modes) lines.push(`  ${m.name.padEnd(12)} ${m.description}`);
  const detail = (o) => {
    for (const [label, key] of [["when", "when"], ["effect", "effect"], ["if omitted", "omitted"], ["caution", "caution"], ["example", "example"]]) {
      if (o[key]) lines.push(`      ${label}: ${o[key]}`);
    }
  };
  lines.push("", "RULES FOR AGENTS");
  schema.agentRules.forEach((r, i) => lines.push(`  ${i + 1}. ${r}`));
  lines.push("", "RECIPES");
  for (const r of schema.recipes) lines.push(`  ${r.goal}`, `      ${r.command}`, ...(r.note ? [`      (${r.note})`] : []));
  lines.push("", "FLAGS");
  for (const f of schema.flags) {
    const name = [...(f.aliases ?? [f.alias]), f.flag + (f.value ? ` ${f.value}` : ""), f.negation].filter(Boolean).join(", ");
    const desc = f.deprecated ? `(deprecated) ${f.deprecated}` : f.description;
    const extra = [f.values ? `values: ${f.values.join("|")}` : "", f.default !== undefined ? `default: ${f.default}` : ""].filter(Boolean).join("; ");
    lines.push(`  ${name}`, `      ${desc}${extra ? `  [${extra}]` : ""}`);
    detail(f);
  }
  lines.push("", "VERSION.YML KEYS");
  for (const k of schema.versionYml) {
    const extra = [k.type, k.values ? k.values.join("|") : "", k.default !== undefined ? `default: ${JSON.stringify(k.default)}` : ""].filter(Boolean).join("; ");
    lines.push(`  ${k.path}  [${extra}]`, `      ${k.description}`);
    detail(k);
  }
  lines.push("", "FILES WRITTEN");
  for (const o of schema.outputFiles) lines.push(`  ${o.path}  (${o.written_by})`, `      ${o.note}`);
  return lines.join("\n");
}
