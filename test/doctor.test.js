import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { localChecks, renderRows, remoteChecks, workflowsWithoutPermissions } from "../src/commands/doctor.js";

function repo({ versionYml = null, workflows = {} } = {}) {
  const root = mkdtempSync(join(tmpdir(), "doctor-"));
  if (versionYml) writeFileSync(join(root, "version.yml"), versionYml, "utf8");
  const wf = join(root, ".github", "workflows");
  mkdirSync(wf, { recursive: true });
  for (const [name, body] of Object.entries(workflows)) writeFileSync(join(wf, name), body, "utf8");
  return root;
}

const VY = 'version: "1.0.0"\nproject_types: ["spring"]\nmetadata:\n  template:\n    version: "4.4.1"\n';
const row = (rows, name) => rows.find((r) => r.name === name);

// ── 통합 상태 ─────────────────────────────────────────────────────────
test("통합 전이면 그 사실만 알리고 나머지 점검을 건너뛴다", () => {
  const rows = localChecks(repo());
  assert.equal(rows.length, 1);
  assert.equal(rows[0].status, "INFO");
  assert.match(rows[0].value, /version\.yml 없음/);
});

test("통합된 레포는 템플릿·프로젝트 버전을 함께 보여준다", () => {
  const rows = localChecks(repo({ versionYml: VY, workflows: { "A.yaml": "name: A\n" } }));
  const r = row(rows, "통합 상태");
  assert.equal(r.status, "OK");
  assert.match(r.value, /4\.4\.1/);
  assert.match(r.value, /1\.0\.0/);
});

test("워크플로우가 하나도 없으면 경고", () => {
  const rows = localChecks(repo({ versionYml: VY }));
  assert.equal(row(rows, "설치된 워크플로우").status, "WARN");
});

// ── 치환·Secret (설치 후 검증 재사용) ─────────────────────────────────
test("치환되지 않은 값을 위치와 함께 보고", () => {
  const rows = localChecks(repo({
    versionYml: VY, workflows: { "A.yaml": "run: echo __DEPLOY_PORT__\n" },
  }));
  const r = row(rows, "치환되지 않은 값");
  assert.equal(r.status, "WARN");
  assert.ok(r.detail.some((l) => l.includes("__DEPLOY_PORT__")));
});

test("필요한 Secret은 INFO — 도구가 '등록하라'고 판정하지 않는다", () => {
  // 쓰지 않는 워크플로우의 Secret은 등록할 이유가 없다. 사실만 진술한다.
  const rows = localChecks(repo({
    versionYml: VY, workflows: { "A.yaml": "  host: ${{ secrets.SERVER_HOST }}\n" },
  }));
  const r = row(rows, "필요한 Secret");
  assert.equal(r.status, "INFO");
  assert.ok(r.detail.some((l) => l.includes("SERVER_HOST")));
});

// ── 워크플로우 권한 선언 (#555 재발 방지) ─────────────────────────────
const DISPATCHER = (perms) => `name: R
on:
  pull_request_target:
    types: [opened]
permissions:
${perms}
jobs:
  a:
    steps:
      - run: python3 .github/scripts/dispatch_downstream.py dispatch --repo x --branch main
`;

test("다른 워크플로우를 깨우는데 actions: write가 없으면 경고 (#555)", () => {
  // 저장소 설정이 Read and write여도 이 선언이 빠지면 API가 403을 준다 — 다른 층이다.
  const rows = localChecks(repo({
    versionYml: VY,
    workflows: { "R.yaml": DISPATCHER("  contents: write\n  pull-requests: write") },
  }));
  const r = row(rows, "워크플로우 권한 선언");
  assert.equal(r.status, "WARN");
  assert.ok(r.detail.some((l) => l.includes("R.yaml")));
});

test("actions: write가 있으면 정상", () => {
  const rows = localChecks(repo({
    versionYml: VY,
    workflows: { "R.yaml": DISPATCHER("  contents: write\n  actions: write") },
  }));
  assert.equal(row(rows, "워크플로우 권한 선언").status, "OK");
});

test("다른 워크플로우를 깨우지 않는 파일은 권한 선언을 요구하지 않는다", () => {
  const rows = localChecks(repo({
    versionYml: VY, workflows: { "A.yaml": "name: A\npermissions:\n  contents: read\n" },
  }));
  assert.equal(row(rows, "워크플로우 권한 선언").status, "OK");
});

// ── 기준점 ────────────────────────────────────────────────────────────
test("기준점이 없으면 다음 업데이트 동작을 알린다", () => {
  const rows = localChecks(repo({ versionYml: VY, workflows: { "A.yaml": "name: A\n" } }));
  const r = row(rows, "업데이트 기준점");
  assert.equal(r.status, "INFO");
  assert.ok(r.detail.some((l) => l.includes("모두 물어봅니다")));
});

