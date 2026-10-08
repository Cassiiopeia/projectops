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
    values: ["spring", "flutter", "react", "react-native", "react-native-expo", "node", "python", "basic"] },
  { flag: "--project-version", value: "VERSION", default: "auto-detected",
    description: "Initial version of the target project (x.y.z)." },
  { flag: "--paths", value: "type=path,...", default: "repo root",
    description: "Per-type project folders for monorepos, e.g. flutter=app,react=client.", versionYml: "project_paths" },
  { flag: "--intent", value: "KIND", values: ["app", "library", "both", "none", "manual"], default: "inferred from --deploy/--publish",
    description: "Project kind. Decides whether deploy and publish questions are asked.", versionYml: "metadata.template.options.intent" },
  { flag: "--deploy", value: "TARGET", values: ["docker-ssh", "vercel", "none"], default: "docker-ssh",
    description: "Where the app is deployed. Pick one.", versionYml: "metadata.template.options.deploy" },
  { flag: "--publish", value: "CSV", values: ["nexus", "npm", "github-packages"], default: "none",
    description: "Registries a library is published to. Several allowed.", versionYml: "metadata.template.options.publish" },
  { flag: "--deploy-branch", value: "NAME", default: "develop",
    description: "Development branch: the head of the release PR. Not the repository default branch.", versionYml: "metadata.deploy_branch" },
  { flag: "--language", value: "LANG", values: ["en", "ko"], default: "en for new installs, ko for existing installs",
    description: "Language of issue/PR templates and bot messages written into the repo.", versionYml: "metadata.template.options.language" },
  { flag: "--label-style", value: "STYLE", values: ["en", "ko"], default: "en for new installs, ko for existing installs",
    description: "Status label names: en = 'status: todo', ko = legacy Korean names.", versionYml: "metadata.template.options.label_style" },
  { flag: "--secret-backup", negation: "--no-secret-backup",
    description: "Include / exclude the workflow that uploads GitHub Secrets to a server over SSH.", default: "excluded",
    versionYml: "metadata.template.options.secret_backup" },
  { flag: "--ai-summary", negation: "--no-ai-summary",
    description: "Include / exclude the workflow that comments an AI summary on work PRs.", default: "included",
    versionYml: "metadata.template.options.code_review.ai_summary" },
  { flag: "--projects-sync", negation: "--no-projects-sync",
    description: "Include / exclude the GitHub Projects status sync workflow. Needs a PAT secret and PROJECT_URL variable.",
    default: "excluded for new installs; kept if already installed", versionYml: "metadata.template.options.projects_sync" },
  { flag: "--remove-legacy",
    description: "Rename retired old-generation workflows to .bak. Without it they are only listed in the summary and in doctor.", default: "off" },
  { flag: "--force", alias: "-y", aliases: ["-y", "--yes"], description: "Skip every confirmation and use non-interactive defaults. Required for agents and CI.", default: "off" },
  { flag: "--lang", value: "LANG", values: ["en", "ko"], default: "system language; pinned to en in CI and with --force",
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
  { path: "metadata.template.options.intent", parserKey: "intent", type: "enum", values: ["app", "library", "both", "none", "manual"],
    description: "Project kind; derives the deploy and publish questions.", edit: "wizard (--intent)" },
  { path: "metadata.template.options.deploy", parserKey: "deploy", type: "enum", values: ["docker-ssh", "vercel", "none"], default: "docker-ssh",
    description: "Where the app is deployed.", edit: "wizard (--deploy)" },
  { path: "metadata.template.options.publish", parserKey: "publish", type: "enum[]", values: ["nexus", "npm", "github-packages"], default: [],
    description: "Library registries.", edit: "wizard (--publish)" },
  { path: "metadata.template.options.secret_backup", parserKey: "secretBackup", type: "boolean", default: false,
    description: "Secret-to-server upload workflow installed.", edit: "wizard (--secret-backup)" },
  { path: "metadata.template.options.semver_auto", parserKey: "semverAuto", type: "boolean",
    default: true,
    description: "Decide the release bump from commit titles: 'type!:' = major, 'feat:' = minor, anything else = patch. Applies to the release PR; in repos without a development branch it also applies to pushes to main.",
    edit: "by hand" },
  { path: "metadata.template.options.close_on_release", parserKey: "closeOnRelease", type: "boolean", default: "true for new installs; missing for existing installs",
    description: "A release merge closes issues that carry the done label and are referenced by a release commit.", edit: "by hand" },
  { path: "metadata.template.options.language", parserKey: "language", type: "enum", values: ["en", "ko"], description: "Issue/PR template and bot message language.", edit: "wizard (--language)" },
  { path: "metadata.template.options.label_style", parserKey: "labelStyle", type: "enum", values: ["en", "ko"], description: "Status label names.", edit: "wizard (--label-style)" },
  { path: "metadata.template.options.projects_sync", parserKey: "projectsSync", type: "boolean", description: "Projects status sync workflow installed.", edit: "wizard (--projects-sync)" },
  { path: "metadata.template.options.app_release", parserKey: "appRelease", type: "boolean",
    description: "Releases go through App Store / Play Store review. Release notes get a review warning banner. Never auto-enabled.", edit: "by hand" },
  { path: "metadata.template.options.excluded_workflows", parserKey: "excludedWorkflows", type: "string[]",
    description: "Workflow file names the update must never install. Deleted files are also not restored; a copy is kept in .github/.projectops/incoming/.",
    edit: "by hand" },
  { path: "metadata.template.options.code_review.coderabbit", parserKey: "codeReviewCoderabbit", type: "boolean", description: "CodeRabbit config installed.", edit: "wizard" },
  { path: "metadata.template.options.code_review.ai_summary", parserKey: "aiPrSummary", type: "boolean", default: true, description: "AI PR summary workflow installed.", edit: "wizard (--ai-summary)" },
  { path: "metadata.template.options.changelog.provider", parserKey: "changelogProvider", type: "enum",
    values: ["commit", "openai", "gemini", "claude", "groq", "mistral", "ollama", "copilot", "coderabbit"], default: "commit",
    description: "Release note generator. 'commit' is free and always works; AI keys are picked up automatically when registered as secrets.", edit: "by hand" },
  { path: "metadata.template.options.changelog.base_url", parserKey: "changelogBaseUrl", type: "string", description: "Only for provider ollama.", edit: "by hand" },
];

