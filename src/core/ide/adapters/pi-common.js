// Shared PI paths and status logic (shared by the pi and pi-harness adapters).
import { join } from "node:path";
import { existsSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { t } from "../../../i18n/index.js";
import { TEMPLATE_REPO_OWNER, TEMPLATE_REPO_WEB_URL } from "../../paths.js";

export const PI_PACKAGE_URL = TEMPLATE_REPO_WEB_URL;

// Installed if 'pi list' output shows our repo. (Both old repo names and the project name are accepted)
export function piInstalled(io) {
  if (!io.which("pi")) return false;
  const r = io.run("pi", ["list"]); // pi sends some output to stderr → check both
  const out = (r.stdout || "") + (r.stderr || "");
  return /SUH-DEVOPS-TEMPLATE|projectops/i.test(out);
}

// pi clone path (where the harness loader lives). Backward compatible with the old path from before the repo rename.
export function piCloneDir(io) {
  const base = join(io.home(), ".pi/agent/git/github.com", TEMPLATE_REPO_OWNER);
  const newDir = join(base, "projectops");
  const oldDir = join(base, "SUH-DEVOPS-TEMPLATE");
  return (!existsSync(newDir) && existsSync(oldDir)) ? oldDir : newDir;
}

export function harnessLoaderPath(io) { return join(piCloneDir(io), "harness/harness-loader.ts"); }
export function piSettingsPath(io) { return join(io.home(), ".pi/agent/settings.json"); }

// Is the loader registered in the extensions array of settings.json?
export function harnessEnabled(io) {
  const settings = piSettingsPath(io), loader = harnessLoaderPath(io);
  if (!existsSync(settings)) return false;
  try {
    const s = JSON.parse(readFileSync(settings, "utf8"));
    return Array.isArray(s.extensions) && s.extensions.includes(loader);
  } catch { return false; }
}

// Add the loader to extensions (no duplicates). {ok, reason}.
export function harnessAdd(io) {
  const settings = piSettingsPath(io), loader = harnessLoaderPath(io);
  if (!existsSync(settings)) return { ok: false, reason: "no-settings" };
  if (!existsSync(loader)) return { ok: false, reason: "no-loader" };
  let s;
  // Do not overwrite on a parse failure (writing {} would wipe every user settings key)
  try { s = JSON.parse(readFileSync(settings, "utf8")); } catch { return { ok: false, reason: "invalid-settings" }; }
  if (s === null || typeof s !== "object" || Array.isArray(s)) return { ok: false, reason: "invalid-settings" };
  const exts = (Array.isArray(s.extensions) ? s.extensions : []).filter(Boolean);
  if (!exts.includes(loader)) exts.push(loader);
  s.extensions = exts;
  writeFileSync(settings, JSON.stringify(s, null, 2));
  return { ok: true };
}

// Remove the loader from extensions. {ok}.
export function harnessRemove(io) {
  const settings = piSettingsPath(io), loader = harnessLoaderPath(io);
  if (!existsSync(settings)) return { ok: true };
  let s;
  try { s = JSON.parse(readFileSync(settings, "utf8")); } catch { return { ok: true }; }
  if (Array.isArray(s.extensions)) {
    s.extensions = s.extensions.filter((e) => e && e !== loader);
    writeFileSync(settings, JSON.stringify(s, null, 2));
  }
  return { ok: true };
}

// When old and new clones coexist, remove the old SUH-DEVOPS-TEMPLATE clone + its loader path from settings.json.
// Clean up only when both exist (if only the old one exists, leave it until pi install makes the new one). Failure is harmless.
export function migratePiLegacy(io) {
  const base = join(io.home(), ".pi/agent/git/github.com", TEMPLATE_REPO_OWNER);
  const oldDir = join(base, "SUH-DEVOPS-TEMPLATE");
  const newDir = join(base, "projectops");
  if (!(existsSync(oldDir) && existsSync(newDir))) return;
  const oldLoader = join(oldDir, "harness/harness-loader.ts");
  const settings = piSettingsPath(io);
  if (existsSync(settings)) {
    try {
      const s = JSON.parse(readFileSync(settings, "utf8"));
      if (Array.isArray(s.extensions)) {
        s.extensions = s.extensions.filter((e) => e && e !== oldLoader);
        writeFileSync(settings, JSON.stringify(s, null, 2));
      }
    } catch { /* ignore */ }
  }
  try { rmSync(oldDir, { recursive: true, force: true }); io.log(t("ide.pi.legacyClone")); } catch { /* ignore */ }
}
