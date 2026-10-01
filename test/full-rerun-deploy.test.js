// 재실행해도 version.yml deploy 값이 보존되고 구조가 변하지 않는다 (#670, 멱등)
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";
import { parseExisting, parseDeployBlock } from "../src/core/version-yml.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));

function makeTemplate() {
  const tpl = fresh("rr-tpl-");
  mkdirSync(join(tpl, ".github/scripts"), { recursive: true });
  writeFileSync(join(tpl, ".github/scripts/version_manager.sh"), "#!/bin/bash\n");
  mkdirSync(join(tpl, ".github/config"), { recursive: true });
  writeFileSync(join(tpl, ".github/config/wizard-prompts.yml"), 'SERVICE_DOMAIN:\n  label: "도메인"\n');
  const dir = join(tpl, ".github/workflows/project-types/node");
  mkdirSync(dir, { recursive: true });
  writeFileSync(join(dir, "PROJECT-NODE-CI.yaml"),
    'name: n\non:\n  push:\nenv:\n  SERVICE_DOMAIN: "x"   # @wizard ask:example.com\n');
  writeFileSync(join(tpl, "version.yml"), 'version: "4.7.0"\n');
  return tpl;
}

async function cli(argv, cwd, tpl) {
  const se = process.stderr.write; const sl = console.log; const sel = console.error;
  process.stderr.write = () => true; console.log = () => {}; console.error = () => {};
  try {
    return await run(argv, { cwd, source: { type: "local", path: tpl },
      clock: { now: "2026-09-16 00:00:00", today: "2026-09-16" } });
  } finally { process.stderr.write = se; console.log = sl; console.error = sel; }
}

test("full 재실행: 구조 불변 + 사용자가 고친 deploy 값 보존 (#670)", async () => {
  const tpl = makeTemplate(); const tgt = fresh("rr-tgt-");
  try {
    writeFileSync(join(tgt, "package.json"), '{"name":"a","version":"1.0.0"}\n');
    const args = ["--mode", "full", "--force", "--type", "node"];
    assert.equal(await cli(args, tgt, tpl), 0);
    const vy = join(tgt, "version.yml");
    const first = readFileSync(vy, "utf8");
    // template 이 metadata 안에 있다 (deploy 의 자식이 아니다)
    assert.equal(parseExisting(first).templateVersion, "4.7.0");
    const dep = parseDeployBlock(first);
    assert.ok(dep.get("node")?.has("SERVICE_DOMAIN"), "deploy 블록에 ask 값이 기록됨");

    // 사용자가 직접 고침 → 재실행해도 유지
    writeFileSync(vy, first.replace(/SERVICE_DOMAIN: "[^"]*"/, 'SERVICE_DOMAIN: "my.real.com"'));
    assert.equal(await cli(args, tgt, tpl), 0);
    const second = readFileSync(vy, "utf8");
    assert.equal(parseDeployBlock(second).get("node").get("SERVICE_DOMAIN"), "my.real.com");
    assert.equal(parseExisting(second).templateVersion, "4.7.0");
    assert.equal((second.match(/^deploy:/gm) || []).length, 1);
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});
