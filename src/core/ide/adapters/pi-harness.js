// PI Persona Harness 어댑터 (.sh _pi_harness_toggle / _pi_harness_remove_only /
// _pi_harness_add / _pi_harness_remove / _pi_harness_enabled 등가).
// PI skill과 독립 — skill은 그대로 두고 harness 등록(settings.json extensions)만 켜고/끈다.
import { existsSync } from "node:fs";
import { harnessEnabled, harnessAdd, harnessRemove, harnessLoaderPath } from "./pi-common.js";
import { t } from "../../../i18n/index.js";

// 이 어댑터는 "설치 가능" 여부가 pi 존재 + loader 파일 존재에 달림.
function available(io) { return !!io.which("pi") && existsSync(harnessLoaderPath(io)); }

function detect(io) {
  if (!io.which("pi")) return { installed: false, version: null, cliMissing: true, note: t("ide.harness.noPi") };
  if (!existsSync(harnessLoaderPath(io))) return { installed: false, version: null, cliMissing: true, note: t("ide.harness.noLoader") };
  return { installed: harnessEnabled(io), version: null, cliMissing: false, note: t(harnessEnabled(io) ? "ide.harness.enabled" : "ide.harness.disabled") };
}

// apply = harness 활성화 (skill은 안 건드림).
function apply(io) {
  if (!available(io)) { io.log(t("ide.harness.needPi")); return false; }
  if (harnessEnabled(io)) { io.log(t("ide.harness.already")); return true; }
  const r = harnessAdd(io);
  if (r.ok) { io.log(t("ide.harness.enabledDone")); return true; }
  io.log(t(r.reason === "no-settings" ? "ide.harness.noSettings" : "ide.harness.needPackage"));
  return false;
}

// remove = harness만 해제 (PI skill 보존).
function remove(io) {
  if (!harnessEnabled(io)) { io.log(t("ide.harness.removeNone")); return true; }
  io.log(t("ide.harness.keepSkill"));
  harnessRemove(io);
  io.log(t("ide.harness.removed"));
  return true;
}

function manualHint() { return t("ide.harness.manual"); }

// harness 설명 (프롬프트에서 재사용).
export const harnessDesc = () => t("ide.harness.desc");

export const piHarnessAdapter = {
  id: "pi-harness", label: "PI Persona Harness", order: 60,
  optional: true, // 감지된 경우에만 메뉴 노출 (registry 순회 시 참고)
  detect, apply, remove, manualHint,
};
