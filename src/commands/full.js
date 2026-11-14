// full mode orchestrator.
// Copy order: version.yml → readme → workflows → (deploy block) → scripts → config →
//            util (per type) → issue → discussion → coderabbit → gitignore → setup_guide → (save options)
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { writeText } from "../core/fsutil.js";
import { PATHS } from "../core/paths.js";
import { installAgentGuide } from "../core/agent-guide.js";
import { buildVersionYml, mergeDeployValues, resolveUpdatedBy, customYml } from "../core/version-yml.js";
import { markerForType } from "../core/detect.js";
import { addVersionSectionToReadme } from "../core/copy/readme.js";
import { copyWorkflows } from "../core/copy/workflows.js";
import {
  copyScripts, copyConfigFolder, copyIssueTemplates, stripIssueTemplateAssignees,
  copyDiscussionTemplates, copySetupGuide,
} from "../core/copy/simple.js";
import { copyUtilModules } from "../core/copy/util.js";
import { copyCoderabbit } from "../core/copy/coderabbit.js";
import { ensureGitignore } from "../core/copy/gitignore.js";
import { applyLabelStyle } from "../core/label-style.js";
import { applyRepoLanguage } from "../core/repo-language.js";
import { t } from "../i18n/index.js";
import { verifyInstall } from "../core/verify.js";
import { toTemplateOptions } from "../core/resolve-options.js";

// context: { version, types, paths:Map, branch, versionCode, deployTarget, publishTargets, includeSecretBackup,
//            force, repoName, resolvers, now, today }
// tempDir: the fetched template. targetRoot: the integration target.
export function runFull(context, tempDir, targetRoot = ".", hooks = {}) {
  // Option values are decided by resolveOptions and put in context — defaults are not picked again here
  const { version, types = [], paths = new Map(), branch = "main", versionCode = 1,
    force = true, now, today, templateVersion, deployBranch = "",
    deployTarget, publishTargets, codeReviewCoderabbit, labelStyle, language } = context;

  // project_paths marker computation (main marker names)
  const pathMarkers = new Map();
  for (const [t] of paths) pathMarkers.set(t, markerForType(t));

  // 3. Copy workflows (+ env substitution) — collects the ask values for the deploy block.
  //    hooks.decisions: Map of interactive 3-way conflict decisions (unset = skip — current force behavior)
  const step = (name, fn, d) => (hooks.trace ? hooks.trace.step(name, fn, d) : fn());
  const wfCounters = step("copy-workflows", () => copyWorkflows(context, tempDir, targetRoot, hooks),
    { types, deploy: deployTarget, publish: publishTargets });
  // Keep the deploy values of the existing version.yml (#670) — it is fully regenerated, so without reading them user edits vanish.
  const vyFile = join(targetRoot, PATHS.versionFile);
  const deployValues = mergeDeployValues(existsSync(vyFile) ? readFileSync(vyFile, "utf8") : "",
    wfCounters.deployValues || new Map()); // Map<type, Map<key,value>

  // 1. Generate version.yml (full regeneration — metadata → deploy → template order)
  step("write-version-yml", () => writeText(join(targetRoot, PATHS.versionFile),
    buildVersionYml({
      version, types, paths, pathMarkers, branch, deployBranch, versionCode, now, today,
      deployValues,
      // Keep keys the generator does not know (issue_helper, etc.) — version.yml is rewritten every time, so otherwise they vanish on every update (#835)
      ...customYml(vyFile),
      updatedBy: resolveUpdatedBy(existsSync(vyFile) ? readFileSync(vyFile, "utf8") : "", targetRoot), // #811
      templateOptions: toTemplateOptions(context, { mode: "full", optionsDate: today }),
    })), { version, versionCode });

  // 2. README version section
  step("update-readme", () => addVersionSectionToReadme(version, targetRoot, language), { version });

  // 5. scripts / config
  //    Areas outside workflows are recorded too (#561) — so the log alone shows "were my scripts updated".
  step("copy-scripts", () => copyScripts(tempDir, targetRoot));
  step("copy-config", () => copyConfigFolder(tempDir, targetRoot));

  // 6. util (per type)
  for (const t of types) step("copy-util", () => copyUtilModules(tempDir, t, { force }, targetRoot), { type: t });

  // 7. issue / discussion templates
  step("copy-templates", () => {
    copyIssueTemplates(tempDir, targetRoot);
    // Discussion templates are overlay targets too (#988) — must be copied before the overlay so the Korean version covers them
    copyDiscussionTemplates(tempDir, targetRoot);
    // Template language (#769) — the source is English, so Korean repos are covered by the overlay right after copying.
    // Must come before the label style conversion (apply-label-style).
    const { changed: overlaid, failed: overlayFailed } = applyRepoLanguage(tempDir, targetRoot, language);
    hooks.trace?.event("copy", "repo-language", language, { overlaid: overlaid.length, failed: overlayFailed.length });
    for (const f of overlayFailed) hooks.trace?.event("copy", "overlay-failed", f.file, { reason: f.error });
    // Remove the fixed assignee (#782) — done after the overlay, since the overlay puts it back.
    hooks.trace?.event("copy", "strip-assignees", "", { files: stripIssueTemplateAssignees(targetRoot).length });
    if (overlayFailed.length) console.error(t("language.overlayFailed", { n: overlayFailed.length, files: overlayFailed.map((f) => f.file).join(", ") }));
  });

  // 8. coderabbit / gitignore / setup guide
  //    If CodeRabbit code review is not used (#457), .coderabbit.yaml is not copied.
  step("copy-coderabbit", () => copyCoderabbit(tempDir, { force, enabled: codeReviewCoderabbit }, targetRoot),
    { enabled: codeReviewCoderabbit });
  step("ensure-gitignore", () => ensureGitignore(targetRoot));
  step("copy-setup-guide", () => copySetupGuide(tempDir, targetRoot));
  step("install-agent-guide", () => installAgentGuide(targetRoot, templateVersion)); // Tells agents how to check options

  // Status label style (#776) — the template source is English, so Korean repos rename back after copying is done.
  step("apply-label-style", () => applyLabelStyle(targetRoot, labelStyle), { labelStyle });

  // 9. Post-install verification (#549) — rereads the final result written to disk.
  //    Substitution happens scattered per file and auto tokens depend on resolver results,
  //    so looking at the final content is the only way to see what will actually deploy.
  const verification = step("verify-install", () => verifyInstall(targetRoot));
  // Mind the detail key names: the run-trace sensitive value guard filters pat|token|secret|password|credential
  // out of keys (#494). These values are not secrets but "substitution placeholder names" and
  // "key names that need registering", so names that do not trip the guard are used — the guard itself is not bypassed.
  hooks.trace?.event("verify", "scan", "", {
    unresolved: verification.unresolved.length,
    requiredKeys: verification.secrets.size,
  });
  // Unreplaced values are spots that will fail at deploy time — log which file and line.
  for (const u of verification.unresolved) {
    hooks.trace?.event("verify", "unresolved", u.filename, { line: u.line, placeholder: u.token });
  }
  for (const [name, users] of verification.secrets) {
    hooks.trace?.event("verify", "required-key", name, { workflows: users });
  }

  return { workflows: wfCounters, verification };
}
