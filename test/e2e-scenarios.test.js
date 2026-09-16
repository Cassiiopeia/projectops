// 실행 시나리오 E2E (#566) — 단위 테스트가 잡지 못하는 종류를 잡는다.
//
// 이번 작업에서 실제로 새어 나간 버그들은 전부 단위 테스트를 통과했다.
//   · 로그가 완료 화면 전에 닫힘   → 함수는 맞고 호출 "순서"가 틀렸다
//   · 죽은 provider가 기본값       → 값은 저장되는데 그 값이 동작하지 않았다
//   · 요약 워크플로우가 실행 불가   → 트리거 조건 조합이 성립 불가였다
//   · 껐는데 파일이 남음           → 켜는 경로만 있고 끄는 경로가 없었다
// 공통점은 "부품은 맞는데 이어 붙이면 틀린다"이다. 그래서 실제 CLI를 끝까지 돌린다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync, readFileSync, existsSync, readdirSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { run } from "../src/index.js";
import { parseExisting } from "../src/core/version-yml.js";
import { MIGRATION_DIR } from "../src/core/run-trace.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));
const write = (root, rel, content) => {
  mkdirSync(join(root, rel, ".."), { recursive: true });
  writeFileSync(join(root, rel), content);
};
const wf = (root, name) => join(root, ".github/workflows", name);

const SUMMARY_WF = "PROJECT-COMMON-AI-PR-SUMMARY.yaml";
const SECRET_WF = "PROJECT-COMMON-SECRET-FILE-UPLOAD.yaml";

function makeTemplate() {
  const tpl = fresh("e2e-tpl-");
  write(tpl, ".github/scripts/version_manager.sh", "#!/bin/bash\n");
  write(tpl, ".github/scripts/changelog_manager.py", "# py\n");
  write(tpl, ".github/scripts/changelog_providers/commit.py", "# py\n");
  write(tpl, ".github/scripts/changelog_providers/copilot.py", "# py\n");
  write(tpl, ".github/config/wizard-prompts.yml", 'PROJECT_NAME:\n  label: "이름"\n');
  write(tpl, ".github/workflows/project-types/common/PROJECT-COMMON-CI.yaml", "name: ci\non:\n  push:\n");
  write(tpl, `.github/workflows/project-types/common/pr-summary/${SUMMARY_WF}`, "name: s\non:\n  push:\n");
  write(tpl, `.github/workflows/project-types/common/secret-backup/${SECRET_WF}`, "name: b\non:\n  push:\n");
  write(tpl, ".github/workflows/project-types/node/PROJECT-NODE-CI.yaml", "name: n\non:\n  push:\n");
  writeFileSync(join(tpl, "version.yml"), 'version: "4.7.0"\n');
  writeFileSync(join(tpl, "PROJECTOPS-SETUP-GUIDE.md"), "# guide\n");
  return tpl;
}

function makeTarget({ versionYml = null } = {}) {
  const t = fresh("e2e-tgt-");
  writeFileSync(join(t, "package.json"), '{"name":"app","version":"1.0.0"}\n');
  if (versionYml) writeFileSync(join(t, "version.yml"), versionYml);
  return t;
}

// stdout은 건드리지 않는다 — 테스트 러너 결과가 그쪽으로 나간다. CLI 출력은 stderr다.
async function cli(argv, target, tpl) {
  const se = process.stderr.write;
  process.stderr.write = () => true;
  try {
    return await run(argv, {
      cwd: target, source: { type: "local", path: tpl },
      clock: { now: "2026-09-16 00:00:00", today: "2026-09-16" },
    });
  } finally { process.stderr.write = se; }
}

const optionsOf = (target) => parseExisting(readFileSync(join(target, "version.yml"), "utf8")).options;

// ── 시나리오 ① 신규 설치 ────────────────────────────────────────────

