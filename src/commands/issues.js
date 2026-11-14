// issues mode (installs issue/PR templates only).
// Copies only issue/PR templates + Discussion templates.
import { applyLabelStyle } from "../core/label-style.js";
import { applyRepoLanguage } from "../core/repo-language.js";
import { t } from "../i18n/index.js";
import { copyIssueTemplates, copyDiscussionTemplates, stripIssueTemplateAssignees } from "../core/copy/simple.js";

export function runIssues(context, tempDir, targetRoot = ".") {
  copyIssueTemplates(tempDir, targetRoot);
  copyDiscussionTemplates(tempDir, targetRoot); // #988 — overlay and label conversion targets, so before them
  const { failed } = applyRepoLanguage(tempDir, targetRoot, context.language ?? "en"); // #769 — before the label conversion
  if (failed.length) console.error(t("language.overlayFailed", { n: failed.length, files: failed.map((f) => f.file).join(", ") }));
  stripIssueTemplateAssignees(targetRoot); // #782 — the overlay puts it back, so after it
  applyLabelStyle(targetRoot, context.labelStyle ?? "en"); // #776
}
