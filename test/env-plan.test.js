// env-plan(@wizard env 계획 질문) 테스트 — collectAsks 수집 + force/대화형(io 스텁) 경로.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { writeText } from "../src/core/fsutil.js";
import { collectAsks, scopeString, promptEnvPlan, printFieldCard } from "../src/ui/env-plan.js";

function fresh(p) { return mkdtempSync(join(tmpdir(), p)); }

// 소형 템플릿 트리 — ask 마커 4개 키 (spring 직하위 1 + server-deploy 3)
function makeTemplate(tempDir) {
  const base = join(tempDir, ".github/workflows/project-types");
  writeText(join(base, "spring/PROJECT-SPRING-CI.yaml"), [
    "env:",
    '  SERVICE_DOMAIN: "api.example.com"  # @wizard ask:api.example.com',
    "",
  ].join("\n"));
  writeText(join(base, "spring/server-deploy/PROJECT-SPRING-SIMPLE-CICD.yaml"), [
    "env:",
    '  PROJECT_NAME: "__PROJECT_NAME__"  # @wizard ask:@repo',
    '  JAVA_VERSION: "21"  # @wizard ask:21',
    '  DEPLOY_PORT: "8080"  # @wizard ask:8080',
    "",
  ].join("\n"));
  // ask 마커 없는 워크플로우 — 수집 대상 아님
  writeText(join(base, "spring/PROJECT-SPRING-PLAIN.yaml"), "name: plain\n");
}

