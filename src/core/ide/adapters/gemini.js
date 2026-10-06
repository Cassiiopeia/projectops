// Gemini CLI 어댑터 (.sh _manage_gemini_extension / _remove_gemini_section 등가).
// extension install/update/uninstall. 마켓플레이스 대신 git URL 확장.
import { migrateConfigRoot } from "../legacy.js";
import { t } from "../../../i18n/index.js";

const EXT = "projectops";
const URL = "https://github.com/Cassiiopeia/projectops";
const LEGACY_EXTS = ["SUH-DEVOPS-TEMPLATE"];

function detect(io) {
  if (!io.which("gemini")) return { installed: false, version: null, cliMissing: true, note: t("ide.cliMissing") };
  // .sh는 gemini 설치 상태를 정밀 조회하지 않고 "설치 가능"으로만 표기 → installed 미상.
  return { installed: false, version: null, cliMissing: false, note: t("ide.installable") };
}

function apply(io) {
  if (!io.which("gemini")) { io.log(manualHint()); return false; }
  migrateLegacy(io);
  migrateConfigRoot(io);
  io.log(t("ide.gemini.updating"));
  if (io.run("gemini", ["extensions", "update", EXT]).code === 0) { io.log(t("ide.gemini.updated")); return true; }
  io.log(t("ide.gemini.installing"));
  if (io.run("gemini", ["extensions", "install", URL]).code === 0) { io.log(t("ide.gemini.installed")); return true; }
  io.log(t("ide.gemini.error", { url: URL }));
  return false;
}

function remove(io) {
  if (!io.which("gemini")) { io.log(t("ide.gemini.notFound")); return true; }
  if (io.run("gemini", ["extensions", "uninstall", EXT]).code === 0) { io.log(t("ide.gemini.removed")); return true; }
  io.log(t("ide.gemini.removeFailed", { ext: EXT }));
  return true; // 미설치 제거는 실패로 보지 않음
}

function manualHint() { return `  💡 Gemini CLI: gemini extensions install ${URL}`; }

// 옛 이름 extension 정리. 없으면 실패 무시.
function migrateLegacy(io) {
  for (const e of LEGACY_EXTS) io.run("gemini", ["extensions", "uninstall", e]);
}

export const geminiAdapter = {
  id: "gemini", label: "Gemini CLI", order: 30,
  detect, apply, remove, manualHint,
};
