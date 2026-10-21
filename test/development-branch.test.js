// 비대화형 개발 브랜치 생성 (#715) — 이미 있음 · 없음 · push 실패 3경우를 실제 git(로컬 bare 원격)으로 확인.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync, readFileSync, readdirSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { createDevelopmentBranchUnattended, runDevelopmentBranchStep } from "../src/core/development-branch.js";
import { parseArgs } from "../src/cli/args.js";
import { run } from "../src/index.js";

const REPO = join(import.meta.dirname, "..");

const git = (cwd, args) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();

// 작업 레포 (main 커밋 1개) + 선택적으로 로컬 bare 원격(origin)
function setupRepo({ withRemote = true, brokenRemote = false } = {}) {
  const base = mkdtempSync(join(tmpdir(), "devbr-"));
  const work = join(base, "work");
  const bare = join(base, "origin.git");
  execFileSync("git", ["init", "-q", "-b", "main", work]);
  git(work, ["config", "user.email", "t@t"]);
  git(work, ["config", "user.name", "t"]);
  writeFileSync(join(work, "package.json"), '{"name":"x","version":"1.0.0"}');
  git(work, ["add", "-A"]);
  git(work, ["commit", "-qm", "init"]);
  if (withRemote) {
    execFileSync("git", ["init", "-q", "--bare", "-b", "main", bare]);
    git(work, ["remote", "add", "origin", bare]);
    git(work, ["push", "-q", "-u", "origin", "main"]);
  }
  // push 실패 재현: 존재하지 않는 경로를 origin 으로
  if (brokenRemote) git(work, ["remote", "add", "origin", join(base, "missing.git")]);
  return { base, work, bare };
}
const remoteHas = (bare, name) => git(bare, ["branch", "--list", name]).length > 0;

test("--create-development-branch 파싱: 기본 꺼짐, 주면 켜짐", () => {
  assert.equal(parseArgs(["--mode", "full"]).createDevelopmentBranch, false);
  assert.equal(parseArgs(["--mode", "full", "--create-development-branch"]).createDevelopmentBranch, true);
});

test("없으면 기본 브랜치에서 만들고 origin 에 push 한다 (created)", async () => {
  const { base, work, bare } = setupRepo();
  try {
    const r = await createDevelopmentBranchUnattended({ targetRoot: work, branch: "develop", defaultBranch: "main" });
    assert.equal(r.status, "created");
    assert.equal(r.pushed, true);
    assert.equal(r.manualCommand, null);
    assert.equal(git(work, ["rev-parse", "develop"]), git(work, ["rev-parse", "main"]));
    assert.ok(remoteHas(bare, "develop"), "origin 에 develop 이 없다");
    assert.equal(git(work, ["branch", "--show-current"]), "main", "checkout 하지 않는다");
  } finally { rmSync(base, { recursive: true, force: true }); }
});

test("이미 있으면 아무것도 하지 않는다 (로컬·원격 모두 skipped, 멱등)", async () => {
  const { base, work, bare } = setupRepo();
  try {
    const first = await createDevelopmentBranchUnattended({ targetRoot: work, branch: "develop", defaultBranch: "main" });
    assert.equal(first.status, "created");
    const again = await createDevelopmentBranchUnattended({ targetRoot: work, branch: "develop", defaultBranch: "main" });
    assert.equal(again.status, "skipped");
    assert.equal(again.reason, "exists-local");

    // 원격에만 있음 (CI 의 새 clone) — 로컬에 만들지 않는다
    git(work, ["branch", "-D", "develop"]);
    const remoteOnly = await createDevelopmentBranchUnattended({ targetRoot: work, branch: "develop", defaultBranch: "main" });
    assert.equal(remoteOnly.status, "skipped");
    assert.equal(remoteOnly.reason, "exists-remote");
    assert.equal(git(work, ["branch", "--list", "develop"]), "");
    assert.ok(remoteHas(bare, "develop"));
  } finally { rmSync(base, { recursive: true, force: true }); }
});

test("push 실패는 예외 없이 failed + 수동 push 명령을 돌려준다", async () => {
  const { base, work } = setupRepo({ withRemote: false, brokenRemote: true });
  try {
    const r = await createDevelopmentBranchUnattended({ targetRoot: work, branch: "develop", defaultBranch: "main" });
    assert.equal(r.status, "failed");
    assert.equal(r.reason, "push-failed");
    assert.equal(r.manualCommand, "git push -u origin develop");
    assert.equal(git(work, ["branch", "--list", "develop"]).replace("*", "").trim(), "develop", "로컬 브랜치는 남는다");
  } finally { rmSync(base, { recursive: true, force: true }); }
});

