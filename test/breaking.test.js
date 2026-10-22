import { test } from "node:test";
import assert from "node:assert/strict";
import { compareVersions, collectBreaking } from "../src/core/breaking.js";

test("compareVersions", () => {
  assert.equal(compareVersions("1.2.3", "1.2.3"), 0);
  assert.equal(compareVersions("v2.0.0", "1.9.9"), 1);
  assert.equal(compareVersions("1.2", "1.2.0"), 0);   // 누락 자리=0
  assert.equal(compareVersions("1.0.0", "1.0.1"), -1);
});

test("collectBreaking range + bug fix (target beyond 1.3.14)", () => {
  const json = {
    _meta: { severity: "critical" },
    "3.0.0": { severity: "critical", title: "x" },   // .sh 버그였다면 1.3.14 초과라 누락됨
    "1.2.0": { severity: "warning", title: "y" },     // current 이하 → 제외
  };
  const { critical, warnings } = collectBreaking(json, "2.9.9", "3.0.5");
  assert.equal(critical.length, 1);   // 3.0.0 잡힘 (버그 수정 효과)
  assert.equal(warnings.length, 0);
});

// ── runBreakingCheck 요약 리스트 표시 (#473) ──
import { runBreakingCheck } from "../src/core/breaking-check.js";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function captureStderr(fn) {
  const orig = process.stderr.write;
  let out = "";
  process.stderr.write = (chunk) => { out += chunk; return true; };
  return Promise.resolve()
    .then(fn)
    .then((r) => { process.stderr.write = orig; return { out, r }; },
          (err) => { process.stderr.write = orig; throw err; });
}

const BC_JSON = {
  "9.0.0": { severity: "critical", title: "큰 변경", message: "아주 긴 조치 방법 본문입니다." },
  "9.1.0": { severity: "warning", title: "작은 변경", message: "경고 본문." },
};

function bcFixture() {
  const cwd = mkdtempSync(join(tmpdir(), "bc-"));
  writeFileSync(join(cwd, "version.yml"),
    'version: "1.0.0"\nmetadata:\n  template:\n    version: "1.0.0"\n');
  return cwd;
}

test("runBreakingCheck: 비대화형 — 제목 요약만 출력, 전문 미출력 + 참고 안내 (#473)", async () => {
  const cwd = bcFixture();
  try {
    const { out, r } = await captureStderr(() =>
      runBreakingCheck({ cwd, tempDir: cwd, templateVersion: "9.9.9", loader: async () => BC_JSON }));
    assert.equal(r, true);
    assert.match(out, /CRITICAL 1, WARNING 1/);
    assert.match(out, /\[CRITICAL\] 9\.0\.0 - 큰 변경/);
    assert.match(out, /\[WARNING\]\s+9\.1\.0 - 작은 변경/);
    assert.doesNotMatch(out, /아주 긴 조치 방법 본문/);   // 전문 통덤프 제거
    assert.doesNotMatch(out, /╔/);                        // 박스 경계 제거 (래핑 붕괴 방지)
    assert.match(out, /see \.github\/config\/breaking-changes\.json/);      // 상세 참조 안내
  } finally { rmSync(cwd, { recursive: true, force: true }); }
});

test("runBreakingCheck: 대화형 — 상세 보기 선택 시에만 전문 출력 (#473)", async () => {
  const cwd = bcFixture();
  try {
    // 1번째 질문(상세 보기)=yes, 2번째 질문(진행 확인)=yes
    const answers = [true, true];
    const { out, r } = await captureStderr(() =>
      runBreakingCheck({ cwd, tempDir: cwd, templateVersion: "9.9.9", loader: async () => BC_JSON,
        askYesNo: async () => answers.shift() }));
    assert.equal(r, true);
    assert.match(out, /아주 긴 조치 방법 본문/);            // 선택 시 전문 표시
  } finally { rmSync(cwd, { recursive: true, force: true }); }
});

test("runBreakingCheck: 대화형 — 상세 거절해도 CRITICAL 진행 게이트는 동작", async () => {
  const cwd = bcFixture();
  try {
    const answers = [false, false]; // 상세 안 봄, 진행 거부
    const { r } = await captureStderr(() =>
      runBreakingCheck({ cwd, tempDir: cwd, templateVersion: "9.9.9", loader: async () => BC_JSON,
        askYesNo: async () => answers.shift() }));
    assert.equal(r, false); // 진행 거부 → false
  } finally { rmSync(cwd, { recursive: true, force: true }); }
});

