// Completion summary, printed to stderr after an install.
// ctx: { mode, types:[], version, counters:{ workflows, workflowFiles, utilModules }, ... }
// All wording lives in src/i18n/summary.*.js so the screen follows the display language.
import { existsSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { WORKFLOW_COMMON_PREFIX } from "../core/paths.js";
import { t } from "../i18n/index.js";

const SEPARATOR = "────────────────────────────────────────";

export function printSummary(ctx, targetRoot = ".", write = null) {
  const { mode, types = [], version = "", counters = {} } = ctx || {};
  const deployBranchName = ctx?.deployBranch || "develop";
  const deployBranchReady = ctx?.deployBranchReady === true; // the wizard confirmed or created it in this run
  const err = (s = "") => (write ? write(`${s}\n`) : process.stderr.write(`${s}\n`));
  // Colors only on a TTY.
  const isTty = write ? false : !!process.stderr.isTTY;
  const BOLD = isTty ? "\u001b[1m" : "";
  const YELLOW = isTty ? "\x1b[1;33m" : "";
  const CYAN = isTty ? "\x1b[0;36m" : "";
  const NC = isTty ? "\x1b[0m" : "";
  const utilModulesCopied = counters.utilModules ?? 0;
  // Without a README the version section is skipped, so do not claim it was added or auto-updated.
  const hasReadme = existsSync(join(targetRoot, "README.md"));

  err("");
  err(SEPARATOR);
  err("");
  err(t("done.title"));
  err("");
  err(SEPARATOR);
  err("");
  err(t("done.integrated"));

  switch (mode) {
    case "full":
      err(`  ✅ ${t("done.feat.version")}`);
      if (hasReadme) err(`  ✅ ${t("done.feat.readme")}`);
      err(`  ✅ ${t("done.feat.workflows")}`);
      if (utilModulesCopied > 0) err(`  ✅ ${t("done.feat.util", { count: utilModulesCopied })}`);
      err(`  ✅ ${t("done.feat.templates")}`);
      err(`  ✅ ${t("done.feat.coderabbit")}`);
      err(`  ✅ ${t("done.feat.gitignore")}`);
      err(`  ✅ ${t("done.feat.guide")}`);
      break;
    case "version":
      err(`  ✅ ${t("done.feat.version")}`);
      if (hasReadme) err(`  ✅ ${t("done.feat.readme")}`);
      err(`  ✅ ${t("done.feat.gitignore")}`);
      err(`  ✅ ${t("done.feat.guide")}`);
      break;
    case "workflows":
      err(`  ✅ ${t("done.feat.workflows")}`);
      if (utilModulesCopied > 0) err(`  ✅ ${t("done.feat.util", { count: utilModulesCopied })}`);
      err(`  ✅ ${t("done.feat.guide")}`);
      break;
    case "issues":
      err(`  ✅ ${t("done.feat.templates")}`);
      break;
    case "skills":
      err(`  ✅ ${t("done.feat.skills")}`);
      break;
  }

  // Skills mode adds no files or workflows, so the screen ends here.
  if (mode === "skills") {
    err("");
    err(`  📖 TEMPLATE REPO: https://github.com/Cassiiopeia/projectops`);
    err("");
    err(SEPARATOR);
    err("");
    return;
  }

  err("");
  err(t("done.addedFiles"));
  err(`  📄 ${t("done.versionYml", { version, types: types.join(",") })}`);
  err(`  📝 ${hasReadme ? t("done.readmeAdded") : t("done.readmeMissing")}`);
  err("");
  err(t("done.addedWorkflows"));

  // Only files the copy engine actually wrote are listed (copiedFiles is the single source).
  const copiedFiles = counters.workflowFiles ?? [];
  const commonWorkflows = copiedFiles.filter((f) => f.startsWith(`${WORKFLOW_COMMON_PREFIX}-`));
  const typeWorkflows = copiedFiles.filter((f) => !f.startsWith(`${WORKFLOW_COMMON_PREFIX}-`));

  if (copiedFiles.length > 0) {
    err(`  📦 ${t("done.installedCount", { count: copiedFiles.length })}`);
    for (const wf of commonWorkflows) err(`     📌 ${wf}`);
    for (const wf of typeWorkflows) err(`     🎯 ${wf}`);
  } else {
    err(`  📦 ${t("done.noneInstalled")}`);
  }

  // Workflows the user modified are kept as-is: say what differs and how to merge.
  const kept = ctx?.skippedConflicts ?? [];
  if (kept.length > 0) {
    err("");
    err(`  ${YELLOW}✋ ${t("done.keptTitle", { count: kept.length })}${NC}`);
    for (const k of kept) {
      const cnt = k.added != null && k.removed != null ? ` (${t("done.keptDiff", { added: k.added, removed: k.removed })})` : "";
      err(`     📝 ${k.filename}${cnt}`);
      if (k.incoming) {
        err(`        diff -u .github/workflows/${k.filename} ${k.incoming}`);
        err(`        git diff --no-index .github/workflows/${k.filename} ${k.incoming}`);
      }
    }
    if (kept.some((k) => k.incoming)) {
      err(`     💡 ${t("done.keptHint1")}`);
      err(`        ${t("done.keptHint2")}`);
    }
  }

  // No baseline to tell whether the file was edited: it was replaced and the original kept as .bak.
  const replaced = ctx?.replacedBak ?? [];
  if (replaced.length > 0) {
    err("");
    err(`  ${YELLOW}⚠️  ${t("done.replacedTitle", { count: replaced.length })}${NC}`);
    for (const f of replaced) err(`     💾 .github/workflows/${f}.bak`);
    err(`     ${t("done.replacedHint")}`);
  }

  // Retired old-generation workflows still installed: they run next to their replacements (#809).
  const legacy = ctx?.legacyLeftover ?? [];
  if (legacy.length > 0) {
    err("");
    err(`  ${YELLOW}⚠️  ${t("done.legacyTitle", { count: legacy.length })}${NC}`);
    for (const e of legacy) {
      err(`     🗑️  ${e.file}${e.replacedBy ? `  →  ${e.replacedBy}` : ""}`);
      err(`        git rm .github/workflows/${e.file}`);
    }
    err(`     ${t("done.legacyHint")}`);
  }

  err("");
  err("  🔧 .github/scripts/");
  err("     ├─ version_manager.sh");
  err("     └─ changelog_manager.py");
  err("");

  if (utilModulesCopied > 0) {
    err(`  🧙 ${t("done.utilTitle")}`);
    for (const type of types) {
      const utilDir = join(targetRoot, ".github/util", type);
      if (!existsSync(utilDir)) continue;
      let entries = [];
      try { entries = readdirSync(utilDir, { withFileTypes: true }); } catch { /* ignore */ }
      for (const e of entries) {
        if (e.isDirectory()) err(`     ├─ ${e.name} (${type})`);
      }
    }
    err("");
  }

  if (types.includes("spring")) {
    err(`  💡 ${t("done.spring.title")}`);
    err(`     • ${t("done.spring.1")}`);
    err(`     • ${t("done.spring.2")}`);
    err(`     • ${t("done.spring.3")}`);
    err("");
  }
  if (types.includes("flutter") && utilModulesCopied > 0) {
    err(`  💡 ${t("done.flutter.title")}`);
    err("     • iOS TestFlight: .github/util/flutter/testflight-wizard/testflight-wizard.html");
    err("     • Android Play Store: .github/util/flutter/playstore-wizard/playstore-wizard.html");
    err("     • Firebase App Distribution: .github/util/flutter/firebase-wizard/firebase-wizard.html");
    err(`     • ${t("done.flutter.open")}`);
    err("");
  }

  err("  📖 TEMPLATE REPO: https://github.com/Cassiiopeia/projectops");
  err(`  📚 ${t("done.workflowGuide")}: .github/workflows/project-types/README.md`);

  // Post-install verification: expand only when something is wrong, one line otherwise.
  const verification = ctx?.verification;
  if (verification) {
    const unresolved = verification.unresolved || [];
    err(SEPARATOR);
    err("");
    if (unresolved.length === 0) {
      err(`✅ ${t("done.verify.ok")}`);
    } else {
      err(`${YELLOW}⚠️  ${t("done.verify.bad", { count: unresolved.length })}${NC}`);
      err("");
      err(`   ${t("done.verify.explain1")}`);
      err(`   ${t("done.verify.explain2")}`);
      err("");
      for (const u of unresolved.slice(0, 10)) {
        err(`   ${u.filename}:${u.line}  ${u.token}`);
      }
      if (unresolved.length > 10) err(`   ${t("done.verify.more", { count: unresolved.length - 10 })}`);
    }
    err("");

    // Secrets needed by the installed workflows only.
    const secrets = verification.secrets;
    if (secrets && secrets.size > 0) {
      err(`${CYAN}🔑 ${t("done.secrets.title", { count: secrets.size })}${NC}`);
      err("   → Repository Settings > Secrets and variables > Actions");
      err("");
      for (const [name, users] of secrets) {
        const where = users.length > 2 ? t("done.secrets.more", { list: users.slice(0, 2).join(", "), count: users.length - 2 }) : users.join(", ");
        err(`   ${name}`);
        err(`     └ ${where}`);
      }
      err("");
      err(`   💡 ${t("done.secrets.hint")}`);
      err("");
    }
  }

  err(SEPARATOR);
  err("");
  err(`${YELLOW}⚠️  ${t("done.todo.title")}${NC}`);
  err("");
  // A PAT is optional: releases complete without it, it only makes follow-up automation smoother.
  err(`  1️⃣  ${t("done.todo.pat")}`);
  err(`     → ${t("done.todo.pat1")}`);
  err(`        ${t("done.todo.pat2")}`);
  err("     → Repository Settings > Secrets > Actions");
  err("     → Secret Name: _GITHUB_PAT_TOKEN / Scopes: repo, workflow");
  err("");
  // Do not re-instruct a task the wizard already did.
  if (deployBranchReady) {
    err(`  2️⃣  ✅ ${t("done.todo.branchReady", { branch: deployBranchName })}`);
  } else {
    err(`  2️⃣  ${t("done.todo.branch", { branch: deployBranchName })}`);
    err(`     → git checkout -b ${deployBranchName} && git push -u origin ${deployBranchName}`);
  }
  err("");
  // Only explain what the user selected: instructions for a disabled feature blur what to do.
  let step = 3;
  if (ctx?.aiPrSummary !== false) {
    err(`  ${step}️⃣  ${t("done.todo.ai")}`);
    err(`     → ${t("done.todo.ai1")}`);
    err(`        ${t("done.todo.ai2")}`);
    err("");
    err(`     ① ${t("done.todo.aiKey")}`);
    err("        https://aistudio.google.com/apikey");
    err(`     ② ${t("done.todo.aiRegister")}`);
    err("        Settings > Secrets and variables > Actions > New repository secret");
    err(`        ${BOLD}Name: GEMINI_API_KEY${NC}   Secret: ${t("done.todo.aiSecret")}`);
    err("");
    err(`     💡 ${t("done.todo.aiOthers")}`);
    err("        OPENAI_API_KEY, ANTHROPIC_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY");
    err("");
    step++;
  }
  if (ctx?.codeReviewCoderabbit === true) {
    err(`  ${step}️⃣  ${t("done.todo.coderabbit")}`);
    err(`     → ${t("done.todo.coderabbit1")}`);
    err(`     → ${t("done.todo.coderabbit2")}`);
    err(`     → ${t("done.todo.coderabbit3")}`);
    err("");
    step++;
  }
  // Label sync only runs on pushes that change issue-labels.yml, and the first push after install can miss it.
  // Status labels missing means label automation is silently ignored, so ask for one manual run.
  err(`  ${step}️⃣  ${t("done.todo.labels")}`);
  err(`     → ${t("done.todo.labels1")}`);
  err(`     → ${t("done.todo.labels2")}`);
  err("");
  step++;
  err(SEPARATOR);
  err("");
  err(`${CYAN}📖 ${t("done.guide")}${NC}`);
  err("   → PROJECTOPS-SETUP-GUIDE.md");
  err("");
  // The run record goes last: with a long secret list the top scrolls away, and this is the first thing people need when something breaks.
  if (ctx?.logFile || ctx?.logDir || ctx?.migrationGuidePath) {
    err(`${CYAN}📁 ${t("done.log.title")}${NC}`);
    if (ctx?.logFile || ctx?.logDir) {
      err(`   ${t("done.log.log")}: ${ctx.logFile || `${ctx.logDir}/`}`);
      if (ctx.traceFile) err(`   ${t("done.log.events")}: ${ctx.traceFile}`);
    }
    if (ctx?.migrationGuidePath) err(`   ${t("done.log.guide")}: ${ctx.migrationGuidePath}`);
    err(`   ${t("done.log.note")}`);
    err(`   💡 ${t("done.log.ask")}`);
    err("");
  }
}
