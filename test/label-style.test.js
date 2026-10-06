import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { applyLabelStyle, resolveLabelStyle } from "../src/core/label-style.js";

function fixture() {
  const root = mkdtempSync(join(tmpdir(), "label-style-"));
  const gh = join(root, ".github");
  mkdirSync(join(gh, "config"), { recursive: true });
  mkdirSync(join(gh, "ISSUE_TEMPLATE"), { recursive: true });
  mkdirSync(join(gh, "workflows"), { recursive: true });
  writeFileSync(join(gh, "config", "issue-labels.yml"),
    '- name: "status: todo"\n  from_name: 작업전\n  description: Not started documentation\n\n- name: documentation\n  from_name: 문서\n');
  writeFileSync(join(gh, "ISSUE_TEMPLATE", "bug_report.md"), '---\nname: bug\nlabels: ["status: todo"]\n---\nbody status: todo\n');
  writeFileSync(join(gh, "workflows", "PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml"), "labels: ['status: todo'],\n");
  return root;
}

test("resolveLabelStyle: 플래그 > 저장값 > (기존 ko / 신규 en)", () => {
  assert.equal(resolveLabelStyle({ flag: "en", stored: "ko", existing: true }), "en");
  assert.equal(resolveLabelStyle({ stored: "ko", existing: false }), "ko");
  assert.equal(resolveLabelStyle({ existing: true }), "ko");
  assert.equal(resolveLabelStyle({ existing: false }), "en");
  assert.equal(resolveLabelStyle({ flag: "xx", existing: false }), "en");
});

test("applyLabelStyle: en 은 아무것도 바꾸지 않는다", () => {
  const root = fixture();
  assert.deepEqual(applyLabelStyle(root, "en"), []);
  assert.match(readFileSync(join(root, ".github/config/issue-labels.yml"), "utf8"), /status: todo/);
});

test("applyLabelStyle: ko 는 name 줄·템플릿 labels·QA 봇만 한글로 되돌린다", () => {
  const root = fixture();
  const changed = applyLabelStyle(root, "ko");
  assert.equal(changed.length, 3);
  const yml = readFileSync(join(root, ".github/config/issue-labels.yml"), "utf8");
  assert.match(yml, /^- name: 작업전$/m);
  assert.match(yml, /^- name: 문서$/m);
  assert.ok(!yml.includes("from_name"));
  assert.ok(yml.includes("Not started documentation"), "설명 문장은 건드리지 않는다");
  const tpl = readFileSync(join(root, ".github/ISSUE_TEMPLATE/bug_report.md"), "utf8");
  assert.match(tpl, /^labels: \[작업전\]$/m);
  assert.ok(tpl.includes("body status: todo"), "본문은 건드리지 않는다");
  assert.match(readFileSync(join(root, ".github/workflows/PROJECT-COMMON-QA-ISSUE-CREATION-BOT.yaml"), "utf8"), /\['작업전'\]/);
});

test("applyLabelStyle: 두 번 적용해도 같다(멱등)", () => {
  const root = fixture();
  applyLabelStyle(root, "ko");
  assert.deepEqual(applyLabelStyle(root, "ko"), []);
});
