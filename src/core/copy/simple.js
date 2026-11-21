// Simple copy functions (always-overwrite kind): scripts, config, issue, discussion, setup guide.
import { join, basename } from "node:path";
import { chmodSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { PATHS } from "../paths.js";
import { exists, copyFileSync, copyDirSync } from "../fsutil.js";

// Always overwrite only the version management/release note scripts + chmod +x.
// version_manager is a .sh (delegating shim) + .py (real logic) pair — both must be copied to work (#448).
// The changelog provider ladder (5 .py files, #455) is called by the RELEASE-CHANGELOG workflow fallback-summary,
// so it must be copied too for release note generation to work in user projects.
// issue_helper.py is called by the SUH-ISSUE-HELPER workflow — must be copied with it (#478).
export function copyScripts(tempDir, targetRoot = ".") {
  const scripts = [
    "version_manager.sh", "version_manager.py",
    "changelog_manager.py",
    "truncate_release_notes.sh", "truncate_release_notes.py",
    "issue_helper.py",
    // Shared GitHub REST calls (#914). issue_helper, changelog_notice, pr_summary_comment, dispatch_downstream,
    // close_issues_on_release and store_deploy_config import it, so without it all those workflows break.
    "github_api.py",
    // Called when the release workflow merges without a PAT and then wakes follow-up workflows (#551).
    "dispatch_downstream.py",
    // Called when the AI PR SUMMARY workflow writes or updates the summary comment (#553).
    "pr_summary_comment.py",
    // Called when the QA issue bot builds its post text (#787). Language is options.language in version.yml.
    "qa_bot_messages.py",
    // Reports how the release notes were made and suggests alternatives when AI was unavailable (#566).
    "changelog_notice.py",
    // Called when the Flutter build workflow settles .env and dart-define in one place (#603).
    // Does nothing in repos without the config (.github/config/build-profile.json).
    "apply_build_profile.py",
    // Build number rules for iOS/Android test builds and iOS releases (#643). The only home of the numbering rules.
    "build_number.py",
    // Step outputs ($GITHUB_OUTPUT) + JSON result line, imported by build_number, ios_release and expo_app
    "github_output.py",
    // App Store Connect lookups (#643). Used by ios_release.py, so it must be copied with it.
    "asc_client.py",
    // iOS version pre-check, upload rejection classification, retries from archive to upload (#643).
    "ios_release.py",
    // Pure rules imported by ios_release.py (version closing, upload error classification, IPA check), copied with it (#1232).
    "ios_release_rules.py",
    // Xcode selection for Flutter iOS builds (empty = latest on the runner) and missing SDK diagnosis (#758). The only home of the selection rules.
    "select_xcode.py",
    // React Native Expo build helpers: package manager, app config, version into app.json, iOS signing files (#1240)
    "expo_app.py",
    // Closes issues labelled done when a release is merged (#771). Works only in repos with the close_on_release option on.
    "close_issues_on_release.py",
    // Reads the Play Store/TestFlight deploy mode from the code config (.github/config/store-deploy.json) (#767).
    "store_deploy_config.py",
    // Prepares store release notes per language (#829). Does nothing without store_locales in version.yml.
    "store_notes.py",
    "changelog_providers/_common.py", "changelog_providers/ladder.py",
    "changelog_providers/commit.py", "changelog_providers/copilot.py",
    "changelog_providers/openai_compatible.py",
  ];
  let copied = 0;
  for (const s of scripts) {
    const src = join(tempDir, PATHS.scriptsDir, s);
    if (exists(src)) {
      const dst = join(targetRoot, PATHS.scriptsDir, s);
      copyFileSync(src, dst);
      try { chmodSync(dst, 0o755); } catch { /* chmod is meaningless on Windows etc. */ }
      copied++;
    }
  }
  // Message catalog (#787): scripts read it at runtime. Copying the whole folder instead of a list
  // lets a translator add a single json file without changing anything else.
  const i18nSrc = join(tempDir, PATHS.scriptsDir, "i18n");
  if (exists(i18nSrc)) {
    for (const f of readdirSync(i18nSrc)) {
      if (!/\.(py|json|cjs)$/.test(f)) continue; // Skip __pycache__ etc. (cjs: workflow comment runtime)
      copyFileSync(join(i18nSrc, f), join(targetRoot, PATHS.scriptsDir, "i18n", f));
      copied++;
    }
  }
  return copied;
}

// Overwrite the whole .github/config folder. Skip if missing.
export function copyConfigFolder(tempDir, targetRoot = ".") {
  const src = join(tempDir, ".github", "config");
  if (!exists(src)) return false;
  copyDirSync(src, join(targetRoot, ".github", "config"));
  return true;
}

// Remove the assignees line from issue templates copied into the user repo (#782).
// The source names this repo's owner, who must not become the assignee of new issues in someone else's repo.
// Assignees are set by the issue helper and QA bot from version.yml settings.
// Only lines in the front matter (between the first and second ---) — the same text in the body is left alone.
// Returns repo-root relative paths of changed files. Must be called after the overlay is applied (the overlay puts it back).
export function stripIssueTemplateAssignees(targetRoot = ".") {
  const dir = join(targetRoot, ".github", "ISSUE_TEMPLATE");
  if (!exists(dir)) return [];
  const changed = [];
  for (const name of readdirSync(dir).filter((f) => f.endsWith(".md"))) {
    const file = join(dir, name);
    const text = readFileSync(file, "utf8");
    const m = text.match(/^(---\r?\n)([\s\S]*?)(\r?\n---)/);
    if (!m) continue;
    const front = m[2].split(/\r?\n/).filter((l) => !/^assignees:/.test(l)).join("\n");
    if (front === m[2]) continue;
    writeFileSync(file, text.replace(m[0], `${m[1]}${front}${m[3]}`));
    changed.push(`.github/ISSUE_TEMPLATE/${name}`);
  }
  return changed;
}

// Overwrite all of .github/ISSUE_TEMPLATE/ + PULL_REQUEST_TEMPLATE.md.
export function copyIssueTemplates(tempDir, targetRoot = ".") {
  const srcIssue = join(tempDir, ".github", "ISSUE_TEMPLATE");
  // Files starting with `projectops-` are this repo's (projectops itself) issue forms and are not copied to user repos (#797).
  if (exists(srcIssue)) copyDirSync(srcIssue, join(targetRoot, ".github", "ISSUE_TEMPLATE"), { filter: (src) => !basename(src).startsWith("projectops-") });
  const srcPr = join(tempDir, ".github", "PULL_REQUEST_TEMPLATE.md");
  if (exists(srcPr)) copyFileSync(srcPr, join(targetRoot, ".github", "PULL_REQUEST_TEMPLATE.md"));
}

// All of .github/DISCUSSION_TEMPLATE/. Skip if missing.
export function copyDiscussionTemplates(tempDir, targetRoot = ".") {
  const src = join(tempDir, ".github", "DISCUSSION_TEMPLATE");
  if (!exists(src)) return false;
  copyDirSync(src, join(targetRoot, ".github", "DISCUSSION_TEMPLATE"));
  return true;
}

// Overwrite PROJECTOPS-SETUP-GUIDE.md at the root. Skip if missing.
export const SETUP_GUIDE_NAME = "PROJECTOPS-SETUP-GUIDE.md";
export function copySetupGuide(tempDir, targetRoot = ".") {
  const src = join(tempDir, SETUP_GUIDE_NAME);
  if (!exists(src)) return false;
  copyFileSync(src, join(targetRoot, SETUP_GUIDE_NAME));
  return true;
}
