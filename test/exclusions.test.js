import { test } from "node:test";
import assert from "node:assert/strict";
import { PLUGIN_ITEMS_TO_REMOVE, DOCS_TO_REMOVE } from "../src/core/exclusions.js";

test("plugin items include CLI + npm workflows, exclude skills", () => {
  for (const x of ["bin", "src", ".claude-plugin", ".github/workflows/PROJECT-TEMPLATE-NPM-PUBLISH.yaml"])
    assert.ok(PLUGIN_ITEMS_TO_REMOVE.includes(x), `missing ${x}`);
  assert.ok(!PLUGIN_ITEMS_TO_REMOVE.includes("skills"));
});

test("docs removed include CLAUDE.md", () => {
  assert.ok(DOCS_TO_REMOVE.includes("CLAUDE.md"));
});

test("community labels are template-only: excluded from installs and removed by the initializer", async () => {
  const { readFileSync } = await import("node:fs");
  for (const x of [".github/config/community-labels.yml", ".github/workflows/PROJECT-TEMPLATE-SYNC-COMMUNITY-LABELS.yaml"]) {
    assert.ok(PLUGIN_ITEMS_TO_REMOVE.includes(x), `exclusions.js is missing ${x}`);
    const initializer = readFileSync(new URL("../.github/scripts/template_initializer.py", import.meta.url), "utf8");
    assert.ok(initializer.includes(x), `template_initializer.py is missing ${x}`);
  }
});

// ── 두 목록은 같은 집합이어야 한다 (#832) ─────────────────────────────────────
// "이 레포에서만 의미 있는 파일"은 template_initializer.py(새 프로젝트에서 삭제)와 exclusions.js(마법사가 복사 제외)
// 두 곳에 같이 적어야 한다. 기존 검사는 일부 항목만 봐서 한쪽에서 빠져도 몰랐다.
test("DOCS_TO_REMOVE 의 모든 파일이 template_initializer.py 삭제 목록에도 있다", async () => {
  const { readFileSync } = await import("node:fs");
  const { DOCS_TO_REMOVE } = await import("../src/core/exclusions.js");
  const py = readFileSync(new URL("../.github/scripts/template_initializer.py", import.meta.url), "utf8");
  // pr_body.md 는 릴리스마다 재생성되는 산출물이라 initializer 가 따로 다룬다
  const missing = DOCS_TO_REMOVE.filter((f) => f !== "pr_body.md" && !py.includes(`("${f}"`));
  assert.deepEqual(missing, [], `template_initializer.py 삭제 목록에 없는 파일: ${missing.join(", ")}`);
});
