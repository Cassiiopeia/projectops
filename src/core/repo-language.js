// 레포 문구 언어(#769): 영문("en")이 정본, 한국어("ko")는 오버레이다.
// 한글 사본을 파일마다 따로 두면 두 벌이 어긋나므로, 한국어판은 .github/i18n/ko/ 한 곳에만 두고
// language: ko 일 때 복사 직후 같은 상대경로로 덮는다.
import { join, relative, dirname } from "node:path";
import { existsSync, readdirSync, copyFileSync, mkdirSync, statSync } from "node:fs";

export const REPO_LANGUAGES = ["en", "ko"];

// version.yml 에 저장값이 없을 때의 결정. 신규 설치는 영문, 이미 설치된 레포는 한국어 유지.
// (label_style 과 같은 원칙 — 업데이트만으로 사용자 레포의 문구가 바뀌면 안 된다.)
export function resolveRepoLanguage({ flag, stored, existing }) {
  if (REPO_LANGUAGES.includes(flag)) return flag;
  if (REPO_LANGUAGES.includes(stored)) return stored;
  return existing ? "ko" : "en";
}

function walk(dir) {
  const out = [];
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

// 한국어 모드: 오버레이의 모든 파일을 targetRoot/.github/ 아래 같은 상대경로로 복사한다.
// 반환: 복사한 파일의 레포 루트 기준 상대경로(.github/...). en 이거나 오버레이가 없으면 [].
// 실패해도 예외를 던지지 않는다 — 영문 템플릿이 남을 뿐 설치를 죽일 이유가 아니다.
export function applyRepoLanguage(tempDir, targetRoot, language) {
  if (language !== "ko") return [];
  const overlay = join(tempDir, ".github", "i18n", "ko");
  if (!existsSync(overlay)) return [];
  const changed = [];
  try {
    for (const file of walk(overlay)) {
      const rel = relative(overlay, file).split("\\").join("/");
      const dst = join(targetRoot, ".github", rel);
      mkdirSync(dirname(dst), { recursive: true });
      copyFileSync(file, dst);
      changed.push(`.github/${rel}`);
    }
  } catch {
    return changed;
  }
  return changed;
}
