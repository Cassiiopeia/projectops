// Wiring for the breaking-changes check flow.
// collectBreaking (pure comparison) lives in breaking.js — this module handles loading (remote → cloned copy fallback), display and the confirm gate.
import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { collectBreaking, localizeBreakingEntry } from "./breaking.js";
import { parseExisting } from "./version-yml.js";
import { t, getLang } from "../i18n/index.js";
import { TEMPLATE_RAW_URL } from "./paths.js";

const BC_URL = `${TEMPLATE_RAW_URL}/.github/config/breaking-changes.json`;

// Remote first (3s timeout) → bundled copy in the cloned template → null if both fail (skip silently)
export async function loadBreakingJson(tempDir) {
  try {
    const res = await fetch(BC_URL, { signal: AbortSignal.timeout(3000) });
    if (res.ok) return await res.json();
  } catch { /* Remote failed — fall back */ }
  try {
    const p = join(tempDir, ".github", "config", "breaking-changes.json");
    if (existsSync(p)) return JSON.parse(readFileSync(p, "utf8"));
  } catch { /* Fallback failed — skip */ }
  return null;
}

// Returns true = proceed, false = cancelled by the user.
// opts:
//   cwd             - integration target root (reads the current template version from the existing version.yml)
//   tempDir         - cloned template (for the bundled fallback)
//   templateVersion - template version being installed (not the fixed DEFAULT_VERSION — design D2)
//   askYesNo        - async(message, defaultYes)→bool. null means non-interactive: print a warning and proceed
//   loader          - test injection (default loadBreakingJson)
//   onItems         - (#493) callback with the entries in range ({current, target, critical, warnings}) —
//                     the migration guide embeds the full action steps from it (called whether or not shown)
export async function runBreakingCheck({ cwd, tempDir, templateVersion, askYesNo = null, loader = loadBreakingJson, onItems = null }) {
  const vy = join(cwd, "version.yml");
  if (!existsSync(vy)) return true; // New integration — nothing to compare with
  const { templateVersion: current } = parseExisting(readFileSync(vy, "utf8"));
  if (!current) return true; // No template metadata (unknown) — skip

  const json = await loader(tempDir);
  if (!json) return true;

  const { critical, warnings } = collectBreaking(json, current, templateVersion);
  if (critical.length || warnings.length) onItems?.({ current, target: templateVersion, critical, warnings });
  if (critical.length === 0 && warnings.length === 0) return true;

  // Show a summary list (#473 — dumping the full text made a wall of text so CRITICAL went unread,
  // and wrapping long bodies broke the ║ box borders. One line per version and title; full text on request.)
  const e = (s = "") => process.stderr.write(s + "\n");
  // Screen text uses the screen language (entries passed to onItems for the guide stay in English — the run log is English)
  const localized = (item) => localizeBreakingEntry(item, getLang());
  e("");
  e(t("breaking.title", { current, target: templateVersion, critical: critical.length, warnings: warnings.length }));
  e("");
  for (const c of critical) e(`  ❗ [CRITICAL] ${c.version} - ${localized(c).title}`);
  for (const w of warnings) e(`  ⚠️ [WARNING]  ${w.version} - ${localized(w).title}`);
  e("");

  if (askYesNo) {
    // Interactive: expand the full text (action steps) only when asked
    const detail = await askYesNo(t("breaking.askDetail"), false);
    if (detail === true) {
      for (const it of [...critical, ...warnings]) {
        e("");
        const { title, message } = localized(it);
        e(`■ ${it.version} - ${title}`);
        e(`  ${message}`);
      }
      e("");
    }
  } else {
    e(t("breaking.seeJson"));
    e(`  (${BC_URL})`);
    e("");
  }

  if (critical.length > 0) {
    if (askYesNo) {
      // Interactive: stop without explicit confirmation (default N)
      const ok = await askYesNo(t("breaking.askContinue"), false);
      if (ok !== true) return false;
    } else {
      // Non-interactive (--force): warn and proceed instead of killing CI at the gate (CI friendly)
      e(t("breaking.nonInteractive"));
    }
  }
  return true;
}
