// 기존 저장소 업데이트 — 죽은 설정에서 자동으로 벗어나는지 (#566)
//
// 실사고: 신규 설치 기본 provider가 서비스 종료된 github-ai였다. 이미 통합한 저장소도
// 그 값을 저장한 채였고, 업데이트를 돌려도 벗어날 길이 없었다.
// 사용자가 설정을 손대지 않아도 살아있는 값으로 옮겨가야 한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";
import { parseExisting } from "../src/core/version-yml.js";
import { migrateProvider } from "../src/core/options-ask.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));
const write = (root, rel, content) => {
  mkdirSync(join(root, rel, ".."), { recursive: true });
  writeFileSync(join(root, rel), content);
};

function makeTemplate() {
  const tpl = fresh("lu-tpl-");
  write(tpl, ".github/scripts/version_manager.sh", "#!/bin/bash\n");
  write(tpl, ".github/config/wizard-prompts.yml", 'PROJECT_NAME:\n  label: "이름"\n');
  write(tpl, ".github/workflows/project-types/common/PROJECT-COMMON-CI.yaml", "name: ci\non:\n  push:\n");
  write(tpl, ".github/workflows/project-types/common/pr-summary/PROJECT-COMMON-AI-PR-SUMMARY.yaml", "name: s\non:\n  push:\n");
  writeFileSync(join(tpl, "version.yml"), 'version: "4.7.0"\n');
  writeFileSync(join(tpl, "PROJECTOPS-SETUP-GUIDE.md"), "# guide\n");
  return tpl;
}

// 구버전으로 통합된 저장소 — 죽은 provider가 저장돼 있다
const LEGACY_VY = [
  'version: "2.5.0"',
  "version_code: 42",
  'project_types: ["node"]',
  "metadata:",
  '  last_updated: "2026-05-01 00:00:00"',
  '  default_branch: "main"',
  '  deploy_branch: "develop"',
  "  template:",
  '    version: "4.2.24"',
  '    mode: "full"',
  "    options:",
  '      deploy: "docker-ssh"',
  "      publish: []",
  "      secret_backup: false",
  "      code_review:",
  "        coderabbit: true",
  "      changelog:",
  '        provider: "github-ai"',
  '        base_url: ""',
  "",
].join("\n");

async function upgrade(target, tpl) {
  // ⚠️ stdout은 건드리지 않는다 — 테스트 러너의 결과 출력이 그쪽으로 나가므로
  // 막으면 테스트가 통째로 집계에서 사라진다. CLI 출력은 stderr다.
  const se = process.stderr.write;
  process.stderr.write = () => true;
  try {
    return await run(["--mode", "full", "--force"], {
      cwd: target, source: { type: "local", path: tpl },
      clock: { now: "2026-09-16 00:00:00", today: "2026-09-16" },
    });
  } finally { process.stderr.write = se; }
}

test("기존 저장소 업데이트: 종료된 provider가 살아있는 값으로 자동 이전된다", async () => {
  const tpl = makeTemplate(); const target = fresh("lu-tgt-");
  try {
    writeFileSync(join(target, "version.yml"), LEGACY_VY);
    writeFileSync(join(target, "package.json"), '{"name":"legacy","version":"2.5.0"}\n');

    assert.equal(await upgrade(target, tpl), 0);
    const opts = parseExisting(readFileSync(join(target, "version.yml"), "utf8")).options;

    assert.equal(opts.changelogProvider, "commit", "죽은 github-ai에서 벗어나야 한다");
    assert.notEqual(opts.changelogProvider, "github-ai");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("기존 저장소 업데이트: 사용자가 정한 설정은 건드리지 않는다", async () => {
  const tpl = makeTemplate(); const target = fresh("lu-tgt2-");
  try {
    writeFileSync(join(target, "version.yml"), LEGACY_VY);
    writeFileSync(join(target, "package.json"), '{"name":"legacy","version":"2.5.0"}\n');

    await upgrade(target, tpl);
    const yml = readFileSync(join(target, "version.yml"), "utf8");
    const parsed = parseExisting(yml);

    assert.equal(parsed.version, "2.5.0", "사용자 버전 보존");
    assert.equal(parsed.versionCode, 42, "빌드번호 보존");
    assert.equal(parsed.options.codeReviewCoderabbit, true, "CodeRabbit 선택 보존");
    assert.equal(parsed.options.deploy, "docker-ssh", "배포 방식 보존");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("기존 저장소 업데이트: 새로 생긴 축은 기본값으로 바로 동작한다", async () => {
  const tpl = makeTemplate(); const target = fresh("lu-tgt3-");
  try {
    writeFileSync(join(target, "version.yml"), LEGACY_VY);
    writeFileSync(join(target, "package.json"), '{"name":"legacy","version":"2.5.0"}\n');

    await upgrade(target, tpl);
    const opts = parseExisting(readFileSync(join(target, "version.yml"), "utf8")).options;

    assert.equal(opts.aiPrSummary, true, "키가 없던 저장소는 기본 true — 설정 없이 바로 동작");
    assert.ok(existsSync(join(target, ".github/workflows/PROJECT-COMMON-AI-PR-SUMMARY.yaml")),
      "요약 워크플로우가 실제로 복사돼야 한다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(target, { recursive: true, force: true }); }
});

test("migrateProvider: 이전 규칙 자체 검증", () => {
  assert.equal(migrateProvider("github-ai"), "commit");
  assert.equal(migrateProvider("gemini"), "gemini");
  assert.equal(migrateProvider(null), null);
});
