// projectops CLI entry pipeline (args > detect > per-mode integration > summary).
// Detect → download → route by mode → run integration → clean up. Non-interactive (--force) first.
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { readFileSync, existsSync } from "node:fs";
import { parseArgs, parsePathsCsv, validatePathsMap, CliError } from "./cli/args.js";
import { helpText } from "./cli/help.js";
import { resolveLang, setLang, t } from "./i18n/index.js";
import { reportFatal } from "./cli/errors.js";
import { createContext } from "./context.js";
import { PATHS } from "./core/paths.js";
import { remove } from "./core/fsutil.js";
import { acquireTemplate, readTemplateVersion } from "./core/assets.js";
import { SHARED_SCRIPTS_DIR_NAME } from "./core/ide/skills-copy.js";
import { detectTypes, detectVersion, detectDefaultBranch, detectRepoName, makeResolvers } from "./core/detect-fs.js";
import { parseExisting } from "./core/version-yml.js";
import { runBreakingCheck } from "./core/breaking-check.js";
import { runMigrations } from "./core/migrations/index.js";
import { detectOrphanWorkflows } from "./core/orphan-workflows.js";
import { createRunTrace, MIGRATION_DIR } from "./core/run-trace.js";
import { appendGuideEntry } from "./core/migration-guide.js";
import { resolveProjectPaths, markerForType } from "./core/paths-resolve.js";
import { resolveOptions } from "./core/resolve-options.js";
import { detectStoreLocalesHint } from "./core/store-locales-hint.js";
import { runDevelopmentBranchStep } from "./core/development-branch.js";
import { listUnappliedBranchValues } from "./core/branch-report.js";
import { printBannerCompact } from "./ui/banner.js";
import { printSummary } from "./ui/summary.js";
import { runFull } from "./commands/full.js";
import { runVersion } from "./commands/version.js";
import { runWorkflows } from "./commands/workflows.js";
import { runIssues } from "./commands/issues.js";
import { runInteractive } from "./commands/interactive.js";
import { runSkills } from "./commands/skills.js";

// Read the projectops package version (for -v/--version output). src/../package.json.
function readPkgVersion() {
  try {
    const here = dirname(fileURLToPath(import.meta.url));
    const pkg = JSON.parse(readFileSync(join(here, "..", "package.json"), "utf8"));
    return pkg.version || "unknown";
  } catch {
    return "unknown";
  }
}

// Deterministic UTC timestamp (injectable — for tests/goldens)
function utcNow(date = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  const d = `${date.getUTCFullYear()}-${p(date.getUTCMonth() + 1)}-${p(date.getUTCDate())}`;
  const t = `${p(date.getUTCHours())}:${p(date.getUTCMinutes())}:${p(date.getUTCSeconds())}`;
  return { now: `${d} ${t}`, today: d };
}

// run(argv, opts) → exitCode. opts: { cwd, source?, clock? }
//   source: for acquireTemplate (default git clone). Tests inject {type:'local', path}.
//   clock: inject {now, today} (default current UTC).
export async function run(argv, options = {}) {
  try {
    return await runCore(argv, options);
  } catch (err) {
    // Environment problems like network, git or permissions are reported as a one-line cause + action instead of a stack trace (#672).
    // The run trace was already closed in runCore's finally.
    reportFatal(err);
    return 1;
  }
}

