// full 모드 오케스트레이터 (.sh execute_integration full case 등가) — template_integrator.sh 4502~4514.
// 복사 순서: version.yml → readme → workflows → (deploy블록) → scripts → config →
//            util(타입별) → issue → discussion → coderabbit → gitignore → setup_guide → (옵션저장)
import { join } from "node:path";
import { writeText } from "../core/fsutil.js";
import { PATHS } from "../core/paths.js";
import { buildVersionYml } from "../core/version-yml.js";
import { markerForType } from "../core/detect.js";
import { addVersionSectionToReadme } from "../core/copy/readme.js";
import { copyWorkflows } from "../core/copy/workflows.js";
import {
  copyScripts, copyConfigFolder, copyIssueTemplates,
  copyDiscussionTemplates, copySetupGuide,
} from "../core/copy/simple.js";
import { copyUtilModules } from "../core/copy/util.js";
import { copyCoderabbit } from "../core/copy/coderabbit.js";
import { ensureGitignore } from "../core/copy/gitignore.js";

// context: { version, types, paths:Map, branch, versionCode, deployTarget, publishTargets, includeSecretBackup,
//            force, repoName, resolvers, now, today }
// tempDir: 획득된 템플릿. targetRoot: 통합 대상.
export function runFull(context, tempDir, targetRoot = ".", hooks = {}) {
  const { version, types = [], paths = new Map(), branch = "main", versionCode = 1,
    force = true, now, today, templateVersion = "unknown",
    deployTarget = "docker-ssh", publishTargets = [], includeSecretBackup = false,
    changelogProvider = "github-ai", changelogBaseUrl = "", codeReviewCoderabbit = true,
    deployBranch = "", intent = null, semverAuto = true } = context;

  // project_paths 마커 계산 (.sh existing_marker_in_dir 등가 — 대표 마커명)
  const pathMarkers = new Map();
  for (const [t] of paths) pathMarkers.set(t, markerForType(t));

  // 3. 워크플로우 복사 (+ env 치환) — deploy 블록에 쓸 ask 값을 수집한다.
  //    hooks.decisions: 대화형 충돌 3지선 결정 Map (미지정=skip — 현행 force 동작)
  const wfCounters = copyWorkflows(context, tempDir, targetRoot, hooks);
  const deployValues = wfCounters.deployValues || new Map(); // Map<type, Map<key,value>>

  // 1. version.yml 생성 (전체 재생성 — metadata → deploy → template 순, .sh 최종형과 동일)
  writeText(join(targetRoot, PATHS.versionFile),
    buildVersionYml({
      version, types, paths, pathMarkers, branch, deployBranch, versionCode, now, today,
      deployValues,
      templateOptions: { templateVersion, deployTarget, publishTargets, includeSecretBackup, optionsDate: today,
        changelogProvider, changelogBaseUrl, codeReviewCoderabbit, intent, mode: "full", semverAuto },
    }));

  // 2. README 버전 섹션
  addVersionSectionToReadme(version, targetRoot);

  // 5. scripts / config
  copyScripts(tempDir, targetRoot);
  copyConfigFolder(tempDir, targetRoot);

  // 6. util (타입별)
  for (const t of types) copyUtilModules(tempDir, t, { force }, targetRoot);

  // 7. issue / discussion 템플릿
  copyIssueTemplates(tempDir, targetRoot);
  copyDiscussionTemplates(tempDir, targetRoot);

  // 8. coderabbit / gitignore / setup guide
  //    CodeRabbit 코드리뷰 미사용 선택(#457)이면 .coderabbit.yaml을 복사하지 않는다.
  copyCoderabbit(tempDir, { force, enabled: codeReviewCoderabbit }, targetRoot);
  ensureGitignore(targetRoot);
  copySetupGuide(tempDir, targetRoot);

  return { workflows: wfCounters };
}
