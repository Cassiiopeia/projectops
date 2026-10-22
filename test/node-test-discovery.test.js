// node --test 자동 탐색이 test/ 밖의 보조 스크립트를 테스트로 실행하지 않는지 확인
// 실사고: .github/scripts/test/helpers/*.cjs 가 탐색돼 stdin 을 기다리다 CI 가 20분 넘게 멈춤
import { test } from "node:test";
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

// Node 20 기본 탐색 패턴과 같은 기준 (test 폴더 하위, *.test / *-test / *_test / test-* / test.js)
const DISCOVERED_RE = /(^|\/)test\/.*\.[cm]?js$|\.test\.[cm]?js$|-test\.[cm]?js$|_test\.[cm]?js$|(^|\/)test-[^/]*\.[cm]?js$|(^|\/)test\.[cm]?js$/;

// 루트 test/ 밖에서 탐색되는 파일 > 왜 괜찮은지
const ALLOWED_OUTSIDE_ROOT_TEST = {
  // 사용자 레포에 설치되는 규칙 테스트 템플릿 (그 자체가 정상 테스트)
  "plugins/projectops-extras/skills/pro-code-consult/templates/rule-tests/javascript/architecture.rules.test.mjs": null,
  // pytest 가 띄우는 보조 실행기 — NODE_TEST_CONTEXT 가드로 즉시 종료해야 함
  ".github/scripts/test/helpers/github_script_runner.cjs": "NODE_TEST_CONTEXT",
};

test("node --test 가 루트 test/ 밖에서 집는 파일은 허용 목록에만 있다", () => {
  const files = execFileSync("git", ["ls-files"], { encoding: "utf8" }).split("\n").filter(Boolean);
  const discovered = files.filter((f) => DISCOVERED_RE.test(f) && !f.startsWith("test/") && !f.startsWith("node_modules/"));
  for (const file of discovered) {
    assert.ok(file in ALLOWED_OUTSIDE_ROOT_TEST, `${file} is picked up by node --test; move it out of a test/ folder or add it here with a guard`);
    const guard = ALLOWED_OUTSIDE_ROOT_TEST[file];
    if (guard) assert.ok(readFileSync(file, "utf8").includes(guard), `${file} must exit early when ${guard} is set`);
  }
});