test("E2E ①: 신규 설치 — 설정 없이 동작하는 상태로 끝난다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    assert.equal(await cli(["--mode", "full", "--type", "node", "--force"], tgt, tpl), 0);
    const o = optionsOf(tgt);

    assert.equal(o.changelogProvider, "commit", "기본 경로에 외부 의존이 없어야 한다");
    assert.notEqual(o.changelogProvider, "github-ai", "종료된 서비스를 기본값으로 두면 안 된다");
    assert.equal(o.aiPrSummary, true, "AI 요약은 기본 포함");
    assert.ok(existsSync(wf(tgt, SUMMARY_WF)), "요약 워크플로우가 실제로 복사돼야 한다");
    assert.ok(existsSync(join(tgt, ".github/scripts/changelog_providers/copilot.py")), "provider 스크립트도 함께");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// ── 시나리오 ② 재실행(멱등) ─────────────────────────────────────────

test("E2E ②: 같은 설정으로 재실행해도 결과가 달라지지 않는다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    await cli(["--mode", "full", "--type", "node", "--force"], tgt, tpl);
    const first = optionsOf(tgt);
    const filesFirst = readdirSync(join(tgt, ".github/workflows")).sort();

    await cli(["--mode", "full", "--type", "node", "--force"], tgt, tpl);
    const second = optionsOf(tgt);
    const filesSecond = readdirSync(join(tgt, ".github/workflows")).sort();

    assert.deepEqual(second, first, "옵션이 흔들리면 안 된다");
    assert.deepEqual(filesSecond, filesFirst, "파일 목록이 흔들리면 안 된다");
    assert.ok(!filesSecond.some((f) => f.endsWith(".bak")), "무변경 재실행에 .bak이 생기면 안 된다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// ── 시나리오 ③ 기존 저장소 업데이트 ─────────────────────────────────

test("E2E ③: 죽은 설정으로 통합된 저장소가 업데이트만으로 살아난다", async () => {
  const tpl = makeTemplate();
  const tgt = makeTarget({ versionYml: [
    'version: "3.1.4"', "version_code: 77", 'project_types: ["node"]',
    "metadata:", '  last_updated: "2026-05-01 00:00:00"',
    '  default_branch: "main"', '  deploy_branch: "develop"',
    "  template:", '    version: "4.2.24"', '    mode: "full"',
    "    options:", '      deploy: "docker-ssh"', "      publish: []",
    "      secret_backup: true", "      code_review:", "        coderabbit: true",
    "      changelog:", '        provider: "github-ai"', '        base_url: ""', "",
  ].join("\n") });
  try {
    assert.equal(await cli(["--mode", "full", "--force"], tgt, tpl), 0);
    const o = optionsOf(tgt);
    const v = parseExisting(readFileSync(join(tgt, "version.yml"), "utf8"));

    assert.equal(o.changelogProvider, "commit", "죽은 값에서 벗어나야 한다");
    assert.equal(v.version, "3.1.4", "사용자 버전 보존");
    assert.equal(v.versionCode, 77, "빌드번호 보존");
    assert.equal(o.codeReviewCoderabbit, true, "사용자 선택 보존");
    assert.equal(o.secretBackup, true, "Secret 백업 선택 보존");
    assert.ok(existsSync(wf(tgt, SECRET_WF)), "켜둔 워크플로우는 유지");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// ── 시나리오 ④ 축 끄기 ──────────────────────────────────────────────

test("E2E ④: Secret 백업을 끄면 기존 파일이 그대로 남지 않는다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    await cli(["--mode", "full", "--type", "node", "--force", "--secret-backup"], tgt, tpl);
    assert.ok(existsSync(wf(tgt, SECRET_WF)), "먼저 켜져 있어야 한다");

    await cli(["--mode", "full", "--type", "node", "--force", "--no-secret-backup"], tgt, tpl);
    assert.equal(optionsOf(tgt).secretBackup, false, "선택이 반영돼야 한다");
    // 비대화형은 자동 무해화를 하지 않고 안내만 한다(배포 파이프라인 오살 방지).
    // 최소한 "감지는 된다"를 고정한다 — 감지조차 못 하면 안내도 못 한다.
    const { detectOrphanWorkflows } = await import("../src/core/orphan-workflows.js");
    const orphans = detectOrphanWorkflows({
      tempDir: tpl, targetRoot: tgt, selectedTypes: ["node"],
      options: { includeSecretBackup: false, aiPrSummary: true, deployTarget: "docker-ssh" },
    });
    assert.ok(orphans.some((o) => o.filename === SECRET_WF), "끈 워크플로우가 고아로 감지돼야 한다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// ── 시나리오 ⑤ 사용자 수정 보호 ─────────────────────────────────────

test("E2E ⑤: 사용자가 고친 워크플로우를 말없이 날리지 않는다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    await cli(["--mode", "full", "--type", "node", "--force"], tgt, tpl);
    writeFileSync(wf(tgt, "PROJECT-COMMON-CI.yaml"), "name: ci\non:\n  push:\n# 내가 추가한 스텝\n");

    // 템플릿이 갱신된 상황
    write(tpl, ".github/workflows/project-types/common/PROJECT-COMMON-CI.yaml", "name: ci\non:\n  push:\n# 업스트림 변경\n");
    await cli(["--mode", "full", "--type", "node", "--force"], tgt, tpl);

    const files = readdirSync(join(tgt, ".github/workflows"));
    const body = readFileSync(wf(tgt, "PROJECT-COMMON-CI.yaml"), "utf8");
    const preserved = body.includes("내가 추가한 스텝")
      || files.some((f) => f.endsWith(".bak") && readFileSync(join(tgt, ".github/workflows", f), "utf8").includes("내가 추가한 스텝"));
    assert.ok(preserved, "내 수정이 원본이든 .bak이든 어딘가에는 남아야 한다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// ── 시나리오 ⑥ 실행 기록 ────────────────────────────────────────────

test("E2E ⑥: 실행 기록이 완료 화면까지 담긴 채 남는다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    await cli(["--mode", "full", "--type", "node", "--force"], tgt, tpl);
    const dir = join(tgt, MIGRATION_DIR);
    assert.ok(existsSync(dir), "기록 폴더가 있어야 한다");

    const log = readdirSync(dir).find((f) => f.endsWith(".log"));
    assert.ok(log, ".log가 있어야 한다");
    const body = readFileSync(join(dir, log), "utf8");
    assert.match(body, /run\/end/, "종료까지 기록돼야 한다");
    assert.ok(body.includes(log), "화면 안내가 이번 실행 파일을 정확히 가리켜야 한다");
    assert.ok(existsSync(join(dir, ".gitignore")), "기록은 저장소에 추적되지 않아야 한다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// ── 시나리오 ⑦ 잘못된 입력 ──────────────────────────────────────────

test("E2E ⑦: 잘못된 타입을 주면 설치하지 않고 실패한다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    const code = await cli(["--mode", "full", "--type", "notatype", "--force"], tgt, tpl);
    assert.notEqual(code, 0, "알 수 없는 타입은 거부해야 한다");
    assert.ok(!existsSync(join(tgt, "version.yml")), "실패했는데 파일을 써두면 안 된다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// ── 시나리오 ⑧ AI 요약 끄기 (복사 게이트) ───────────────────────────

test("E2E ⑧: AI 요약을 끄면 워크플로우가 복사되지 않는다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    await cli(["--mode", "full", "--type", "node", "--force", "--no-ai-summary"], tgt, tpl);
    assert.equal(optionsOf(tgt).aiPrSummary, false, "선택이 저장돼야 한다");
    assert.ok(!existsSync(wf(tgt, SUMMARY_WF)), "끈 워크플로우가 복사되면 안 된다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("E2E ⑨: 껐다가 다시 켜면 복사된다", async () => {
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    await cli(["--mode", "full", "--type", "node", "--force", "--no-ai-summary"], tgt, tpl);
    assert.ok(!existsSync(wf(tgt, SUMMARY_WF)));

    await cli(["--mode", "full", "--type", "node", "--force", "--ai-summary"], tgt, tpl);
    assert.equal(optionsOf(tgt).aiPrSummary, true);
    assert.ok(existsSync(wf(tgt, SUMMARY_WF)), "다시 켜면 들어와야 한다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// ── 시나리오 ⑩ 대화형 경로 ──────────────────────────────────────────
// 비대화형(--force)과 대화형은 옵션 결정 코드가 다르다. 한쪽만 고치고 다른 쪽을
// 놓치는 사고가 실제로 있었으므로(#566 역검증에서 발견) 양쪽을 모두 태운다.

test("E2E ⑩: 대화형도 죽은 provider를 기본값으로 삼지 않는다", async () => {
  const { askAllOptionalWorkflows } = await import("../src/core/options-ask.js");
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    const calls = { select: [], confirm: [], text: [] };
    const io = {
      log: () => {},
      select: async (a) => { calls.select.push(a.message); return "summary"; },
      confirm: async (a) => { calls.confirm.push(a.message); return false; },
      multiselect: async () => [],
      text: async (a) => { calls.text.push(a.message); return "develop"; },
    };
    const r = await askAllOptionalWorkflows({ tempDir: tpl, types: ["node"], targetRoot: tgt, tty: true, io });

    assert.notEqual(r.changelogProvider, "github-ai", "대화형에서도 종료된 서비스를 고르면 안 된다");
    assert.equal(r.changelogProvider, "commit");
    assert.ok(!calls.select.some((m) => /changelog|생성기|릴리스 노트/.test(m)), "provider를 묻지 않아야 한다");
    assert.equal(r.aiPrSummary, true, "'AI 변경 요약' 선택이 반영돼야 한다");
    assert.equal(r.codeReviewCoderabbit, false);
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("E2E ⑪: 대화형에서 '사용 안 함'을 고르면 둘 다 꺼진다", async () => {
  const { askAllOptionalWorkflows } = await import("../src/core/options-ask.js");
  const tpl = makeTemplate(); const tgt = makeTarget();
  try {
    const io = {
      log: () => {},
      select: async () => "none",
      confirm: async () => false,
      multiselect: async () => [],
      text: async () => "develop",
    };
    const r = await askAllOptionalWorkflows({ tempDir: tpl, types: ["node"], targetRoot: tgt, tty: true, io });
    assert.equal(r.codeReviewCoderabbit, false);
    assert.equal(r.aiPrSummary, false, "'사용 안 함'이 실제로 꺼져야 한다");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});
