// #782: 사용자 레포로 복사된 이슈 템플릿에 이 저장소 소유자가 담당자로 남으면 안 된다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, mkdirSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";
import { stripIssueTemplateAssignees } from "../src/core/copy/simple.js";

const REPO = join(import.meta.dirname, "..");
const project = () => {
  const dir = mkdtempSync(join(tmpdir(), "assg-"));
  writeFileSync(join(dir, "package.json"), '{"name":"x","version":"1.0.0"}');
  return dir;
};
const templates = (dir) => {
  const d = join(dir, ".github/ISSUE_TEMPLATE");
  return readdirSync(d).filter((f) => f.endsWith(".md")).map((f) => [f, readFileSync(join(d, f), "utf8")]);
};

test("stripIssueTemplateAssignees: frontmatter 의 assignees 줄만 지우고 본문은 건드리지 않는다", () => {
  const dir = project();
  mkdirSync(join(dir, ".github/ISSUE_TEMPLATE"), { recursive: true });
  writeFileSync(join(dir, ".github/ISSUE_TEMPLATE/a.md"),
    '---\nname: x\nlabels: ["status: todo"]\nassignees: [Cassiiopeia]\n---\n\nassignees: [본문의 같은 문구]\n');
  assert.deepEqual(stripIssueTemplateAssignees(dir), [".github/ISSUE_TEMPLATE/a.md"]);
  const out = readFileSync(join(dir, ".github/ISSUE_TEMPLATE/a.md"), "utf8");
  assert.ok(!/^assignees: \[Cassiiopeia\]$/m.test(out.split("\n---\n")[0]));
  assert.match(out, /assignees: \[본문의 같은 문구\]/);
  assert.deepEqual(stripIssueTemplateAssignees(dir), [], "두 번째는 바꿀 것이 없다 (멱등)");
});

for (const language of ["en", "ko"]) {
  test(`설치된 템플릿에 assignees 가 없다 (language=${language})`, async () => {
    const dir = project();
    const code = await run(["--force", "-t", "node", "-m", "full", "--lang", "en", "--language", language],
      { cwd: dir, source: { type: "local", path: REPO } });
    assert.equal(code, 0);
    for (const [name, text] of templates(dir)) {
      const front = text.split("\n---\n")[0];
      assert.ok(!/^assignees:/m.test(front), `${name} 에 assignees 가 남았다`);
    }
  });
}

test("이 저장소 자신의 템플릿 원본은 소유자를 유지한다", () => {
  assert.match(readFileSync(join(REPO, ".github/ISSUE_TEMPLATE/bug_report.md"), "utf8"), /^assignees: \[Cassiiopeia\]$/m);
});
