// IDE skills install orchestrator.
// Registry based — does not know individual IDEs by name, only iterates the ADAPTERS array.
// A new IDE works with just a file in adapters/ + registry entry, with no changes here.
import { ADAPTERS } from "../core/ide/registry.js";
import { versionTag } from "../core/ide/util.js";
import { defaultIo } from "../core/ide/runner.js";
import * as skillsPrompts from "../ui/skills-prompts.js";
import { t } from "../i18n/index.js";

// Collect status → [{adapter, status}]. Optional adapters are left out when undetectable (cliMissing).
export function collectStatuses(io) {
  const rows = [];
  for (const a of ADAPTERS) {
    const status = safe(() => a.detect(io), { installed: false, version: null, cliMissing: true });
    if (a.optional && status.cliMissing) continue; // Conditional items like the harness are hidden when unavailable
    rows.push({ adapter: a, status });
  }
  return rows;
}

// Status display strings (for display, pure).
export function formatStatuses(rows, templateVersion) {
  return rows.map(({ adapter, status }) => {
    const label = adapter.label.padEnd(12);
    if (status.cliMissing) return `${label}: ${status.note || t("skills.status.noCli")}`;
    if (status.installed) {
      const v = status.version ? ` (v${status.version})` : "";
      return `${label}: ${t("skills.status.installed")}${v}${versionTag(status.version, templateVersion)}`;
    }
    return `${label}: ${status.note || t("skills.status.notInstalled")}`;
  });
}

// Shared entry for interactive/non-interactive. opts: {io, templateVersion, sourceSkillsDir, tempDir, interactive, ui, installedOnly}
// installedOnly (#502 — update mode): limits non-interactive apply to already-installed adapters.
// Never installs into IDEs not yet installed — an update's contract is "bring what exists up to date".
export async function runSkills(opts = {}) {
  const io = opts.io || defaultIo();
  const ui = opts.ui || skillsPrompts;
  const ctx = { templateVersion: opts.templateVersion || "", sourceSkillsDir: opts.sourceSkillsDir, tempDir: opts.tempDir };

  const rows = collectStatuses(io);
  io.log("");
  io.log(t("skills.statusTitle"));
  for (const line of formatStatuses(rows, ctx.templateVersion)) io.log(line);
  io.log("");

  // Non-interactive: run apply (install/update) in order on every detected (= manageable) adapter.
  // With installedOnly, installed adapters only (update mode — IDEs not installed are left alone).
  if (!opts.interactive) {
    for (const { adapter, status } of rows) {
      if (opts.installedOnly && !status.installed) continue;
      safe(() => adapter.apply(io, ctx), false);
    }
    return 0;
  }

  // Interactive: choose action → IDE multiselect → run.
  const action = await ui.selectAction();
  if (action == null || action === skillsPrompts.CANCEL || action === "skip") {
    io.log(t("skills.unchanged"));
    return 0;
  }

  const choices = rows.map(({ adapter, status }) => ({
    id: adapter.id, label: adapter.label,
    disabled: action === "apply" && status.cliMissing, // Install needs the CLI; removal is always a candidate
  }));
  const preselect = rows
    .filter(({ status }) => action === "apply" ? !status.cliMissing : true)
    .map(({ adapter }) => adapter.id);

  const targets = await ui.selectTargets(choices, preselect, action);
  if (targets == null || targets === skillsPrompts.CANCEL || !targets.length) {
    io.log(t("skills.noneSelected"));
    return 0;
  }

  const selected = new Set(targets);
  for (const { adapter } of rows) {
    if (!selected.has(adapter.id)) continue;
    io.log("");
    io.log(t(action === "apply" ? "skills.header.apply" : "skills.header.remove", { label: adapter.label }));
    safe(() => (action === "apply" ? adapter.apply(io, ctx) : adapter.remove(io, ctx)), false);
  }
  return 0;
}

function safe(fn, fallback) { try { return fn(); } catch { return fallback; } }
