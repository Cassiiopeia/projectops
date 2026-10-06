// 브랜치 전략 실효화 (#477) — 치환·가상비교·git 헬퍼·생성 플로우 검증.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { substituteBranches } from "../src/core/branch-sub.js";
import { isUnchanged } from "../src/core/wizard-env.js";
import { branchStatus, createBranch } from "../src/core/git-branch.js";
import { ensureDeployBranch } from "../src/core/options-ask.js";

// ── substituteBranches ────────────────────────────────────────────────

const WF = `on:
  push:
    branches: ["main"]
  pull_request:
    branches: [develop]
jobs:
  x:
    if: github.event.pull_request.head.ref == 'develop'
    steps:
      - run: git fetch origin main 2>/dev/null || true
`;

test("substituteBranches: 표준(main/develop)이면 바이트 동일 no-op", () => {
  assert.equal(substituteBranches(WF, { defaultBranch: "main", deployBranch: "develop" }), WF);
  assert.equal(substituteBranches(WF, null), WF);
});

test("substituteBranches: 인라인 트리거·가드·fetch 치환", () => {
  const out = substituteBranches(WF, { defaultBranch: "master", deployBranch: "release" });
  assert.match(out, /branches: \["master"\]/);
  assert.match(out, /branches: \[release\]/);
  assert.match(out, /== 'release'/);
  assert.match(out, /git fetch origin master/);
  assert.doesNotMatch(out, /\bdevelop\b/);
});

