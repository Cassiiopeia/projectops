// issues 모드 (이슈·PR 템플릿만 설치).
// 이슈/PR 템플릿 + Discussion 템플릿만 복사.
import { applyLabelStyle } from "../core/label-style.js";
import { applyRepoLanguage } from "../core/repo-language.js";
import { t } from "../i18n/index.js";
import { copyIssueTemplates, copyDiscussionTemplates, stripIssueTemplateAssignees } from "../core/copy/simple.js";

export function runIssues(context, tempDir, targetRoot = ".") {
  copyIssueTemplates(tempDir, targetRoot);
  copyDiscussionTemplates(tempDir, targetRoot); // #988 — 오버레이·라벨 변환 대상이라 그보다 먼저
  const { failed } = applyRepoLanguage(tempDir, targetRoot, context.language ?? "en"); // #769 — 라벨 변환보다 먼저
  if (failed.length) console.error(t("language.overlayFailed", { n: failed.length, files: failed.map((f) => f.file).join(", ") }));
  stripIssueTemplateAssignees(targetRoot); // #782 — 오버레이가 다시 넣으므로 그 뒤에
  applyLabelStyle(targetRoot, context.labelStyle ?? "en"); // #776
}
