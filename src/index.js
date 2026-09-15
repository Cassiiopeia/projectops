// projectops CLI 진입 파이프라인 (.sh main + execute_integration 등가).
// 감지 → 다운로드 → 모드 라우팅 → 통합 실행 → 정리. 비대화형(--force) 우선.
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync, existsSync } from "node:fs";
import { parseArgs, parsePathsCsv, CliError } from "./cli/args.js";
import { HELP_TEXT } from "./cli/help.js";
import { createContext } from "./context.js";
import { PATHS } from "./core/paths.js";
import { remove } from "./core/fsutil.js";
import { acquireTemplate, readTemplateVersion } from "./core/assets.js";
import { detectTypes, detectVersion, detectDefaultBranch, detectRepoName, makeResolvers } from "./core/detect-fs.js";
import { parseExisting } from "./core/version-yml.js";
import { runBreakingCheck } from "./core/breaking-check.js";
import { runMigrations } from "./core/migrations/index.js";
import { detectOrphanWorkflows } from "./core/orphan-workflows.js";
import { createRunTrace } from "./core/run-trace.js";
import { appendGuideEntry } from "./core/migration-guide.js";
import { resolveProjectPaths } from "./core/paths-resolve.js";
import { applicableTargets } from "./core/options-ask.js";
import { printBannerCompact } from "./ui/banner.js";
import { printSummary } from "./ui/summary.js";
import { runFull } from "./commands/full.js";
import { runVersion } from "./commands/version.js";
import { runWorkflows } from "./commands/workflows.js";
import { runIssues } from "./commands/issues.js";
import { runInteractive } from "./commands/interactive.js";
import { runSkills } from "./commands/skills.js";

// projectops 패키지 버전 읽기 (-v/--version 출력용). src/../package.json.
function readPkgVersion() {
  try {
    const here = dirname(fileURLToPath(import.meta.url));
    const pkg = JSON.parse(readFileSync(join(here, "..", "package.json"), "utf8"));
    return pkg.version || "unknown";
  } catch {
    return "unknown";
  }
}

// 결정적 UTC 타임스탬프 (주입 가능 — 테스트/골든용)
function utcNow(date = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  const d = `${date.getUTCFullYear()}-${p(date.getUTCMonth() + 1)}-${p(date.getUTCDate())}`;
  const t = `${p(date.getUTCHours())}:${p(date.getUTCMinutes())}:${p(date.getUTCSeconds())}`;
  return { now: `${d} ${t}`, today: d };
}

