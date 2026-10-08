// 업데이트가 깔지 말아야 할 워크플로우를 다시 까는 문제 (#810).
//  ① 사용자가 지운 파일이 매번 되돌아옴  ② develop 이 없는 레포에 develop 전용 워크플로우 설치
//  ③ --force 에서 example.com 같은 예시값이 조용히 기록됨  ④ upstream 갱신 때 고른 env 값이 기본값으로 초기화됨
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, rmSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { execFileSync } from "node:child_process";
import { copyWorkflows, onlyTriggersOnDevelop } from "../src/core/copy/workflows.js";
import { substituteEnv } from "../src/core/wizard-env.js";
import { parseTemplateOptions } from "../src/core/version-yml.js";

const fresh = (p) => mkdtempSync(join(tmpdir(), p));
const DEV_ONLY = 'name: d\non:\n  push:\n    branches: [ develop ]\n  workflow_dispatch:\n';
const MAIN_ONLY = 'name: m\non:\n  push:\n    branches: ["main"]\n';

function template(files) {
  const tpl = fresh("sn-tpl-");
  const dir = join(tpl, ".github/workflows/project-types/common");
  mkdirSync(dir, { recursive: true });
  for (const [n, body] of Object.entries(files)) writeFileSync(join(dir, n), body);
  return tpl;
}
// 원격(origin)이 있는 git 레포. withDevelop 면 origin 에 develop 이 있다.
function repo({ withDevelop }) {
  const origin = fresh("sn-origin-"); execFileSync("git", ["init", "-q", "--bare", origin]);
  const r = fresh("sn-repo-");
  const g = (...a) => execFileSync("git", a, { cwd: r, stdio: "ignore" });
  g("init", "-q", "-b", "main"); g("config", "user.email", "t@t"); g("config", "user.name", "t");
  writeFileSync(join(r, "a"), "1"); g("add", "-A"); g("commit", "-qm", "i");
  g("remote", "add", "origin", origin); g("push", "-q", "origin", "main");
  if (withDevelop) g("push", "-q", "origin", "main:develop");
  return r;
}
const ctx = { types: [], deployTarget: "none", templateVersion: "1", now: "n" };

test("onlyTriggersOnDevelop: develop 전용만 true", () => {
  assert.equal(onlyTriggersOnDevelop(DEV_ONLY), true);
  assert.equal(onlyTriggersOnDevelop(MAIN_ONLY), false);
  // 다른 이벤트(issues)로도 돌 수 있으면 건너뛰면 안 된다
  assert.equal(onlyTriggersOnDevelop('on:\n  issues:\n    types: [opened]\n  push:\n    branches: [develop]\n'), false);
  // 필터 없는 push 는 모든 브랜치에서 돈다
  assert.equal(onlyTriggersOnDevelop('on:\n  push:\n  pull_request:\n    branches: [develop]\n'), false);
});

test("develop 이 원격에 없으면 develop 전용 워크플로우를 깔지 않고, 있으면 깐다", () => {
  const tpl = template({ "PROJECT-COMMON-D.yaml": DEV_ONLY, "PROJECT-COMMON-M.yaml": MAIN_ONLY });
  const noDev = repo({ withDevelop: false }), withDev = repo({ withDevelop: true });
  try {
    const a = copyWorkflows(ctx, tpl, noDev);
    assert.ok(!existsSync(join(noDev, ".github/workflows/PROJECT-COMMON-D.yaml")));
    assert.ok(existsSync(join(noDev, ".github/workflows/PROJECT-COMMON-M.yaml")));
    assert.deepEqual(a.notInstalled.map((x) => [x.filename, x.reason]), [["PROJECT-COMMON-D.yaml", "no-dev-branch"]]);
    copyWorkflows(ctx, tpl, withDev);
    assert.ok(existsSync(join(withDev, ".github/workflows/PROJECT-COMMON-D.yaml")));
  } finally { for (const d of [tpl, noDev, withDev]) rmSync(d, { recursive: true, force: true }); }
});

