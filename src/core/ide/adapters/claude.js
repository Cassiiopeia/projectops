// Claude Code 어댑터 (.sh _manage_claude_section / _do_claude_plugin_install /
// _remove_claude_section / _remove_claude_plugin_data 등가).
// 마켓플레이스 Cassiiopeia/projectops, 플러그인 projectops@projectops-marketplace.
import { join } from "node:path";
import { existsSync, readdirSync, mkdirSync, cpSync, rmSync } from "node:fs";
import { compareCacheName } from "../util.js";
import { migrateConfigRoot } from "../legacy.js";
import { t } from "../../../i18n/index.js";

const MARKETPLACE = "Cassiiopeia/projectops";
const PLUGIN = "projectops@projectops-marketplace";
const LEGACY_PLUGINS = ["cassiiopeia@cassiiopeia-marketplace", "cassiiopeia"];
const LEGACY_MARKETPLACES = ["cassiiopeia-marketplace"];

function detect(io) {
  if (!io.which("claude")) return { installed: false, version: null, cliMissing: true, note: t("ide.cliMissing") };
  const r = io.run("claude", ["plugin", "list", "--json"]);
  let scope = "", version = null;
  try {
    const arr = JSON.parse(r.stdout || "[]");
    const list = Array.isArray(arr) ? arr : (arr.plugins || []);
    for (const p of list) {
      const name = String(p.name || p.id || "");
      if (name.includes("projectops@") || name === "projectops") { scope = p.scope || ""; version = p.version || null; break; }
    }
  } catch { /* 파싱 실패 → 미설치 취급 */ }
  return { installed: !!scope, version, cliMissing: false, scope };
}

function apply(io, ctx = {}) {
  const st = detect(io);
  if (st.cliMissing) { io.log(manualHint(io)); return false; }
  migrateLegacy(io);          // 옛 cassiiopeia 플러그인/마켓 정리
  migrateConfigRoot(io);      // 공용 config 루트 이관
  const st2 = detect(io);     // 정리 후 재감지
  if (st2.installed) return update(io, st2.scope);
  return install(io, "user");
}

// 옛 이름(cassiiopeia) 플러그인·마켓 정리. 조용히, 로그만. 실패 무해(없으면 no-op).
function migrateLegacy(io) {
  const r = io.run("claude", ["plugin", "list", "--json"]);
  let list = [];
  try { const arr = JSON.parse(r.stdout || "[]"); list = Array.isArray(arr) ? arr : (arr.plugins || []); } catch { /* 무시 */ }
  for (const legacy of LEGACY_PLUGINS) {
    const hit = list.find((p) => {
      const name = String(p.name || p.id || "");
      return name === legacy || name.startsWith(legacy + "@");
    });
    if (hit) {
      const scope = hit.scope || "user";
      io.log(t("ide.claude.legacy", { name: legacy, scope }));
      io.run("claude", ["plugin", "uninstall", legacy, "--scope", scope]);
    }
  }
  for (const mp of LEGACY_MARKETPLACES) {
    io.run("claude", ["plugin", "marketplace", "remove", mp]); // 없으면 no-op
  }
}

function install(io, scope = "user") {
  io.log(t("ide.claude.marketAdding"));
  const add = io.run("claude", ["plugin", "marketplace", "add", MARKETPLACE]);
  io.log(t(add.code === 0 ? "ide.claude.marketAdded" : "ide.claude.marketSkipped"));
  io.log(t("ide.claude.installing", { scope }));
  const ins = io.run("claude", ["plugin", "install", PLUGIN, "--scope", scope]);
  if (ins.code === 0) { io.log(t("ide.claude.installed", { scope })); return true; }
  io.log(t("ide.claude.installFailed", { plugin: PLUGIN, scope }));
  return false;
}

function update(io, scope) {
  const cacheRoot = join(io.home(), ".claude/plugins/cache/projectops-marketplace/projectops");
  const oldCache = latestCacheDir(cacheRoot);
  io.log(t("ide.claude.updating"));
  const up = io.run("claude", ["plugin", "update", PLUGIN, "--scope", scope]);
  if (up.code !== 0) { io.log(t("ide.claude.updateFailed", { plugin: PLUGIN, scope })); return false; }
  io.log(t("ide.claude.updated", { scope }));
  migrateConfig(io, oldCache, latestCacheDir(cacheRoot));
  return true;
}

function remove(io) {
  const st = detect(io);
  if (st.cliMissing || !st.installed) { io.log(t("ide.claude.removeNone")); return true; }
  io.log(t("ide.claude.removeTarget", { plugin: PLUGIN, scope: st.scope }));
  const un = io.run("claude", ["plugin", "uninstall", PLUGIN, "--scope", st.scope]);
  if (un.code === 0) { io.log(t("ide.claude.removed")); removePluginData(io); return true; }
  io.log(t("ide.claude.removeFailed", { plugin: PLUGIN, scope: st.scope }));
  return false;
}

function manualHint() {
  return t("ide.claude.manual", { market: MARKETPLACE, plugin: PLUGIN });
}

// ── 내부 헬퍼 ──
function latestCacheDir(root) {
  if (!existsSync(root)) return "";
  const dirs = readdirSync(root, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name).sort(compareCacheName);
  return dirs.length ? join(root, dirs[dirs.length - 1]) : "";
}
function migrateConfig(io, oldCache, newCache) {
  if (!oldCache || !newCache || oldCache === newCache) return;
  const oldCfg = join(oldCache, "config"), newCfg = join(newCache, "config");
  if (!existsSync(oldCfg)) return;
  try {
    mkdirSync(newCfg, { recursive: true });
    let copied = 0;
    for (const f of readdirSync(oldCfg)) if (f.endsWith(".json")) { cpSync(join(oldCfg, f), join(newCfg, f)); copied++; }
    if (copied) io.log(t("ide.claude.configMigrated"));
  } catch { /* 무해 */ }
}
function removePluginData(io) {
  const dataDir = join(io.home(), ".claude/plugins/data", PLUGIN);
  if (existsSync(dataDir)) { try { rmSync(dataDir, { recursive: true, force: true }); io.log(t("ide.claude.dataRemoved")); } catch { /* 무해 */ } }
}

export const claudeAdapter = {
  id: "claude", label: "Claude Code", order: 10,
  detect, apply, remove, manualHint,
};
