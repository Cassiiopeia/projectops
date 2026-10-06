import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { applyRepoLanguage, resolveRepoLanguage } from "../src/core/repo-language.js";

function tpl(withOverlay = true) {
  const root = mkdtempSync(join(tmpdir(), "lang-tpl-"));
  if (withOverlay) {
    mkdirSync(join(root, ".github/i18n/ko/ISSUE_TEMPLATE"), { recursive: true });
    writeFileSync(join(root, ".github/i18n/ko/ISSUE_TEMPLATE/bug_report.md"), "한국어 버그\n");
    writeFileSync(join(root, ".github/i18n/ko/PULL_REQUEST_TEMPLATE.md"), "한국어 PR\n");
  }
  return root;
}
function target() {
  const root = mkdtempSync(join(tmpdir(), "lang-tgt-"));
  mkdirSync(join(root, ".github/ISSUE_TEMPLATE"), { recursive: true });
  writeFileSync(join(root, ".github/ISSUE_TEMPLATE/bug_report.md"), "English bug\n");
  writeFileSync(join(root, ".github/PULL_REQUEST_TEMPLATE.md"), "English PR\n");
  return root;
}

test("resolveRepoLanguage: 플래그 > 저장값 > (기존 ko / 신규 en)", () => {
  assert.equal(resolveRepoLanguage({ flag: "en", stored: "ko", existing: true }), "en");
  assert.equal(resolveRepoLanguage({ stored: "ko", existing: false }), "ko");
  assert.equal(resolveRepoLanguage({ existing: true }), "ko");
  assert.equal(resolveRepoLanguage({ existing: false }), "en");
  assert.equal(resolveRepoLanguage({ flag: "xx", existing: false }), "en");
});

test("applyRepoLanguage: en 은 아무것도 바꾸지 않는다", () => {
  const t = target();
  assert.deepEqual(applyRepoLanguage(tpl(), t, "en"), []);
  assert.equal(readFileSync(join(t, ".github/ISSUE_TEMPLATE/bug_report.md"), "utf8"), "English bug\n");
});

test("applyRepoLanguage: ko 는 오버레이를 같은 상대경로로 덮는다", () => {
  const t = target();
  const changed = applyRepoLanguage(tpl(), t, "ko");
  assert.deepEqual(changed.sort(), [".github/ISSUE_TEMPLATE/bug_report.md", ".github/PULL_REQUEST_TEMPLATE.md"]);
  assert.equal(readFileSync(join(t, ".github/ISSUE_TEMPLATE/bug_report.md"), "utf8"), "한국어 버그\n");
  assert.equal(readFileSync(join(t, ".github/PULL_REQUEST_TEMPLATE.md"), "utf8"), "한국어 PR\n");
});

test("applyRepoLanguage: 오버레이가 없으면 죽지 않고 영문을 그대로 둔다", () => {
  const t = target();
  assert.deepEqual(applyRepoLanguage(tpl(false), t, "ko"), []);
  assert.equal(readFileSync(join(t, ".github/ISSUE_TEMPLATE/bug_report.md"), "utf8"), "English bug\n");
});

test("applyRepoLanguage: 두 번 적용해도 같다 (멱등), 오버레이 폴더는 복사하지 않는다", () => {
  const t = target();
  const src = tpl();
  applyRepoLanguage(src, t, "ko");
  applyRepoLanguage(src, t, "ko");
  assert.equal(readFileSync(join(t, ".github/PULL_REQUEST_TEMPLATE.md"), "utf8"), "한국어 PR\n");
  assert.ok(!existsSync(join(t, ".github/i18n")));
});
