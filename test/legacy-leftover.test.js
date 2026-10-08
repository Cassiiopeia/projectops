// 은퇴한 구세대 워크플로우가 감지만 되고 로그에만 남던 문제 (#809).
// 업데이트 요약·doctor 어디에도 안 나와 신·구 세대가 함께 돌며 실패가 두 배가 됐다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { runMigrations } from "../src/core/migrations/index.js";
import { localChecks } from "../src/commands/doctor.js";
import { printSummary } from "../src/ui/summary.js";
import { setLang } from "../src/i18n/index.js";
import { parseArgs } from "../src/cli/args.js";

const OLD = "PROJECT-SPRING-SYNOLOGY-PR-PREVIEW.yaml";

function repoWithLegacy() {
  const root = mkdtempSync(join(tmpdir(), "legacy-"));
  const wf = join(root, ".github", "workflows");
  mkdirSync(wf, { recursive: true });
  writeFileSync(join(wf, OLD), "name: old\n");
  writeFileSync(join(root, "version.yml"), 'version: "1.0.0"\nproject_types: ["spring"]\nmetadata:\n  template:\n    version: "4.36.4"\n');
  return { root, wf };
}

test("--force 에서도 기본은 건드리지 않고 --remove-legacy 안내를 남긴다", async () => {
  const { root, wf } = repoWithLegacy();
  try {
    const logs = [];
    const r = await runMigrations({ targetRoot: root, log: (m) => logs.push(m) });
    assert.ok(existsSync(join(wf, OLD)));
    assert.equal(r.confirmPending.length, 1);
    assert.ok(logs.some((l) => l.includes("--remove-legacy")));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("removeLegacy 면 .bak 으로 치우고 남은 목록에서 뺀다", async () => {
  const { root, wf } = repoWithLegacy();
  try {
    const r = await runMigrations({ targetRoot: root, removeLegacy: true, log: () => {} });
    assert.ok(!existsSync(join(wf, OLD)));
    assert.ok(existsSync(join(wf, `${OLD}.bak`)));
    assert.equal(r.confirmPending.length, 0);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("대화형은 묻고, 기본값은 '아니오'(현역 배포일 수 있다)", async () => {
  const { root, wf } = repoWithLegacy();
  try {
    let asked = null;
    await runMigrations({ targetRoot: root, log: () => {},
      askYesNo: async (msg, def) => { if (msg.includes(".bak")) asked = def; return def; } });
    assert.equal(asked, false);
    assert.ok(existsSync(join(wf, OLD)));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("doctor 가 남은 구세대 파일과 삭제 명령을 보여준다", () => {
  const { root } = repoWithLegacy();
  try {
    setLang("en", "flag");
    const row = localChecks(root).find((r) => r.name === "Retired workflows");
    assert.equal(row.status, "WARN");
    assert.ok(row.detail.some((l) => l.includes(`git rm .github/workflows/${OLD}`)));
  } finally { setLang("en", "default"); rmSync(root, { recursive: true, force: true }); }
});

test("완료 요약에 남은 구세대 파일과 삭제 명령이 나온다", () => {
  setLang("en", "flag");
  let out = "";
  try {
    printSummary({ mode: "workflows", types: ["spring"], version: "1.0.0",
      legacyLeftover: [{ file: OLD, replacedBy: "PROJECT-SPRING-PR-PREVIEW.yaml" }] },
      mkdtempSync(join(tmpdir(), "sum-")), (s) => { out += s; });
  } finally { setLang("en", "default"); }
  assert.match(out, /retired workflow/);
  assert.ok(out.includes(`git rm .github/workflows/${OLD}`));
});

test("--remove-legacy 플래그를 파싱한다", () => {
  assert.equal(parseArgs(["--remove-legacy"]).removeLegacy, true);
  assert.equal(parseArgs([]).removeLegacy, false);
});
