// Codex CLI 어댑터 (.sh _manage_codex_skills / _do_codex_marketplace_register /
// _remove_codex_section 등가).
// marketplace 등록/업그레이드가 주 경로. native ~/.agents/skills/projectops 심링크는 감지·제거에 사용.
import { join } from "node:path";
import { existsSync, lstatSync, rmSync } from "node:fs";
import { migrateConfigRoot } from "../legacy.js";
import { t } from "../../../i18n/index.js";

const MARKETPLACE = "Cassiiopeia/projectops";
const PLUGIN = "projectops";
const LEGACY_NATIVES = ["SUH-DEVOPS-TEMPLATE"];
const LEGACY_MARKETPLACES = ["SUH-DEVOPS-TEMPLATE"];

function nativeTarget(io) { return join(io.home(), ".agents/skills/projectops"); }

function detect(io) {
  const tgt = nativeTarget(io);
  const nativeInstalled = existsSync(tgt);
  if (nativeInstalled) return { installed: true, version: null, cliMissing: false, note: "native skills" };
  if (!io.which("codex")) return { installed: false, version: null, cliMissing: true, note: t("ide.cliMissing") };
  return { installed: false, version: null, cliMissing: false, note: t("ide.installable") };
}

function apply(io) {
  if (!io.which("codex")) { io.log(manualHint()); return false; }
  migrateLegacy(io);
  migrateConfigRoot(io);
  io.log(t("ide.codex.marketAdding"));
  const add = io.run("codex", ["plugin", "marketplace", "add", MARKETPLACE]);
  io.log(t(add.code === 0 ? "ide.codex.marketAdded" : "ide.codex.marketSkipped"));
  io.log(t("ide.codex.marketUpgrading"));
  if (io.run("codex", ["plugin", "marketplace", "upgrade", PLUGIN]).code === 0) { io.log(t("ide.codex.marketDone")); return true; }
  io.log(t("ide.codex.marketError", { market: MARKETPLACE }));
  return false;
}

function remove(io) {
  const tgt = nativeTarget(io);
  let removed = false;
  if (existsSync(tgt) || isSymlink(tgt)) {
    try { rmSync(tgt, { recursive: true, force: true }); io.log(t("ide.codex.skillsRemoved", { path: tgt })); removed = true; } catch { /* 무해 */ }
  }
  if (!removed) io.log(t("ide.codex.removeNone"));
  if (io.which("codex")) io.log(t("ide.codex.unregisterManual", { plugin: PLUGIN }));
  return true;
}

function manualHint() { return `  💡 Codex CLI: codex plugin marketplace add ${MARKETPLACE}`; }

// 옛 native skills 폴더/심링크 + 옛 marketplace 정리. 실패 무해.
function migrateLegacy(io) {
  for (const name of LEGACY_NATIVES) {
    const old = join(io.home(), ".agents/skills", name);
    if (existsSync(old) || isSymlink(old)) {
      try { rmSync(old, { recursive: true, force: true }); io.log(t("ide.codex.legacy", { name })); } catch { /* 무시 */ }
    }
  }
  if (io.which("codex")) for (const mp of LEGACY_MARKETPLACES) io.run("codex", ["plugin", "marketplace", "remove", mp]);
}

function isSymlink(p) { try { return lstatSync(p).isSymbolicLink(); } catch { return false; } }

export const codexAdapter = {
  id: "codex", label: "Codex CLI", order: 40,
  detect, apply, remove, manualHint,
};
