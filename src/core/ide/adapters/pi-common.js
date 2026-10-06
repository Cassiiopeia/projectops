// PI 공용 경로·상태 로직 (pi 어댑터와 pi-harness 어댑터가 공유).
// .sh: PI_PACKAGE_URL / _pi_is_installed / _pi_clone_dir / _pi_harness_loader_path /
//      _pi_settings_path / _pi_harness_enabled 등가.
import { join } from "node:path";
import { existsSync, readFileSync, writeFileSync, rmSync } from "node:fs";
import { t } from "../../../i18n/index.js";

export const PI_PACKAGE_URL = "https://github.com/Cassiiopeia/projectops";

// 'pi list' 출력에 우리 레포가 잡히면 설치됨. (구 레포명·프로젝트명 모두 허용)
export function piInstalled(io) {
  if (!io.which("pi")) return false;
  const r = io.run("pi", ["list"]); // pi는 일부 출력을 stderr로 보냄 → 둘 다 검사
  const out = (r.stdout || "") + (r.stderr || "");
  return /SUH-DEVOPS-TEMPLATE|projectops/i.test(out);
}

// pi 클론 경로(harness loader가 사는 곳). 레포명 변경 전 구 경로 하위호환.
export function piCloneDir(io) {
  const base = join(io.home(), ".pi/agent/git/github.com/Cassiiopeia");
  const newDir = join(base, "projectops");
  const oldDir = join(base, "SUH-DEVOPS-TEMPLATE");
  return (!existsSync(newDir) && existsSync(oldDir)) ? oldDir : newDir;
}

export function harnessLoaderPath(io) { return join(piCloneDir(io), "harness/harness-loader.ts"); }
export function piSettingsPath(io) { return join(io.home(), ".pi/agent/settings.json"); }

// settings.json의 extensions 배열에 loader가 등록돼 있는가.
export function harnessEnabled(io) {
  const settings = piSettingsPath(io), loader = harnessLoaderPath(io);
  if (!existsSync(settings)) return false;
  try {
    const s = JSON.parse(readFileSync(settings, "utf8"));
    return Array.isArray(s.extensions) && s.extensions.includes(loader);
  } catch { return false; }
}

// extensions에 loader 추가(중복 방지). {ok, reason}.
export function harnessAdd(io) {
  const settings = piSettingsPath(io), loader = harnessLoaderPath(io);
  if (!existsSync(settings)) return { ok: false, reason: "no-settings" };
  if (!existsSync(loader)) return { ok: false, reason: "no-loader" };
  let s = {};
  try { s = JSON.parse(readFileSync(settings, "utf8")); } catch { s = {}; }
  const exts = (Array.isArray(s.extensions) ? s.extensions : []).filter(Boolean);
  if (!exts.includes(loader)) exts.push(loader);
  s.extensions = exts;
  writeFileSync(settings, JSON.stringify(s, null, 2));
  return { ok: true };
}

// extensions에서 loader 제거. {ok}.
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

// 신·구 clone 공존 시 옛 SUH-DEVOPS-TEMPLATE clone 제거 + settings.json에서 그 loader 경로 제거.
// 공존일 때만 정리(옛것만 있으면 pi install이 신규를 만들 때까지 그대로 둔다). 실패 무해.
export function migratePiLegacy(io) {
  const base = join(io.home(), ".pi/agent/git/github.com/Cassiiopeia");
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
    } catch { /* 무시 */ }
  }
  try { rmSync(oldDir, { recursive: true, force: true }); io.log(t("ide.pi.legacyClone")); } catch { /* 무시 */ }
}
