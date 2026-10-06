// 업데이트 기준점이 없을 때 수정 가능성이 있는 워크플로 교체를 화면에 알린다 (#673)
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { copyWorkflows } from "../src/core/copy/workflows.js";
import { printSummary } from "../src/ui/summary.js";
import { writeText } from "../src/core/fsutil.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));

function captureStderr(fn) {
  const orig = process.stderr.write;
  let out = "";
  process.stderr.write = (c) => { out += c; return true; };
  try { fn(); } finally { process.stderr.write = orig; }
  return out;
}

test("기준점 없이 달라진 common 워크플로: .bak 교체 + replacedBak 집계 + 화면 안내 (#673)", () => {
  const tpl = fresh("bn-t-"); const tgt = fresh("bn-g-");
  try {
    writeText(join(tpl, ".github/workflows/project-types/common/PROJECT-COMMON-X.yaml"), "name: new\n");
    writeText(join(tgt, ".github/workflows/PROJECT-COMMON-X.yaml"), "name: my custom edit\n");
    const c = copyWorkflows({ types: [], paths: new Map(), force: true, repoName: "r", resolvers: {} }, tpl, tgt, {});
    assert.deepEqual(c.replacedBak, ["PROJECT-COMMON-X.yaml"]);
    assert.ok(existsSync(join(tgt, ".github/workflows/PROJECT-COMMON-X.yaml.bak")));

    const out = captureStderr(() => printSummary({
      mode: "full", types: ["basic"], version: "1.0.0",
      counters: { workflowFiles: c.copiedFiles }, replacedBak: c.replacedBak,
    }, tgt));
    assert.match(out, /saved as \.bak/);
    assert.match(out, /PROJECT-COMMON-X\.yaml\.bak/);
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("교체한 파일이 없으면 안내를 출력하지 않는다 (#673)", () => {
  const out = captureStderr(() => printSummary({
    mode: "full", types: ["basic"], version: "1.0.0", counters: { workflowFiles: [] }, replacedBak: [],
  }, "."));
  assert.doesNotMatch(out, /saved as \.bak/);
});
