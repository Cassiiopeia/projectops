// Interactive prompt wrappers (menus, selection, questions).
// Uses an in-house node:readline engine (@clack/prompts was removed because Enter froze on Windows TTYs).
// Cancel (ESC/Ctrl+C) makes each function return the CANCEL symbol → the caller exits normally (exit 0).
import * as engine from "./readline-engine.js";
import { t } from "../i18n/index.js";
import { VALID_TYPES } from "../core/project-types.js";

export const CANCEL = engine.CANCEL;

// Mode selection — localized labels, returns the internal key. CANCEL on cancel.
// update (#502): { from, to } — when detected as an already integrated repo. Adds the update item at the top
// as the default selection (first item = default). New repos (no update passed) keep the current 5 items.
export async function selectMode({ update = null } = {}) {
  const options = [];
  if (update) {
    const range = update.from ? `v${update.from} → v${update.to}` : `v${update.to}`;
    options.push({ value: "update", label: t("mode.update", { range: `v${range}` }) });
  }
  options.push(
    { value: "full", label: t("mode.full") },
    { value: "version", label: t("mode.version") },
    { value: "workflows", label: t("mode.workflows") },
    { value: "issues", label: t("mode.issues") },
    { value: "skills", label: t("mode.skills") },
  );
  return engine.select({ message: t("mode.prompt"), options });
}

// Project confirmation screen menu (continue/edit/cancel).
export async function confirmProjectMenu() {
  return engine.select({
    message: t("confirm.prompt"),
    options: [
      { value: "continue", label: t("confirm.continue") },
      { value: "edit", label: t("confirm.edit") },
      { value: "cancel", label: t("confirm.cancel") },
    ],
  });
}

// Edit menu — which item to change. showOptional exposes nexus/secret only for full/workflows.
// axes (#498): applicableTargets(types) result — items for non-applicable axes are hidden (mobile app/basic alone, etc.).
// null shows everything as before (backward compat for test stubs).
export async function editMenu({ showOptional = false, axes = null } = {}) {
  const options = [
    { value: "type", label: t("edit.type") },
    { value: "version", label: t("edit.version") },
    { value: "branch", label: t("edit.branch") },
  ];
  if (showOptional) {
    const hasDeploy = axes == null || axes.deploy.length > 0;
    const hasPublish = axes == null || axes.publish.length > 0;
    // #485 — project nature (intent): re-selecting re-derives the deploy/publish axes. Meaningless with no axes → hidden.
    if (hasDeploy || hasPublish) options.push({ value: "intent", label: t("edit.intent") });
    // #483 — per-item isolation: pick one axis and re-ask only that axis (splits the all-in-one "deploy/publish method")
    if (hasDeploy) options.push({ value: "deploy", label: t("edit.deploy") });
    if (hasPublish) options.push({ value: "publish", label: t("edit.publish") });
    options.push({ value: "code-review", label: t("edit.codeReview") });
    options.push({ value: "changelog", label: t("edit.changelog") });
    options.push({ value: "release-branch", label: t("edit.releaseBranch") });
    options.push({ value: "secret", label: t("edit.secret") });
  }
  options.push({ value: "done", label: t("edit.done") });
  return engine.select({ message: t("edit.prompt"), options });
}

// Type multiselect.
export async function selectTypes(current = []) {
  const all = VALID_TYPES;
  return engine.multiselect({
    message: t("types.prompt"),
    options: all.map((t) => ({ value: t, label: t })),
    initialValues: current.length ? current : ["basic"],
    required: true,
  });
}

// Text input (empty input = keep default).
export async function askText(message, defaultValue = "") {
  const v = await engine.text({ message, defaultValue });
  if (v === CANCEL) return CANCEL;
  return v === "" || v == null ? defaultValue : v;
}

// Yes/no.
export async function askYesNo(message, initial = true) {
  return engine.confirm({ message, initialValue: initial });
}

// Banner and notice output.
export function intro(text) { engine.intro(text); }
export function outro(text) { engine.outro(text); }
export function note(text, title) { engine.note(text, title); }
export function cancelMessage(text = "Cancelled.") { engine.cancelMessage(text); }

// ── #446 first-screen UI 5 layers + SP2-C interactive layer real io ─────────────────
// runInteractive calls io.<method>?.() optionally — test stubs omit these methods
// to skip the visual layers and env questions (the run contract is the same).
import { printBanner as _printBanner } from "./banner.js";
import {
  printDetectionLog as _detLog, printAnalysisCard as _card,
  printIdeStatus as _ideStatus, printInstallKind as _installKind, collectIdeStatuses,
} from "./status-cards.js";
import { printSummary as _summary } from "./summary.js";
import { defaultIo } from "../core/ide/runner.js";

export function banner(info) { _printBanner(info); }
export function detectionLog(info) { _detLog(info); }
export function analysisCard(info) { _card(info); }
export function installKind(info) { _installKind(info); }
export function ideStatus() { _ideStatus(collectIdeStatuses(defaultIo())); }
export function summary(ctx, targetRoot) { _summary(ctx, targetRoot); }

// Low-level engine io used by the env plan, path resolution and conflict menus (the io contract of env-plan/paths-resolve)
export const engineIo = {
  select: engine.select,
  multiselect: engine.multiselect,
  text: engine.text,
  confirm: engine.confirm,
};
