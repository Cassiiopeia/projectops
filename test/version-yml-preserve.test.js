// full·version 업데이트가 version.yml 을 처음부터 다시 쓰면서 생성기가 모르는 키를 지우던 문제 (#835).
// 문서화된 options.issue_helper(브랜치 접두사·커밋 템플릿·시간대)가 업데이트마다 조용히 초기화됐다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { extractCustomYml, buildVersionYml, customYml, parseTemplateOptions } from "../src/core/version-yml.js";

const base = { version: "1.0.0", types: ["node"], now: "2026-10-10 00:00:00", today: "2026-10-10" };
const OPTS = { templateVersion: "4.40.0", language: "ko", deployTarget: "none", publishTargets: [] };

const SAMPLE = `version: "1.0.0"
version_code: 1
project_types: ["node"]
metadata:
  last_updated: "2026-01-01 00:00:00"
  template:
    version: "4.0.0"
    options:
      deploy: "none"
      publish: []
      nexus: true
      semver_auto: true
      issue_helper:
        # 브랜치 접두사
        branch_prefix: "feat"
        commit_type_map:
          bug: "fix"
        timezone: "Asia/Seoul"
      my_custom_key: "keep-me"
extra_top_level:
  nested: 1
`;

function regenerate(text) {
  const dir = mkdtempSync(join(tmpdir(), "vyp-"));
  const f = join(dir, "version.yml");
  writeFileSync(f, text);
  try {
    return buildVersionYml({ ...base, templateOptions: OPTS, ...customYml(f) });
  } finally { rmSync(dir, { recursive: true, force: true }); }
}

test("생성기가 모르는 옵션 블록과 최상위 키를 찾아낸다", () => {
  const { optionBlocks, topBlocks } = extractCustomYml(SAMPLE);
  assert.equal(optionBlocks.length, 2);
  assert.match(optionBlocks[0], /issue_helper:[\s\S]*timezone: "Asia\/Seoul"/);
  assert.match(optionBlocks[0], /# 브랜치 접두사/, "블록 안의 주석도 함께");
  assert.equal(optionBlocks[1], '      my_custom_key: "keep-me"');
  assert.deepEqual(topBlocks, ["extra_top_level:\n  nested: 1"]);
});

test("다시 쓴 version.yml 에 issue_helper 와 사용자 키가 그대로 남는다", () => {
  const out = regenerate(SAMPLE);
  assert.match(out, /issue_helper:\n {8}# 브랜치 접두사\n {8}branch_prefix: "feat"\n {8}commit_type_map:\n {10}bug: "fix"\n {8}timezone: "Asia\/Seoul"/);
  assert.match(out, /my_custom_key: "keep-me"/);
  assert.match(out, /^extra_top_level:\n {2}nested: 1$/m);
});

test("두 번째 실행에도 중복되지 않는다 (멱등)", () => {
  const once = regenerate(SAMPLE);
  const twice = regenerate(once);
  const thrice = regenerate(twice);
  for (const k of ["issue_helper:", "my_custom_key", "extra_top_level"]) {
    assert.equal(thrice.split(k).length - 1, 1, `${k} 가 중복됐다`);
  }
  // 날짜 같은 생성값을 빼면 두 번째부터는 바이트가 같다
  assert.equal(twice, thrice);
});

test("옛 키(nexus · npm_publish · synology · project_type)는 보존하지 않는다 — 신형으로 바뀌어 이중 기록이 된다", () => {
  const out = regenerate(SAMPLE.replace("project_types:", 'project_type: "node"\nproject_types:'));
  assert.doesNotMatch(out, /^\s+nexus:/m);
  assert.doesNotMatch(out, /^project_type:/m);
  const legacy = extractCustomYml(SAMPLE.replace("my_custom_key", "npm_publish").replace('"keep-me"', "true"));
  assert.ok(!legacy.optionBlocks.some((b) => b.includes("npm_publish")));
});

test("생성기가 쓰는 키(store_locales · excluded_workflows 등)는 보존 대상이 아니다 — 두 번 쓰이면 안 된다", () => {
  const withOwned = SAMPLE.replace('      deploy: "none"', '      deploy: "none"\n      excluded_workflows: ["A.yaml"]\n      store_locales: ["ko-KR"]');
  const { optionBlocks } = extractCustomYml(withOwned);
  assert.ok(!optionBlocks.join("\n").includes("excluded_workflows"));
  assert.ok(!optionBlocks.join("\n").includes("store_locales"));
});

test("보존한 결과도 파서가 그대로 읽는다", () => {
  const o = parseTemplateOptions(regenerate(SAMPLE));
  assert.equal(o.deploy, "none");
  assert.equal(o.semverAuto, true);
});

test("CRLF 파일도 보존하고 파일이 없어도 업데이트를 막지 않는다", () => {
  assert.match(regenerate(SAMPLE.replace(/\n/g, "\r\n")), /issue_helper:/);
  assert.deepEqual(customYml(join(tmpdir(), "no-such-dir", "version.yml")), {});
  assert.deepEqual(extractCustomYml(""), { optionBlocks: [], topBlocks: [] });
});

test("깨진 덩어리는 되돌려 쓰지 않는다 — 쓰면 version.yml 전체가 깨져 모든 워크플로가 버전을 못 읽는다", () => {
  for (const bad of ["not: [valid", 'broken: "unclosed', "x: {a: 1", "y: [1, 2}"]) {
    assert.deepEqual(extractCustomYml(bad).topBlocks, [], `${bad} 를 보존했다`);
  }
  const out = regenerate(SAMPLE.replace("my_custom_key: \"keep-me\"", "my_custom_key: [unclosed"));
  assert.doesNotMatch(out, /unclosed/);
  assert.match(out, /issue_helper:/, "멀쩡한 블록은 그대로 남는다");
  // 따옴표 안의 괄호와 줄 끝 주석의 괄호는 깨진 것이 아니다
  assert.equal(extractCustomYml('tpl: "{x} [y"  # (note').topBlocks.length, 1);
});

test("생성기가 아는 것만 있는 version.yml 은 아무것도 보존하지 않아 출력이 바뀌지 않는다 (기존 프로젝트 무영향)", () => {
  const plain = buildVersionYml({ ...base, templateOptions: OPTS });
  const again = regenerate(plain);
  assert.equal(again, plain);
  assert.deepEqual(extractCustomYml(plain), { optionBlocks: [], topBlocks: [] });
});

test("full 모드 실행에서도 지켜진다 (command 연결)", () => {
  for (const f of ["src/commands/full.js", "src/commands/version.js"]) {
    assert.match(readFileSync(new URL(`../${f}`, import.meta.url), "utf8"), /\.\.\.customYml\(vyFile\)/, `${f} 가 customYml 을 펼치지 않는다`);
  }
});
