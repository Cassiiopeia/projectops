import { test } from "node:test";
import assert from "node:assert/strict";
import { copyScripts, copyConfigFolder, copyIssueTemplates, copyDiscussionTemplates, copySetupGuide } from "../src/core/copy/simple.js";
import { ensureGitignore, normalizeGitignoreEntry } from "../src/core/copy/gitignore.js";
import { addVersionSectionToReadme } from "../src/core/copy/readme.js";
import { writeText, exists, readText } from "../src/core/fsutil.js";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

function fresh(prefix) { return mkdtempSync(join(tmpdir(), prefix)); }

test("copyScripts 2개 복사", () => {
  const tmp = fresh("cs-tmp-"); const tgt = fresh("cs-tgt-");
  try {
    writeText(join(tmp, ".github/scripts/version_manager.sh"), "#!/bin/bash\n");
    writeText(join(tmp, ".github/scripts/changelog_manager.py"), "print()\n");
    assert.equal(copyScripts(tmp, tgt), 2);
    assert.ok(exists(join(tgt, ".github/scripts/version_manager.sh")));
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyScripts changelog provider 사다리(.py) 복사 (#455)", () => {
  const tmp = fresh("cp-tmp-"); const tgt = fresh("cp-tgt-");
  try {
    // github_ai.py는 GitHub Models 종료로 복사 목록에서 빠지고 copilot.py가 들어왔다 (#566)
    const providers = ["_common.py", "ladder.py", "commit.py", "copilot.py", "openai_compatible.py"];
    for (const p of providers) writeText(join(tmp, ".github/scripts/changelog_providers", p), "# py\n");
    assert.equal(copyScripts(tmp, tgt), providers.length);
    for (const p of providers) assert.ok(exists(join(tgt, ".github/scripts/changelog_providers", p)), `누락: ${p}`);
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyIssueTemplates + PR", () => {
  const tmp = fresh("ci-tmp-"); const tgt = fresh("ci-tgt-");
  try {
    writeText(join(tmp, ".github/ISSUE_TEMPLATE/bug.md"), "bug\n");
    writeText(join(tmp, ".github/PULL_REQUEST_TEMPLATE.md"), "pr\n");
    copyIssueTemplates(tmp, tgt);
    assert.ok(exists(join(tgt, ".github/ISSUE_TEMPLATE/bug.md")));
    assert.ok(exists(join(tgt, ".github/PULL_REQUEST_TEMPLATE.md")));
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("copyDiscussion/setupGuide 없으면 스킵", () => {
  const tmp = fresh("cd-tmp-"); const tgt = fresh("cd-tgt-");
  try {
    assert.equal(copyDiscussionTemplates(tmp, tgt), false);
    assert.equal(copySetupGuide(tmp, tgt), false);
  } finally { rmSync(tmp, { recursive: true, force: true }); rmSync(tgt, { recursive: true, force: true }); }
});

test("normalizeGitignoreEntry: /.idea == .idea/ == ./.idea", () => {
  const n = normalizeGitignoreEntry("/.idea");
  assert.equal(normalizeGitignoreEntry(".idea/"), n);
  assert.equal(normalizeGitignoreEntry("./.idea"), n);
});

test("ensureGitignore 신규 생성", () => {
  const tgt = fresh("gi-new-");
  try {
    const r = ensureGitignore(tgt);
    assert.equal(r.created, true);
    const c = readText(join(tgt, ".gitignore"));
    assert.ok(c.includes("/.idea"));
    assert.ok(c.includes("/.claude/settings.local.json"));
  } finally { rmSync(tgt, { recursive: true, force: true }); }
});

test("ensureGitignore 기존에 이미 있으면 미변경", () => {
  const tgt = fresh("gi-dup-");
  try {
    writeText(join(tgt, ".gitignore"), ".idea\n.claude/settings.local.json\n");
    const r = ensureGitignore(tgt);
    assert.equal(r.added.length, 0);
  } finally { rmSync(tgt, { recursive: true, force: true }); }
});

test("addVersionSectionToReadme 마커 있으면 스킵", () => {
  const tgt = fresh("rm-mk-");
  try {
    writeText(join(tgt, "README.md"), "# X\n<!-- AUTO-VERSION-SECTION: DO NOT EDIT -->\n");
    assert.equal(addVersionSectionToReadme("1.0.0", tgt), "skip-marker");
  } finally { rmSync(tgt, { recursive: true, force: true }); }
});

test("addVersionSectionToReadme 없으면 append", () => {
  const tgt = fresh("rm-add-");
  try {
    writeText(join(tgt, "README.md"), "# My Project\n");
    assert.equal(addVersionSectionToReadme("1.2.3", tgt), "added");
    const c = readText(join(tgt, "README.md"));
    assert.ok(c.includes("## 최신 버전 : v1.2.3"));
  } finally { rmSync(tgt, { recursive: true, force: true }); }
});
