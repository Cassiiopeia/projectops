// 수정한 워크플로 병합 안내 (#654) — 건너뛴 파일의 새 템플릿을 incoming에 남기고 종료 화면에 안내한다.
// 기존 복사 동작(사용자 수정본 유지)은 그대로여야 하고, incoming 실패가 마법사를 죽이면 안 된다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";
import { lineDiffCounts, INCOMING_DIR } from "../src/core/incoming.js";
import { MIGRATION_DIR } from "../src/core/run-trace.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));
const write = (root, rel, content) => {
  mkdirSync(join(root, rel, ".."), { recursive: true });
  writeFileSync(join(root, rel), content);
};
const NODE_WF = "PROJECT-NODE-CI.yaml";
const TPL_BODY = "name: n\non:\n  push:\njobs:\n  a: 1\n";
const USER_BODY = "name: n\non:\n  pull_request:\njobs:\n  a: 1\n  b: 2\n";

function makeTemplate() {
  const tpl = fresh("inc-tpl-");
  write(tpl, ".github/scripts/version_manager.sh", "#!/bin/bash\n");
  write(tpl, ".github/scripts/changelog_manager.py", "# py\n");
  write(tpl, ".github/config/wizard-prompts.yml", 'PROJECT_NAME:\n  label: "이름"\n');
  write(tpl, ".github/workflows/project-types/common/PROJECT-COMMON-CI.yaml", "name: ci\non:\n  push:\n");
  write(tpl, `.github/workflows/project-types/node/${NODE_WF}`, TPL_BODY);
  writeFileSync(join(tpl, "version.yml"), 'version: "4.7.0"\n');
  writeFileSync(join(tpl, "PROJECTOPS-SETUP-GUIDE.md"), "# guide\n");
  return tpl;
}
function makeTarget(modified = true) {
  const t = fresh("inc-tgt-");
  writeFileSync(join(t, "package.json"), '{"name":"app","version":"1.0.0"}\n');
  if (modified) write(t, `.github/workflows/${NODE_WF}`, USER_BODY);
  return t;
}
// 종료 화면(stderr)을 캡처한다
async function cli(argv, target, tpl) {
  let out = "";
  const se = process.stderr.write;
  process.stderr.write = (s) => { out += String(s); return true; };
  let code;
  try {
    code = await run(argv, { cwd: target, source: { type: "local", path: tpl }, clock: { now: "2026-09-30 00:00:00", today: "2026-09-30" } });
  } finally { process.stderr.write = se; }
  return { code, out };
}
const cleanup = (...d) => d.forEach((x) => rmSync(x, { recursive: true, force: true }));
const ARGV = ["--mode", "workflows", "--type", "node", "--force"];

test("lineDiffCounts: 추가/삭제 줄 수를 센다", () => {
  assert.deepEqual(lineDiffCounts("a\nb\nc\n", "a\nb\nc\n"), { added: 0, removed: 0 });
  assert.deepEqual(lineDiffCounts("a\nb\n", "a\nx\ny\n"), { added: 2, removed: 1 });
  assert.deepEqual(lineDiffCounts("a\r\nb\r\n", "a\nb\n"), { added: 0, removed: 0 });
});

