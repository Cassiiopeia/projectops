// PI Persona Harness adapter (enable, disable, status).
// Independent of the PI skill — leaves the skill alone and only toggles the harness registration (settings.json extensions).
import { existsSync } from "node:fs";
import { harnessEnabled, harnessAdd, harnessRemove, harnessLoaderPath, piSettingsPath } from "./pi-common.js";
import { t } from "../../../i18n/index.js";

// For this adapter, "installable" depends on pi existing + the loader file existing.
function available(io) { return !!io.which("pi") && existsSync(harnessLoaderPath(io)); }

function detect(io) {
  if (!io.which("pi")) return { installed: false, version: null, cliMissing: true, note: t("ide.harness.noPi") };
  if (!existsSync(harnessLoaderPath(io))) return { installed: false, version: null, cliMissing: true, note: t("ide.harness.noLoader") };
  return { installed: harnessEnabled(io), version: null, cliMissing: false, note: t(harnessEnabled(io) ? "ide.harness.enabled" : "ide.harness.disabled") };
}

// apply = enable the harness (skill untouched).
function apply(io) {
  if (!available(io)) { io.log(t("ide.harness.needPi")); return false; }
  if (harnessEnabled(io)) { io.log(t("ide.harness.already")); return true; }
  const r = harnessAdd(io);
  if (r.ok) { io.log(t("ide.harness.enabledDone")); return true; }
  const messageKeyByReason = { "no-settings": "ide.harness.noSettings", "invalid-settings": "ide.harness.invalidSettings" };
  io.log(t(messageKeyByReason[r.reason] ?? "ide.harness.needPackage", { file: piSettingsPath(io) }));
  return false;
}

// remove = disable only the harness (PI skill kept).
function remove(io) {
  if (!harnessEnabled(io)) { io.log(t("ide.harness.removeNone")); return true; }
  io.log(t("ide.harness.keepSkill"));
  harnessRemove(io);
  io.log(t("ide.harness.removed"));
  return true;
}

function manualHint() { return t("ide.harness.manual"); }

// Harness description (reused in prompts).
export const harnessDesc = () => t("ide.harness.desc");

export const piHarnessAdapter = {
  id: "pi-harness", label: "PI Persona Harness", order: 60,
  optional: true, // Shown in the menu only when detected (consulted when iterating the registry)
  detect, apply, remove, manualHint,
};
