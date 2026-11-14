// Shared legacy utilities for IDE adapters — version check + config root migration.
// Shared when moving pre-rebrand (#459) installs (cassiiopeia/SUH-DEVOPS-TEMPLATE) to the new one (projectops).
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { copyFileSync } from "../fsutil.js";
import { compareCacheName } from "./util.js";
import { t } from "../../i18n/index.js";

// Legacy if version <= maxLegacy. null/empty string cannot be judged → false (safe).
export function isLegacyVersion(version, maxLegacy) {
  if (!version || !maxLegacy) return false;
  return compareCacheName(String(version), String(maxLegacy)) <= 0;
}

// true if the file exists, parses as JSON and has at least 1 key.
export function hasNonEmptyJson(path) {
  if (!path || !existsSync(path)) return false;
  try {
    const o = JSON.parse(readFileSync(path, "utf8"));
    return o && typeof o === "object" && Object.keys(o).length > 0;
  } catch { return false; }
}

// Config root migration: copy from the old path only when the target (~/.projectops/config/config.json) is empty.
// The old file is not deleted (keeps sensitive values). Idempotent.
export function migrateConfigRoot(io) {
  const target = join(io.home(), ".projectops", "config", "config.json");
  if (hasNonEmptyJson(target)) return { migrated: false, reason: "target-exists" };
  const sources = [
    join(io.home(), ".suh-template", "config", "config.json"), // 2nd generation first
    join(io.home(), ".cassiiopeia", "config.json"),            // 1st generation fallback
  ];
  const src = sources.find(hasNonEmptyJson);
  if (!src) return { migrated: false, reason: "no-source" };
  try {
    copyFileSync(src, target);
    io.log(t("ide.legacy.configMigrated", { source: src }));
    return { migrated: true, from: src };
  } catch (e) {
    io.log(t("ide.legacy.configMigrateFailed", { error: e.message }));
    return { migrated: false, reason: "error" };
  }
}
