// 단순 복사 함수 (무조건 덮어쓰기류) — .sh copy_scripts/config/issue/discussion/setup_guide 등가.
// 실측: template_integrator.sh 3818, 3845, 3872, 3895, 4114.
import { join } from "node:path";
import { chmodSync } from "node:fs";
import { PATHS } from "../paths.js";
import { exists, copyFileSync, copyDirSync } from "../fsutil.js";

// 버전관리/릴리스노트 스크립트만 무조건 덮어쓰기 + chmod +x.
// version_manager는 .sh(위임 shim) + .py(실 로직) 한 쌍 — 둘 다 복사해야 동작 (#448).
// changelog provider 사다리(.py 5종, #455)는 RELEASE-CHANGELOG 워크플로우 fallback-summary가
// 호출하므로 함께 복사해야 사용자 프로젝트에서 릴리스 노트 생성이 동작한다.
// issue_helper.py는 SUH-ISSUE-HELPER 워크플로우가 호출 — 함께 복사 필수 (#478).
export function copyScripts(tempDir, targetRoot = ".") {
  const scripts = [
    "version_manager.sh", "version_manager.py",
    "changelog_manager.py",
    "truncate_release_notes.sh", "truncate_release_notes.py",
    "issue_helper.py",
    // 릴리스 워크플로우가 PAT 없이 머지한 뒤 후속 워크플로우를 깨울 때 호출 (#551).
    "dispatch_downstream.py",
    // AI PR SUMMARY 워크플로우가 요약 댓글을 작성·갱신할 때 호출 (#553).
    "pr_summary_comment.py",
    // 릴리스 노트가 어떤 경로로 만들어졌는지 알리고, AI를 못 썼을 때 대안을 안내 (#566).
    "changelog_notice.py",
    // Flutter 빌드 워크플로우가 .env와 dart-define을 한 곳에서 정할 때 호출 (#603).
    // 설정(.github/config/build-profile.json)이 없는 저장소에서는 아무 일도 하지 않는다.
    "apply_build_profile.py",
    "changelog_providers/_common.py", "changelog_providers/ladder.py",
    "changelog_providers/commit.py", "changelog_providers/copilot.py",
    "changelog_providers/openai_compatible.py",
  ];
  let copied = 0;
  for (const s of scripts) {
    const src = join(tempDir, PATHS.scriptsDir, s);
    if (exists(src)) {
      const dst = join(targetRoot, PATHS.scriptsDir, s);
      copyFileSync(src, dst);
      try { chmodSync(dst, 0o755); } catch { /* Windows 등 chmod 무의미 */ }
      copied++;
    }
  }
  return copied;
}

// .github/config 폴더 전체 덮어쓰기. 없으면 스킵.
export function copyConfigFolder(tempDir, targetRoot = ".") {
  const src = join(tempDir, ".github", "config");
  if (!exists(src)) return false;
  copyDirSync(src, join(targetRoot, ".github", "config"));
  return true;
}

// .github/ISSUE_TEMPLATE/ 전체 + PULL_REQUEST_TEMPLATE.md 덮어쓰기.
export function copyIssueTemplates(tempDir, targetRoot = ".") {
  const srcIssue = join(tempDir, ".github", "ISSUE_TEMPLATE");
  if (exists(srcIssue)) copyDirSync(srcIssue, join(targetRoot, ".github", "ISSUE_TEMPLATE"));
  const srcPr = join(tempDir, ".github", "PULL_REQUEST_TEMPLATE.md");
  if (exists(srcPr)) copyFileSync(srcPr, join(targetRoot, ".github", "PULL_REQUEST_TEMPLATE.md"));
}

// .github/DISCUSSION_TEMPLATE/ 전체. 없으면 스킵.
export function copyDiscussionTemplates(tempDir, targetRoot = ".") {
  const src = join(tempDir, ".github", "DISCUSSION_TEMPLATE");
  if (!exists(src)) return false;
  copyDirSync(src, join(targetRoot, ".github", "DISCUSSION_TEMPLATE"));
  return true;
}

// PROJECTOPS-SETUP-GUIDE.md 루트로 덮어쓰기. 없으면 스킵.
export const SETUP_GUIDE_NAME = "PROJECTOPS-SETUP-GUIDE.md";
export function copySetupGuide(tempDir, targetRoot = ".") {
  const src = join(tempDir, SETUP_GUIDE_NAME);
  if (!exists(src)) return false;
  copyFileSync(src, join(targetRoot, SETUP_GUIDE_NAME));
  return true;
}
