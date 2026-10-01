// CLI 입력 검증·오류 처리 회귀 테스트 (#674 #672 등) — 실제 run()을 로컬 템플릿으로 끝까지 돌린다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, existsSync } from "node:fs";
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
