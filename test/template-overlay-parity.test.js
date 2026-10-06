// 영문 원본과 한국어 오버레이가 같은 구조인지 지킨다 (#769). 번역은 달라도 구조는 같아야 한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";

const ROOT = join(import.meta.dirname, "..");
const read = (rel) => readFileSync(join(ROOT, rel), "utf8");
const TEMPLATES = ["bug_report", "feature_request", "design_request", "qa_request"].map((n) => `.github/ISSUE_TEMPLATE/${n}.md`);
const PAIRS = [...TEMPLATES, ".github/PULL_REQUEST_TEMPLATE.md"].map((rel) => [rel, rel.replace(".github/", ".github/i18n/ko/")]);

function frontmatter(text) {
  const m = text.match(/^---\n([\s\S]*?)\n---\n/);
  return m ? Object.fromEntries(m[1].split("\n").map((l) => [l.split(":")[0], l.slice(l.indexOf(":") + 1).trim()])) : {};
}
const count = (text, re) => (text.match(re) || []).length;

test("오버레이 파일 목록이 원본과 같다", () => {
  for (const [en, ko] of PAIRS) {
    assert.ok(existsSync(join(ROOT, en)), en);
    assert.ok(existsSync(join(ROOT, ko)), ko);
  }
  const overlay = readdirSync(join(ROOT, ".github/i18n/ko/ISSUE_TEMPLATE")).filter((f) => f.endsWith(".md")).sort();
  assert.deepEqual(overlay, TEMPLATES.map((t) => t.split("/").pop()).sort());
});

test("frontmatter 의 labels 와 assignees 가 같고, name 과 about 은 둘 다 있다", () => {
  for (const [en, ko] of PAIRS.filter(([e]) => e.includes("ISSUE_TEMPLATE"))) {
    const a = frontmatter(read(en)); const b = frontmatter(read(ko));
    assert.equal(a.labels, b.labels, `${en} labels`);
    assert.equal(a.assignees, b.assignees, `${en} assignees`);
    assert.ok(a.name && b.name && a.about && b.about, en);
  }
});

test("절 개수, 제목 태그 개수, 주석 개수가 같다", () => {
  for (const [en, ko] of PAIRS) {
    const a = read(en); const b = read(ko);
    assert.equal(count(a, /^.+\n---$/gm), count(b, /^.+\n---$/gm), `${en} sections`);
    assert.equal(count(a, /\[[^\]\n]+\]/g), count(b, /\[[^\]\n]+\]/g), `${en} bracket tags`);
    assert.equal(count(a, /<!--/g), count(b, /<!--/g), `${en} comments`);
  }
});

test("영문 원본의 제목 태그는 영문 표준 태그만 쓴다", () => {
  const allowed = new Set(["Bug", "Feature Request", "Feature", "Improvement", "Docs", "Design", "QA", "Urgent", "Category"]);
  for (const rel of TEMPLATES) {
    for (const t of read(rel).matchAll(/\[([^\]\n]+)\]/g)) {
      if (t[1].startsWith("status:") || t[1].includes('"') || t[1] === "Cassiiopeia" || t[1].startsWith("~")) continue;
      assert.ok(allowed.has(t[1]), `${rel}: 허용되지 않은 태그 [${t[1]}]`);
    }
  }
});

test("영문 원본에는 한글이 없다", () => {
  for (const [en] of PAIRS) assert.ok(!/[가-힣]/.test(read(en)), `${en} 에 한글이 남았다`);
});

test("오버레이 폴더는 초기화 때 지워지고, 설치 시 제외 목록에는 없다 (제외하면 오버레이를 읽을 수 없다)", () => {
  assert.match(read(".github/scripts/template_initializer.py"), /"\.github\/i18n"/);
  assert.doesNotMatch(read("src/core/exclusions.js"), /^\s+"\.github\/i18n",/m);
});
