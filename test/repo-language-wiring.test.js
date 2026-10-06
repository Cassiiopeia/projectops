import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";
import { parseTemplateOptions } from "../src/core/version-yml.js";
import { parseArgs, CliError } from "../src/cli/args.js";

const REPO = join(import.meta.dirname, "..");

function project(existingVersionYml) {
  const dir = mkdtempSync(join(tmpdir(), "lang-wire-"));
  writeFileSync(join(dir, "package.json"), '{"name":"x","version":"1.0.0"}');
  if (existingVersionYml) writeFileSync(join(dir, "version.yml"), existingVersionYml);
  return dir;
}
const EXISTING = 'version: "1.0.0"\nversion_code: 1\nproject_types: ["node"]\nmetadata:\n  template:\n    source: "projectops"\n    version: "4.0.0"\n    options:\n      deploy: "none"\n      publish: []\n';
const install = (dir, extra = []) =>
  run(["--force", "-t", "node", "-m", "full", "--lang", "en", ...extra], { cwd: dir, source: { type: "local", path: REPO } });
const bug = (dir) => readFileSync(join(dir, ".github/ISSUE_TEMPLATE/bug_report.md"), "utf8");

test("parseTemplateOptions: language 를 읽고, 없으면 null", () => {
  assert.equal(parseTemplateOptions("metadata:\n  template:\n    options:\n      language: ko\n").language, "ko");
  assert.equal(parseTemplateOptions("metadata:\n  template:\n    options:\n      deploy: none\n").language, null);
});

test("parseArgs: --language 는 en|ko 만 받는다", () => {
  assert.equal(parseArgs(["--language", "ko"]).language, "ko");
  assert.throws(() => parseArgs(["--language", "xx"]), CliError);
});

test("신규 설치는 language: en, 템플릿은 영문", async () => {
  const dir = project();
  assert.equal(await install(dir), 0);
  assert.match(readFileSync(join(dir, "version.yml"), "utf8"), /language: en/);
  assert.match(bug(dir), /\[Bug\]/);
  assert.ok(!existsSync(join(dir, ".github/i18n")), "오버레이 폴더는 사용자 레포로 복사되지 않는다");
});

test("키 없는 기존 설치는 ko 를 유지하고 라벨은 label_style 이 변환한다 (오버레이 먼저)", async () => {
  const dir = project(EXISTING);
  assert.equal(await install(dir), 0);
  assert.match(readFileSync(join(dir, "version.yml"), "utf8"), /language: ko/);
  assert.match(bug(dir), /\[버그\]/);
  assert.match(bug(dir), /^labels: \[작업전\]$/m, "오버레이 뒤에 label_style ko 가 적용돼야 한다");
});

test("기존 ko 레포를 --language en 으로 전환", async () => {
  const dir = project(EXISTING);
  assert.equal(await install(dir, ["--language", "en"]), 0);
  assert.match(readFileSync(join(dir, "version.yml"), "utf8"), /language: en/);
  assert.match(bug(dir), /\[Bug\]/);
});

// 최종 리뷰 Critical: 대화형 issues 모드가 baseCtx 로 ctx 를 만들어 language/labelStyle 이 null 이 되고,
// runIssues 의 ?? "en" 때문에 키 없는 기존 한국어 레포가 질문 없이 영문 템플릿을 받았다.
import { runInteractive } from "../src/commands/interactive.js";
const noop = () => {};
const issuesIo = { intro: noop, outro: noop, note: noop, cancelMessage: noop, summary: noop,
  selectMode: async () => "issues", askYesNo: async () => true, askText: async (_m, d) => d };

test("대화형 issues 모드: 키 없는 기존 한국어 레포는 한국어 템플릿을 유지한다", async () => {
  const dir = project(EXISTING);
  const code = await runInteractive({}, { cwd: dir, source: { type: "local", path: REPO }, io: issuesIo });
  assert.equal(code, 0);
  assert.match(bug(dir), /\[버그\]/);
  assert.match(bug(dir), /^labels: \[작업전\]$/m);
});

test("대화형 issues 모드: 신규 레포는 영문 템플릿", async () => {
  const dir = project();
  const code = await runInteractive({}, { cwd: dir, source: { type: "local", path: REPO }, io: issuesIo });
  assert.equal(code, 0);
  assert.match(bug(dir), /\[Bug\]/);
  assert.match(bug(dir), /^labels: \["status: todo"\]$/m);
});