async function runCore(argv, { cwd = process.cwd(), source = { type: "git" }, clock } = {}) {
  let opts;
  try {
    opts = parseArgs(argv);
  } catch (e) {
    if (e instanceof CliError) { console.error(e.message); return 1; }
    throw e;
  }
  // Language: --lang > PROJECTOPS_LANG > system. Non-interactive runs are pinned to English
  // so logs do not depend on the runner's locale.
  const langInfo = resolveLang({ flag: opts.lang, pinEnglish: opts.force || !process.stdout.isTTY });
  setLang(langInfo.lang, langInfo.source);
  if (opts.showVersion) { console.log(readPkgVersion()); return 0; }
  if (opts.help) { console.log(helpText()); return 0; }

  // options mode — prints the option source of truth. AI agents read it in one go without digging through docs. Read-only, no network.
  if (opts.mode === "options") {
    const { buildSchema, renderText } = await import("./core/options-schema.js");
    const schema = buildSchema(readPkgVersion());
    console.log(opts.json ? JSON.stringify(schema, null, 2) : renderText(schema));
    return 0;
  }

  // doctor mode (#558) — read-only diagnosis. Does not download the template, so it works without a network.
  if (opts.mode === "doctor") {
    const { runDoctor } = await import("./commands/doctor.js");
    await runDoctor({ cwd });
    return 0;   // A diagnosis is not a failure — ends with 0 even when there are items to look at
  }

  // skills mode — install/update/remove IDE skills (no template integration).
  // Needs the skills/ source for the Cursor copy, so it runs after fetching the template.
  if (opts.mode === "skills") {
    const tempDir = join(cwd, PATHS.tempDir);
    const interactive = !opts.force && process.stdout.isTTY;
    try {
      // skills mode: skill CLIs import scripts/common > keep it out of the exclusions (#994)
      acquireTemplate({ tempDir, source, keep: [SHARED_SCRIPTS_DIR_NAME] });
      const templateVersion = readTemplateVersion(tempDir);
      return await runSkills({ templateVersion, tempDir, interactive });
    } finally {
      remove(tempDir);
    }
  }
  // Interactive mode — run with no args or --mode interactive
  if (opts.mode === "interactive") {
    if (!process.stdout.isTTY) {
      console.error(t("cli.nonTty"));
      return 1;
    }
    return await runInteractive({}, { cwd, source, clock });
  }
  // Explicit mode without --force (the non-interactive CLI needs --force)
  if (!opts.force && !process.stdout.isTTY) {
    console.error(t("cli.needForce"));
    return 1;
  }

  // Run trace (#494/#561) — recording must start at the detect/decide steps so "why it was decided this way" is kept.
  const trace = createRunTrace();
  const recordArtifacts = opts.mode === "full" || opts.mode === "workflows";
  let disarmSignals = () => {};
  if (recordArtifacts) {
    trace.mirrorStart();
    // Even when cut off with Ctrl+C, the record up to here stays (#561). The path is settled below, but
    // a signal can come at any time, so arm with targetRoot alone first.
    disarmSignals = trace.armSignals({ targetRoot: cwd, now: "" });
  }

  // Load the existing version.yml — single source of truth for keeping version/version_code/project_paths
  const vyPath = join(cwd, "version.yml");
  const existing = existsSync(vyPath) ? parseExisting(readFileSync(vyPath, "utf8")) : null;
  trace.event("detect", "existing-install", existing ? "found" : "none", {
    templateVersion: existing?.templateVersion || null,
    version: existing?.version || null,
    types: existing?.types || null,
  });

  // Detection (CLI args first, else auto-detect — the version.yml-first rule lives inside detectTypes/detectVersion)
  const types = opts.types.length ? opts.types : detectTypes(cwd);
  trace.event("detect", "types", types.join(",") || "(none)", {
    source: opts.types.length ? "cli-flag(--type)" : "auto-detect(marker file scan)",
  });
  // version: existing version.yml first (SSoT — prevents overwriting on re-run) → CLI value → file detection
  const version = (existing?.version) || opts.version || detectVersion(cwd);
  trace.event("detect", "version", version, {
    source: existing?.version ? "version.yml(existing value kept)"
      : (opts.version ? "cli-flag(--project-version)" : "project file detection"),
  });
  const versionCode = existing?.versionCode ?? 1; // Keep the existing build number
  const branch = detectDefaultBranch(cwd);
  const repoName = detectRepoName(cwd);
  trace.event("detect", "repo", repoName || "(unknown)", { defaultBranch: branch, versionCode });
  // Settle paths (non-interactive — --paths first → saved value → single candidate automatically → root fallback)
  let cliPaths;
  try {
    cliPaths = parsePathsCsv(opts.pathsCsv);
    validatePathsMap(cliPaths, { root: cwd, types });   // #674 — filter before writing any file
  } catch (e) {
    if (e instanceof CliError) {
      console.error(e.message);
      trace.mirrorStop();
      disarmSignals();
      return 1;
    }
    throw e;
  }
  const paths = await resolveProjectPaths({
    root: cwd, types, paths: cliPaths,
    existingPaths: existing?.paths ?? new Map(), force: true, tty: false, io: {},
  });

  for (const [ty, pth] of paths) {
    // Record the basis too: "what was seen to choose that path" — the starting point for tracing a wrong path.
    const marker = markerForType(ty);
    const at = pth === "." ? marker : `${pth}/${marker}`;
    trace.event("detect", "project-path", ty, {
      path: pth,
      marker: existsSync(join(cwd, at)) ? at : `${at} (missing)`,
      source: parsePathsCsv(opts.pathsCsv).has(ty) ? "cli-flag(--paths)"
        : (existing?.paths?.has(ty) ? "version.yml(stored value)" : "marker file search"),
    });
  }

  const { now, today } = clock || utcNow();
  const tempDir = join(cwd, PATHS.tempDir);

  // Option values are decided in one place, resolve-options.js (#851) — same rules as interactive.
  const { values: resolved, sources } = resolveOptions({
    flags: {
      intent: opts.intent, deployTarget: opts.deployTarget, publishTargets: opts.publishTargets,
      includeSecretBackup: opts.includeSecretBackup, aiPrSummary: opts.aiPrSummary, projectsSync: opts.projectsSync,
      deployBranch: opts.deployBranch, deployTriggerBranch: opts.deployTriggerBranch, ciMinutesSaver: opts.ciMinutesSaver, codeReviewCoderabbit: opts.codeReviewCoderabbit,
      language: opts.language, labelStyle: opts.labelStyle,
    },
    existing, types, cwd,
  });
  const { intent, deployTarget, publishTargets } = resolved;
  const { before: beforeCleanup, applicable } = sources;
  // Multi-language store with store_locales unset: notice only (#843) — judged on the state before copying
  const storeLocalesHint = detectStoreLocalesHint({ root: cwd, existing, paths, trace });

  // Basis for settling the axes (#561) — "why this value" is the most confusing spot.
  // Records which won: CLI flag / saved value / intent derivation / type applicability cleanup.
  trace.event("resolve", "intent", String(intent ?? "(unset)"), { source: sources.intent });
  trace.event("resolve", "deploy", deployTarget, {
    source: sources.deploy,
    applicableForTypes: applicable.deploy,
    adjusted: beforeCleanup.deploy !== deployTarget
      ? `${beforeCleanup.deploy} → ${deployTarget} (not applicable to the selected types)` : null,
  });
  trace.event("resolve", "publish", publishTargets.join(",") || "(none)", {
    source: sources.publish,
    applicableForTypes: applicable.publish,
    adjusted: beforeCleanup.publish.join(",") !== publishTargets.join(",")
      ? `${beforeCleanup.publish.join(",") || "(none)"} → ${publishTargets.join(",") || "(none)"} (cleaned up, not applicable)` : null,
  });

  const context = createContext({
    mode: opts.mode, force: true, types, version, versionCode, branch, paths,
    ...resolved,
    repoName,
    // The 4 real resolvers (including spring-app-yml)
    resolvers: makeResolvers(cwd, repoName, paths),
    now, today,
  });

  // Snapshot of the final values (#561) — this one line pins down "what will be installed and how".
  trace.event("resolve", "context", opts.mode || "", {
    types, version, versionCode, branch,
    deploy: deployTarget, publish: publishTargets, intent,
    secretBackup: context.includeSecretBackup,
    changelogProvider: context.changelogProvider,
    coderabbit: context.codeReviewCoderabbit,
    deployBranch: context.deployBranch || "(not given, falls back to develop)",
    deployTriggerBranch: context.deployTriggerBranch || "(not given, the default branch)",
    recordMode: context.recordMode,
  });
  trace.event("resolve", "semver-auto", String(context.semverAuto), {
    reason: existing?.options?.semverAuto != null ? "stored value in version.yml kept"
      : (existing ? "existing integrated repo without the key, turned on by default (announced in the summary)"
                  : "new integration, true"),
  });
  trace.event("resolve", "app-release", String(context.appRelease), {
    reason: existing?.options?.appRelease != null ? "stored value in version.yml kept" : "unset (key not written)",
  });

  let result = null;
  // trace/recordArtifacts were already created above to record the detection steps (#561)
  let breakingReport = null;
  let migrationsResult = null;
  let orphanPending = [];
  // Run boundary (#561) — the log alone must show "what ran with which arguments".
  trace.event("run", "start", opts.mode || "", {
    cli: "non-interactive", types, version, branch,
    force: true, deploy: deployTarget, publish: publishTargets, intent,
  });
  try {
    trace.step("acquire-template", () => acquireTemplate({ tempDir, source }), { source: source?.type || "git" });
    context.templateVersion = readTemplateVersion(tempDir);
    trace.event("detect", "template-version", context.templateVersion, { tempDir: PATHS.tempDir });

    // Short non-interactive banner (settled in #446 — 1 line, minimal log noise)
    printBannerCompact({ version: context.templateVersion, mode: opts.mode });

    // Breaking changes gate (non-interactive warns and proceeds)
    const proceed = await trace.stepAsync("breaking-check", () => runBreakingCheck({
      cwd, tempDir, templateVersion: context.templateVersion,
      onItems: (items) => { breakingReport = items; },
    }));
    trace.event("breaking", "result", proceed ? "proceed" : "halt", { items: (breakingReport ?? []).length });
    if (!proceed) {
      trace.event("run", "cancelled", "breaking-gate", { reason: "stopped by breaking-change warning" });
      return 0;
    }

    // Legacy migration (#470) — only in modes that touch workflows. Non-interactive applies the safe tier automatically.
    if (recordArtifacts) {
      migrationsResult = await trace.stepAsync("legacy-migrations", () => runMigrations({ targetRoot: cwd, removeLegacy: opts.removeLegacy === true }));
      for (const a of migrationsResult.applied ?? []) trace.event("legacy", a.action === "error" ? "error" : "neutralized", a.from ?? a.id ?? "", { to: a.to ?? "", id: a.id ?? "" });
      for (const e of migrationsResult.confirmPending ?? []) trace.event("legacy", "leftover-old-gen", e.file, { replacement: e.replacedBy ?? "", reason: e.reason ?? "" });
    }

    // Orphan type workflow notice (#487) — non-interactive never neutralizes automatically (may be a deploy pipeline), notice only
    if (recordArtifacts) {
      const orphans = trace.step("orphan-scan",
        () => detectOrphanWorkflows({ tempDir, targetRoot: cwd, selectedTypes: types,
          // Also catch workflows that were turned off but remain and keep running (#566)
          options: { includeSecretBackup: context.includeSecretBackup, aiPrSummary: context.aiPrSummary, projectsSync: context.projectsSync, deployTarget } }),
        { selectedTypes: types });
      orphanPending = orphans.map((o) => o.filename);
      for (const o of orphans) trace.event("orphan", "detected", o.filename, { type: o.type, action: "notice only (non-interactive)" });
      for (const o of orphans) {
        console.error(t("run.orphanNotice", { type: o.type, file: o.filename }));
      }
    }

    switch (opts.mode) {
      case "full": result = trace.step("install-full", () => runFull(context, tempDir, cwd, { trace })); break;
      case "version": result = trace.step("install-version", () => runVersion(context, tempDir, cwd)); break;
      case "workflows": result = trace.step("install-workflows", () => runWorkflows(context, tempDir, cwd, { trace })); break;
      case "issues": result = trace.step("install-issues", () => runIssues(context, tempDir, cwd)); break;
      default:
        // Unknown mode → 0 copies, not an error
        break;
    }
    // Development branch creation (#715) — only with --create-development-branch. The run continues on failure (manual command shown)
    const developmentBranchResult = await runDevelopmentBranchStep({
      isRequested: opts.createDevelopmentBranch === true, targetRoot: cwd,
      branch: context.deployBranch || "develop", defaultBranch: branch, trace,
      say: (line) => console.error(line),
    });
    const isDevelopmentBranchReady = developmentBranchResult ? developmentBranchResult.status !== "failed" : null;
    // Typed branch values not applied (#1248) — after branch creation, so a branch created just now is not reported
    const unappliedBranches = recordArtifacts ? listUnappliedBranchValues({
      targetRoot: cwd, defaultBranch: branch, deployBranch: context.deployBranch, deployTriggerBranch: context.deployTriggerBranch,
      workflowsResult: result?.workflows, isBranchRecorded: result?.isBranchRecorded !== false, isNonInteractive: true, trace,
    }) : [];

    // Migration record (#493/#494) — Layer 2/3 trace files + Layer 1 guide entry
    let migrationGuidePath = null;
    // Compute the record file paths first (the guide references them) and delay the actual write until after the finish screen —
    // so the terminal mirror captures the finish screen too (#561).
    const files = recordArtifacts
      ? trace.paths({ fromVersion: existing?.templateVersion || "", toVersion: context.templateVersion, now })
      : null;
    if (recordArtifacts) {
      migrationGuidePath = appendGuideEntry(cwd, {
        now, mode: opts.mode, types, repoName,
        templateFrom: existing?.templateVersion || "", templateTo: context.templateVersion,
        options: { deploy: deployTarget, publish: publishTargets, secretBackup: context.includeSecretBackup, coderabbit: context.codeReviewCoderabbit, changelogProvider: context.changelogProvider, intent, semverAuto: context.semverAuto , appRelease: context.appRelease, language: context.language, labelStyle: context.labelStyle, closeOnRelease: context.closeOnRelease, projectsSync: context.projectsSync, excludedWorkflows: context.excludedWorkflows, storeLocales: context.storeLocales, storeLocalesIos: context.storeLocalesIos, storeLocalesPlay: context.storeLocalesPlay },
        storeLocalesHint,                                              // #843 one checklist item
        branches: { defaultBranch: branch, deployBranch: context.deployBranch || "develop", ready: isDevelopmentBranchReady,
          created: developmentBranchResult ? developmentBranchResult.status === "created" : null, result: developmentBranchResult },
        breaking: breakingReport, migrations: migrationsResult, orphans: { cleaned: [], pending: orphanPending },
        events: trace.events, counters: { skipped: result?.workflows?.skipped ?? 0 },
        traceFile: files?.traceFile ?? "", logFile: files?.logFile ?? "",
      }).guidePath;
    }

    // Finish summary (printed in CLI mode too)
    printSummary({
      mode: opts.mode, types, version, deployBranch: context.deployBranch, migrationGuidePath,
      developmentBranchResult,                                        // #715 creation result (null without the flag)
      shouldSuggestCreateBranchFlag: !developmentBranchResult,        // #715 ran without the flag, so suggest it next time
      counters: { workflows: result?.workflows?.copied ?? 0, workflowFiles: result?.workflows?.copiedFiles ?? [], utilModules: 0 },
      skippedConflicts: result?.workflows?.skippedConflicts ?? [],   // #654 merge notice
      replacedBak: result?.workflows?.replacedBak ?? [],             // #673 notice for files replaced without a reference point
      legacyLeftover: migrationsResult?.confirmPending ?? [],         // #809 notice for old and new generations running together
      notInstalled: result?.workflows?.notInstalled ?? [],            // #810 notice for workflows not installed
      branchSynced: result?.workflows?.branchSynced ?? [],            // #1248 kept files applied (branch-only diff)
      unappliedBranches, defaultBranch: branch,                       // #1248 typed branch values not applied
      semverAutoNewlyOn: sources.semverAutoNewlyOn && context.semverAuto === true, // Notice that the update turned it on
      storeLocalesHint,                                               // #843 multi-language store notice
      verification: result?.verification,   // #549 post-install verification result (only in full/workflows modes)
      // #569 — the chosen values are needed to mention only what was picked
      aiPrSummary: context.aiPrSummary, codeReviewCoderabbit: context.codeReviewCoderabbit,
      logDir: files ? MIGRATION_DIR : null,   // #561 record location notice
      logFile: files?.logFile ?? null,
      traceFile: files?.traceFile ?? null,
    }, cwd);

    trace.event("run", "end", opts.mode || "", {
      workflowsCopied: result?.workflows?.copied ?? 0,
      workflowsSkipped: result?.workflows?.skipped ?? 0,
    });
  } catch (err) {
    // Log the failure cause (#561) — like a server log, it must be easy to pinpoint afterwards.
    trace.event("run", "error", opts.mode || "", {
      message: err?.message || String(err),
      stack: String(err?.stack || "").split("\n").slice(0, 3).join(" | "),
    });
    throw err;
  } finally {
    // Leave a record however it exits (#561) — including early return, mid-run cancel and exceptions.
    // The finish screen output must be inside try so it is captured in the mirror before closing here.
    if (recordArtifacts) {
      trace.finalize({ targetRoot: cwd, fromVersion: existing?.templateVersion || "", toVersion: context.templateVersion, now });
    } else {
      trace.mirrorStop();
    }
    disarmSignals();
    remove(tempDir);
  }

  return 0;
}