test("collectAsks: 타입 직하위 + server-deploy의 ask 키 전부 수집 (@접두는 resolver 해석)", () => {
  const tmp = fresh("ep-");
  try {
    makeTemplate(tmp);
    const asks = collectAsks(tmp, ["spring"], { resolvers: { repo: () => "myrepo" } });
    assert.equal(asks.keys.length, 4, "ask 키 4개 수집");
    assert.deepEqual(asks.keys, ["SERVICE_DOMAIN", "PROJECT_NAME", "JAVA_VERSION", "DEPLOY_PORT"]);
    assert.equal(asks.defaults.get("PROJECT_NAME"), "myrepo", "@repo → resolver 해석");
    assert.equal(asks.defaults.get("JAVA_VERSION"), "21");
    assert.equal(asks.typeDefaults.get("spring|DEPLOY_PORT"), "8080");
    // 사용처: prompts 없이 확장자 제거 폴백명
    assert.deepEqual(asks.usages.get("JAVA_VERSION"), [{ type: "spring", workflowName: "PROJECT-SPRING-SIMPLE-CICD" }]);
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("collectAsks: deploy!=docker-ssh면 server-deploy 스캔 제외 (복사 엔진과 범위 일치, #439)", () => {
  const tmp = fresh("ep-nx-");
  try {
    makeTemplate(tmp);
    const asks = collectAsks(tmp, ["spring"], { deployTarget: "none" });
    assert.deepEqual(asks.keys, ["SERVICE_DOMAIN"], "server-deploy 키 미수집");
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("scopeString: 단일 타입은 '타입 name들', 복수 타입은 타입만 (.sh wf_scope_string 등가)", () => {
  assert.equal(scopeString([
    { type: "spring", workflowName: "단일 서버 배포" },
    { type: "spring", workflowName: "PR 프리뷰" },
    { type: "spring", workflowName: "단일 서버 배포" }, // 중복 제거
  ]), "spring 단일 서버 배포·PR 프리뷰");
  assert.equal(scopeString([
    { type: "spring", workflowName: "a" },
    { type: "react", workflowName: "b" },
  ]), "spring·react");
});

test("promptEnvPlan: force → 전부 기본값 Map + useDefaults=true (@repo resolver 해석 포함)", async () => {
  const tmp = fresh("ep-f-");
  try {
    makeTemplate(tmp);
    const r = await promptEnvPlan({
      tempDir: tmp, types: ["spring"], force: true,
      resolvers: { repo: () => "myrepo" }, log: () => {},
    });
    assert.equal(r.useDefaults, true);
    assert.equal(r.values.size, 4);
    assert.equal(r.values.get("PROJECT_NAME"), "myrepo");
    assert.equal(r.values.get("DEPLOY_PORT"), "8080");
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("promptEnvPlan: ask 키 0개면 빈 Map + useDefaults=true", async () => {
  const tmp = fresh("ep-0-");
  try {
    writeText(join(tmp, ".github/workflows/project-types/react/PROJECT-REACT-CI.yaml"), "name: ci\n");
    const r = await promptEnvPlan({ tempDir: tmp, types: ["react"], force: false, log: () => {} });
    assert.equal(r.values.size, 0);
    assert.equal(r.useDefaults, true);
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("promptEnvPlan: ③some 경로 — 고른 키(1개)만 입력값으로, useDefaults=false", async () => {
  const tmp = fresh("ep-s-");
  try {
    makeTemplate(tmp);
    const textCalls = [];
    const io = {
      select: async () => "some",
      multiselect: async () => ["JAVA_VERSION"],
      text: async ({ message, defaultValue }) => { textCalls.push({ message, defaultValue }); return "17"; },
    };
    const r = await promptEnvPlan({
      tempDir: tmp, types: ["spring"], io, force: false,
      resolvers: { repo: () => "myrepo" }, log: () => {},
    });
    assert.equal(r.useDefaults, false, "사용자 직접 입력 → useDefaults=false");
    assert.equal(r.values.size, 1, "고른 키만 values에 담김 (나머지는 substituteEnv 기본값 경로)");
    assert.equal(r.values.get("JAVA_VERSION"), "17");
    assert.equal(textCalls.length, 1, "고른 1개만 text 입력");
    assert.equal(textCalls[0].defaultValue, "21");
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("promptEnvPlan: ②each 경로 — 빈 입력(Enter)=기본값 유지, 전 키 처리", async () => {
  const tmp = fresh("ep-e-");
  try {
    makeTemplate(tmp);
    let n = 0;
    const io = {
      select: async () => "each",
      multiselect: async () => { throw new Error("each 경로에서 multiselect 호출 금지"); },
      text: async () => { n++; return n === 1 ? "custom.domain.com" : ""; }, // 첫 키만 입력, 나머지 Enter
    };
    const r = await promptEnvPlan({
      tempDir: tmp, types: ["spring"], io, force: false,
      resolvers: { repo: () => "myrepo" }, log: () => {},
    });
    assert.equal(r.useDefaults, false);
    assert.equal(r.values.size, 4, "each는 모든 키 확정 (.sh _wf_prefill_interactive 전체 등가)");
    assert.equal(r.values.get("SERVICE_DOMAIN"), "custom.domain.com");
    assert.equal(r.values.get("JAVA_VERSION"), "21", "빈 입력 → 기본값");
    assert.equal(r.values.get("PROJECT_NAME"), "myrepo");
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("promptEnvPlan: ①all/ESC → 전부 기본값 + useDefaults=true", async () => {
  const tmp = fresh("ep-a-");
  try {
    makeTemplate(tmp);
    const io = { select: async () => "all", multiselect: async () => [], text: async () => "" };
    const r = await promptEnvPlan({ tempDir: tmp, types: ["spring"], io, force: false, log: () => {} });
    assert.equal(r.useDefaults, true);
    assert.equal(r.values.size, 4);
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});

test("printFieldCard: 라벨·사용처·기본값 라인 출력 (log 주입)", () => {
  const lines = [];
  printFieldCard(null, "JAVA_VERSION", {
    default: "21",
    usages: [{ type: "spring", workflowName: "단일 서버 배포" }],
  }, 1, 4, (s) => lines.push(s));
  assert.match(lines[0], /\(1\/4\) JAVA_VERSION\s+\[spring 단일 서버 배포\]/);
  assert.ok(lines.some((l) => l.includes("Default: 21")));
});

// #489 — 카드에 노출되는 기본값도 설치본과 동일하게 전역 토큰을 해석해 보여준다
test("collectAsks: repoName 주입 시 기본값의 __PROJECT_NAME__ 해석 (#489)", () => {
  const tmp = fresh("ep-rn-");
  try {
    const base = join(tmp, ".github/workflows/project-types");
    writeText(join(base, "spring/server-deploy/PROJECT-SPRING-SIMPLE-CICD.yaml"), [
      "env:",
      '  VOLUME_HOST_PATH: "/volume1/projects/__PROJECT_NAME__"  # @wizard ask:/volume1/projects/__PROJECT_NAME__',
      "",
    ].join("\n"));
    const asks = collectAsks(tmp, ["spring"], { repoName: "my-repo" });
    assert.equal(asks.defaults.get("VOLUME_HOST_PATH"), "/volume1/projects/my-repo");
  } finally { rmSync(tmp, { recursive: true, force: true }); }
});
