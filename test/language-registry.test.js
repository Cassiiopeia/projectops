// 지원 언어 목록과 파일 구조가 어긋나지 않는다 (#787). 새 언어를 추가하는 사람은
// 파일(.github/scripts/i18n/<lang>.json, .github/i18n/<lang>/)과 REPO_LANGUAGES 한 줄을 함께 넣어야 한다.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { REPO_LANGUAGES } from "../src/core/repo-language.js";
import { LANGUAGE_VALUES } from "../src/cli/args.js";

const ROOT = join(import.meta.dirname, "..");
const jsonLangs = readdirSync(join(ROOT, ".github/scripts/i18n")).filter((f) => f.endsWith(".json")).map((f) => f.replace(/\.json$/, "")).sort();
const overlayLangs = readdirSync(join(ROOT, ".github/i18n")).filter((f) => statSync(join(ROOT, ".github/i18n", f)).isDirectory()).sort();

test("REPO_LANGUAGES 와 메시지 카탈로그 파일이 같다", () => {
  assert.deepEqual([...REPO_LANGUAGES].sort(), jsonLangs);
});

test("영문을 뺀 모든 지원 언어에 이슈/PR 템플릿 오버레이가 있다", () => {
  assert.deepEqual(REPO_LANGUAGES.filter((l) => l !== "en").sort(), overlayLangs);
});

test("--language 가 받는 값은 REPO_LANGUAGES 와 같은 목록이다 (목록이 두 벌이 아니다)", () => {
  assert.deepEqual(LANGUAGE_VALUES, REPO_LANGUAGES);
});

test("영문이 정본이다: 목록의 첫 항목이고 카탈로그가 있다", () => {
  assert.equal(REPO_LANGUAGES[0], "en");
  assert.ok(jsonLangs.includes("en"));
});
