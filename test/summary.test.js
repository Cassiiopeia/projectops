import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, dirname } from "node:path";
import { printSummary } from "../src/ui/summary.js";

function touch(root, rel, content = "") {
  const p = join(root, rel);
  mkdirSync(dirname(p), { recursive: true });
  writeFileSync(p, content);
}

// stderr 캡처 — printSummary는 전부 stderr로 쓴다
function captureStderr(fn) {
  const orig = process.stderr.write;
  let out = "";
  process.stderr.write = (chunk) => { out += chunk; return true; };
  try { fn(); } finally { process.stderr.write = orig; }
  return out;
}

test("printSummary: full 모드 스모크 — 워크플로우 분류·타입 안내 포함", () => {
  const root = mkdtempSync(join(tmpdir(), "summary-"));
  try {
    // 레거시 파일이 디렉토리에 존재해도 목록에 안 나와야 한다 (#473 — 스캔 제거, copiedFiles가 소스)
    touch(root, ".github/workflows/PROJECT-COMMON-SYNOLOGY-SECRET-FILE-UPLOAD.yaml");
    touch(root, ".github/util/flutter/testflight-wizard/index.html");
    const out = captureStderr(() => printSummary({
      mode: "full", types: ["spring", "flutter"], version: "1.2.3",
      counters: {
        workflows: 2, utilModules: 1,
        workflowFiles: ["PROJECT-COMMON-VERSION-CONTROL.yaml", "PROJECT-SPRING-SIMPLE-CICD.yaml"],
      },
    }, root));
    assert.match(out, /Setup Complete/);
    assert.match(out, /version\.yml \(버전: 1\.2\.3, 타입: spring,flutter\)/);
    assert.match(out, /새로 설치·갱신됨 \(2개\)/);                        // 카운터 = 목록 길이 (#473)
    assert.match(out, /📌 PROJECT-COMMON-VERSION-CONTROL\.yaml/);       // 공통 분류
    assert.match(out, /🎯 PROJECT-SPRING-SIMPLE-CICD\.yaml/);           // 타입 분류
    assert.doesNotMatch(out, /SYNOLOGY-SECRET-FILE-UPLOAD/);            // 존재만 하는 레거시 미표기 (#473)
    assert.match(out, /testflight-wizard \(flutter\)/);                 // util 모듈 트리
    assert.match(out, /Spring 프로젝트 추가 설정/);                       // spring 안내
    assert.match(out, /Flutter 배포 마법사 사용법/);                      // flutter 안내
    assert.match(out, /_GITHUB_PAT_TOKEN/);                             // 다음 3가지 작업
    assert.match(out, /coderabbit\.ai/);
    assert.match(out, /PROJECTOPS-SETUP-GUIDE\.md/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("printSummary: skills 모드 — 간결 종료 (파일 목록·3가지 작업 없음)", () => {
  const root = mkdtempSync(join(tmpdir(), "summarysk-"));
  try {
    const out = captureStderr(() => printSummary({
      mode: "skills", types: [], version: "", counters: {},
    }, root));
    assert.match(out, /Agent Skill 설치/);
    assert.match(out, /TEMPLATE REPO/);
    assert.doesNotMatch(out, /추가된 파일/);
    assert.doesNotMatch(out, /다음 3가지 작업/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("printSummary: issues 모드 — 체크리스트에 템플릿만", () => {
  const root = mkdtempSync(join(tmpdir(), "summaryis-"));
  try {
    const out = captureStderr(() => printSummary({
      mode: "issues", types: ["basic"], version: "0.0.1", counters: {},
    }, root));
    assert.match(out, /이슈\/PR\/Discussion 템플릿/);
    assert.doesNotMatch(out, /버전 관리 시스템/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// #490 — 마법사가 이번 실행에서 브랜치를 확인·생성했으면 재지시하지 않는다
test("printSummary: deployBranchReady=true면 생성 재지시 대신 완료 표시 (#490)", () => {
  const root = mkdtempSync(join(tmpdir(), "summary-br-"));
  try {
    const base = { mode: "full", types: ["spring"], version: "1.0.0", deployBranch: "develop", counters: { workflows: 0, workflowFiles: [] } };
    const done = captureStderr(() => printSummary({ ...base, deployBranchReady: true }, root));
    assert.match(done, /develop 브랜치 준비 완료/);
    assert.equal(done.includes("git checkout -b develop"), false, "완료됐는데 생성 명령 안내 금지");
    // 미확인(기본) — 기존 안내 유지
    const todo = captureStderr(() => printSummary(base, root));
    assert.match(todo, /develop 브랜치 생성 \(아직 없다면\)/);
    assert.equal(todo.includes("git checkout -b develop"), true);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// #493 — 마이그레이션 가이드 포인터
test("printSummary: migrationGuidePath 있으면 가이드 안내 출력 (#493)", () => {
  const root = mkdtempSync(join(tmpdir(), "summary-mg-"));
  try {
    const base = { mode: "full", types: ["spring"], version: "1.0.0", counters: { workflows: 0, workflowFiles: [] } };
    const withGuide = captureStderr(() => printSummary({ ...base, migrationGuidePath: ".github/.projectops/logs/PROJECTOPS-MIGRATION-GUIDE.md" }, root));
    assert.match(withGuide, /🧭 마이그레이션 가이드: .github\/.projectops\/logs\/PROJECTOPS-MIGRATION-GUIDE\.md/);
    const without = captureStderr(() => printSummary(base, root));
    assert.doesNotMatch(without, /마이그레이션 가이드:/);
  } finally { rmSync(root, { recursive: true, force: true }); }
});