test("substituteBranches: 멀티라인 트리거 (- main, 뒤 주석 허용)", () => {
  const y = "on:\n  push:\n    branches:\n      - main  # 배포 환경\n      - develop\n";
  const out = substituteBranches(y, { defaultBranch: "prod", deployBranch: "dev" });
  assert.match(out, /- prod {2}# 배포 환경/);
  assert.match(out, /- dev\n/);
});

test("substituteBranches: 값 충돌 (기본 브랜치=develop) — 연쇄 오염 없음", () => {
  // main→develop 치환 결과가 develop→X 치환에 다시 걸리면 안 된다
  const out = substituteBranches(WF, { defaultBranch: "develop", deployBranch: "feature-x" });
  assert.match(out, /branches: \["develop"\]/);   // main → develop
  assert.match(out, /branches: \[feature-x\]/);   // develop → feature-x
  assert.match(out, /== 'feature-x'/);
  assert.match(out, /git fetch origin develop/);
});

test("substituteBranches: 무관한 리스트 항목·문장 안의 단어는 건드리지 않음", () => {
  const y = "labels:\n  - maintainer\nrun: echo 'develop mode'\nbranches: [\"main\"]\n";
  const out = substituteBranches(y, { defaultBranch: "master", deployBranch: "release" });
  assert.match(out, /- maintainer/);           // '- main'과 유사하지만 다른 단어
  assert.match(out, /echo 'develop mode'/);    // 문장 속 develop 불변
  assert.doesNotMatch(out, /branches: \["main"\]/);
});

// ── isUnchanged 브랜치 가상비교 ─────────────────────────────────────────

test("isUnchanged: 브랜치 치환 설치본을 unchanged로 판정 (재복사 churn 방지)", () => {
  const branches = { defaultBranch: "master", deployBranch: "release" };
  const installed = substituteBranches(WF, branches);
  assert.equal(isUnchanged(WF, installed, { branches }), true);
  assert.equal(isUnchanged(WF, installed, {}), false, "branches 없이는 다르게 보임(정상)");
});

// ── git 헬퍼 + ensureDeployBranch ─────────────────────────────────────

function gitRepo() {
  const root = mkdtempSync(join(tmpdir(), "gitbr-"));
  const g = (args) => execFileSync("git", args, { cwd: root, stdio: "ignore" });
  g(["init", "-q", "-b", "main"]);
  g(["config", "user.email", "t@t"]); g(["config", "user.name", "t"]);
  writeFileSync(join(root, "a.txt"), "x");
  g(["add", "-A"]); g(["commit", "-qm", "init"]);
  return root;
}

test("branchStatus/createBranch: 로컬 생성 및 감지 (원격 없음 → remote null)", () => {
  const root = gitRepo();
  try {
    let st = branchStatus(root, "develop");
    assert.equal(st.isRepo, true);
    assert.equal(st.local, false);
    assert.equal(st.remote, null); // origin 없음 → 불명
    assert.equal(createBranch(root, "develop", "main"), true);
    st = branchStatus(root, "develop");
    assert.equal(st.local, true);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("ensureDeployBranch: 없으면 확인 후 생성 (push 거절 경로) + push 질문에 브랜치명 명시(#481)", async () => {
  const root = gitRepo();
  try {
    const answers = [true, false]; // 생성 yes, push no
    const prompts = [];
    const logs = [];
    const r = await ensureDeployBranch({
      targetRoot: root, deployBranch: "develop", defaultBranch: "main",
      io: { confirm: async ({ message }) => { prompts.push(message); return answers.shift(); } },
      say: (m) => logs.push(m),
    });
    assert.equal(r.created, true);
    assert.equal(r.pushed, false);
    assert.equal(branchStatus(root, "develop").local, true);
    // #481 — push 질문이 어느 브랜치인지 명시
    assert.ok(prompts.some((p) => p.includes("'develop'") && p.includes("push")), `push 질문에 브랜치명 없음: ${JSON.stringify(prompts)}`);
    // #482 — 안내에서 "배포 브랜치" 대신 "개발" 표현 사용
    assert.ok(logs.some((l) => l.includes("Development") && l.includes("develop")), "개발 브랜치 표현 없음");
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("ensureDeployBranch: 이미 있으면 조용히 통과, 거절하면 안내만", async () => {
  const root = gitRepo();
  try {
    createBranch(root, "develop", "main");
    const r1 = await ensureDeployBranch({
      targetRoot: root, deployBranch: "develop", defaultBranch: "main",
      io: { confirm: async () => { throw new Error("물어보면 안 됨"); } },
    });
    assert.equal(r1.created, false);

    const logs = [];
    const r2 = await ensureDeployBranch({
      targetRoot: root, deployBranch: "release", defaultBranch: "main",
      io: { confirm: async () => false }, say: (m) => logs.push(m),
    });
    assert.equal(r2.created, false);
    assert.equal(branchStatus(root, "release").local, false);
    assert.ok(logs.some((l) => l.includes("git checkout -b release")));
  } finally { rmSync(root, { recursive: true, force: true }); }
});

test("ensureDeployBranch: 비레포·io.confirm 없음이면 no-op", async () => {
  const root = mkdtempSync(join(tmpdir(), "nonrepo-"));
  try {
    const r = await ensureDeployBranch({
      targetRoot: root, deployBranch: "develop", defaultBranch: "main",
      io: { confirm: async () => true },
    });
    assert.equal(r.created, false);
    const r2 = await ensureDeployBranch({ targetRoot: root, deployBranch: "develop", io: {} });
    assert.equal(r2.created, false);
  } finally { rmSync(root, { recursive: true, force: true }); }
});

// #490 — ready 시그널: 완료 요약이 "브랜치 만들어라" 재지시를 접을지 판단하는 근거
test("ensureDeployBranch: ready — 존재/생성=true, 거절=false, 비레포=null (#490)", async () => {
  const root = gitRepo();
  try {
    // 이미 로컬 존재 → true
    createBranch(root, "develop", "main");
    const r1 = await ensureDeployBranch({
      targetRoot: root, deployBranch: "develop", defaultBranch: "main",
      io: { confirm: async () => true },
    });
    assert.equal(r1.ready, true);
    // 없는데 생성 거절 → false
    const r2 = await ensureDeployBranch({
      targetRoot: root, deployBranch: "rel-a", defaultBranch: "main",
      io: { confirm: async () => false }, say: () => {},
    });
    assert.equal(r2.ready, false);
    // 생성 승인(push 거절) → true
    const answers = [true, false];
    const r3 = await ensureDeployBranch({
      targetRoot: root, deployBranch: "rel-b", defaultBranch: "main",
      io: { confirm: async () => answers.shift() }, say: () => {},
    });
    assert.equal(r3.ready, true);
  } finally { rmSync(root, { recursive: true, force: true }); }
  // 비레포 → null (확인 불가 — 요약은 보수적으로 안내 유지)
  const nr = mkdtempSync(join(tmpdir(), "nonrepo-rd-"));
  try {
    const r = await ensureDeployBranch({
      targetRoot: nr, deployBranch: "develop", defaultBranch: "main",
      io: { confirm: async () => true },
    });
    assert.equal(r.ready, null);
  } finally { rmSync(nr, { recursive: true, force: true }); }
});
