import { test } from "node:test";
import assert from "node:assert/strict";
import { copyWorkflows } from "../src/core/copy/workflows.js";
import { writeText, exists, readText } from "../src/core/fsutil.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function fresh(p) { return mkdtempSync(join(tmpdir(), p)); }

// 소형 템플릿 트리 (tempDir/.github/workflows/project-types/...)
function makeTemplate(tempDir) {
  const base = join(tempDir, ".github/workflows/project-types");
  writeText(join(base, "common/PROJECT-COMMON-CI.yaml"), "name: common-ci\n");
  writeText(join(base, "react/PROJECT-REACT-CICD.yaml"), '  APP: "__X__"  # @wizard ask:myapp\n');
  writeText(join(base, "spring/server-deploy/PROJECT-SPRING-SIMPLE-CICD.yaml"), "name: spring-deploy\n");
  writeText(join(base, "spring/publish/nexus/PROJECT-SPRING-NEXUS-PUBLISH.yaml"), "name: nexus\n");
  writeText(join(base, "common/deploy/vercel/PROJECT-COMMON-VERCEL-DEPLOY.yaml"), "name: vercel\n");
  writeText(join(base, "common/secret-backup/PROJECT-COMMON-SECRET.yaml"), "name: secret\n");
}

test("copyWorkflows: common 복사 + 타입별 신규 + env 치환", () => {
  const tmp = fresh("wf-t-"); const tgt = fresh("wf-g-");
  try {
    makeTemplate(tmp);
    const ctx = { types: ["react"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, force: true, repoName: "projectops", resolvers: { repo: () => "projectops" } };
    const c = copyWorkflows(ctx, tmp, tgt);
    // common 복사됨
    assert.ok(exists(join(tgt, ".github/workflows/PROJECT-COMMON-CI.yaml")));
    // react 복사 + env 치환 (기본값 myapp)
    const react = readText(join(tgt, ".github/workflows/PROJECT-REACT-CICD.yaml"));
    assert.equal(react, '  APP: "myapp"\n'); // 원본 끝 개행 보존
    assert.ok(c.copied >= 2);
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyWorkflows: server-deploy 포함(nexus 아님), nexus 제외", () => {
  const tmp = fresh("wf2t-"); const tgt = fresh("wf2g-");
  try {
    makeTemplate(tmp);
    const ctx = { types: ["spring"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, force: true, repoName: "r", resolvers: {} };
    copyWorkflows(ctx, tmp, tgt);
    assert.ok(exists(join(tgt, ".github/workflows/PROJECT-SPRING-SIMPLE-CICD.yaml")), "server-deploy 포함");
    assert.equal(exists(join(tgt, ".github/workflows/PROJECT-SPRING-NEXUS-PUBLISH.yaml")), false, "nexus 제외(opt-in)");
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyWorkflows: deploy=none + publish=[nexus]면 server-deploy 제외 + nexus 포함 (#439)", () => {
  const tmp = fresh("wf3t-"); const tgt = fresh("wf3g-");
  try {
    makeTemplate(tmp);
    const ctx = { types: ["spring"], paths: new Map(), deployTarget: "none", publishTargets: ["nexus"], includeSecretBackup: false, force: true, repoName: "r", resolvers: {} };
    copyWorkflows(ctx, tmp, tgt);
    assert.equal(exists(join(tgt, ".github/workflows/PROJECT-SPRING-SIMPLE-CICD.yaml")), false, "deploy=none이라 server-deploy 제외");
    assert.ok(exists(join(tgt, ".github/workflows/PROJECT-SPRING-NEXUS-PUBLISH.yaml")), "nexus 포함");
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyWorkflows: secret-backup은 opt-in", () => {
  const tmp = fresh("wf4t-"); const tgt = fresh("wf4g-");
  try {
    makeTemplate(tmp);
    const noSB = { types: ["react"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, force: true, repoName: "r", resolvers: {} };
    copyWorkflows(noSB, tmp, tgt);
    assert.equal(exists(join(tgt, ".github/workflows/PROJECT-COMMON-SECRET.yaml")), false, "옵션 없으면 제외");

    const tgt2 = fresh("wf4g2-");
    const withSB = { ...noSB, includeSecretBackup: true };
    copyWorkflows(withSB, tmp, tgt2);
    assert.ok(exists(join(tgt2, ".github/workflows/PROJECT-COMMON-SECRET.yaml")), "옵션 있으면 포함");
    rmSync(tgt2, { recursive: true, force: true });
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyWorkflows: deploy=vercel이면 common/deploy/vercel 포함 + server-deploy 제외 (#439)", () => {
  const tmp = fresh("wf6t-"); const tgt = fresh("wf6g-");
  try {
    makeTemplate(tmp);
    const ctx = { types: ["spring"], paths: new Map(), deployTarget: "vercel", publishTargets: [], includeSecretBackup: false, force: true, repoName: "r", resolvers: {} };
    copyWorkflows(ctx, tmp, tgt);
    assert.ok(exists(join(tgt, ".github/workflows/PROJECT-COMMON-VERCEL-DEPLOY.yaml")), "vercel 배포 워크플로우 포함");
    assert.equal(exists(join(tgt, ".github/workflows/PROJECT-SPRING-SIMPLE-CICD.yaml")), false, "deploy=vercel이라 server-deploy 제외");
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyWorkflows: common unchanged면 재복사 스킵", () => {
  const tmp = fresh("wf5t-"); const tgt = fresh("wf5g-");
  try {
    makeTemplate(tmp);
    // 대상에 이미 동일 common 설치돼 있음
    writeText(join(tgt, ".github/workflows/PROJECT-COMMON-CI.yaml"), "name: common-ci\n");
    const ctx = { types: ["react"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, force: true, repoName: "r", resolvers: {} };
    const c = copyWorkflows(ctx, tmp, tgt);
    assert.ok(c.skipped >= 1, "unchanged common 스킵");
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// #491 — 템플릿 util 동기화 워크플로우는 util 모듈이 있(게 되)는 레포에만 복사된다
test("copyWorkflows: util 없는 레포에는 TEMPLATE-UTIL-VERSION-SYNC 제외 (#491)", () => {
  const tmp = fresh("wfu1t-"); const tgt = fresh("wfu1g-");
  try {
    makeTemplate(tmp);
    writeText(join(tmp, ".github/workflows/project-types/common/PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml"), "name: util-sync\n");
    // spring 단독: 템플릿에 util/spring 없음 + 대상에 .github/util 없음 → 제외
    const ctx = { types: ["spring"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, force: true, repoName: "r", resolvers: {} };
    copyWorkflows(ctx, tmp, tgt);
    assert.equal(exists(join(tgt, ".github/workflows/PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml")), false, "util 없는 레포 — 제외");
    assert.ok(exists(join(tgt, ".github/workflows/PROJECT-COMMON-CI.yaml")), "다른 common은 정상 복사");
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyWorkflows: util 모듈이 복사될 타입이면 TEMPLATE-UTIL-VERSION-SYNC 포함 (#491)", () => {
  const tmp = fresh("wfu2t-"); const tgt = fresh("wfu2g-");
  try {
    makeTemplate(tmp);
    writeText(join(tmp, ".github/workflows/project-types/common/PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml"), "name: util-sync\n");
    writeText(join(tmp, ".github/util/spring/some-wizard/version.json"), "{}\n"); // 이번 통합에서 util 복사 예정
    const ctx = { types: ["spring"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, force: true, repoName: "r", resolvers: {} };
    copyWorkflows(ctx, tmp, tgt);
    assert.ok(exists(join(tgt, ".github/workflows/PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml")), "util 복사 예정 타입 — 포함");
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyWorkflows: 대상에 이미 .github/util 있으면(업데이트) TEMPLATE-UTIL-VERSION-SYNC 포함 (#491)", () => {
  const tmp = fresh("wfu3t-"); const tgt = fresh("wfu3g-");
  try {
    makeTemplate(tmp);
    writeText(join(tmp, ".github/workflows/project-types/common/PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml"), "name: util-sync\n");
    writeText(join(tgt, ".github/util/flutter/testflight-wizard/version.json"), "{}\n"); // 기존 설치 레포
    const ctx = { types: ["spring"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, force: true, repoName: "r", resolvers: {} };
    copyWorkflows(ctx, tmp, tgt);
    assert.ok(exists(join(tgt, ".github/workflows/PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml")), "대상 util 보유 — 포함");
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// #489 — deploy 블록(version.yml 기억값)에 들어갈 수집값이 파일 설치본과 일치해야 한다
test("copyWorkflows: deployValues 수집값도 __PROJECT_NAME__ 치환 — 설치본과 일치 (#489)", () => {
  const tmp = fresh("wfd1t-"); const tgt = fresh("wfd1g-");
  try {
    makeTemplate(tmp);
    writeText(join(tmp, ".github/workflows/project-types/spring/server-deploy/PROJECT-SPRING-VOL.yaml"), [
      "env:",
      '  VOLUME_HOST_PATH: "/volume1/projects/__PROJECT_NAME__"  # @wizard ask:/volume1/projects/__PROJECT_NAME__',
      "",
    ].join("\n"));
    const ctx = { types: ["spring"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, force: true, repoName: "my-repo", resolvers: {} };
    const c = copyWorkflows(ctx, tmp, tgt);
    const installed = readText(join(tgt, ".github/workflows/PROJECT-SPRING-VOL.yaml"));
    assert.match(installed, /"\/volume1\/projects\/my-repo"/);
    assert.equal(c.deployValues.get("spring").get("VOLUME_HOST_PATH"), "/volume1/projects/my-repo");
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

// #494 — 복사 엔진 트레이스: hooks.trace로 파일별 결정·치환 이벤트가 남는다
test("copyWorkflows: hooks.trace에 copy/env 이벤트 기록 (#494)", () => {
  const tmp = fresh("wftr-t-"); const tgt = fresh("wftr-g-");
  try {
    makeTemplate(tmp);
    const events = [];
    const trace = { event: (phase, action, target, detail) => events.push({ phase, action, target, detail }) };
    const ctx = { types: ["react"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: false, force: true, repoName: "projectops", resolvers: { repo: () => "projectops" } };
    copyWorkflows(ctx, tmp, tgt, { trace });
    assert.ok(events.some((e) => e.phase === "copy" && e.action === "copied" && e.target === "PROJECT-COMMON-CI.yaml"));
    assert.ok(events.some((e) => e.phase === "copy" && e.action === "copied" && e.target === "PROJECT-REACT-CICD.yaml"));
    const env = events.find((e) => e.phase === "env" && e.action === "substituted" && e.target === "PROJECT-REACT-CICD.yaml");
    assert.ok(env, "env 치환 이벤트");
    assert.equal(env.detail.key, "APP");
    assert.equal(env.detail.after, "myapp");
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyWorkflows: secret-backup 의 PROJECT_NAME 을 레포 이름으로 채운다 (#729)", () => {
  const tmp = fresh("sb-t-"); const tgt = fresh("sb-g-");
  try {
    makeTemplate(tmp);
    writeText(join(tmp, ".github/workflows/project-types/common/secret-backup/PROJECT-COMMON-SECRET.yaml"),
      'env:\n  PROJECT_NAME: "__PROJECT_NAME__"\n  ROLE: "backend"\n');
    const ctx = { types: ["react"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: true, force: true, repoName: "my-real-app", resolvers: {} };
    copyWorkflows(ctx, tmp, tgt);
    const body = readText(join(tgt, ".github/workflows/PROJECT-COMMON-SECRET.yaml"));
    assert.match(body, /PROJECT_NAME: "my-real-app"/);
    assert.doesNotMatch(body, /__PROJECT_NAME__/);
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyWorkflows: 레포 이름을 모르면 secret-backup 에 빈 이름 대신 기본값을 쓴다 (#729)", () => {
  const tmp = fresh("sb2-t-"); const tgt = fresh("sb2-g-");
  try {
    makeTemplate(tmp);
    writeText(join(tmp, ".github/workflows/project-types/common/secret-backup/PROJECT-COMMON-SECRET.yaml"),
      'env:\n  PROJECT_NAME: "__PROJECT_NAME__"\n');
    const ctx = { types: ["react"], paths: new Map(), deployTarget: "docker-ssh", publishTargets: [], includeSecretBackup: true, force: true, repoName: "", resolvers: {} };
    copyWorkflows(ctx, tmp, tgt);
    assert.match(readText(join(tgt, ".github/workflows/PROJECT-COMMON-SECRET.yaml")), /PROJECT_NAME: "my-project"/);
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});
