// Status layers shown around the start screen: detection log, summary card, IDE status, install kind.
// (The Breaking Changes box lives in core/breaking-check.js.)
// All text goes through t() so it follows the display language; markers and ids stay as-is.
import { A, paint, padEndVisual } from "./ansi.js";
import { ADAPTERS } from "../core/ide/registry.js";
import { markerForType } from "../core/detect.js";
import { t } from "../i18n/index.js";

const GUT = paint("│", A.gray);
const HEAD = paint("◆", A.cyan);
const OK = paint("✓", A.green);

// Detection log: one line per detected type, then version and branch.
export function printDetectionLog({ types = [], version = "", branch = "" }, out = (s) => process.stdout.write(s)) {
  out(`${paint("┌", A.gray)}  ${t("detect.title")}\n`);
  if (types.length && !(types.length === 1 && types[0] === "basic")) {
    for (const type of types) {
      const marker = markerForType(type);
      const name = paint(type, A.bold);
      out(`${GUT}  ${OK} ${marker ? t("detect.found", { marker, type: name }) : t("detect.foundNoMarker", { type: name })}\n`);
    }
  } else {
    out(`${GUT}  ${paint("-", A.dim)} ${t("detect.none")}\n`);
  }
  out(`${GUT}  ${OK} ${t("detect.versionBranch", { version: paint(version, A.green), branch: paint(branch, A.green) })}\n`);
  out(`${GUT}\n`);
}

// Summary card shown before the "continue?" menu: what is about to be installed.
export function printAnalysisCard({ mode = "", modeLabel = "", types = [], version = "", branch = "",
  deployTarget = null, publishTargets = null, includeSecretBackup = null, paths = new Map(), showOptional = false },
  out = (s) => process.stdout.write(s)) {
  out(`${HEAD}  ${paint(t("card.title"), A.bold)}\n`);
  // Labels are padded by visual width (CJK counts as 2 columns) so values line up in both languages.
  const row = (label, value) => out(`${GUT}  ${padEndVisual(label, 14)} ${value}\n`);
  row(types.length > 1 ? t("card.typeMulti") : t("card.type"), paint(types.join(", ") || "basic", A.bold));
  row(t("card.version"), paint(`v${version}`, A.green));
  row(t("card.branch"), branch);
  if (modeLabel || mode) row(t("card.mode"), modeLabel || mode);
  if (showOptional) {
    row(t("card.deploy"), paint(deployTarget || "docker-ssh", A.bold));
    const pub = (publishTargets ?? []).join(",");
    row(t("card.publish"), pub ? paint(pub, A.green) : paint(t("card.none"), A.dim));
    row(t("card.secret"), includeSecretBackup === true ? paint(t("card.included"), A.green) : paint(t("card.excluded"), A.dim));
  }
  // Monorepo paths: shown only when at least one type is not at the repository root.
  const nonRoot = [...paths.entries()].filter(([, p]) => p && p !== ".");
  if (nonRoot.length) {
    row(t("card.paths"), [...paths.entries()].map(([type, p]) => `${type}→${p}`).join(", "));
  }
  out(`${GUT}\n`);
}

// IDE skills: ask every adapter what it sees (adapters never throw by contract).
export function collectIdeStatuses(io) {
  return ADAPTERS.map((a) => {
    let st;
    try { st = a.detect(io); } catch { st = { installed: false, version: null, cliMissing: true, note: t("ide.detectFailed") }; }
    return { id: a.id, label: a.label, ...st };
  });
}

export function printIdeStatus(statuses, out = (s) => process.stdout.write(s)) {
  if (!statuses?.length) return;
  out(`${HEAD}  ${paint(t("ide.title"), A.bold)}\n`);
  for (const s of statuses) {
    let mark, detail;
    if (s.installed) {
      mark = OK;
      detail = paint(`${t("ide.installed")}${s.version ? ` v${s.version}` : ""}${s.scope ? ` (${s.scope})` : ""}`, A.green);
    } else if (s.cliMissing) {
      mark = paint("⚠", A.yellow);
      detail = paint(s.note || t("ide.cliMissing"), A.yellow);
    } else {
      mark = paint("-", A.dim);
      detail = paint(t("ide.notInstalled"), A.dim);
    }
    out(`${GUT}  ${mark} ${s.label.padEnd(14)} ${detail}${s.note && !s.cliMissing ? paint(`  ${s.note}`, A.dim) : ""}\n`);
  }
  out(`${GUT}\n`);
}

// New install vs update: one line plus the reason, so users know why the menu looks the way it does.
// Rule: version.yml carrying metadata.template.version means a previous install, so it is an update.
export function printInstallKind({ currentTemplateVersion = "", templateVersion = "" }, out = (s) => process.stdout.write(s)) {
  if (currentTemplateVersion) {
    out(`${GUT}  ${paint(t("kind.update"), A.bold)}: ${t("kind.updateFrom", { from: paint(currentTemplateVersion, A.dim), to: paint(templateVersion, A.green) })}\n`);
    out(`${GUT}  ${paint(t("kind.updateWhy"), A.dim)}\n`);
  } else {
    out(`${GUT}  ${paint(t("kind.new"), A.bold)}: ${t("kind.newTemplate", { to: paint(templateVersion, A.green) })}\n`);
    out(`${GUT}  ${paint(t("kind.newWhy"), A.dim)}\n`);
  }
  out(`${GUT}\n`);
}
