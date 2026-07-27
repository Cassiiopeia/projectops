// #459 네임스페이스 중립화 정합성 회귀 테스트.
// suh-* 스킬명·cassiiopeia 플러그인명 잔재를 막고, 외부 실체(보존 대상)는 살아있는지 지킨다.
//
// OS 독립: git grep 대신 `git ls-files`(추적 파일 목록)만 셸로 얻고, 내용 검사는 Node fs로 한다.
// (git grep의 pathspec magic·`:` 특수문자·셸 인용이 Windows CI에서 다르게 동작해 오탐하던 문제 수정.)
import { test } from "node:test";
import assert from "node:assert/strict";
import { execSync } from "node:child_process";
import { readdirSync, statSync, existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

const ROOT = process.cwd();

// 추적 파일 목록 (node_modules·.git 자동 제외). 경로 구분자는 git이 항상 '/'로 준다(Windows 포함).
const TRACKED = execSync("git ls-files", { cwd: ROOT, encoding: "utf-8" })
  .split("\n").map((s) => s.trim()).filter(Boolean);

// 히스토리(과거 산출물·스펙)·CHANGELOG·breaking-changes(구→신 설명)는 잔재 검사에서 제외한다.
// 이 테스트 파일 자신도 검색어 문자열(cassiiopeia:suh- 등)을 리터럴로 포함하므로 제외한다.
const EXCLUDE_PREFIX = ["docs/superpowers/", "docs/projectops/"];
const EXCLUDE_EXACT = [
  "CHANGELOG.md", "CHANGELOG.json", ".github/config/breaking-changes.json",
  "test/rename-consistency.test.js",
  // 레거시 자동 마이그레이션 로직 — 구 플러그인/config 이름(cassiiopeia)을 감지·정리하려면
  // 그 문자열을 반드시 리터럴로 참조해야 한다(#459 방침: 감지·마이그레이션 로직은 구 이름 보존).
  "src/core/ide/legacy.js",
  "src/core/ide/adapters/claude.js",
  "src/core/ide/adapters/cursor.js",
];

function isExcluded(path) {
  if (EXCLUDE_EXACT.includes(path)) return true;
  return EXCLUDE_PREFIX.some((p) => path.startsWith(p));
}

// path가 주어진 매처(확장자/접두 경로) 중 하나에 해당하는지.
function matchScope(path, scopes) {
  return scopes.some((s) => {
    if (s.startsWith("ext:")) return path.endsWith(s.slice(4));
    if (s.endsWith("/")) return path.startsWith(s);   // 디렉토리 접두
    return path === s;                                 // 정확 파일
  });
}

// scopes 범위의 추적 파일에서 substring을 포함한 파일 경로 목록을 반환 (제외 목록 적용).
function findFiles(substring, scopes) {
  const hits = [];
  for (const path of TRACKED) {
    if (isExcluded(path)) continue;
    if (!matchScope(path, scopes)) continue;
    let content;
    try { content = readFileSync(join(ROOT, path), "utf-8"); }
    catch { continue; } // 바이너리·읽기 실패는 건너뜀
    if (content.includes(substring)) hits.push(path);
  }
  return hits;
}

const DOC_CODE = ["ext:.md", "ext:.js", "ext:.py"]; // 활성 문서·코드

test("skills/ 아래 suh- 폴더가 0개다", () => {
  const dirs = readdirSync(join(ROOT, "skills"))
    .filter((d) => statSync(join(ROOT, "skills", d)).isDirectory() && d.startsWith("suh-"));
  assert.deepEqual(dirs, [], `잔존 suh- 스킬 폴더: ${dirs.join(", ")}`);
});

test("17개 pro- 스킬 폴더가 모두 존재한다", () => {
  // pro-issue는 #467에서 pro-github로 통합·삭제됨 (25종→24종)
  // design·design-analyze·refactor·refactor-analyze·test·ppt·document 7종은 superpowers 및
  // pro-report와 역할이 겹쳐 삭제됨 (24종→17종)
  const expected = [
    "pro-analyze", "pro-build", "pro-changelog-deploy", "pro-commit",
    "pro-figma", "pro-github", "pro-implement", "pro-init-worktree", "pro-plan",
    "pro-report", "pro-review", "pro-skill-creator",
    "pro-spring-test", "pro-ssh", "pro-synology-expose", "pro-testcase", "pro-troubleshoot",
  ];
  for (const s of expected) {
    assert.ok(existsSync(join(ROOT, "skills", s, "SKILL.md")), `누락: skills/${s}/SKILL.md`);
  }
});

test("활성 문서/코드에 cassiiopeia:suh- 커맨드 표기 잔재가 없다", () => {
  const hits = findFiles("cassiiopeia:suh-", DOC_CODE);
  assert.deepEqual(hits, [], `cassiiopeia:suh- 잔재:\n${hits.join("\n")}`);
});

test("소문자 플러그인명 cassiiopeia 잔재가 없다(대문자 조직명은 허용)", () => {
  // 매니페스트·IDE 어댑터·활성 문서 대상. 대문자 Cassiiopeia(조직명)는 대소문자 구분으로 통과.
  const hits = findFiles("cassiiopeia", [
    ".claude-plugin/", ".codex-plugin/", ".agents/", ".cursor/",
    "gemini-extension.json", "src/", "ext:.md",
  ]);
  assert.deepEqual(hits, [], `소문자 cassiiopeia 잔재:\n${hits.join("\n")}`);
});

test("@suh-lab 트리거 잔재가 없다(외부 봇 서명 Guide by SUH-LAB은 별개)", () => {
  const hits = findFiles("@suh-lab", ["ext:.md", ".github/"]);
  assert.deepEqual(hits, [], `@suh-lab 잔재:\n${hits.join("\n")}`);
});

// ── 보존 대상(치환 금지)이 살아있는지 — 과잉 치환 회귀 방지 ──

test("보존: suh-logger Maven 의존성이 pro-spring-test SKILL에 남아있다", () => {
  const hits = findFiles("me.suhsaechan:suh-logger", ["skills/pro-spring-test/"]);
  assert.ok(hits.length > 0, "me.suhsaechan:suh-logger가 사라짐(과잉 치환)");
});

test("보존: 외부 봇 서명 'Guide by SUH-LAB' 매칭이 살아있다", () => {
  const hits = findFiles("Guide by SUH-LAB", [".github/"]);
  assert.ok(hits.length > 0, "'Guide by SUH-LAB' 서명 매칭이 사라짐(빌드 트리거 파손)");
});
