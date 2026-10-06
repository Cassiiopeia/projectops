// 레거시 마이그레이션 (#470) — registry 정합성 + detect/apply/티어 정책 검증.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, existsSync, rmSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { MIGRATIONS } from "../src/core/migrations/registry.js";
import { detectMigrations, applySafeMigrations, runMigrations } from "../src/core/migrations/index.js";

const ROOT = process.cwd();

function fresh() { return mkdtempSync(join(tmpdir(), "mig-")); }
function wfDir(root) { const d = join(root, ".github", "workflows"); mkdirSync(d, { recursive: true }); return d; }

// ── registry 정합성 ───────────────────────────────────────────────────

test("registry: id 중복 없음", () => {
  const ids = MIGRATIONS.map((m) => m.id);
  assert.equal(new Set(ids).size, ids.length);
});

test("registry: 현행 배포 세트와 파일명이 절대 겹치지 않는다 (살아있는 워크플로우 오살 방지)", () => {
  // 현행 배포 세트 = 루트 + project-types 전체 (TEMPLATE-* 레포 전용 포함 — 보수적으로 전부)
  const shipped = new Set();
  const collect = (dir) => {
    for (const e of readdirSync(join(ROOT, dir), { withFileTypes: true })) {
      if (e.isDirectory()) collect(`${dir}/${e.name}`);
      else if (/\.ya?ml$/.test(e.name)) shipped.add(e.name);
    }
  };
  collect(".github/workflows");
  const collisions = MIGRATIONS.filter((m) => m.category === "workflow" && shipped.has(m.file));
  assert.deepEqual(collisions.map((m) => m.file), [],
    `레지스트리에 현행 배포 파일이 들어있음(오살 위험): ${collisions.map((m) => m.file).join(", ")}`);
});

test("registry: 모든 항목이 필수 필드와 유효한 tier/category를 가진다", () => {
  for (const m of MIGRATIONS) {
    assert.ok(m.id && m.file && m.reason, `필드 누락: ${m.id || m.file}`);
    assert.ok(["safe", "confirm", "ask"].includes(m.tier), `tier 오류: ${m.id}`);
    assert.ok(["workflow", "root-file", "legacy-dir", "util-file"].includes(m.category), `category 오류: ${m.id}`);
    assert.ok(!m.file.includes("*"), `글롭 금지 위반: ${m.id}`); // 정확명 매칭 원칙
  }
});

// ── util-file (#500 — Flutter 마법사 스크립트 Python 단일화) ─────────────

test("registry: util-file 항목이 현행 템플릿 파일과 겹치지 않는다 (살아있는 util 파일 오살 방지)", () => {
  const collisions = MIGRATIONS.filter(
    (m) => m.category === "util-file" && existsSync(join(ROOT, m.file)),
  );
  assert.deepEqual(collisions.map((m) => m.file), [],
    `레지스트리에 현행 템플릿 util 파일이 들어있음(오살 위험): ${collisions.map((m) => m.file).join(", ")}`);
});

