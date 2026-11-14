// version mode (generate/update version.yml).
// Order: version.yml → readme → scripts → config → gitignore → setup_guide.
// (No workflow copy → no deploy block. No util, issue or coderabbit either.)
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { writeText } from "../core/fsutil.js";
import { PATHS } from "../core/paths.js";
import { installAgentGuide } from "../core/agent-guide.js";
import { buildVersionYml, mergeDeployValues, resolveUpdatedBy, customYml } from "../core/version-yml.js";
import { markerForType } from "../core/detect.js";
import { addVersionSectionToReadme } from "../core/copy/readme.js";
import { applyLabelStyle } from "../core/label-style.js";
import { copyScripts, copyConfigFolder, copySetupGuide } from "../core/copy/simple.js";
import { ensureGitignore } from "../core/copy/gitignore.js";
import { toTemplateOptions } from "../core/resolve-options.js";

export function runVersion(context, tempDir, targetRoot = ".") {
  // Option values are decided by resolveOptions and put in context — defaults are not picked again here
  const { version, types = [], paths = new Map(), branch = "main", versionCode = 1,
    now, today, templateVersion, deployBranch = "", recordMode = "version", labelStyle } = context;

  const pathMarkers = new Map();
  for (const [t] of paths) pathMarkers.set(t, markerForType(t));

  // version.yml is fully regenerated, so without reading it, deploy values left by a previous integration (including user edits) vanish (#670)
  const vyFile = join(targetRoot, PATHS.versionFile);
  const deployValues = mergeDeployValues(existsSync(vyFile) ? readFileSync(vyFile, "utf8") : "", new Map());

  writeText(vyFile,
    buildVersionYml({
      version, types, paths, pathMarkers, branch, deployBranch, versionCode, now, today,
      deployValues,
      // Keep keys the generator does not know (issue_helper, etc.) — version.yml is rewritten every time, so otherwise they vanish on every update (#835)
      ...customYml(vyFile),
      updatedBy: resolveUpdatedBy(existsSync(vyFile) ? readFileSync(vyFile, "utf8") : "", targetRoot), // #811
      // mode (#502): so version mode does not downgrade an existing full integration record to "version",
      // the caller passes the existing value as recordMode (full wins — prevents shrinking the update re-run scope).
      templateOptions: toTemplateOptions(context, { mode: recordMode, optionsDate: today }),
    }));
  addVersionSectionToReadme(version, targetRoot, context.language);
  copyScripts(tempDir, targetRoot);
  copyConfigFolder(tempDir, targetRoot);
  applyLabelStyle(targetRoot, labelStyle); // #776
  ensureGitignore(targetRoot);
  copySetupGuide(tempDir, targetRoot);
  installAgentGuide(targetRoot, templateVersion);
}
