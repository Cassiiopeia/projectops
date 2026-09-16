// 완료 화면이 .log에 담기는지 (#561) — 종료(finalize) 순서 계약을 고정한다.
//
// 실사고: finally에서 기록을 닫는 바람에 그 뒤에 출력되는 완료 화면이 통째로 빠졌다.
// .log가 "step/done install-full"에서 끊겨, 사용자는 로그에 아무 안내도 없다고 느꼈다.
// 코드 순서만 바뀌어도 재발하므로 실 실행 경로로 고정한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, readdirSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";
import { MIGRATION_DIR } from "../src/core/run-trace.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));
const write = (root, rel, content) => {
  mkdirSync(join(root, rel, ".."), { recursive: true });
  writeFileSync(join(root, rel), content);
};

function makeTemplate() {
  const tpl = fresh("logtpl-");
  write(tpl, ".github/scripts/version_manager.sh", "#!/bin/bash\n");
  write(tpl, ".github/config/wizard-prompts.yml", 'PROJECT_NAME:\n  label: "이름"\n');
  write(tpl, ".github/workflows/project-types/common/PROJECT-COMMON-CI.yaml", "name: ci\n");
  writeFileSync(join(tpl, "version.yml"), 'version: "4.0.3"\n');
  writeFileSync(join(tpl, "PROJECTOPS-SETUP-GUIDE.md"), "# guide\n");
  return tpl;
}

// 실 CLI는 완료 화면을 stderr로 뿜는다. 미러가 감싸기 전에 먼저 스텁해 테스트 출력을 조용히 둔다.
async function runQuiet(argv, opts) {
  const so = process.stdout.write, se = process.stderr.write;
  process.stdout.write = () => true;
  process.stderr.write = () => true;
  try { return await run(argv, opts); }
  finally { process.stdout.write = so; process.stderr.write = se; }
}

const logsOf = (root) => {
  const dir = join(root, MIGRATION_DIR);
  return existsSync(dir) ? readdirSync(dir) : [];
};

test("run(--mode full): .log에 완료 화면과 run/end가 모두 담긴다", async () => {
  const tpl = makeTemplate();
  const target = fresh("logtgt-");
  try {
    writeFileSync(join(target, "package.json"), '{"name":"t","version":"1.0.0"}\n');
    const code = await runQuiet(["--mode", "full", "--type", "node", "--force"], {
      cwd: target, source: { type: "local", path: tpl },
      clock: { now: "2026-07-08 00:00:00", today: "2026-07-08" },
    });
    assert.equal(code, 0);

    const logName = logsOf(target).find((f) => f.endsWith(".log"));
    assert.ok(logName, ".log가 생성돼야 함");
    const log = readFileSync(join(target, MIGRATION_DIR, logName), "utf8");

    // 종료 이벤트 — 여기가 없으면 기록이 조기에 닫힌 것이다.
    assert.match(log, /run\/end/, "run/end가 기록돼야 함");
    // 완료 화면 본문 — finalize가 화면 출력보다 앞서면 통째로 빠진다.
    assert.match(log, /이번 실행 기록/, "완료 화면의 기록 안내가 담겨야 함");
    assert.match(log, /PROJECTOPS-SETUP-GUIDE\.md/, "완료 화면의 설정 안내가 담겨야 함");
    // 화면에 찍힌 로그 경로가 실제 파일명과 일치해야 한다 (#561 — 폴더만 알려주면 못 찾는다).
    assert.ok(log.includes(logName), "화면 안내가 이번 실행의 로그 파일명을 정확히 가리켜야 함");
    // 기록 안내가 마지막 자리 — Secret 목록이 길어도 tail에 남는다.
    const tailIdx = log.lastIndexOf("이번 실행 기록");
    assert.ok(tailIdx > log.lastIndexOf("PROJECTOPS-SETUP-GUIDE.md"), "기록 안내가 완료 화면 맨 끝이어야 함");
  } finally {
    rmSync(tpl, { recursive: true, force: true });
    rmSync(target, { recursive: true, force: true });
  }
});

test("run(--mode version): 기록 대상 모드가 아니면 로그 폴더를 만들지 않는다", async () => {
  const tpl = makeTemplate();
  const target = fresh("logtgt2-");
  try {
    const code = await runQuiet(["--mode", "version", "--force"], {
      cwd: target, source: { type: "local", path: tpl },
      clock: { now: "2026-07-08 00:00:00", today: "2026-07-08" },
    });
    assert.equal(code, 0);
    assert.deepEqual(logsOf(target), [], "version 모드는 기록 파일을 남기지 않아야 함");
  } finally {
    rmSync(tpl, { recursive: true, force: true });
    rmSync(target, { recursive: true, force: true });
  }
});
