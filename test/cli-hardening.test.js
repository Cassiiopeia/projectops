// CLI 입력 검증·오류 처리 회귀 테스트 (#674 #672 등) — 실제 run()을 로컬 템플릿으로 끝까지 돌린다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, existsSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));
const rm = (...dirs) => dirs.forEach((d) => rmSync(d, { recursive: true, force: true }));

function makeTemplate() {
  const tpl = fresh("hard-tpl-");
  mkdirSync(join(tpl, ".github/scripts"), { recursive: true });
  writeFileSync(join(tpl, ".github/scripts/version_manager.sh"), "#!/bin/bash\n");
  mkdirSync(join(tpl, ".github/workflows/project-types/common"), { recursive: true });
  writeFileSync(join(tpl, ".github/workflows/project-types/common/PROJECT-COMMON-CI.yaml"), "name: ci\non:\n  push:\n");
  writeFileSync(join(tpl, "version.yml"), 'version: "4.7.0"\n');
  return tpl;
}

// 출력은 삼키고 종료코드와 오류 텍스트만 돌려준다
async function cli(argv, cwd, tpl) {
  const se = process.stderr.write; const so = process.stdout.write;
  const sl = console.log; const sel = console.error;
  let err = "";
  process.stderr.write = (s) => { err += s; return true; };
  process.stdout.write = () => true;
  console.log = () => {}; console.error = (m) => { err += `${m}\n`; };
  try {
    const code = await run(argv, { cwd, source: { type: "local", path: tpl },
      clock: { now: "2026-09-16 00:00:00", today: "2026-09-16" } });
    return { code, err };
  } finally { process.stderr.write = se; process.stdout.write = so; console.log = sl; console.error = sel; }
}

test("--paths: 저장소 밖 경로(..)·절대경로는 거부하고 파일을 쓰지 않는다 (#674)", async () => {
  const tpl = makeTemplate(); const tgt = fresh("hard-tgt-");
  try {
    for (const bad of ["node=../outside", "node=/etc"]) {
      const r = await cli(["--mode", "full", "--force", "--type", "node", "--paths", bad], tgt, tpl);
      assert.equal(r.code, 1, bad);
      assert.match(r.err, /--paths/);
    }
    assert.equal(existsSync(join(tgt, "version.yml")), false);
  } finally { rm(tpl, tgt); }
});

test("--paths: 존재하지 않는 폴더·선택하지 않은 타입 키는 거부한다 (#674)", async () => {
  const tpl = makeTemplate(); const tgt = fresh("hard-tgt-");
  try {
    let r = await cli(["--mode", "full", "--force", "--type", "node", "--paths", "node=nope"], tgt, tpl);
    assert.equal(r.code, 1);
    r = await cli(["--mode", "full", "--force", "--type", "node", "--paths", "react=client"], tgt, tpl);
    assert.equal(r.code, 1);
    assert.match(r.err, /react/);
    assert.equal(existsSync(join(tgt, "version.yml")), false);
  } finally { rm(tpl, tgt); }
});

test("--paths: 유효한 하위 폴더는 통과한다 (#674)", async () => {
  const tpl = makeTemplate(); const tgt = fresh("hard-tgt-");
  try {
    mkdirSync(join(tgt, "client"));
    writeFileSync(join(tgt, "client/package.json"), '{"name":"c","version":"1.0.0"}\n');
    const r = await cli(["--mode", "full", "--force", "--type", "node", "--paths", "node=client"], tgt, tpl);
    assert.equal(r.code, 0);
  } finally { rm(tpl, tgt); }
});

test("템플릿 내려받기 실패는 스택 트레이스 없이 오류 한 줄 + 종료코드 1 (#672)", async () => {
  const tgt = fresh("hard-tgt-");
  try {
    const se = process.stderr.write; let err = "";
    process.stderr.write = (s) => { err += s; return true; };
    const sl = console.log; console.log = () => {};
    let code;
    try {
      code = await run(["--mode", "full", "--force", "--type", "basic"], { cwd: tgt, source: { type: "git", repo: join(tgt, "no-such-repo") } });
    } finally { process.stderr.write = se; console.log = sl; }
    assert.equal(code, 1);
    assert.match(err, /Could not download the template/);
    assert.doesNotMatch(err, /\bat .*\(.*\.js:\d+/);   // 스택 프레임 없음
  } finally { rm(tgt); }
});

test("describeError: git 없음·권한·기타를 구분한다 (#672)", async () => {
  const { describeError } = await import("../src/cli/errors.js");
  assert.match(describeError(Object.assign(new Error("spawnSync git ENOENT"), { code: "ENOENT", syscall: "spawnSync git", path: "git" })).message, /git/);
  assert.match(describeError(Object.assign(new Error("EACCES: permission denied, mkdir x"), { code: "EACCES", path: "/x" })).hint, /write permission/);
  assert.match(describeError(new Error("boom")).message, /boom/);
});

test("읽기 전용 .github 는 스택 트레이스 없이 권한 안내 + 종료코드 1 (#672)", { skip: process.platform === "win32" || process.getuid?.() === 0 }, async () => {
  const tpl = makeTemplate(); const tgt = fresh("hard-tgt-");
  try {
    mkdirSync(join(tgt, ".github"));
    chmodSync(join(tgt, ".github"), 0o555);
    const r = await cli(["--mode", "full", "--force", "--type", "basic"], tgt, tpl);
    assert.equal(r.code, 1);
    assert.match(r.err, /write permission/);
  } finally { chmodSync(join(tgt, ".github"), 0o755); rm(tpl, tgt); }
});

test("읽기 전용 프로젝트 폴더는 clone 실패가 아니라 쓰기 불가로 안내한다 (#720)", { skip: process.platform === "win32" || process.getuid?.() === 0 }, async () => {
  const { acquireTemplate } = await import("../src/core/assets.js");
  const { describeError } = await import("../src/cli/errors.js");
  const tgt = fresh("hard-ro-");
  try {
    chmodSync(tgt, 0o555);
    let caught;
    try {
      // 존재하지 않는 원격 — 네트워크 없이도 clone 단계까지 가게 한다
      acquireTemplate({ tempDir: join(tgt, ".template_download_temp"), source: { type: "git", repo: join(tgt, "no-such-repo") } });
    } catch (e) { caught = e; }
    assert.ok(caught, "예외가 나야 한다");
    const d = describeError(caught);
    assert.match(d.message, /Cannot write the file/);
    assert.doesNotMatch(d.message, /Could not download/);
  } finally { chmodSync(tgt, 0o755); rm(tgt); }
});