test("util-file: 구 마법사 sh/ps1 감지 후 삭제, 멱등", () => {
  const root = fresh();
  try {
    const wiz = join(root, ".github", "util", "flutter", "playstore-wizard");
    mkdirSync(wiz, { recursive: true });
    writeFileSync(join(wiz, "playstore-wizard-setup.sh"), "old\n");
    writeFileSync(join(wiz, "playstore-wizard-setup.ps1"), "old\n");
    writeFileSync(join(wiz, "playstore-wizard.py"), "new\n"); // 신형은 건드리면 안 됨

    const { safe } = detectMigrations(root);
    assert.deepEqual(safe.map((e) => e.id).sort(),
      ["util-playstore-setup-ps1", "util-playstore-setup-sh"]);

    const results = applySafeMigrations(root, safe);
    assert.ok(results.every((r) => r.action === "deleted"), JSON.stringify(results));
    assert.ok(!existsSync(join(wiz, "playstore-wizard-setup.sh")));
    assert.ok(!existsSync(join(wiz, "playstore-wizard-setup.ps1")));
    assert.ok(existsSync(join(wiz, "playstore-wizard.py")), "신형 py를 오살함!");
    assert.equal(detectMigrations(root).safe.length, 0); // 멱등
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("util-file: 비대화형(--force)에서도 safe 티어로 자동 정리된다", async () => {
  const root = fresh();
  try {
    const wiz = join(root, ".github", "util", "flutter", "firebase-wizard");
    mkdirSync(join(wiz, "test"), { recursive: true });
    writeFileSync(join(wiz, "firebase-wizard-setup.sh"), "old\n");
    writeFileSync(join(wiz, "test", "setup-script-test.ps1"), "old\n");
    const { applied } = await runMigrations({ targetRoot: root, log: () => {} });
    assert.equal(applied.length, 2);
    assert.ok(!existsSync(join(wiz, "firebase-wizard-setup.sh")));
    assert.ok(!existsSync(join(wiz, "test", "setup-script-test.ps1")));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// ── detect ────────────────────────────────────────────────────────────

test("detect: 구 워크플로우는 safe, 배포 계열은 confirm으로 분류", () => {
  const root = fresh();
  try {
    const d = wfDir(root);
    writeFileSync(join(d, "PROJECT-COMMON-AUTO-CHANGELOG-CONTROL.yaml"), "name: old\n");
    writeFileSync(join(d, "PROJECT-SPRING-SYNOLOGY-SIMPLE-CICD.yaml"), "name: syno\n");
    writeFileSync(join(d, "ROMROM-ANDROID-CICD.yaml"), "name: custom\n"); // 사용자 커스텀
    const { safe, confirm } = detectMigrations(root);
    assert.deepEqual(safe.map((e) => e.file), ["PROJECT-COMMON-AUTO-CHANGELOG-CONTROL.yaml"]);
    assert.deepEqual(confirm.map((e) => e.file), ["PROJECT-SPRING-SYNOLOGY-SIMPLE-CICD.yaml"]);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("detect: contentMarker — 범용 파일명은 내용 마커 있어야 템플릿 소유 판정", () => {
  const root = fresh();
  try {
    writeFileSync(join(root, "SETUP-GUIDE.md"), "# 우리 팀 자체 셋업 가이드\n");
    assert.equal(detectMigrations(root).safe.length, 0, "사용자 문서를 오탐");
    writeFileSync(join(root, "SETUP-GUIDE.md"), "# SUH-DEVOPS-TEMPLATE 셋업\n");
    assert.deepEqual(detectMigrations(root).safe.map((e) => e.id), ["root-setup-guide-v1"]);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// ── apply ─────────────────────────────────────────────────────────────

test("apply: 워크플로우는 .bak 무해화(기존 .bak 덮어씀), root-file은 삭제, 멱등", () => {
  const root = fresh();
  try {
    const d = wfDir(root);
    const wf = join(d, "PROJECT-VERSION-CONTROL.yaml");
    writeFileSync(wf, "name: old\n");
    writeFileSync(`${wf}.bak`, "stale bak\n"); // 기존 .bak 충돌 케이스
    writeFileSync(join(root, "SUH-DEVOPS-TEMPLATE-SETUP-GUIDE.md"), "# guide\n");

    const { safe } = detectMigrations(root);
    const results = applySafeMigrations(root, safe);
    assert.ok(results.every((r) => r.action !== "error"), JSON.stringify(results));
    assert.ok(!existsSync(wf), "구 워크플로우가 남아있음");
    assert.ok(existsSync(`${wf}.bak`), ".bak 미생성");
    assert.ok(!existsSync(join(root, "SUH-DEVOPS-TEMPLATE-SETUP-GUIDE.md")), "구 가이드 미삭제");

    // 멱등 — 재감지 0건
    assert.equal(detectMigrations(root).safe.length, 0);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// ── runMigrations (티어 정책) ─────────────────────────────────────────

test("runMigrations: 비대화형(askYesNo 없음)은 safe 자동 적용, confirm은 불변", async () => {
  const root = fresh();
  try {
    const d = wfDir(root);
    writeFileSync(join(d, "PROJECT-README-VERSION-UPDATE.yaml"), "old\n");
    writeFileSync(join(d, "PROJECT-SPRING-CICD.yaml"), "deploy\n"); // confirm 티어
    const logs = [];
    const { applied, confirmPending } = await runMigrations({ targetRoot: root, log: (m) => logs.push(m) });
    assert.equal(applied.length, 1);
    assert.ok(!existsSync(join(d, "PROJECT-README-VERSION-UPDATE.yaml")));
    assert.ok(existsSync(join(d, "PROJECT-SPRING-CICD.yaml")), "confirm 티어를 건드림!");
    assert.equal(confirmPending.length, 1);
    assert.ok(logs.some((l) => l.includes("left untouched")));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("runMigrations: 대화형에서 아니오 선택 시 아무것도 적용하지 않음", async () => {
  const root = fresh();
  try {
    const d = wfDir(root);
    writeFileSync(join(d, "PROJECT-VERSION-CONTROL.yaml"), "old\n");
    const { applied } = await runMigrations({ targetRoot: root, askYesNo: async () => false, log: () => {} });
    assert.equal(applied.length, 0);
    assert.ok(existsSync(join(d, "PROJECT-VERSION-CONTROL.yaml")));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("runMigrations: 감지 0건이면 조용히 통과 (신규 통합 no-op)", async () => {
  const root = fresh();
  try {
    const logs = [];
    const { applied, confirmPending } = await runMigrations({ targetRoot: root, log: (m) => logs.push(m) });
    assert.equal(applied.length + confirmPending.length + logs.length, 0);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// ── legacy-dir / ask 티어 (#476) — 구명칭 산출물 폴더 확인 후 이동 ──────────────

function docsFixture() {
  const root = fresh();
  mkdirSync(join(root, "docs", "suh-template", "issue"), { recursive: true });
  writeFileSync(join(root, "docs", "suh-template", "issue", "a.md"), "이슈 문서");
  writeFileSync(join(root, "docs", "suh-template", "note.md"), "루트 문서");
  return root;
}

test("legacy-dir: 대상 폴더 없으면 통째 이동 (구조·내용 보존)", async () => {
  const root = docsFixture();
  try {
    const logs = [];
    const r = await runMigrations({ targetRoot: root, askYesNo: async () => true, log: (s) => logs.push(s) });
    assert.equal(existsSync(join(root, "docs", "suh-template")), false, "구 폴더 제거");
    assert.equal(existsSync(join(root, "docs", "projectops", "issue", "a.md")), true, "하위 문서 이동");
    assert.equal(existsSync(join(root, "docs", "projectops", "note.md")), true, "루트 문서 이동");
    assert.ok(r.applied.some((a) => a.action === "moved" && a.moved === 2), "이동 2건 보고");
    assert.equal(r.askPending.length, 0);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("legacy-dir: 대상 폴더 존재 시 재귀 병합 — 충돌 파일은 원위치 유지", async () => {
  const root = docsFixture();
  try {
    mkdirSync(join(root, "docs", "projectops", "issue"), { recursive: true });
    writeFileSync(join(root, "docs", "projectops", "issue", "a.md"), "신규 경로에 이미 있는 동명 문서");
    const r = await runMigrations({ targetRoot: root, askYesNo: async () => true, log: () => {} });
    // a.md 충돌 → 양쪽 모두 보존, note.md는 이동
    assert.equal(readFileSync(join(root, "docs", "projectops", "issue", "a.md"), "utf8"), "신규 경로에 이미 있는 동명 문서");
    assert.equal(readFileSync(join(root, "docs", "suh-template", "issue", "a.md"), "utf8"), "이슈 문서");
    assert.equal(existsSync(join(root, "docs", "projectops", "note.md")), true);
    assert.ok(r.applied.some((a) => a.action === "moved" && a.moved === 1 && a.skipped === 1));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("legacy-dir: 비대화형(--force)은 자동 이동하지 않고 askPending으로 보고 (#476 정책)", async () => {
  const root = docsFixture();
  try {
    const logs = [];
    const r = await runMigrations({ targetRoot: root, log: (s) => logs.push(s) }); // askYesNo=null
    assert.equal(existsSync(join(root, "docs", "suh-template", "issue", "a.md")), true, "이동 안 함");
    assert.equal(r.askPending.length, 1);
    assert.ok(logs.some((l) => l.includes("Not moved automatically")));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("legacy-dir: 대화형에서 거절하면 이동하지 않고 다음에 다시 안내", async () => {
  const root = docsFixture();
  try {
    const r = await runMigrations({ targetRoot: root, askYesNo: async () => false, log: () => {} });
    assert.equal(existsSync(join(root, "docs", "suh-template", "issue", "a.md")), true);
    assert.equal(r.askPending.length, 1);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("legacy-dir: 멱등 — 이동 후 재실행 시 재감지 없음", async () => {
  const root = docsFixture();
  try {
    await runMigrations({ targetRoot: root, askYesNo: async () => true, log: () => {} });
    const d = detectMigrations(root);
    assert.equal(d.ask.length, 0);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// ── 설정 이관 (settingsExtractor, 이슈 헬퍼 내재화 #478) ─────────────────────

const OLD_MODULE = "PROJECT-COMMON-SUH-ISSUE-HELPER-MODULE.yml";

function writeOldModule(root, withBlock) {
  writeFileSync(join(wfDir(root), OLD_MODULE), [
    "name: PROJECT-COMMON-SUH-ISSUE-HELPER-MODULE",
    "jobs:",
    "  generate-comment:",
    "    steps:",
    "      - uses: Cassiiopeia/github-issue-helper@deploy",
    "        with:",
    ...withBlock.map((l) => `          ${l}`),
    "",
  ].join("\n"));
}

test("carryover: 커스텀 with 값이 version.yml issue_helper로 이관된다", () => {
  const root = fresh();
  try {
    writeOldModule(root, ['branch_prefix: "feat/"', "max_branch_length: 100",
      'commit_template: "${issueTitle} : feat : {변경 사항에 대한 설명} ${issueUrl}"']);
    writeFileSync(join(root, "version.yml"),
      'version: "1.0.0"\nmetadata:\n  last_updated: "x"\n');
    const { safe } = detectMigrations(root);
    const entry = safe.find((e) => e.file === OLD_MODULE);
    const [r] = applySafeMigrations(root, [entry]);
    assert.deepEqual(r.carried, ["branch_prefix"]); // 기본값과 다른 것만 이관
    const vy = readFileSync(join(root, "version.yml"), "utf8");
    assert.match(vy, /issue_helper:/);
    assert.match(vy, /branch_prefix: "feat\/"/);
    assert.ok(existsSync(join(wfDir(root), `${OLD_MODULE}.bak`))); // 무해화도 수행됨
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("carryover: 전부 기본값이면 version.yml을 건드리지 않는다", () => {
  const root = fresh();
  try {
    writeOldModule(root, ['branch_prefix: ""', "max_branch_length: 100"]);
    const before = 'version: "1.0.0"\nmetadata:\n  last_updated: "x"\n';
    writeFileSync(join(root, "version.yml"), before);
    const { safe } = detectMigrations(root);
    applySafeMigrations(root, [safe.find((e) => e.file === OLD_MODULE)]);
    assert.equal(readFileSync(join(root, "version.yml"), "utf8"), before);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("carryover: issue_helper 섹션이 이미 있으면 덮어쓰지 않는다 (신형 설정 우선·멱등)", () => {
  const root = fresh();
  try {
    writeOldModule(root, ['branch_prefix: "old/"']);
    const before = [
      'version: "1.0.0"', "metadata:", "  template:", "    options:",
      "      issue_helper:", '        branch_prefix: "new/"', "",
    ].join("\n");
    writeFileSync(join(root, "version.yml"), before);
    const { safe } = detectMigrations(root);
    applySafeMigrations(root, [safe.find((e) => e.file === OLD_MODULE)]);
    assert.equal(readFileSync(join(root, "version.yml"), "utf8"), before);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("carryover: version.yml이 없으면 조용히 건너뛰고 무해화는 진행한다", () => {
  const root = fresh();
  try {
    writeOldModule(root, ['branch_prefix: "feat/"']);
    const { safe } = detectMigrations(root);
    const [r] = applySafeMigrations(root, [safe.find((e) => e.file === OLD_MODULE)]);
    assert.equal(r.action, "bak");
    assert.ok(!existsSync(join(root, "version.yml")));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("registry: 이슈 헬퍼 구 파일 2종이 safe로 등록되어 있다", () => {
  const api = MIGRATIONS.find((m) => m.file === "PROJECT-COMMON-SUH-ISSUE-HELPER-API.yaml");
  const mod = MIGRATIONS.find((m) => m.file === OLD_MODULE);
  assert.equal(api?.tier, "safe");
  assert.equal(mod?.tier, "safe");
  assert.equal(mod?.settingsExtractor, "suh-issue-helper-module");
  assert.equal(api?.replacedBy, "PROJECT-COMMON-SUH-ISSUE-HELPER.yaml");
  assert.equal(mod?.replacedBy, "PROJECT-COMMON-SUH-ISSUE-HELPER.yaml");
});

// #661 — 템플릿에서 사라진 RELEASE-PUBLISH 가 레거시로 잡히지 않아 없어진 ai-summary 를 호출하던 문제.
test("registry: PROJECT-COMMON-RELEASE-PUBLISH 는 confirm 단계 레거시로 등록돼 있다 (#661)", async () => {
  const { MIGRATIONS } = await import("../src/core/migrations/registry.js");
  const m = MIGRATIONS.find((e) => e.file === "PROJECT-COMMON-RELEASE-PUBLISH.yaml");
  assert.ok(m, "등록되지 않았다");
  assert.equal(m.tier, "confirm", "유일한 릴리스 경로일 수 있어 자동 무해화하지 않는다");
  assert.equal(m.contentMarker, "ai-summary", "같은 이름의 사용자 파일을 오탐하지 않게 내용으로 확인한다");
});
