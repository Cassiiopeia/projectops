// Interactive wizard (#446 UI, 5 layers).
// Testable via io injection. A real run passes the src/ui/prompts.js functions as io.
// The new visual layers (banner/detectionLog/analysisCard/ideStatus/installKind/summary) and the low-level engine (engineIo) are
// "optional members" of io — if a stub omits one, only that layer is skipped and the run contract stays the same.
import { resolveOptions } from "../core/resolve-options.js";
import { detectStoreLocalesHint } from "../core/store-locales-hint.js";
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { PATHS } from "../core/paths.js";
import { remove } from "../core/fsutil.js";
import { acquireTemplate, readTemplateVersion } from "../core/assets.js";
import { SHARED_SCRIPTS_DIR_NAME } from "../core/ide/skills-copy.js";
import { detectTypes, detectVersion, detectDefaultBranch, detectRepoName, makeResolvers } from "../core/detect-fs.js";
import { parseExisting } from "../core/version-yml.js";
import { runBreakingCheck } from "../core/breaking-check.js";
import { runMigrations } from "../core/migrations/index.js";
import { detectOrphanWorkflows, applyOrphanCleanup } from "../core/orphan-workflows.js";
import { resolveProjectPaths, filterExcludedTypes } from "../core/paths-resolve.js";
import { askAllOptionalWorkflows, OPTION_AXES, applicableTargets } from "../core/options-ask.js";
import { createRunTrace, MIGRATION_DIR } from "../core/run-trace.js";
import { appendGuideEntry } from "../core/migration-guide.js";
import { promptEnvPlan } from "../ui/env-plan.js";
import { listWorkflowConflicts } from "../core/copy/workflows.js";
import { extractEnvValues } from "../core/wizard-env.js";
import { createContext, VALID_TYPES } from "../context.js";
import { runFull } from "./full.js";
import { runVersion } from "./version.js";
import { runWorkflows } from "./workflows.js";
import { runIssues } from "./issues.js";
import { runSkills } from "./skills.js";
import * as prompts from "../ui/prompts.js";
import { t, getLang, withLang } from "../i18n/index.js";
import { resolveLabelStyle } from "../core/label-style.js";
import { resolveRepoLanguage } from "../core/repo-language.js";
import { printSummary } from "../ui/summary.js";
import { listUnappliedBranchValues } from "../core/branch-report.js";

const CANCEL = prompts.CANCEL;
const isCancel = (v) => v === CANCEL || typeof v === "symbol";