export function buildSchema(packageVersion = "") {
  return {
    tool: "projectops",
    packageVersion,
    schemaVersion: SCHEMA_VERSION,
    usage: "npx projectops --mode <mode> [--type csv] [--force] ...   (agents: always pass --force and an explicit --mode)",
    modes: MODES,
    flags: FLAGS,
    versionYml: VERSION_YML,
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
  lines.push("", "FLAGS");
  for (const f of schema.flags) {
    const name = [...(f.aliases ?? [f.alias]), f.flag + (f.value ? ` ${f.value}` : ""), f.negation].filter(Boolean).join(", ");
    const desc = f.deprecated ? `(deprecated) ${f.deprecated}` : f.description;
    const extra = [f.values ? `values: ${f.values.join("|")}` : "", f.default !== undefined ? `default: ${f.default}` : ""].filter(Boolean).join("; ");
    lines.push(`  ${name}`, `      ${desc}${extra ? `  [${extra}]` : ""}`);
  }
  lines.push("", "VERSION.YML KEYS");
  for (const k of schema.versionYml) {
    const extra = [k.type, k.values ? k.values.join("|") : "", k.default !== undefined ? `default: ${JSON.stringify(k.default)}` : ""].filter(Boolean).join("; ");
    lines.push(`  ${k.path}  [${extra}]`, `      ${k.description}`);
  }
  return lines.join("\n");
}
