// CLI 플래그가 --help 와 문서 두 곳에 모두 적혀 있는지 (#832).
// `--help`·docs/CLI.md·docs/en/cli.md 가 args.js 와 따로 놀아 --language·--label-style·--projects-sync 가
// 문서에서 빠져 있었다. 새 플래그를 args.js 에만 넣으면 여기서 실패한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (p) => readFileSync(new URL(`../${p}`, import.meta.url), "utf8");
// 더 이상 쓰지 않는 플래그는 --help 에 한 줄로 묶어 안내하고 문서에는 "deprecated" 한 줄만 둔다
const DEPRECATED = new Set(["--nexus", "--no-nexus", "--npm-publish", "--no-npm-publish"]);
const flags = [...read("src/cli/args.js").matchAll(/case "(--[a-z-]+)"/g)].map((m) => m[1]).filter((f) => !DEPRECATED.has(f));

test("args.js 의 플래그를 찾았다 (검사가 헛돌지 않게)", () => {
  assert.ok(flags.length >= 15, `플래그 ${flags.length}개`);
});

for (const [name, path] of [["--help (src/cli/help.js)", "src/cli/help.js"], ["docs/CLI.md", "docs/CLI.md"], ["docs/en/cli.md", "docs/en/cli.md"]]) {
  test(`${name} 가 모든 플래그를 언급한다`, () => {
    const text = read(path);
    const missing = flags.filter((f) => !text.includes(f));
    assert.deepEqual(missing, [], `${path} 에 없는 플래그: ${missing.join(", ")} — 새 플래그는 help·docs/CLI.md·docs/en/cli.md 에 같이 적는다`);
  });
}

test("한국어·영어 --help 가 같은 플래그를 다룬다", () => {
  const text = read("src/cli/help.js");
  const [en, ko] = [text.slice(text.indexOf("HELP_EN"), text.indexOf("HELP_KO")), text.slice(text.indexOf("HELP_KO"))];
  for (const f of flags) {
    assert.ok(en.includes(f), `영문 --help 에 ${f} 없음`);
    assert.ok(ko.includes(f), `한국어 --help 에 ${f} 없음`);
  }
});
