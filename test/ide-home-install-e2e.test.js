// 홈 복사형 설치(Cursor·GitHub Copilot) 끝까지 확인 (#200):
// 실제 apply 경로로 임시 HOME 에 설치 > 설치본의 스킬 CLI 를 진짜 파이썬으로 실행 > ok:true
// 지키려는 것: 스킬만 복사하면 CLI 가 scripts/common 을 못 찾아 import 에서 죽는다 (Cursor 가 그랬다).
import { test } from "node:test";
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, mkdirSync, existsSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { adapterById } from "../src/core/ide/registry.js";

const REPO_ROOT = process.cwd();
const ISSUE_TITLE = "⚙️[Feature][Copilot] Support GitHub Copilot";
// 정규화 결과에 반드시 남는 본문 (태그 처리 규칙은 common/title.py 가 정한다)
const TITLE_BODY = "Support_GitHub_Copilot";

// 파이썬 실행 파일 (python3 > python). 없으면 null
function findPython() {
  for (const candidate of process.platform === "win32" ? ["python", "python3"] : ["python3", "python"]) {
    const probe = spawnSync(candidate, ["-c", "import sys; sys.exit(0)"], { encoding: "utf8" });
    if (probe.status === 0) return candidate;
  }
  return null;
}
const PYTHON = findPython();

// 임시 HOME 으로 실행 — 실제 홈의 ~/.projectops·~/.copilot 을 건드리지 않는다
function runPythonInHome(home, args) {
  const environment = { ...process.env, HOME: home, USERPROFILE: home, PROJECTOPS_HOME: join(home, ".projectops"), PYTHONIOENCODING: "utf-8" };
  // 다른 설치본을 가리키는 변수는 지운다 (임시 HOME 의 설치본만 보게)
  delete environment.PROJECTOPS_SKILLS_ROOT;
  delete environment.CLAUDE_CONFIG_DIR;
  const result = spawnSync(PYTHON, args, { cwd: home, env: environment, encoding: "utf8" });
  assert.equal(result.status, 0, `exit ${result.status}\nstdout: ${result.stdout}\nstderr: ${result.stderr}`);
  return JSON.parse(result.stdout);
}

// SKILL.md 의 "스크립트 찾기" 블록 그대로 (pro-commit) — 에이전트가 문서대로 실행했을 때 홈 설치본을 찾는지 본다
const POSIX_BASH = "/bin/bash";
function readCommitDiscoveryBlock() {
  const skillDoc = readFileSync(join(REPO_ROOT, "skills/pro-commit/SKILL.md"), "utf8");
  const block = skillDoc.split("```bash").map((part) => part.split("```")[0]).find((code) => code.includes("SKILL=pro-commit;"));
  assert.ok(block, "pro-commit SKILL.md 에서 스크립트 찾기 블록을 찾지 못했다");
  return block;
}

function runDiscoveryInHome(home) {
  const result = spawnSync(POSIX_BASH, ["-c", readCommitDiscoveryBlock()], {
    cwd: home, env: { PATH: process.env.PATH, HOME: home }, encoding: "utf8",
  });
  assert.equal(result.status, 0, `exit ${result.status}\nstdout: ${result.stdout}\nstderr: ${result.stderr}`);
  return /SCRIPTS=(\S+)/.exec(result.stdout)?.[1];
}

function quietIo(home) {
  const logs = [];
  return { logs, which: () => null, run: () => ({ code: 0, stdout: "", stderr: "" }), home: () => home, log: (m) => logs.push(m) };
}

// 설치 루트별 시나리오: Cursor(~/.cursor), Copilot(~/.copilot, JetBrains 플러그인으로 감지)
const SCENARIOS = [
  { adapterId: "cursor", installRoot: ".cursor", prepareHome: () => {} },
  {
    adapterId: "copilot", installRoot: ".copilot",
    // IntelliJ 에만 Copilot 이 있는 사람 (~/.copilot 없음) — macOS 플러그인 위치
    prepareHome: (home) => mkdirSync(join(home, "Library/Application Support/JetBrains/IntelliJIdea2025.2/plugins/github-copilot-intellij"), { recursive: true }),
  },
];

for (const { adapterId, installRoot, prepareHome } of SCENARIOS) {
  test(`${adapterId}: 설치본의 스킬 CLI 가 실제로 돈다 (scripts/common 동봉, 고정 진입점)`, { skip: PYTHON ? false : "python 없음" }, () => {
    const home = mkdtempSync(join(tmpdir(), `e2e-${adapterId}-`));
    try {
      prepareHome(home);
      const io = quietIo(home);
      // 설치 (실제 apply 경로, 소스 = 이 레포 skills/ + 옆 scripts/)
      assert.equal(adapterById(adapterId).apply(io, { sourceSkillsDir: join(REPO_ROOT, "skills"), templateVersion: "9.9.9" }), true, io.logs.join("\n"));
      const root = join(home, installRoot);
      assert.ok(existsSync(join(root, "skills/pro-commit/SKILL.md")));
      assert.ok(existsSync(join(root, "scripts/common/__init__.py")), "공용 파이썬이 설치되지 않았다");
      // 테스트 코드는 나가지 않는다 (스킬·공용 파이썬 둘 다)
      assert.equal(existsSync(join(root, "scripts/tests")), false);
      assert.equal(existsSync(join(root, "skills/pro-commit/tests")), false);
      assert.equal(existsSync(join(root, "skills/conftest.py")), false);

      // 설치본 CLI 직접 실행
      const direct = runPythonInHome(home, [join(root, "skills/pro-commit/scripts/commit_cli.py"), "normalize-title", ISSUE_TITLE]);
      assert.equal(direct.ok, true);
      assert.ok(String(direct.normalized).includes(TITLE_BODY), JSON.stringify(direct));
      // SKILL.md 가 먼저 부르는 고정 진입점 > 홈 설치본을 찾아 실행
      const entrypoint = join(home, ".projectops/bin/projectops_cli.py");
      assert.ok(existsSync(entrypoint), "고정 진입점이 설치되지 않았다");
      assert.ok(existsSync(join(home, ".projectops/bin/launch_cli.py")));
      const viaEntrypoint = runPythonInHome(home, [entrypoint, "commit", "normalize-title", ISSUE_TITLE]);
      assert.equal(viaEntrypoint.ok, true);
      assert.equal(viaEntrypoint.normalized, direct.normalized);

      // 고정 진입점이 아직 없는 상황에서도 SKILL.md 찾기 블록이 홈 설치본을 고른다 (bash 있는 OS 만)
      if (existsSync(POSIX_BASH)) {
        assert.equal(runDiscoveryInHome(home), join(root, "skills/pro-commit/scripts"));
      }

      // 제거: 스킬·공용 파이썬 모두 정리, 고정 진입점은 다른 설치본과 공유라 유지
      assert.equal(adapterById(adapterId).remove(io, { sourceSkillsDir: join(REPO_ROOT, "skills") }), true);
      assert.equal(existsSync(join(root, "skills")), false);
      assert.equal(existsSync(join(root, "scripts")), false);
      assert.ok(existsSync(entrypoint));
    } finally { rmSync(home, { recursive: true, force: true }); }
  });
}
