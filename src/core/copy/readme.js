// README 버전 섹션 추가.
import { join } from "node:path";
import { existsSync, readFileSync, appendFileSync } from "node:fs";

const MARKER = "<!-- AUTO-VERSION-SECTION";
// ## (최신 버전|최신버전|Latest version|Version|버전) : vX.Y.Z (대소문자 무시)
const VERSION_LINE_RE = /##\s*(최신\s*버전|최신버전|Latest\s+version|Version|버전)\s*:\s*v[0-9]+\.[0-9]+\.[0-9]+/i;

// 레포 언어별 섹션 문구 (.github/scripts/i18n 의 readme.version_heading 과 같은 값)
const SECTION_TEXT = {
  en: { heading: "Latest version", changelogLink: "View the full version history" },
  ko: { heading: "최신 버전", changelogLink: "전체 버전 기록 보기" },
};

// README.md 없으면 스킵. 마커 또는 버전 라인 있으면 스킵. 없으면 파일 끝에 append.
// 반환: 'skip-no-readme' | 'skip-marker' | 'skip-version-line' | 'added'
// language 미지정은 ko — 언어를 넘기지 않는 기존 호출부의 결과를 바꾸지 않기 위함
export function addVersionSectionToReadme(version, targetRoot = ".", language = "ko") {
  const p = join(targetRoot, "README.md");
  if (!existsSync(p)) return "skip-no-readme";
  const content = readFileSync(p, "utf8");
  if (content.includes(MARKER)) return "skip-marker";
  if (VERSION_LINE_RE.test(content)) return "skip-version-line";

  const text = SECTION_TEXT[language] ?? SECTION_TEXT.ko;
  // append 본문은 빈 줄 + "---"로 시작 (원본 파일이 개행으로 끝난다는 전제).
  const section =
    "\n" +
    "---\n" +
    "\n" +
    "<!-- AUTO-VERSION-SECTION: DO NOT EDIT MANUALLY -->\n" +
    `## ${text.heading} : v${version}\n` +
    "\n" +
    `[${text.changelogLink}](CHANGELOG.md)\n`;
  appendFileSync(p, section);
  return "added";
}
