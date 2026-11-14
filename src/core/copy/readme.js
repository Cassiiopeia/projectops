// Add the README version section.
import { join } from "node:path";
import { existsSync, readFileSync, appendFileSync } from "node:fs";

const MARKER = "<!-- AUTO-VERSION-SECTION";
// ## (최신 버전|최신버전|Latest version|Version|버전) : vX.Y.Z (case-insensitive)
const VERSION_LINE_RE = /##\s*(최신\s*버전|최신버전|Latest\s+version|Version|버전)\s*:\s*v[0-9]+\.[0-9]+\.[0-9]+/i;

// Section text per repo language (same values as readme.version_heading in .github/scripts/i18n)
const SECTION_TEXT = {
  en: { heading: "Latest version", changelogLink: "View the full version history" },
  ko: { heading: "최신 버전", changelogLink: "전체 버전 기록 보기" },
};

// Skip if README.md is missing. Skip if the marker or a version line exists. Otherwise append at the end of the file.
// Returns 'skip-no-readme' | 'skip-marker' | 'skip-version-line' | 'added'
// language defaults to ko — keeps results unchanged for existing callers that pass no language
export function addVersionSectionToReadme(version, targetRoot = ".", language = "ko") {
  const p = join(targetRoot, "README.md");
  if (!existsSync(p)) return "skip-no-readme";
  const content = readFileSync(p, "utf8");
  if (content.includes(MARKER)) return "skip-marker";
  if (VERSION_LINE_RE.test(content)) return "skip-version-line";

  const text = SECTION_TEXT[language] ?? SECTION_TEXT.ko;
  // The appended body starts with a blank line + "---" (assumes the original file ends with a newline).
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