// run(argv, opts) → exitCode. opts: { cwd, source?, clock? }
//   source: acquireTemplate용 (기본 git clone). 테스트는 {type:'local', path} 주입.
//   clock: {now, today} 주입 (기본 현재 UTC).
export async function run(argv, { cwd = process.cwd(), source = { type: "git" }, clock } = {}) {
  let opts;
  try {
    opts = parseArgs(argv);
  } catch (e) {
    if (e instanceof CliError) { console.error(e.message); return 1; }
    throw e;
  }
  if (opts.showVersion) { console.log(readPkgVersion()); return 0; }
  if (opts.help) { console.log(HELP_TEXT); return 0; }

  // skills 모드 — IDE 스킬 설치/업데이트/제거 (템플릿 통합 없음).
  // Cursor 복사용 skills/ 소스가 필요하므로 템플릿을 획득한 뒤 실행한다.
  if (opts.mode === "skills") {
    const tempDir = join(cwd, PATHS.tempDir);
    const interactive = !opts.force && process.stdout.isTTY;
    try {
      acquireTemplate({ tempDir, source });
      const templateVersion = readTemplateVersion(tempDir);
      return await runSkills({ templateVersion, tempDir, interactive });
    } finally {
      remove(tempDir);
    }
  }
  // 대화형 모드 — 인자 없이 실행 or --mode interactive
  if (opts.mode === "interactive") {
    if (!process.stdout.isTTY) {
      console.error("대화형 입력이 불가능한 환경입니다. --mode <full|version|workflows|issues> 와 --force 를 지정하세요.");
      return 1;
    }
    return await runInteractive({}, { cwd, source, clock });
  }
  // 명시 모드인데 --force 없으면 (비대화형 CLI는 --force 필요)
  if (!opts.force && !process.stdout.isTTY) {
    console.error("비대화형 환경에서는 --force 옵션이 필요합니다.");
    return 1;
  }

  // 기존 version.yml 로드 — version/version_code/project_paths 보존의 단일 진실 (.sh L2208~2239 SSoT)
  const vyPath = join(cwd, "version.yml");
  const existing = existsSync(vyPath) ? parseExisting(readFileSync(vyPath, "utf8")) : null;

  // 감지 (CLI 인자 우선, 없으면 자동 감지 — version.yml 우선 규칙은 detectTypes/detectVersion 내부)
  const types = opts.types.length ? opts.types : detectTypes(cwd);
  // version: 기존 version.yml 최우선(SSoT — 재실행 시 덮어쓰기 방지) → CLI 지정 → 파일 감지
  const version = (existing?.version) || opts.version || detectVersion(cwd);
  const versionCode = existing?.versionCode ?? 1; // 기존 빌드번호 보존 (.sh L2208~2221)
  const branch = detectDefaultBranch(cwd);
  const repoName = detectRepoName(cwd);
  // 경로 확정 (.sh resolve_project_paths 비대화형 경로 — --paths 우선 → 저장값 → 후보 1개 자동 → 루트 폴백)
  const paths = await resolveProjectPaths({
    root: cwd, types, paths: parsePathsCsv(opts.pathsCsv),
    existingPaths: existing?.paths ?? new Map(), force: true, tty: false, io: {},
  });

  const { now, today } = clock || utcNow();
  const tempDir = join(cwd, PATHS.tempDir);

  // 프로젝트 성격(#485): CLI --intent → version.yml 저장값. deploy/publish 유도의 기준.
  let intent = opts.intent ?? existing?.options?.intent ?? null;
  // 배포/publish 축(#439): CLI 플래그 최우선 → 저장값 → 기본값(적용 가능할 때만 docker-ssh — #498).
  //   단 --intent가 명시됐고 해당 축 플래그가 없으면 intent가 유도한다 (#485 비대화형):
  //   library/none이면 deploy=none, app/none이면 publish=[].
  const applicable = applicableTargets(types);
  let deployTarget = opts.deployTarget ?? existing?.options?.deploy
    ?? (applicable.deploy.includes("docker-ssh") ? "docker-ssh" : "none");
  let publishTargets = opts.publishTargets ?? existing?.options?.publish ?? [];
  if (opts.intent != null) {
    if ((intent === "library" || intent === "none") && opts.deployTarget == null) deployTarget = "none";
    if ((intent === "app" || intent === "none") && opts.publishTargets == null) publishTargets = [];
  }
  // 적용 불가 타겟 조용한 정리 (#498) — 대화형과 동일 규칙. 타입에 성립하지 않는 축 값은
  // 복사 결과가 동일하므로 경고 없이 none/교집합으로 정리한다 (모바일 앱/basic 단독 등).
  if (deployTarget !== "none" && !applicable.deploy.includes(deployTarget)) deployTarget = "none";
  publishTargets = publishTargets.filter((t) => applicable.publish.includes(t));
  if (types.length > 0 && applicable.deploy.length === 0 && applicable.publish.length === 0) intent = "none";

  const context = createContext({
    mode: opts.mode, force: true, types, version, versionCode, branch,
    paths,
    deployTarget,
    publishTargets,
    includeSecretBackup: opts.includeSecretBackup ?? existing?.options?.secretBackup ?? false,
    // #502 — version 모드가 기존 full 통합 기록(mode)을 강등하지 않도록 (full이 우세)
    recordMode: existing?.templateMode === "full" ? "full" : "version",
    // 릴리스 배포 브랜치(#456): CLI 플래그 → version.yml 저장값 → 빈 값(미출력, 스킬이 develop 폴백)
    deployBranch: opts.deployBranch || existing?.options?.deployBranch || "",
    intent,
    // changelog/code_review 축(#455): 비대화형은 저장값 → 기본값. null이 흘러 provider:"null"로 기록되던 버그 수정.
    changelogProvider: existing?.options?.changelogProvider ?? "github-ai",
    changelogBaseUrl: existing?.options?.changelogBaseUrl ?? "",
    codeReviewCoderabbit: existing?.options?.codeReviewCoderabbit ?? false,
    // semver 자동 승격(#546): 저장값 → (기존 통합 레포면 false / 신규면 true).
    // 이미 통합된 레포의 버전이 업데이트만으로 예고 없이 minor로 튀지 않게 하는 안전장치다.
    semverAuto: existing?.options?.semverAuto ?? (existing ? false : true),
    repoName,
    // 실 resolver 4종 (.sh resolve_token 등가 — spring-app-yml 스텁 제거)
    resolvers: makeResolvers(cwd, repoName, paths),
    now, today,
  });

  let result = null;
  // 실행 트레이스 (#494) — 비대화형도 이벤트 기록 (터미널 미러는 CLI 실행에서만 유의미하므로 함께 켠다)
  const trace = createRunTrace();
  const recordArtifacts = opts.mode === "full" || opts.mode === "workflows";
  let breakingReport = null;
  let migrationsResult = null;
  let orphanPending = [];
  if (recordArtifacts) trace.mirrorStart();
  try {
    acquireTemplate({ tempDir, source });
    context.templateVersion = readTemplateVersion(tempDir);

    // 비대화형 축약 배너 (#446 확정 — 1줄, 로그 오염 최소)
    printBannerCompact({ version: context.templateVersion, mode: opts.mode });

    // Breaking Changes 게이트 (.sh execute_integration L4415~4420 등가 — 비대화형은 경고 후 진행)
    const proceed = await runBreakingCheck({
      cwd, tempDir, templateVersion: context.templateVersion,
      onItems: (items) => { breakingReport = items; },
    });
    if (!proceed) return 0;

    // 레거시 마이그레이션 (#470) — 워크플로우를 만지는 모드에서만. 비대화형은 safe 티어 자동 적용.
    if (recordArtifacts) {
      migrationsResult = await runMigrations({ targetRoot: cwd });
      for (const a of migrationsResult.applied ?? []) trace.event("legacy", a.action === "error" ? "error" : "neutralized", a.from ?? a.id ?? "", { to: a.to ?? "", id: a.id ?? "" });
      for (const e of migrationsResult.confirmPending ?? []) trace.event("legacy", "leftover-old-gen", e.file, { replacement: e.replacedBy ?? "", reason: e.reason ?? "" });
    }

    // 고아 타입 워크플로우 안내 (#487) — 비대화형은 자동 무해화 금지(배포 파이프라인일 수 있음), 안내만
    if (recordArtifacts) {
      const orphans = detectOrphanWorkflows({ tempDir, targetRoot: cwd, selectedTypes: types });
      orphanPending = orphans.map((o) => o.filename);
      for (const o of orphans) {
        console.error(`⚠️ 선택되지 않은 타입(${o.type})의 워크플로우가 남아있습니다: ${o.filename} — 대화형 마법사(npx projectops)에서 정리할 수 있습니다.`);
      }
    }

    switch (opts.mode) {
      case "full": result = runFull(context, tempDir, cwd, { trace }); break;
      case "version": result = runVersion(context, tempDir, cwd); break;
      case "workflows": result = runWorkflows(context, tempDir, cwd, { trace }); break;
      case "issues": result = runIssues(context, tempDir, cwd); break;
      default:
        // 알 수 없는 모드 → .sh와 동일하게 복사 0건, 에러 아님
        break;
    }
  } finally {
    trace.mirrorStop();
    remove(tempDir);
  }

  // 마이그레이션 기록 (#493/#494) — Layer 2/3 트레이스 파일 + Layer 1 가이드 엔트리
  let migrationGuidePath = null;
  if (recordArtifacts) {
    const files = trace.write({ targetRoot: cwd, fromVersion: existing?.templateVersion || "", toVersion: context.templateVersion, now });
    migrationGuidePath = appendGuideEntry(cwd, {
      now, mode: opts.mode, types, repoName,
      templateFrom: existing?.templateVersion || "", templateTo: context.templateVersion,
      options: { deploy: deployTarget, publish: publishTargets, secretBackup: context.includeSecretBackup, coderabbit: context.codeReviewCoderabbit, changelogProvider: context.changelogProvider, intent, semverAuto: context.semverAuto },
      branches: { defaultBranch: branch, deployBranch: context.deployBranch || "develop", ready: null, created: null },
      breaking: breakingReport, migrations: migrationsResult, orphans: { cleaned: [], pending: orphanPending },
      events: trace.events, counters: { skipped: result?.workflows?.skipped ?? 0 },
      traceFile: files?.traceFile ?? "", logFile: files?.logFile ?? "",
    }).guidePath;
  }

  // 완료 요약 (.sh print_summary — CLI 모드에서도 출력)
  printSummary({
    mode: opts.mode, types, version, deployBranch: context.deployBranch, migrationGuidePath,
    counters: { workflows: result?.workflows?.copied ?? 0, workflowFiles: result?.workflows?.copiedFiles ?? [], utilModules: 0 },
    verification: result?.verification,   // #549 설치 후 검증 결과 (full/workflows 모드에서만 존재)
  }, cwd);
  return 0;
}
