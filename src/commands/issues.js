// issues 모드 (.sh execute_integration issues case 등가) — template_integrator.sh 4532~4535.
// 이슈/PR 템플릿 + Discussion 템플릿만 복사.
import { applyLabelStyle } from "../core/label-style.js";
import { copyIssueTemplates, copyDiscussionTemplates } from "../core/copy/simple.js";

export function runIssues(context, tempDir, targetRoot = ".") {
  copyIssueTemplates(tempDir, targetRoot);
  applyLabelStyle(targetRoot, context.labelStyle ?? "en"); // #776
  copyDiscussionTemplates(tempDir, targetRoot);
}
