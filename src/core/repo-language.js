// Repo text language (#769): English ("en") is the source, Korean ("ko") is an overlay.
// Keeping a Korean copy next to every file lets the two drift, so the Korean version lives only in .github/i18n/ko/
// and, with language: ko, is copied over the same relative paths right after the copy.
import { join, relative, dirname } from "node:path";
import { existsSync, readdirSync, copyFileSync, mkdirSync, statSync } from "node:fs";

export const REPO_LANGUAGES = ["en", "ko"];

// Decision when version.yml has no saved value. New installs get English; existing installs keep Korean.
// (Same principle as label_style — an update alone must not change the text in a user repo.)
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

// Korean mode: copy every overlay file to the same relative path under targetRoot/.github/.
// Returns { changed, failed }. changed holds copied paths relative to the repo root (.github/...),
// failed holds { file, error } entries that could not be copied. Both are empty for en or when there is no overlay.
// One failure does not stop the rest — stopping at the first failure would leave English and Korean mixed, or all English.
// Never throws: the English template simply remains, which is no reason to kill the install. The caller reports failed instead.
export function applyRepoLanguage(tempDir, targetRoot, language) {
  const changed = [];
  const failed = [];
  if (language !== "ko") return { changed, failed };
  const overlay = join(tempDir, ".github", "i18n", "ko");
  if (!existsSync(overlay)) return { changed, failed };
  let files = [];
  try {
    files = walk(overlay);
  } catch (e) {
    failed.push({ file: ".github/i18n/ko", error: String(e?.message ?? e) });
    return { changed, failed };
  }
  for (const file of files) {
    const rel = relative(overlay, file).split("\\").join("/");
    try {
      const dst = join(targetRoot, ".github", rel);
      mkdirSync(dirname(dst), { recursive: true });
      copyFileSync(file, dst);
      changed.push(`.github/${rel}`);
    } catch (e) {
      failed.push({ file: `.github/${rel}`, error: String(e?.message ?? e) });
    }
  }
  return { changed, failed };
}