// ── 렌더 ──────────────────────────────────────────────────────────────
test("정상 항목은 한 줄로 압축하고 문제 항목만 펼친다", () => {
  const out = [];
  renderRows([
    { name: "정상", purpose: "p", status: "OK", value: "v", detail: ["펼치면 안 됨"] },
    { name: "문제", purpose: "p", status: "WARN", value: "v", detail: ["펼쳐야 함"] },
  ], (s) => out.push(s));
  const text = out.join("\n");
  assert.ok(!text.includes("펼치면 안 됨"));
  assert.ok(text.includes("펼쳐야 함"));
});

test("renderRows는 살펴볼 항목 수를 반환한다", () => {
  const n = renderRows([
    { name: "a", status: "OK", value: "" },
    { name: "b", status: "WARN", value: "" },
    { name: "c", status: "FAIL", value: "" },
    { name: "d", status: "INFO", value: "" },
  ], () => {});
  assert.equal(n, 2); // WARN + FAIL만 센다 (INFO는 조치가 필요한 것이 아니다)
});

test("항목 이름 옆에 purpose를 병기한다", () => {
  const out = [];
  renderRows([{ name: "이름", purpose: "무엇을 위한 것", status: "OK", value: "값" }], (s) => out.push(s));
  assert.match(out[0], /이름 — 무엇을 위한 것: 값/);
});

// ── 조직 읽기 전용 기본 권한 (#723) ─────────────────────────────────────
// 저장소 기본값이 read 여도 워크플로우가 permissions 를 선언하면 그 범위로 동작한다 (조직에서 릴리스 automerge 실측).
function fakeGithub(routes) {
  const orig = globalThis.fetch;
  globalThis.fetch = async (url) => {
    const path = String(url).replace("https://api.github.com", "");
    const hit = Object.entries(routes).find(([k]) => path.startsWith(k));
    const body = hit ? hit[1] : {};
    return { ok: true, status: 200, json: async () => body, text: async () => JSON.stringify(body) };
  };
  return () => { globalThis.fetch = orig; };
}

test("permissions 미선언 워크플로우만 골라낸다", () => {
  const root = repo({ workflows: {
    "A.yaml": "name: A\npermissions:\n  contents: write\njobs: {}\n",
    "B.yaml": "name: B\njobs:\n  x:\n    permissions:\n      issues: write\n",
    "C.yaml": "name: C\njobs: {}\n",
  } });
  assert.deepEqual(workflowsWithoutPermissions(root), ["C.yaml"]);
});

test("기본 권한이 읽기 전용이어도 모두 선언했으면 경고하지 않는다", async () => {
  const restore = fakeGithub({ "/repos/o/r/actions/permissions/workflow": { default_workflow_permissions: "read" },
                               "/repos/o/r": { allow_merge_commit: true } });
  try {
    const rows = await remoteChecks("o/r", "t", [], []);
    const r = row(rows, "Workflow permissions");
    assert.equal(r.status, "INFO");
    assert.match(r.value, /영향 없음/);
  } finally { restore(); }
});

test("기본 권한이 읽기 전용이고 미선언 워크플로우가 있으면 그 파일을 알리며 경고한다", async () => {
  const restore = fakeGithub({ "/repos/o/r/actions/permissions/workflow": { default_workflow_permissions: "read" },
                               "/repos/o/r": { allow_merge_commit: true } });
  try {
    const rows = await remoteChecks("o/r", "t", [], ["C.yaml"]);
    const r = row(rows, "Workflow permissions");
    assert.equal(r.status, "WARN");
    assert.ok(r.detail.some((d) => d.includes("C.yaml")));
  } finally { restore(); }
});

test("선택 항목인 AI 키는 배포 Secret 미등록 목록에 넣지 않는다", async () => {
  const restore = fakeGithub({ "/repos/o/r/actions/permissions/workflow": { default_workflow_permissions: "write" },
                               "/repos/o/r/actions/secrets": { secrets: [] },
                               "/repos/o/r": { allow_merge_commit: true } });
  try {
    const rows = await remoteChecks("o/r", "t", ["GEMINI_API_KEY", "OPENAI_API_KEY", "SERVER_HOST"], []);
    const r = row(rows, "Secret 등록 여부");
    assert.equal(r.status, "WARN");
    assert.match(r.value, /1개 미등록/);
    assert.ok(r.detail.some((d) => d.includes("SERVER_HOST")));
    assert.ok(!r.detail.some((d) => d.includes("GEMINI_API_KEY")));
  } finally { restore(); }
});