test("원격을 확인할 수 없으면(git 레포 아님) 건너뛰지 않는다 — 불확실하면 설치", () => {
  const tpl = template({ "PROJECT-COMMON-D.yaml": DEV_ONLY });
  const tgt = fresh("sn-nogit-");
  try {
    copyWorkflows(ctx, tpl, tgt);
    assert.ok(existsSync(join(tgt, ".github/workflows/PROJECT-COMMON-D.yaml")));
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("사용자가 지운 파일은 다시 깔리지 않고 incoming 에 사본이 남는다", () => {
  const tpl = template({ "PROJECT-COMMON-M.yaml": MAIN_ONLY });
  const tgt = repo({ withDevelop: true });
  try {
    copyWorkflows(ctx, tpl, tgt); // 최초 설치 — baseline 기록
    rmSync(join(tgt, ".github/workflows/PROJECT-COMMON-M.yaml"));
    const r = copyWorkflows(ctx, tpl, tgt);
    assert.ok(!existsSync(join(tgt, ".github/workflows/PROJECT-COMMON-M.yaml")));
    assert.equal(r.notInstalled[0].reason, "deleted-by-user");
    assert.ok(existsSync(join(tgt, r.notInstalled[0].incoming)));
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("options.excluded_workflows 에 적은 파일은 신규 설치에서도 깔지 않는다", () => {
  const tpl = template({ "PROJECT-COMMON-M.yaml": MAIN_ONLY });
  const tgt = repo({ withDevelop: true });
  try {
    const r = copyWorkflows({ ...ctx, excludedWorkflows: ["PROJECT-COMMON-M.yaml"] }, tpl, tgt);
    assert.ok(!existsSync(join(tgt, ".github/workflows/PROJECT-COMMON-M.yaml")));
    assert.equal(r.notInstalled[0].reason, "excluded");
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("excluded_workflows 파싱", () => {
  const o = parseTemplateOptions('metadata:\n  template:\n    options:\n      excluded_workflows: ["A.yaml", "B.yml"]\n');
  assert.deepEqual(o.excludedWorkflows, ["A.yaml", "B.yml"]);
});

test("--force(기본값 사용): example.com 같은 예시값은 채우지 않고 토큰을 남긴다", () => {
  const src = '  SERVICE_DOMAIN: "__SERVICE_DOMAIN__"  # @wizard ask:example.com\n  PORT: "__PORT__"  # @wizard ask:8080\n';
  const out = substituteEnv(src, { useDefaults: true });
  assert.match(out, /SERVICE_DOMAIN: "__SERVICE_DOMAIN__"/);
  assert.match(out, /PORT: "8080"/);
  // 사용자가 직접 고른 값은 당연히 쓴다
  const chosen = substituteEnv(src, { useDefaults: false, values: new Map([["SERVICE_DOMAIN", "api.real.dev"]]) });
  assert.match(chosen, /SERVICE_DOMAIN: "api.real.dev"/);
});

test("템플릿만 바뀐 파일을 갱신해도 사용자가 고른 env 값은 유지된다", () => {
  const tpl = fresh("sn-tpl-"), tgt = fresh("sn-tgt-");
  const dir = join(tpl, ".github/workflows/project-types/spring");
  mkdirSync(dir, { recursive: true }); mkdirSync(join(tpl, ".github/workflows/project-types/common"), { recursive: true });
  const body = (v) => `name: x ${v}\nenv:\n  JAVA_VERSION: "__JAVA_VERSION__"  # @wizard ask:21\n`;
  try {
    writeFileSync(join(dir, "PROJECT-SPRING-X.yaml"), body(1));
    const c = { types: ["spring"], deployTarget: "none", templateVersion: "1", now: "n" };
    copyWorkflows({ ...c, envValues: new Map([["JAVA_VERSION", "17"]]), envUseDefaults: false }, tpl, tgt);
    writeFileSync(join(dir, "PROJECT-SPRING-X.yaml"), body(2));
    copyWorkflows(c, tpl, tgt);
    const got = readFileSync(join(tgt, ".github/workflows/PROJECT-SPRING-X.yaml"), "utf8");
    assert.match(got, /name: x 2/);
    assert.match(got, /JAVA_VERSION: "17"/);
  } finally { rmSync(tpl, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});