// ── 항목 문구 화면 언어 선택 (#988) ──
import { readFileSync } from "node:fs";
import { localizeBreakingEntry } from "../src/core/breaking.js";
import { setLang, getLang, getLangSource } from "../src/i18n/index.js";

const BILINGUAL_ENTRY = {
  severity: "critical",
  title: "Big change", message: "English action steps.",
  title_ko: "큰 변경", message_ko: "한국어 조치 방법.",
};

test("localizeBreakingEntry: ko 는 *_ko, en 은 영어 원문", () => {
  assert.deepEqual(localizeBreakingEntry(BILINGUAL_ENTRY, "ko"), { title: "큰 변경", message: "한국어 조치 방법." });
  assert.deepEqual(localizeBreakingEntry(BILINGUAL_ENTRY, "en"), { title: "Big change", message: "English action steps." });
});

test("localizeBreakingEntry: *_ko 없으면 ko 여도 영어로 폴백", () => {
  const englishOnly = { severity: "warning", title: "Only English", message: "Body." };
  assert.deepEqual(localizeBreakingEntry(englishOnly, "ko"), { title: "Only English", message: "Body." });
  // 한 필드만 번역된 경우 필드별 폴백
  assert.deepEqual(localizeBreakingEntry({ ...englishOnly, title_ko: "제목만" }, "ko"), { title: "제목만", message: "Body." });
  assert.deepEqual(localizeBreakingEntry({}, "ko"), { title: "", message: "" });
});

// 화면 언어를 잠깐 바꿔 runBreakingCheck 출력 확인 (끝나면 원래 언어로 복원)
async function runCheckInLang(lang, answers) {
  const previousLang = getLang(), previousSource = getLangSource();
  setLang(lang);
  const cwd = bcFixture();
  try {
    return await captureStderr(() =>
      runBreakingCheck({ cwd, tempDir: cwd, templateVersion: "9.9.9",
        loader: async () => ({ "9.0.0": BILINGUAL_ENTRY }),
        askYesNo: async () => answers.shift() }));
  } finally {
    setLang(previousLang, previousSource);
    rmSync(cwd, { recursive: true, force: true });
  }
}

test("runBreakingCheck: 화면 언어 ko 면 한국어 제목·본문 (#988)", async () => {
  const { out } = await runCheckInLang("ko", [true, true]);
  assert.match(out, /\[CRITICAL\] 9\.0\.0 - 큰 변경/);
  assert.match(out, /한국어 조치 방법/);
  assert.doesNotMatch(out, /English action steps/);
});

test("runBreakingCheck: 화면 언어 en 이면 영어 제목·본문 (#988)", async () => {
  const { out } = await runCheckInLang("en", [true, true]);
  assert.match(out, /\[CRITICAL\] 9\.0\.0 - Big change/);
  assert.match(out, /English action steps/);
  assert.doesNotMatch(out, /큰 변경|한국어 조치 방법/);
});

// 실제 레지스트리: 구버전 CLI가 읽는 title/message 가 모든 항목에 영어로 있어야 함
const HANGUL_RE = /[가-힣]/;
// 영어 message 안 한글 허용 항목 (실제 GitHub 라벨 이름 — 번역하면 틀린 안내)
const HANGUL_ALLOWED_IN_MESSAGE = new Set(["2.6.23"]);

test("breaking-changes.json: 유효한 JSON, 모든 항목에 영어 title/message (#988)", () => {
  const registry = JSON.parse(readFileSync(new URL("../.github/config/breaking-changes.json", import.meta.url), "utf8"));
  const versions = Object.keys(registry).filter((key) => !key.startsWith("_"));
  assert.ok(versions.length > 0);
  for (const version of versions) {
    const entry = registry[version];
    assert.match(version, /^\d+\.\d+\.\d+$/, version);
    assert.ok(["critical", "warning"].includes(entry.severity), `${version} severity`);
    assert.ok(entry.title?.trim(), `${version} title`);
    assert.ok(entry.message?.trim(), `${version} message`);
    assert.doesNotMatch(entry.title, HANGUL_RE, `${version} title 은 영어`);
    if (!HANGUL_ALLOWED_IN_MESSAGE.has(version)) assert.doesNotMatch(entry.message, HANGUL_RE, `${version} message 는 영어`);
    // *_ko 는 선택 — 있으면 비어 있지 않은 문자열
    for (const key of ["title_ko", "message_ko"]) {
      if (key in entry) assert.ok(typeof entry[key] === "string" && entry[key].trim(), `${version} ${key}`);
    }
  }
});