test("건너뛴 파일: 사용자 수정본 유지 + incoming에 새 템플릿 저장 + workflows에 새 파일 없음", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    const before = readdirSync(join(tgt, ".github/workflows")).sort();
    const { code, out } = await cli(ARGV, tgt, tpl);
    assert.equal(code, 0);
    assert.equal(readFileSync(join(tgt, ".github/workflows", NODE_WF), "utf8"), USER_BODY, "사용자 원본 무변경");
    assert.equal(readFileSync(join(tgt, INCOMING_DIR, NODE_WF), "utf8"), TPL_BODY, "새 템플릿 저장");
    const wfAfter = readdirSync(join(tgt, ".github/workflows")).sort();
    // 다른 공통 워크플로는 새로 생길 수 있으나 incoming 사본·.template 류가 workflows에 생기면 안 된다
    assert.deepEqual(wfAfter.filter((f) => !before.includes(f)), ["PROJECT-COMMON-CI.yaml"]);
    assert.match(readFileSync(join(tgt, INCOMING_DIR, ".gitignore"), "utf8"), /^\*$/m);
    assert.match(readFileSync(join(tgt, INCOMING_DIR, ".gitignore"), "utf8"), /^!\.gitignore$/m);
    assert.equal(existsSync(join(tgt, ".gitignore")), false, "루트 .gitignore 무접촉");

    assert.match(out, /수정한 워크플로 1개/);
    assert.ok(out.includes(NODE_WF));
    assert.match(out, /추가 1줄, 삭제 2줄/);
    assert.ok(out.includes(`diff -u .github/workflows/${NODE_WF} ${INCOMING_DIR}/${NODE_WF}`));
    assert.ok(out.includes("git diff --no-index"));
    assert.ok(!/[·—]/.test((out.split("수정한 워크플로")[1] ?? "").split("🔧")[0]), "가운뎃점/em dash 금지");

    // 로그·가이드에도 남는다
    const logs = readdirSync(join(tgt, MIGRATION_DIR));
    const jsonl = readFileSync(join(tgt, MIGRATION_DIR, logs.find((f) => f.endsWith(".jsonl"))), "utf8");
    const ev = jsonl.split("\n").filter(Boolean).map((l) => JSON.parse(l)).find((e) => e.action === "skipped-conflict");
    assert.equal(ev.detail.incoming, `${INCOMING_DIR}/${NODE_WF}`);
    assert.equal(ev.detail.added, 1); assert.equal(ev.detail.removed, 2);
    const guide = readFileSync(join(tgt, ".github/.projectops/logs/PROJECTOPS-MIGRATION-GUIDE.md"), "utf8");
    assert.ok(guide.includes(`${INCOMING_DIR}/${NODE_WF}`));
  } finally { cleanup(tpl, tgt); }
});

test("건너뛴 파일이 없으면 종료 화면에 병합 안내가 없고 incoming도 생기지 않는다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget(false);
  try {
    const { code, out } = await cli(ARGV, tgt, tpl);
    assert.equal(code, 0);
    assert.ok(!out.includes("수정한 워크플로"));
    assert.ok(!out.includes("incoming"));
    assert.equal(existsSync(join(tgt, INCOMING_DIR)), false);
  } finally { cleanup(tpl, tgt); }
});

test("incoming 저장이 실패해도 마법사는 정상 완료한다 (exit 0, 나머지 복사 진행)", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    // incoming 자리를 파일로 막아 mkdir 실패를 유도한다
    write(tgt, INCOMING_DIR, "not a dir");
    const { code, out } = await cli(ARGV, tgt, tpl);
    assert.equal(code, 0);
    assert.equal(readFileSync(join(tgt, ".github/workflows", NODE_WF), "utf8"), USER_BODY);
    assert.ok(existsSync(join(tgt, ".github/workflows/PROJECT-COMMON-CI.yaml")), "나머지 복사는 진행");
    assert.match(out, /incoming/);          // 경고 한 줄
    assert.ok(out.includes("Setup Complete"), "종료 화면 정상 출력");
  } finally { cleanup(tpl, tgt); }
});

test("재실행하면 incoming을 최신 템플릿으로 덮어쓴다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    await cli(ARGV, tgt, tpl);
    write(tpl, `.github/workflows/project-types/node/${NODE_WF}`, TPL_BODY + "  c: 3\n");
    await cli(ARGV, tgt, tpl);
    assert.equal(readFileSync(join(tgt, INCOMING_DIR, NODE_WF), "utf8"), TPL_BODY + "  c: 3\n");
  } finally { cleanup(tpl, tgt); }
});
