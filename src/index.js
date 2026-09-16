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
import { createRunTrace, MIGRATION_DIR } from "./core/run-trace.js";
import { appendGuideEntry } from "./core/migration-guide.js";
import { resolveProjectPaths, markerForType } from "./core/paths-resolve.js";
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

  // doctor 모드 (#558) — 읽기 전용 진단. 템플릿을 내려받지 않으므로 네트워크 없이도 동작한다.
  if (opts.mode === "doctor") {
    const { runDoctor } = await import("./commands/doctor.js");
    await runDoctor({ cwd });
    return 0;   // 진단은 실패가 아니다 — 살펴볼 항목이 있어도 0으로 끝낸다
  }

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

  // 실행 트레이스 (#494/#561) — 감지·판단 단계부터 기록해야 "왜 이렇게 정해졌는지"가 남는다.
  const trace = createRunTrace();
  const recordArtifacts = opts.mode === "full" || opts.mode === "workflows";
  if (recordArtifacts) trace.mirrorStart();

  // 기존 version.yml 로드 — version/version_code/project_paths 보존의 단일 진실 (.sh L2208~2239 SSoT)
  const vyPath = join(cwd, "version.yml");
  const existing = existsSync(vyPath) ? parseExisting(readFileSync(vyPath, "utf8")) : null;
  trace.event("detect", "existing-install", existing ? "found" : "none", {
    templateVersion: existing?.templateVersion || null,
    version: existing?.version || null,
    types: existing?.types || null,
  });

  // 감지 (CLI 인자 우선, 없으면 자동 감지 — version.yml 우선 규칙은 detectTypes/detectVersion 내부)
  const types = opts.types.length ? opts.types : detectTypes(cwd);
  trace.event("detect", "types", types.join(",") || "(없음)", {
    source: opts.types.length ? "cli-flag(--type)" : "auto-detect(마커 파일 스캔)",
  });
  // version: 기존 version.yml 최우선(SSoT — 재실행 시 덮어쓰기 방지) → CLI 지정 → 파일 감지
  const version = (existing?.version) || opts.version || detectVersion(cwd);
  trace.event("detect", "version", version, {
    source: existing?.version ? "version.yml(기존값 보존)"
      : (opts.version ? "cli-flag(--project-version)" : "프로젝트 파일 감지"),
  });
  const versionCode = existing?.versionCode ?? 1; // 기존 빌드번호 보존 (.sh L2208~2221)
  const branch = detectDefaultBranch(cwd);
  const repoName = detectRepoName(cwd);
  trace.event("detect", "repo", repoName || "(미상)", { defaultBranch: branch, versionCode });
  // 경로 확정 (.sh resolve_project_paths 비대화형 경로 — --paths 우선 → 저장값 → 후보 1개 자동 → 루트 폴백)
  const paths = await resolveProjectPaths({
    root: cwd, types, paths: parsePathsCsv(opts.pathsCsv),
    existingPaths: existing?.paths ?? new Map(), force: true, tty: false, io: {},
  });

  for (const [ty, pth] of paths) {
    // 근거로 "무엇을 보고 그 경로로 정했는지"까지 남긴다 — 경로가 틀렸을 때 추적의 시작점이다.
    const marker = markerForType(ty);
    const at = pth === "." ? marker : `${pth}/${marker}`;
    trace.event("detect", "project-path", ty, {
      path: pth,
      marker: existsSync(join(cwd, at)) ? at : `${at} (없음)`,
      source: parsePathsCsv(opts.pathsCsv).has(ty) ? "cli-flag(--paths)"
        : (existing?.paths?.has(ty) ? "version.yml(저장값)" : "마커 파일 탐색"),
    });
  }

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
  const beforeCleanup = { deploy: deployTarget, publish: [...publishTargets] };
  if (deployTarget !== "none" && !applicable.deploy.includes(deployTarget)) deployTarget = "none";
  publishTargets = publishTargets.filter((t) => applicable.publish.includes(t));
  if (types.length > 0 && applicable.deploy.length === 0 && applicable.publish.length === 0) intent = "none";

  // 축 확정 근거 (#561) — "왜 이 값인가"가 가장 헷갈리는 자리다.
  // CLI 플래그 / 저장값 / intent 유도 / 타입 적용성 정리 중 무엇이 이겼는지 남긴다.
  trace.event("resolve", "intent", String(intent ?? "(미설정)"), {
    source: opts.intent != null ? "cli-flag(--intent)"
      : (existing?.options?.intent ? "version.yml(저장값)" : "미지정 → deploy/publish에서 역추론"),
  });
  trace.event("resolve", "deploy", deployTarget, {
    source: opts.deployTarget != null ? "cli-flag(--deploy)"
      : (existing?.options?.deploy ? "version.yml(저장값)" : "기본값"),
    applicableForTypes: applicable.deploy,
    adjusted: beforeCleanup.deploy !== deployTarget
      ? `${beforeCleanup.deploy} → ${deployTarget} (선택 타입에 적용 불가)` : null,
  });
  trace.event("resolve", "publish", publishTargets.join(",") || "(없음)", {
    source: opts.publishTargets != null ? "cli-flag(--publish)"
      : (existing?.options?.publish ? "version.yml(저장값)" : "기본값"),
    applicableForTypes: applicable.publish,
    adjusted: beforeCleanup.publish.join(",") !== publishTargets.join(",")
      ? `${beforeCleanup.publish.join(",") || "(없음)"} → ${publishTargets.join(",") || "(없음)"} (적용 불가 정리)` : null,
  });

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
    // 앱 심사 배포 레포 여부(#553): 저장값만 보존한다. 마법사가 묻지 않으므로 새로 켜지 않는다
    // (사용자가 version.yml에 직접 쓰거나 스킬이 기록한 값을 그대로 유지).
    appRelease: existing?.options?.appRelease ?? null,
    repoName,
    // 실 resolver 4종 (.sh resolve_token 등가 — spring-app-yml 스텁 제거)
    resolvers: makeResolvers(cwd, repoName, paths),
    now, today,
  });

  // 최종 확정값 스냅샷 (#561) — 이 한 줄로 "무엇이 어떻게 설치될 것인지"가 고정된다.
  trace.event("resolve", "context", opts.mode || "", {
    types, version, versionCode, branch,
    deploy: deployTarget, publish: publishTargets, intent,
    secretBackup: context.includeSecretBackup,
    changelogProvider: context.changelogProvider,
    coderabbit: context.codeReviewCoderabbit,
    deployBranch: context.deployBranch || "(미지정 → develop 폴백)",
    recordMode: context.recordMode,
  });
  trace.event("resolve", "semver-auto", String(context.semverAuto), {
    reason: existing?.options?.semverAuto != null ? "version.yml 저장값 보존"
      : (existing ? "기존 통합 레포 → 예고 없는 버전 상승 방지를 위해 false"
                  : "신규 통합 → true"),
  });
  trace.event("resolve", "app-release", String(context.appRelease), {
    reason: existing?.options?.appRelease != null ? "version.yml 저장값 보존" : "미설정(키를 쓰지 않음)",
  });

  let result = null;
  // trace/recordArtifacts는 감지 단계 기록을 위해 위에서 이미 생성했다 (#561)
  let breakingReport = null;
  let migrationsResult = null;
  let orphanPending = [];
  // 실행 경계(#561) — 로그만 보고 "무엇을 어떤 인자로 돌렸는지"를 알 수 있어야 한다.
  trace.event("run", "start", opts.mode || "", {
    cli: "non-interactive", types, version, branch,
    force: true, deploy: deployTarget, publish: publishTargets, intent,
  });
  try {
    trace.step("acquire-template", () => acquireTemplate({ tempDir, source }), { source: source?.type || "git" });
    context.templateVersion = readTemplateVersion(tempDir);
    trace.event("detect", "template-version", context.templateVersion, { tempDir: PATHS.tempDir });

    // 비대화형 축약 배너 (#446 확정 — 1줄, 로그 오염 최소)
    printBannerCompact({ version: context.templateVersion, mode: opts.mode });

    // Breaking Changes 게이트 (.sh execute_integration L4415~4420 등가 — 비대화형은 경고 후 진행)
    const proceed = await trace.stepAsync("breaking-check", () => runBreakingCheck({
      cwd, tempDir, templateVersion: context.templateVersion,
      onItems: (items) => { breakingReport = items; },
    }));
    trace.event("breaking", "result", proceed ? "proceed" : "halt", { items: (breakingReport ?? []).length });
    if (!proceed) {
      trace.event("run", "cancelled", "breaking-gate", { reason: "호환성 경고로 중단" });
      return 0;
    }

    // 레거시 마이그레이션 (#470) — 워크플로우를 만지는 모드에서만. 비대화형은 safe 티어 자동 적용.
    if (recordArtifacts) {
      migrationsResult = await trace.stepAsync("legacy-migrations", () => runMigrations({ targetRoot: cwd }));
      for (const a of migrationsResult.applied ?? []) trace.event("legacy", a.action === "error" ? "error" : "neutralized", a.from ?? a.id ?? "", { to: a.to ?? "", id: a.id ?? "" });
      for (const e of migrationsResult.confirmPending ?? []) trace.event("legacy", "leftover-old-gen", e.file, { replacement: e.replacedBy ?? "", reason: e.reason ?? "" });
    }

    // 고아 타입 워크플로우 안내 (#487) — 비대화형은 자동 무해화 금지(배포 파이프라인일 수 있음), 안내만
    if (recordArtifacts) {
      const orphans = trace.step("orphan-scan",
        () => detectOrphanWorkflows({ tempDir, targetRoot: cwd, selectedTypes: types }),
        { selectedTypes: types });
      orphanPending = orphans.map((o) => o.filename);
      for (const o of orphans) trace.event("orphan", "detected", o.filename, { type: o.type, action: "안내만(비대화형)" });
      for (const o of orphans) {
        console.error(`⚠️ 선택되지 않은 타입(${o.type})의 워크플로우가 남아있습니다: ${o.filename} — 대화형 마법사(npx projectops)에서 정리할 수 있습니다.`);
      }
    }

    switch (opts.mode) {
      case "full": result = trace.step("install-full", () => runFull(context, tempDir, cwd, { trace })); break;
      case "version": result = trace.step("install-version", () => runVersion(context, tempDir, cwd)); break;
      case "workflows": result = trace.step("install-workflows", () => runWorkflows(context, tempDir, cwd, { trace })); break;
      case "issues": result = trace.step("install-issues", () => runIssues(context, tempDir, cwd)); break;
      default:
        // 알 수 없는 모드 → .sh와 동일하게 복사 0건, 에러 아님
        break;
    }
  } catch (err) {
    // 실패 원인을 로그에 남긴다 (#561) — 서버 로그처럼 사후에 바로 짚을 수 있어야 한다.
    trace.event("run", "error", opts.mode || "", {
      message: err?.message || String(err),
      stack: String(err?.stack || "").split("\n").slice(0, 3).join(" | "),
    });
    throw err;
  } finally {
    // 예외로 빠져나가도 기록을 남긴다 (#561). finalize는 멱등 — 정상 경로에서 이미
    // 호출됐으면 여기서는 아무 일도 하지 않는다.
    if (recordArtifacts) {
      trace.finalize({ targetRoot: cwd, fromVersion: existing?.templateVersion || "", toVersion: context.templateVersion, now });
    }
    remove(tempDir);
  }

  // 마이그레이션 기록 (#493/#494) — Layer 2/3 트레이스 파일 + Layer 1 가이드 엔트리
  let migrationGuidePath = null;
  // 기록 파일 경로는 먼저 계산하고(가이드가 참조), 실제 쓰기는 완료 화면 출력 뒤로 미룬다 —
  // 그래야 터미널 미러에 완료 화면까지 담긴다 (#561).
  const files = recordArtifacts
    ? trace.paths({ fromVersion: existing?.templateVersion || "", toVersion: context.templateVersion, now })
    : null;
  if (recordArtifacts) {
    migrationGuidePath = appendGuideEntry(cwd, {
      now, mode: opts.mode, types, repoName,
      templateFrom: existing?.templateVersion || "", templateTo: context.templateVersion,
      options: { deploy: deployTarget, publish: publishTargets, secretBackup: context.includeSecretBackup, coderabbit: context.codeReviewCoderabbit, changelogProvider: context.changelogProvider, intent, semverAuto: context.semverAuto , appRelease: context.appRelease },
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
    logDir: files ? MIGRATION_DIR : null,  // #561 기록 위치 안내
  }, cwd);

  // 완료 화면까지 캡처한 뒤 종료하고 기록한다 (#561)
  trace.event("run", "end", opts.mode || "", {
    workflowsCopied: result?.workflows?.copied ?? 0,
    workflowsSkipped: result?.workflows?.skipped ?? 0,
  });
  if (recordArtifacts) {
    trace.finalize({ targetRoot: cwd, fromVersion: existing?.templateVersion || "", toVersion: context.templateVersion, now });
  } else {
    trace.mirrorStop();
  }
  return 0;
}
