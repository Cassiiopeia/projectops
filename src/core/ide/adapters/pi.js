// PI 패키지 어댑터 (.sh _manage_pi_section / _remove_pi_section 등가).
// pi install/update/remove. skill은 복사되지 않고 pi가 startup마다 스캔 → 설치 검증은 'pi list'.
import { PI_PACKAGE_URL, piInstalled, harnessEnabled, harnessRemove, migratePiLegacy } from "./pi-common.js";
import { migrateConfigRoot } from "../legacy.js";
import { t } from "../../../i18n/index.js";

function detect(io) {
  if (!io.which("pi")) return { installed: false, version: null, cliMissing: true, note: t("ide.cliMissing") };
  return { installed: piInstalled(io), version: null, cliMissing: false };
}

function apply(io) {
  if (!io.which("pi")) { io.log(manualHint()); return false; }
  migratePiLegacy(io);
  migrateConfigRoot(io);
  if (piInstalled(io)) {
    io.log(t("ide.pi.updating"));
    if (io.run("pi", ["update", PI_PACKAGE_URL]).code !== 0) io.run("pi", ["install", PI_PACKAGE_URL]);
  } else {
    io.log(t("ide.pi.installing"));
    io.run("pi", ["install", PI_PACKAGE_URL]);
  }
  if (piInstalled(io)) {
    io.log(t("ide.pi.done"));
    io.log(t("ide.pi.afterInstall"));
    return true;
  }
  io.log(t("ide.pi.failed", { url: PI_PACKAGE_URL }));
  return false;
}

function remove(io) {
  if (!io.which("pi")) { io.log(t("ide.pi.notFound")); return true; }
  if (!piInstalled(io)) { io.log(t("ide.pi.removeNone")); return true; }
  io.log(`  pi remove ${PI_PACKAGE_URL}`);
  io.run("pi", ["remove", PI_PACKAGE_URL]);
  if (piInstalled(io)) io.log(t("ide.pi.stillThere"));
  else io.log(t("ide.pi.removed"));
  // package 클론이 사라지면 harness loader 경로가 허공을 가리킴 → 함께 해제
  if (harnessEnabled(io)) { io.log(t("ide.pi.harnessAlso")); harnessRemove(io); }
  return true;
}

function manualHint() { return `  💡 PI: pi install ${PI_PACKAGE_URL}`; }

export const piAdapter = {
  id: "pi", label: "PI", order: 50,
  detect, apply, remove, manualHint,
};
