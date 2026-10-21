// 홈 복사형 IDE(Cursor·Copilot) 설치·제거 흐름 공용: 소스 찾기 > 복사 > 진입점 > 로그
// 메시지는 어댑터별 키 묶음(<messagePrefix>.copying 등)을 쓴다.
import { existsSync } from "node:fs";
import { join } from "node:path";
import { t } from "../../i18n/index.js";
import { resolveSkillsSrc, resolveScriptsSrc, installHomeSkills, removeOwnedEntries } from "./skills-copy.js";
import { refreshStableEntrypoints, projectopsHomeOf } from "./stable-entry.js";

/**
 * 설치·업데이트: 스킬 소스 확인 > 스킬·공용 파이썬 복사 > 고정 진입점 > 결과 로그
 * options: { skillsDest, metaFileName, messagePrefix }
 */
export function applyHomeSkills(io, ctx, { skillsDest, metaFileName, messagePrefix }) {
  const skillsSrc = resolveSkillsSrc(ctx);
  if (!skillsSrc) { io.log(t(`${messagePrefix}.noSource`)); return false; }
  const scriptsSrc = resolveScriptsSrc(ctx, skillsSrc);
  io.log(t(`${messagePrefix}.copying`));
  try {
    const { obsoleteNames, hasSharedScripts } = installHomeSkills({
      skillsSrc, scriptsSrc, skillsDest, metaFileName, templateVersion: ctx.templateVersion,
    });
    for (const name of obsoleteNames) io.log(t("ide.skillsCopy.obsolete", { name }));
    // 공용 파이썬이 없으면 스킬 CLI 가 import 에 실패 → 알림만 (문서형 스킬은 동작)
    if (!hasSharedScripts) io.log(t("ide.skillsCopy.noScripts"));
    io.log(t(`${messagePrefix}.installed`, { dest: skillsDest, version: ctx.templateVersion || "unknown" }));
  } catch {
    io.log(t(`${messagePrefix}.copyFailed`));
    return false;
  }
  installStableEntrypoints(io, skillsSrc, scriptsSrc);
  return true;
}

// 진입점 실패는 설치 실패가 아니다 (CLI 첫 실행 때 파이썬이 다시 깐다)
function installStableEntrypoints(io, skillsSrc, scriptsSrc) {
  try {
    const projectopsHome = projectopsHomeOf(io);
    for (const name of refreshStableEntrypoints(projectopsHome, { skillsSrc, scriptsSrc })) {
      io.log(t("ide.skillsCopy.entrypoint", { path: join(projectopsHome, "bin", name) }));
    }
  } catch { io.log(t("ide.skillsCopy.entrypointFailed")); }
}

// 제거: 메타 없으면 건너뜀 > 우리 항목·공용 파이썬만 삭제 (남의 스킬이 남으면 폴더 유지)
export function removeHomeSkills(io, ctx, { skillsDest, metaFileName, messagePrefix }) {
  if (!existsSync(join(skillsDest, metaFileName))) { io.log(t(`${messagePrefix}.removeNone`)); return true; }
  try {
    removeOwnedEntries(skillsDest, ctx, metaFileName);
    io.log(t(`${messagePrefix}.removed`, { dir: skillsDest }));
    return true;
  } catch { io.log(t(`${messagePrefix}.removeFailed`, { dir: skillsDest })); return false; }
}
