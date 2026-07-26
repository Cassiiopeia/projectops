// util 모듈 복사 (.sh copy_util_modules 등가, force 경로) — template_integrator.sh 4203~.
// tempDir/.github/util/<type>/ 있으면 (force) .github/util/<type>/로 전체 복사, 모듈 수 카운트.
import { join } from "node:path";
import { readdirSync } from "node:fs";
import { exists, copyDirSync } from "../fsutil.js";

// 반환: {copied:bool, moduleCount:number}. force가 아니면(비TTY) 스킵.
// ⚠️ overlay 복사다 — 템플릿에서 삭제/리네임된 구 파일은 여기서 지우지 않는다.
//    구 util 파일 정리는 migrations registry(util-file 카테고리)가 담당한다 (#500).
export function copyUtilModules(tempDir, type, { force = false } = {}, targetRoot = ".") {
  const src = join(tempDir, ".github", "util", type);
  if (!exists(src)) return { copied: false, moduleCount: 0 };
  if (!force) return { copied: false, moduleCount: 0 }; // SP2-B: force 경로만

  const dst = join(targetRoot, ".github", "util", type);
  copyDirSync(src, dst);

  // 하위 디렉토리 개수 = 모듈 수 (.sh: for dir in "$util_dst"/*/)
  // `_` 로 시작하는 폴더는 모듈이 아니라 모듈들이 공유하는 자산이다
  // (예: flutter/_shared — 마법사 3종 공통 CSS/JS). 개수에서 제외한다.
  let moduleCount = 0;
  for (const e of readdirSync(dst, { withFileTypes: true })) {
    if (e.isDirectory() && !e.name.startsWith("_")) moduleCount++;
  }
  return { copied: true, moduleCount };
}
