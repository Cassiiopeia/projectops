// 단순 복사 함수 (무조건 덮어쓰기류) — .sh copy_scripts/config/issue/discussion/setup_guide 등가.
// 실측: template_integrator.sh 3818, 3845, 3872, 3895, 4114.
import { join } from "node:path";
import { chmodSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
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
    // iOS/Android 테스트 빌드와 iOS 릴리스의 빌드 번호 규칙 (#643). 번호 규칙의 유일한 위치.
    "build_number.py",
    // App Store Connect 조회 (#643). ios_release.py가 사용하므로 함께 복사해야 한다.
    "asc_client.py",
    // iOS 버전 사전 점검, 업로드 거부 분류, 아카이브부터 업로드까지 재시도 (#643).
    "ios_release.py",
    // 릴리스 머지 때 완료 라벨이 붙은 이슈를 닫는다 (#771). close_on_release 옵션이 켜진 레포에서만 동작한다.
    "close_issues_on_release.py",
    // Play Store/TestFlight 배포 모드를 코드 설정(.github/config/store-deploy.json)에서 읽는다 (#767).
    "store_deploy_config.py",
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

// 사용자 레포로 복사된 이슈 템플릿에서 담당자(assignees) 줄을 지운다 (#782).
// 원본에는 이 저장소 소유자가 박혀 있는데, 남의 레포에서 새 이슈를 만들 때 그 사람이 담당자로
// 지정되면 안 된다. 담당자는 이슈 헬퍼와 QA 봇이 version.yml 설정으로 정한다.
// frontmatter(첫 --- 와 둘째 --- 사이)의 줄만 대상이다 — 본문에 같은 문구가 있어도 건드리지 않는다.
// 반환: 바뀐 파일의 레포 루트 기준 상대경로. 오버레이 적용 뒤에 불러야 한다(오버레이가 다시 넣는다).
export function stripIssueTemplateAssignees(targetRoot = ".") {
  const dir = join(targetRoot, ".github", "ISSUE_TEMPLATE");
  if (!exists(dir)) return [];
  const changed = [];
  for (const name of readdirSync(dir).filter((f) => f.endsWith(".md"))) {
    const file = join(dir, name);
    const text = readFileSync(file, "utf8");
    const m = text.match(/^(---\r?\n)([\s\S]*?)(\r?\n---)/);
    if (!m) continue;
    const front = m[2].split(/\r?\n/).filter((l) => !/^assignees:/.test(l)).join("\n");
    if (front === m[2]) continue;
    writeFileSync(file, text.replace(m[0], `${m[1]}${front}${m[3]}`));
    changed.push(`.github/ISSUE_TEMPLATE/${name}`);
  }
  return changed;
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
