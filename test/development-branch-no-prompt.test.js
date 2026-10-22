// 비대화형 개발 브랜치 push 는 자격 증명을 묻지 않는다 (#988)
// 실사고 가능성: HTTPS 원격에 저장된 자격 증명이 없으면 git 이 사용자 입력을 기다려 무인 실행이 멈춘다.
// 재현: 모든 요청에 401 을 돌려주는 로컬 HTTP 원격 + 호출되면 흔적을 남기는 가짜 askpass.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync, existsSync, chmodSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { execFileSync, spawn, spawnSync } from "node:child_process";
import { nonInteractiveGitEnv } from "../src/core/git-branch.js";

const MODULE_URL = pathToFileURL(join(import.meta.dirname, "..", "src/core/development-branch.js")).href;
// 질문 차단이 깨지면 git 이 입력을 기다린다 — 이 시간 안에 끝나야 통과
const WORKER_TIMEOUT_MILLISECONDS = 30000;

const git = (cwd, args) => execFileSync("git", args, { cwd, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();

// 모든 요청에 Basic 인증을 요구하는 HTTP 서버 (별도 프로세스 — 테스트 쪽은 동기 git 호출로 막힌다)
function startAuthRequiredServer() {
  const code = `
    const server = require("node:http").createServer((request, response) => {
      response.writeHead(401, { "WWW-Authenticate": 'Basic realm="projectops-test"' });
      response.end("auth required");
    });
    server.listen(0, "127.0.0.1", () => console.log(server.address().port));`;
  const child = spawn(process.execPath, ["-e", code], { stdio: ["ignore", "pipe", "inherit"] });
  return new Promise((resolve, reject) => {
    child.once("error", reject);
    child.stdout.once("data", (chunk) => resolve({ port: Number(String(chunk).trim()), stop: () => child.kill() }));
  });
}

function setupRepo(base, port) {
  const work = join(base, "work");
  execFileSync("git", ["init", "-q", "-b", "main", work]);
  git(work, ["config", "user.email", "t@t"]);
  git(work, ["config", "user.name", "t"]);
  writeFileSync(join(work, "README.md"), "x\n");
  git(work, ["add", "-A"]);
  git(work, ["commit", "-qm", "init"]);
  git(work, ["remote", "add", "origin", `http://127.0.0.1:${port}/repo.git`]);
  return work;
}

test("nonInteractiveGitEnv: 질문 4종을 막고, 사용자 ssh 명령은 덮지 않는다", () => {
  const env = nonInteractiveGitEnv({ PATH: "/bin", GIT_ASKPASS: "/x/askpass" });
  assert.equal(env.GIT_TERMINAL_PROMPT, "0");
  assert.equal(env.GIT_ASKPASS, "");
  assert.equal(env.SSH_ASKPASS, "");
  assert.equal(env.GCM_INTERACTIVE, "never");
  assert.equal(env.GIT_SSH_COMMAND, "ssh -o BatchMode=yes");
  assert.equal(env.PATH, "/bin");

  assert.equal(nonInteractiveGitEnv({ GIT_SSH_COMMAND: "ssh -i key" }).GIT_SSH_COMMAND, "ssh -i key");
  assert.equal(nonInteractiveGitEnv({ GIT_SSH: "/usr/bin/plink" }).GIT_SSH_COMMAND, undefined);
  assert.equal(nonInteractiveGitEnv({}, { hasCustomSshCommand: true }).GIT_SSH_COMMAND, undefined);
});

test("인증을 요구하는 HTTPS 원격: 묻지 않고 바로 failed + 수동 push 명령", async () => {
  const base = mkdtempSync(join(tmpdir(), "devbr-noprompt-"));
  const server = await startAuthRequiredServer();
  try {
    const work = setupRepo(base, server.port);
    // 질문 경로가 열려 있으면 git 이 이 스크립트를 부른다 — 부르면 흔적 파일이 생긴다
    const marker = join(base, "askpass-called");
    const askpass = join(base, "askpass.sh");
    writeFileSync(askpass, `#!/bin/sh\necho called >> "${marker}"\necho secret\n`);
    chmodSync(askpass, 0o755);
    const emptyConfig = join(base, "empty.gitconfig");
    writeFileSync(emptyConfig, "");

    const worker = `
      const { createDevelopmentBranchUnattended } = await import(${JSON.stringify(MODULE_URL)});
      const result = await createDevelopmentBranchUnattended({ targetRoot: ${JSON.stringify(work)}, branch: "develop", defaultBranch: "main" });
      console.log(JSON.stringify(result));`;
    const startedAt = Date.now();
    const run = spawnSync(process.execPath, ["--input-type=module", "-e", worker], {
      encoding: "utf8",
      timeout: WORKER_TIMEOUT_MILLISECONDS,
      env: {
        ...process.env,
        // 질문을 부르는 환경 흉내 + 사용자 git 설정(자격 증명 도우미 등) 차단
        GIT_ASKPASS: askpass, SSH_ASKPASS: askpass,
        GIT_CONFIG_GLOBAL: emptyConfig, GIT_CONFIG_NOSYSTEM: "1",
        NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost",
      },
    });
    assert.equal(run.error, undefined, `worker did not finish in ${WORKER_TIMEOUT_MILLISECONDS}ms (git waited for input?)`);
    assert.equal(run.status, 0, run.stderr);
    const result = JSON.parse(run.stdout.trim().split("\n").pop());
    assert.equal(result.status, "failed");
    assert.equal(result.reason, "push-failed");
    assert.equal(result.manualCommand, "git push -u origin develop");
    assert.ok(Date.now() - startedAt < WORKER_TIMEOUT_MILLISECONDS);
    // Windows 는 sh 스크립트 askpass 실행 방식이 달라 흔적 검사만 건너뛴다
    if (process.platform !== "win32") assert.equal(existsSync(marker), false, "git asked for credentials");
  } finally {
    server.stop();
    rmSync(base, { recursive: true, force: true });
  }
});
