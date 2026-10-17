// .coderabbit.yaml 복사 (force 경로).
// SP2-B는 force/비대화형 경로만 구현. 대화형 덮어쓰기/건너뛰기 메뉴는 SP2-C.
import { join } from "node:path";
import { exists, copyFileSync } from "../fsutil.js";

// 반환: 'skip-disabled' | 'skip-no-src' | 'copied-new' | 'overwritten-backup' | 'skip-non-tty'
// opts: { force, tty, enabled }  — SP2-B 검증은 force:true 경로.
// enabled=false면(#457 CodeRabbit 미사용 선택) 파일을 아예 복사하지 않는다.
// enabled 미지정(undefined)이면 기존 동작(복사) 유지 — 구 호출부 하위호환.
export function copyCoderabbit(tempDir, { force = false, tty = false, enabled } = {}, targetRoot = ".") {
  if (enabled === false) return "skip-disabled";
  const src = join(tempDir, ".coderabbit.yaml");
  if (!exists(src)) return "skip-no-src";
  const dst = join(targetRoot, ".coderabbit.yaml");

  if (exists(dst)) {
    if (force) {
      copyFileSync(dst, dst + ".bak"); // 백업 후 덮어쓰기
      copyFileSync(src, dst);
      return "overwritten-backup";
    }
    if (!tty) return "skip-non-tty"; // 비TTY & !force → 유지
    // 대화형 메뉴는 SP2-C — 여기서는 force가 아니면 유지
    return "skip-non-tty";
  }
  copyFileSync(src, dst); // 신규
  return "copied-new";
}