// io default = real prompts. Tests inject a stub io.
// skills = injection point for runSkills (so tests do not touch real IDE CLIs). Default is the real runSkills.
export async function runInteractive(baseCtx, { cwd = process.cwd(), source = { type: "git" }, clock, io = prompts, skills = runSkills } = {}) {
  const tempDir = join(cwd, PATHS.tempDir);
  // Run trace (#494) — the terminal mirror is on only in the real CLI (io=prompts) (test stub io records events only).
  const trace = createRunTrace();
  // The record stays even when cut off with Ctrl+C (#561) — people often stop the interactive wizard midway.
  const disarmSignals = trace.armSignals({ targetRoot: cwd, now: clock?.now || "" });
  // Values used when recording in finally — kept outside because a cancel may come before try settles them (#561).
  let traceFrom = "";
  let traceTo = "";
  // Whether this mode leaves record files — false by default since a cancel may come before mode selection.
  let recordArtifacts = false;
  // true only when ending without a record (normal finish of version/issues modes).
  // Cancels and exceptions are recorded regardless of mode — when cut off is exactly when "how far did it get" matters most.
  let skipRecord = false;
  if (io === prompts) trace.mirrorStart();
  try {
    // Fetch the template first — the banner shows the real template version
    // Interactive also installs/updates skills at the end > keep scripts/common (#994)
    trace.step("acquire-template", () => acquireTemplate({ tempDir, source, keep: [SHARED_SCRIPTS_DIR_NAME] }), { source: source?.type || "git" });
    const templateVersion = readTemplateVersion(tempDir);
    traceTo = templateVersion;

    // Layer 1 — start banner (#446 settled mockup A). Stubs have no banner → intro fallback.
    if (io.banner) io.banner({ version: templateVersion, modeLabel: t("banner.interactive") });
    else io.intro?.(`projectops, ${t("banner.interactive")}`);

    // Existing version.yml — single source of truth for keeping version/version_code/paths/options
    const vyPath = join(cwd, "version.yml");
    const existing = existsSync(vyPath) ? parseExisting(readFileSync(vyPath, "utf8")) : null;
    traceFrom = existing?.templateVersion || "";

    // Layer 4 — current IDE skills status · Layer 5 — new vs. update (#446)
    io.installKind?.({ currentTemplateVersion: existing?.templateVersion || "", templateVersion });

    // 1) Mode selection — for an already integrated repo, show the update item at the top (#502)
    const updateInfo = existing?.templateVersion ? { from: existing.templateVersion, to: templateVersion } : null;
    // Run boundary (#561) — for interactive, what the person chose is the key record.
    trace.event("run", "start", "interactive", { templateVersion, isUpdate: !!updateInfo });
    const picked = await io.selectMode(updateInfo ? { update: updateInfo } : {});
    trace.event("prompt", "mode", String(picked ?? ""), { update: !!updateInfo });
    if (picked === CANCEL || picked == null) { trace.event("run", "cancelled", "mode-select", { reason: "user-cancel" }); io.cancelMessage?.(t("flow.cancelInstall")); return 0; }
    // Update mode (#502): re-runs the saved integration scope (templateMode, full if missing),
    // and the updateRun branches below minimize questions ("apply the saved settings as is" is the contract).
    const updateRun = picked === "update";
    const mode = updateRun ? (existing?.templateMode || "full") : picked;

    // Breaking changes gate (all modes; interactive asks for confirmation)
    let breakingReport = null; // #493 — embeds the full action steps of entries in range into the guide
    const proceed = await trace.stepAsync("breaking-check", () => runBreakingCheck({
      cwd, tempDir, templateVersion,
      askYesNo: (msg, def) => io.askYesNo(msg, def),
      onItems: (items) => { breakingReport = items; },
    }));
    if (!proceed) { trace.event("run", "cancelled", "breaking-gate", { reason: "user-declined" }); io.cancelMessage?.(t("flow.cancelBreaking")); return 0; }

    // skills mode — install IDE skills (no template integration). Runs interactively.
    if (mode === "skills") {
      io.ideStatus?.();
      await skills({ templateVersion, tempDir, interactive: true });
      io.outro?.(t("flow.doneSkills"));
      return 0;
    }

    // issues mode runs right away without gathering info
    if (mode === "issues") {
      // Existing repos keep the saved template language and label style. Starting from an empty baseCtx would make both null,
      // applying runIssues' default (en) and silently switching existing Korean repos without the key to English (#769).
      const ctx = createContext({
        ...baseCtx, mode, force: true,
        language: resolveRepoLanguage({ flag: null, stored: existing?.options?.language, existing: !!existing }),
        labelStyle: resolveLabelStyle({ flag: null, stored: existing?.options?.labelStyle, existing: !!existing }),
      });
      runIssues(ctx, tempDir, cwd);
      io.summary?.({ mode, types: [], version: "", counters: {} }, cwd);
      io.outro?.(t("flow.doneIssues"));
      return 0;
    }

    // full/version/workflows — detection (version: existing version.yml first)
    let types = detectTypes(cwd);
    // Update mode — saved types first (so re-detection does not shake the type set, #502)
    if (updateRun && existing?.types?.length) {
      const saved = existing.types.filter((t) => VALID_TYPES.includes(t));
      if (saved.length) types = saved;
    }
    let version = (existing?.version) || detectVersion(cwd);
    let branch = detectDefaultBranch(cwd);
    const repoName = detectRepoName(cwd);
    const versionCode = existing?.versionCode ?? 1; // Keep the existing build number
    // Initial option values come from resolve-options.js, same as non-interactive (#851).
    // Modes that skip questions (version, etc.) record these values as is, so they must already include the type applicability cleanup.
    const { values: init, sources: initSources } = resolveOptions({ existing, types, cwd });
    let deployTarget = init.deployTarget;
    let publishTargets = init.publishTargets;
    let includeSecretBackup = init.includeSecretBackup;
    let aiPrSummary = init.aiPrSummary;
    let codeReviewCoderabbit = init.codeReviewCoderabbit;
    let changelogProvider = init.changelogProvider;
    let changelogBaseUrl = init.changelogBaseUrl;
    let deployBranch = init.deployBranch; // #456 — not recorded when empty. Only a value picked in the question is kept
    let deployBranchReady = null; // #490 — whether the development branch was confirmed/created in this run
    let deployBranchCreated = null; // #493 — whether the wizard created it (for the guide record)
    let deployTriggerBranch = init.deployTriggerBranch; // #1248 — asked right after the development branch ("" = the default branch)
    let intent = init.intent; // #485 project nature
    // Values not asked — the saved-value rule lives in resolve-options.js
    const { semverAuto, appRelease, closeOnRelease, excludedWorkflows, storeLocales, storeLocalesIos, storeLocalesPlay, projectsSync, ciMinutesSaver } = init;
    const semverAutoNewlyOn = initSources.semverAutoNewlyOn;
    // Repo text language (#769) and label style (#776): existing repos get the English switch offered only once (below).
    let language = init.language;
    let labelStyle = init.labelStyle;
    const showOptional = mode === "full" || mode === "workflows";
    const realTty = process.stdout.isTTY === true;
    // Existing repos with Korean labels get the English standard switch offered only once (#776). If declined, Korean is saved so it is not asked again.
    // from_name in the label definitions carries over the labels attached to issues, so issue history is kept.
    if (existing && !existing.options?.labelStyle && realTty && showOptional && io.askYesNo) {
      const adopt = await io.askYesNo(t("labelStyle.propose"), false);
      labelStyle = adopt ? "en" : "ko";
    }
    if (existing && !existing.options?.language && realTty && showOptional && io.askYesNo) {
      const adopt = await io.askYesNo(t("language.propose"), false);
      language = adopt ? "en" : "ko";
    }

    // Layer 2 — detection log (#446)
    io.detectionLog?.({ types, version, branch });

    // Deploy/publish axes + secret backup questions (#439 — full/workflows only)
    if (showOptional) {
      const r = await askAllOptionalWorkflows({
        tempDir, types, targetRoot: cwd, defaultBranch: branch,
        current: {
          deploy: existing?.options?.deploy ?? null, publish: existing?.options?.publish ?? null, secretBackup: existing?.options?.secretBackup ?? null,
          codeReviewCoderabbit: existing?.options?.codeReviewCoderabbit ?? null,
          changelogProvider: existing?.options?.changelogProvider ?? null,
          changelogBaseUrl: existing?.options?.changelogBaseUrl ?? null,
          deployBranch: existing?.options?.deployBranch ?? null,
          deployTriggerBranch: existing?.options?.deployTriggerBranch ?? null,
          intent: existing?.options?.intent ?? null,
        },
        force: false, tty: realTty,
        io: {
          confirm: ({ message, initialValue }) => io.askYesNo(message, initialValue),
          select: io.engineIo?.select,
          multiselect: io.engineIo?.multiselect,
          text: io.engineIo?.text ?? (({ message }) => io.askText?.(message, "")),
        },
      });
      deployTarget = r.deploy;
      publishTargets = r.publish;
      includeSecretBackup = r.secretBackup;
      codeReviewCoderabbit = r.codeReviewCoderabbit;
      aiPrSummary = r.aiPrSummary; // #851 — was missing, so the PR summary choice was dropped
      changelogProvider = r.changelogProvider;
      changelogBaseUrl = r.changelogBaseUrl;
      deployBranch = r.deployBranch;
      deployBranchReady = r.deployBranchReady ?? deployBranchReady; // #490
      deployBranchCreated = r.deployBranchCreated ?? deployBranchCreated; // #493
      deployTriggerBranch = r.deployTriggerBranch; // #1248
      intent = r.intent;
    }

    // Confirm/edit loop — ESC means 'stay' (only an explicit 'no' exits)
    let paths = new Map();
    let confirmed = false;
    // Update mode — show the card but skip the confirm loop (#502: changing settings belongs to the existing modes)
    if (updateRun) {
      if (io.analysisCard) {
        io.analysisCard({ mode, modeLabel: t("flow.updateScope", { scope: modeLabel(mode) }), types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, paths });
      } else {
        io.note?.(summarize({ mode, types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, changelogProvider, codeReviewCoderabbit }), t("flow.title.update"));
      }
      confirmed = true;
    }
    while (!confirmed) {
      // Layer 3 — project analysis overview card (#446). Missing in stubs → note fallback.
      if (io.analysisCard) {
        io.analysisCard({ mode, modeLabel: modeLabel(mode), types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, paths });
      } else {
        io.note?.(summarize({ mode, types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, changelogProvider, codeReviewCoderabbit }), t("card.title"));
      }
      const choice = await io.confirmProjectMenu();
      if (choice === "cancel") { trace.event("run", "cancelled", "confirm-loop", { reason: "user-cancel" }); io.cancelMessage?.(t("flow.cancelInstall")); return 0; }
      if (isCancel(choice) || choice == null) continue; // ESC = stay (redraw the loop)
      if (choice === "continue") { confirmed = true; break; }
      // edit loop
      let editing = true;
      while (editing) {
        // #498 — hide deploy axis items that do not apply to the types (shown again from the next entry if types change)
        const what = await io.editMenu({ showOptional, axes: applicableTargets(types) });
        if (isCancel(what) || what === "done") { editing = false; break; }
        if (what === "type") {
          const t = await io.selectTypes(types);
          trace.event("prompt", "types", (Array.isArray(t) ? t : []).join(",") || "", { before: types });
          if (!isCancel(t) && Array.isArray(t) && t.length) {
            // When the type set really changes, reset it for path re-resolution (sorted set comparison)
            const oldSorted = [...types].sort().join(",");
            types = t.filter((x) => VALID_TYPES.includes(x));
            if ([...types].sort().join(",") !== oldSorted) paths = new Map();
          }
        } else if (what === "version") {
          const v = await io.askText(t("flow.askVersion"), version);
          if (!isCancel(v) && v !== version) {
            // semver format check
            if (/^\d+\.\d+\.\d+$/.test(v)) version = v;
            else io.note?.(t("flow.badVersion"), t("flow.badVersionTitle"));
          }
        } else if (what === "branch") {
          const b = await io.askText(t("flow.askBranch"), branch);
          if (!isCancel(b) && b) branch = b;
        } else if (OPTION_AXES.includes(what)) {
          // #483 — re-ask only the one chosen axis (scope). Other options keep their current values.
          const r = await askAllOptionalWorkflows({
            tempDir, types, targetRoot: cwd, defaultBranch: branch,
            current: {
              deploy: deployTarget, publish: publishTargets, secretBackup: includeSecretBackup,
              codeReviewCoderabbit, aiPrSummary, changelogProvider, changelogBaseUrl, deployBranch, deployTriggerBranch, intent,
            },
            force: false, tty: realTty, forceAsk: true, scope: [what],
            io: {
              confirm: ({ message, initialValue }) => io.askYesNo(message, initialValue),
              select: io.engineIo?.select,
              multiselect: io.engineIo?.multiselect,
              text: io.engineIo?.text ?? (({ message }) => io.askText?.(message, "")),
            },
          });
          deployTarget = r.deploy;
          publishTargets = r.publish;
          includeSecretBackup = r.secretBackup;
          codeReviewCoderabbit = r.codeReviewCoderabbit;
          aiPrSummary = r.aiPrSummary; // #851
          changelogProvider = r.changelogProvider;
          changelogBaseUrl = r.changelogBaseUrl;
          deployBranch = r.deployBranch;
          deployBranchReady = r.deployBranchReady ?? deployBranchReady; // #490
          deployBranchCreated = r.deployBranchCreated ?? deployBranchCreated; // #493
          deployTriggerBranch = r.deployTriggerBranch; // #1248
          intent = r.intent;
        }
      }
    }

    // Settle paths (full/version only. saved values, candidate scan, questions)
    if (mode === "full" || mode === "version") {
      paths = await resolveProjectPaths({
        root: cwd, types, paths, existingPaths: existing?.paths ?? new Map(),
        force: false, tty: realTty, io: io.engineIo ?? {},
      });
      // Type escape hatch (#487) — types excluded at the path step are dropped from version.yml, copy and env steps
      types = filterExcludedTypes(types, paths);
    } else {
      for (const t of types) if (t !== "basic" && !paths.has(t)) paths.set(t, existing?.paths.get(t) || ".");
    }

    // @wizard env plan questions (full/workflows only).
    // Skipped in update mode — new files get defaults; replaced files carry over existing values via carryover below.
    const resolvers = makeResolvers(cwd, repoName, paths);
    // Multi-language store with store_locales unset: notice only (#843) — judged on the state before copying
    const storeLocalesHint = detectStoreLocalesHint({ root: cwd, existing, paths, trace });
    let envValues = new Map(), envUseDefaults = true;
    if (showOptional && !updateRun) {
      const plan = await promptEnvPlan({
        tempDir, types, io: io.engineIo ?? null, force: false,
        resolvers, deployTarget, publishTargets, targetRoot: cwd, repoName,
      });
      envValues = plan.values;
      envUseDefaults = plan.useDefaults;
    }

    // Update mode conflict handling (#502) — one bulk confirmation (default Y: .bak backup then replace) instead of a 3-way choice per type.
    // When replacing, real env values are extracted from the existing install and carried over into the new file —
    // the key to keeping values the user filled in (FIREBASE_APP_ID, etc.) from being reset by default re-substitution.
    let updateDecisions = null;
    if (showOptional && updateRun) {
      const liteCtx = { types, paths, deployTarget, publishTargets, repoName, resolvers, branch, deployBranch, deployTriggerBranch, ciMinutesSaver };
      const conflicts = listWorkflowConflicts(liteCtx, tempDir, cwd);
      if (conflicts.length) {
        io.note?.(conflicts.map((c) => `• ${c.filename}`).join("\n"), t("flow.conflictsTitle", { count: conflicts.length }));
        const yes = await io.askYesNo(t("flow.conflictsAsk", { count: conflicts.length }), true);
        trace.event("prompt", "conflict-bulk", yes ? "backup" : "skip", { count: conflicts.length, files: conflicts.map((c) => c.filename) });
        const decision = yes === true ? "backup" : "skip";
        updateDecisions = new Map();
        for (const { filename } of conflicts) updateDecisions.set(filename, decision);
        if (decision === "backup") {
          const carried = new Map();
          for (const { filename } of conflicts) {
            const p = join(cwd, PATHS.workflowsDir, filename);
            if (!existsSync(p)) continue;
            for (const [k, v] of extractEnvValues(readFileSync(p, "utf8"))) carried.set(k, v);
          }
          if (carried.size) { envValues = carried; envUseDefaults = false; }
        }
      }
    }

    const { now, today } = clock || utcNow();
    const ctx = createContext({
      mode, force: true, types, version, versionCode, branch, paths, deployTarget, publishTargets, includeSecretBackup,
      aiPrSummary, codeReviewCoderabbit, changelogProvider, changelogBaseUrl, deployBranch, intent, semverAuto, appRelease, labelStyle, closeOnRelease, projectsSync, language, excludedWorkflows, storeLocales, storeLocalesIos, storeLocalesPlay,
      deployTriggerBranch, ciMinutesSaver,
      repoName, templateVersion, resolvers, envValues, envUseDefaults, now, today,
      // #502 — keeps version mode from downgrading an existing full record (full wins)
      recordMode: init.recordMode,
    });
    ctx.templateVersion = templateVersion;

    // 3-way choice for existing workflow conflicts — one decision per type, cached and applied to its files
    // Update mode decided in bulk above (updateDecisions), so the 3-way choice is skipped (#502).
    let hooks = updateDecisions ? { decisions: updateDecisions } : {};
    if (showOptional && io.engineIo?.select && !updateRun) {
      const conflicts = listWorkflowConflicts(ctx, tempDir, cwd);
      if (conflicts.length) {
        const perType = new Map();
        const decisions = new Map();
        for (const { filename, type } of conflicts) {
          if (!perType.has(type)) {
            const sel = await io.engineIo.select({
              message: t("flow.conflictType", { type }),
              options: [
                { value: "skip", label: t("flow.opt.skip") },
                { value: "backup", label: t("flow.opt.backup") },
                { value: "template", label: t("flow.opt.template") },
              ],
            });
            perType.set(type, isCancel(sel) || sel == null ? "skip" : sel); // ESC = skip
          }
          decisions.set(filename, perType.get(type));
        }
        hooks = { decisions };
      }
    }

    // Legacy migration (#470) — only in modes that touch workflows. Interactive confirms the safe tier once.
    let migrationsResult = null; // #493 — for the guide record
    if (mode === "full" || mode === "workflows") {
      migrationsResult = await runMigrations({
        targetRoot: cwd,
        askYesNo: (msg, def) => io.askYesNo(msg, def),
      });
      for (const a of migrationsResult.applied ?? []) trace.event("legacy", a.action === "error" ? "error" : "neutralized", a.from ?? a.id ?? "", { to: a.to ?? "", id: a.id ?? "" });
      for (const e of migrationsResult.confirmPending ?? []) trace.event("legacy", "leftover-old-gen", e.file, { replacement: e.replacedBy ?? "", reason: e.reason ?? "" });
    }

    // Orphan type workflow cleanup (#487) — leftover workflows of types dropped from the selection by a type change
    const orphanReport = { cleaned: [], pending: [] }; // #493 — for the guide record
    if (mode === "full" || mode === "workflows") {
      const orphans = detectOrphanWorkflows({ tempDir, targetRoot: cwd, selectedTypes: types,
        // Also catch workflows that were turned off but remain and keep running (#566)
        options: { includeSecretBackup, aiPrSummary: aiPrSummary !== false, projectsSync, deployTarget } });
      if (orphans.length > 0) {
        io.note?.(
          orphans.map((o) => `• ${t("flow.orphanLine", { file: o.filename, type: o.type })}`).join("\n"),
          t("flow.orphanTitle", { count: orphans.length }),
        );
        const yes = await io.askYesNo(t("flow.orphanAsk", { count: orphans.length }), true);
        trace.event("prompt", "orphan-cleanup", yes ? "clean" : "keep", { count: orphans.length });
        if (yes === true) {
          const results = applyOrphanCleanup(cwd, orphans);
          const ok = results.filter((r) => r.action === "bak");
          const failed = results.filter((r) => r.action === "error");
          orphanReport.cleaned = ok.map((r) => r.filename);
          for (const r of ok) trace.event("orphan", "neutralized", r.filename);
          io.note?.(t("flow.orphanDone", { ok: ok.length, failed: failed.length ? t("flow.orphanFailed", { count: failed.length }) : "" }), t("flow.orphanDoneTitle"));
        } else {
          orphanReport.pending = orphans.map((o) => o.filename);
        }
      }
    }

    let result = null;
    if (mode === "full") result = trace.step("install-full", () => runFull(ctx, tempDir, cwd, { ...hooks, trace }));
    else if (mode === "version") result = trace.step("install-version", () => runVersion(ctx, tempDir, cwd));
    else if (mode === "workflows") result = trace.step("install-workflows", () => runWorkflows(ctx, tempDir, cwd, { ...hooks, trace }));

    // Typed branch values not applied (#1248) — listed in the finish summary with the reason
    const unappliedBranches = (mode === "full" || mode === "workflows") ? listUnappliedBranchValues({
      targetRoot: cwd, defaultBranch: branch, deployBranch, deployTriggerBranch,
      workflowsResult: result?.workflows, isBranchRecorded: result?.isBranchRecorded !== false, trace,
    }) : [];

    // IDE skills offer after integration (gate question first, default N)
    // Update mode (#502): update only already-installed IDE skills without asking (IDEs not installed are left alone)
    if (updateRun) {
      await skills({ templateVersion, tempDir, interactive: false, installedOnly: true });
    } else {
      const wantSkills = await io.askYesNo(t("flow.askSkills"), false);
      if (wantSkills === true) { io.ideStatus?.(); await skills({ templateVersion, tempDir, interactive: true }); }
    }

    // Migration record (#493/#494) — Layer 2/3 trace files + Layer 1 guide entry (full/workflows only)
    let migrationGuidePath = null;
    recordArtifacts = mode === "full" || mode === "workflows";
    // Compute paths first and delay the actual write until after the finish screen — so the summary is captured in the terminal mirror (#561)
    const files = recordArtifacts
      ? trace.paths({ fromVersion: existing?.templateVersion || "", toVersion: templateVersion, now })
      : null;
    if (recordArtifacts) {
      migrationGuidePath = appendGuideEntry(cwd, {
        now, mode, types, repoName,
        templateFrom: existing?.templateVersion || "", templateTo: templateVersion,
        options: { deploy: deployTarget, publish: publishTargets, secretBackup: includeSecretBackup, coderabbit: codeReviewCoderabbit, changelogProvider, intent, semverAuto , appRelease, labelStyle, closeOnRelease, projectsSync, language, excludedWorkflows, storeLocales, storeLocalesIos, storeLocalesPlay },
        storeLocalesHint,                        // #843 one checklist item
        branches: { defaultBranch: branch, deployBranch, ready: deployBranchReady, created: deployBranchCreated },
        breaking: breakingReport, migrations: migrationsResult, orphans: orphanReport,
        events: trace.events, counters: { skipped: result?.workflows?.skipped ?? 0 },
        traceFile: files?.traceFile ?? "", logFile: files?.logFile ?? "",
      }).guidePath;
    }

    // Finish summary
    const summaryCtx = {
      mode, types, version, deployBranch, deployBranchReady, migrationGuidePath,
      counters: { workflows: result?.workflows?.copied ?? 0, workflowFiles: result?.workflows?.copiedFiles ?? [], utilModules: 0 },
      skippedConflicts: result?.workflows?.skippedConflicts ?? [],   // #654 merge notice
      replacedBak: result?.workflows?.replacedBak ?? [],             // #673 notice for files replaced without a reference point
      legacyLeftover: migrationsResult?.confirmPending ?? [],         // #809 notice for old and new generations running together
      notInstalled: result?.workflows?.notInstalled ?? [],            // #810 notice for workflows not installed
      branchSynced: result?.workflows?.branchSynced ?? [],            // #1248 kept files applied (branch-only diff)
      unappliedBranches, defaultBranch: branch,                       // #1248 typed branch values not applied
      semverAutoNewlyOn,
      storeLocalesHint,                        // #843 multi-language store notice
      verification: result?.verification,      // #549 install verification result
      aiPrSummary, codeReviewCoderabbit,       // #569 — mention only what was picked
      logDir: files ? MIGRATION_DIR : null,    // #561 record location notice
      logFile: files?.logFile ?? null,
      traceFile: files?.traceFile ?? null,
    };
    io.summary?.(summaryCtx, cwd);
    // The run log is English only: when the screen is in another language, add an English copy of this screen.
    if (getLang() !== "en") {
      const buf = [];
      withLang("en", () => printSummary(summaryCtx, cwd, (x) => buf.push(x)));
      trace.appendText(buf.join(""));
    }
    io.outro?.(t("flow.done", { mode }));

    // Close in finally after printing the finish screen (#561) — closing here would drop the screen below from the record.
    trace.event("run", "end", mode || "", {
      workflowsCopied: result?.workflows?.copied ?? 0,
      workflowsSkipped: result?.workflows?.skipped ?? 0,
    });
    skipRecord = !recordArtifacts;
    return 0;
  } catch (err) {
    trace.event("run", "error", "interactive", {
      message: err?.message || String(err),
      stack: String(err?.stack || "").split("\n").slice(0, 3).join(" | "),
    });
    throw err;
  } finally {
    // Leave a record however it exits (#561) — including mid-run cancel, exceptions and Ctrl+C.
    // The finish screen output must be inside try so it is captured in the mirror before closing here.
    if (skipRecord) trace.mirrorStop();
    else trace.finalize({ targetRoot: cwd, fromVersion: traceFrom, toVersion: traceTo, now: clock?.now || "" });
    disarmSignals();
    remove(tempDir);
  }
}