test("레포가 아니면 failed + 생성·push 명령", async () => {
  const dir = mkdtempSync(join(tmpdir(), "devbr-nonrepo-"));
  try {
    const r = await createDevelopmentBranchUnattended({ targetRoot: dir, branch: "develop", defaultBranch: "main" });
    assert.equal(r.status, "failed");
    assert.equal(r.reason, "not-a-repo");
    assert.match(r.manualCommand, /git checkout -b develop && git push -u origin develop/);
  } finally { rmSync(dir, { recursive: true, force: true }); }
});

test("플래그가 없으면 만들지 않고 not-requested 만 기록한다", async () => {
  const { base, work } = setupRepo();
  try {
    const events = [];
    const trace = { event: (phase, action, target, detail) => events.push({ phase, action, target, detail }) };
    const r = await runDevelopmentBranchStep({ isRequested: false, targetRoot: work, branch: "develop", defaultBranch: "main", trace });
    assert.equal(r, null);
    assert.equal(git(work, ["branch", "--list", "develop"]), "");
    assert.deepEqual(events.map((e) => `${e.phase}/${e.action}`), ["dev-branch/not-requested"]);
  } finally { rmSync(base, { recursive: true, force: true }); }
});

// ── 실제 CLI 실행 (요약 · 실행 기록 · 마이그레이션 가이드) ──────────────────────────
function captureStderr() {
  const orig = process.stderr.write.bind(process.stderr);
  const origError = console.error;
  let out = "";
  process.stderr.write = (chunk) => { out += chunk; return true; };
  console.error = (...a) => { out += a.join(" ") + "\n"; };
  return { text: () => out, restore: () => { process.stderr.write = orig; console.error = origError; } };
}
const install = async (cwd, extra = []) => {
  const cap = captureStderr();
  try {
    const code = await run(["--force", "-t", "node", "-m", "full", "--lang", "en", ...extra], { cwd, source: { type: "local", path: REPO } });
    return { code, stderr: cap.text() };
  } finally { cap.restore(); }
};
const readLogs = (cwd) => {
  const dir = join(cwd, ".github/.projectops/logs");
  const jsonl = readdirSync(dir).find((f) => f.endsWith(".jsonl"));
  return readFileSync(join(dir, jsonl), "utf8");
};
const readGuide = (cwd) => {
  const dir = join(cwd, ".github/.projectops/logs");
  const md = readdirSync(dir).find((f) => f.endsWith(".md"));
  return readFileSync(join(dir, md), "utf8");
};

test("CLI: --create-development-branch 로 만들고 요약·기록·가이드에 남긴다", async () => {
  const { base, work, bare } = setupRepo();
  try {
    const { code, stderr } = await install(work, ["--create-development-branch"]);
    assert.equal(code, 0);
    assert.ok(remoteHas(bare, "develop"), "origin 에 develop 이 없다");
    assert.match(stderr, /Branch develop was created from main and pushed to origin/);
    assert.match(readLogs(work), /"phase":"dev-branch","action":"created"/);
    const guide = readGuide(work);
    assert.match(guide, /- \[x\] Development \(release source\) branch `develop`: created from `main` and pushed/);
    assert.match(guide, /create_result: "created"/);

    // 다시 돌리면 아무것도 바꾸지 않는다
    const again = await install(work, ["--create-development-branch"]);
    assert.equal(again.code, 0);
    assert.match(again.stderr, /Branch develop already exists: nothing was changed/);
  } finally { rmSync(base, { recursive: true, force: true }); }
});

test("CLI: push 가 실패해도 종료 코드 0 + 수동 명령 안내 + ERROR 기록", async () => {
  const { base, work } = setupRepo({ withRemote: false, brokenRemote: true });
  try {
    const { code, stderr } = await install(work, ["--create-development-branch"]);
    assert.equal(code, 0);
    assert.match(stderr, /Branch develop could not be created or pushed \(push-failed\)/);
    assert.match(stderr, /→ git push -u origin develop/);
    assert.match(readLogs(work), /"phase":"dev-branch","action":"failed"/);
    assert.match(readGuide(work), /- \[ \] \*\*Create the development \(release source\) branch `develop`\*\*: automatic creation failed \(push-failed\)\. Run: `git push -u origin develop`/);
  } finally { rmSync(base, { recursive: true, force: true }); }
});

test("CLI: 플래그 없이 돌면 만들지 않고 다음 할 일에 플래그를 안내한다", async () => {
  const { base, work, bare } = setupRepo();
  try {
    const { code, stderr } = await install(work);
    assert.equal(code, 0);
    assert.equal(remoteHas(bare, "develop"), false);
    assert.equal(git(work, ["branch", "--list", "develop"]), "");
    assert.match(stderr, /Create the develop branch \(if it does not exist yet\)/);
    assert.match(stderr, /add --create-development-branch/);
    assert.match(readLogs(work), /"phase":"dev-branch","action":"not-requested"/);
    assert.ok(existsSync(join(work, "version.yml")));
  } finally { rmSync(base, { recursive: true, force: true }); }
});
