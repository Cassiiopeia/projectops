// issues 모드 (.sh execute_integration issues case 등가) — template_integrator.sh 4532~4535.
// 이슈/PR 템플릿 + Discussion 템플릿만 복사.
import { applyLabelStyle } from "../core/label-style.js";
import { applyRepoLanguage } from "../core/repo-language.js";
import { t } from "../i18n/index.js";
import { copyIssueTemplates, copyDiscussionTemplates } from "../core/copy/simple.js";

export function runIssues(context, tempDir, targetRoot = ".") {
  copyIssueTemplates(tempDir, targetRoot);
  const { failed } = applyRepoLanguage(tempDir, targetRoot, context.language ?? "en"); // #769 — 라벨 변환보다 먼저
  if (failed.length) console.error(t("language.overlayFailed", { n: failed.length, files: failed.map((f) => f.file).join(", ") }));
  applyLabelStyle(targetRoot, context.labelStyle ?? "en"); // #776
  copyDiscussionTemplates(tempDir, targetRoot);
}