function summarize({ mode, types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, changelogProvider, codeReviewCoderabbit }) {
  const lines = [
    `${t("sum.mode")}: ${modeLabel(mode)}`,
    `${t("sum.types")}: ${types.join(", ")}${types.length > 1 ? t("sum.multi") : ""}`,
    `${t("card.version")}: ${version}`,
    `${t("edit.branch")}: ${branch}`,
  ];
  if (showOptional) {
    lines.push(`${t("sum.deploy")}: ${deployTarget || "docker-ssh"}`);
    lines.push(`${t("sum.publish")}: ${(publishTargets ?? []).join(",") || t("card.none")}`);
    lines.push(`${t("sum.secret")}: ${includeSecretBackup ? t("card.included") : t("card.excluded")}`);
    lines.push(`${t("sum.changelog")}: ${changelogProvider || "commit"}`);
    lines.push(`${t("sum.coderabbit")}: ${codeReviewCoderabbit ? t("sum.on") : t("sum.off")}`);
  }
  return lines.join("\n");
}

function modeLabel(m) {
  return m === "update" ? t("mode.update.short") : (t(`mode.${m}`) === `mode.${m}` ? m : t(`mode.${m}`));
}

function utcNow(date = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  const d = `${date.getUTCFullYear()}-${p(date.getUTCMonth() + 1)}-${p(date.getUTCDate())}`;
  const t = `${p(date.getUTCHours())}:${p(date.getUTCMinutes())}:${p(date.getUTCSeconds())}`;
  return { now: `${d} ${t}`, today: d };
}
