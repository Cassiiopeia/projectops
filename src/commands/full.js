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
import { verifyInstall } from "../core/verify.js";

// context: { version, types, paths:Map, branch, versionCode, deployTarget, publishTargets, includeSecretBackup,
//            force, repoName, resolvers, now, today }
// tempDir: 획득된 템플릿. targetRoot: 통합 대상.
export function runFull(context, tempDir, targetRoot = ".", hooks = {}) {
  const { version, types = [], paths = new Map(), branch = "main", versionCode = 1,
    force = true, now, today, templateVersion = "unknown",
    deployTarget = "docker-ssh", publishTargets = [], includeSecretBackup = false,
    changelogProvider = "github-ai", changelogBaseUrl = "", codeReviewCoderabbit = true,
    deployBranch = "", intent = null, semverAuto = true , appRelease = null } = context;

  // project_paths 마커 계산 (.sh existing_marker_in_dir 등가 — 대표 마커명)
  const pathMarkers = new Map();
  for (const [t] of paths) pathMarkers.set(t, markerForType(t));

  // 3. 워크플로우 복사 (+ env 치환) — deploy 블록에 쓸 ask 값을 수집한다.
  //    hooks.decisions: 대화형 충돌 3지선 결정 Map (미지정=skip — 현행 force 동작)
  const step = (name, fn, d) => (hooks.trace ? hooks.trace.step(name, fn, d) : fn());
  const wfCounters = step("copy-workflows", () => copyWorkflows(context, tempDir, targetRoot, hooks),
    { types, deploy: deployTarget, publish: publishTargets });
  const deployValues = wfCounters.deployValues || new Map(); // Map<type, Map<key,value>>

  // 1. version.yml 생성 (전체 재생성 — metadata → deploy → template 순, .sh 최종형과 동일)
  step("write-version-yml", () => writeText(join(targetRoot, PATHS.versionFile),
    buildVersionYml({
      version, types, paths, pathMarkers, branch, deployBranch, versionCode, now, today,
      deployValues,
      templateOptions: { templateVersion, deployTarget, publishTargets, includeSecretBackup, optionsDate: today,
        changelogProvider, changelogBaseUrl, codeReviewCoderabbit, intent, mode: "full", semverAuto, appRelease },
    })), { version, versionCode });

  // 2. README 버전 섹션
  step("update-readme", () => addVersionSectionToReadme(version, targetRoot), { version });

  // 5. scripts / config
  //    워크플로우 밖 영역도 기록한다 (#561) — 종전에는 "내 스크립트가 갱신됐나"를
  //    로그만 보고 알 수 없었다.
  step("copy-scripts", () => copyScripts(tempDir, targetRoot));
  step("copy-config", () => copyConfigFolder(tempDir, targetRoot));

  // 6. util (타입별)
  for (const t of types) step("copy-util", () => copyUtilModules(tempDir, t, { force }, targetRoot), { type: t });

  // 7. issue / discussion 템플릿
  step("copy-templates", () => {
    copyIssueTemplates(tempDir, targetRoot);
    copyDiscussionTemplates(tempDir, targetRoot);
  });

  // 8. coderabbit / gitignore / setup guide
  //    CodeRabbit 코드리뷰 미사용 선택(#457)이면 .coderabbit.yaml을 복사하지 않는다.
  step("copy-coderabbit", () => copyCoderabbit(tempDir, { force, enabled: codeReviewCoderabbit }, targetRoot),
    { enabled: codeReviewCoderabbit });
  step("ensure-gitignore", () => ensureGitignore(targetRoot));
  step("copy-setup-guide", () => copySetupGuide(tempDir, targetRoot));

  // 9. 설치 후 검증 (#549) — 디스크에 쓰인 최종 결과물을 다시 읽는다.
  //    치환은 파일 단위로 흩어져 일어나고 auto 토큰은 resolver 결과에 의존하므로,
  //    최종 내용을 보는 것이 실제 배포될 것과 같은 것을 보는 유일한 방법이다.
  const verification = step("verify-install", () => verifyInstall(targetRoot));
  // detail 키 이름 주의: run-trace의 민감값 가드가 pat|token|secret|password|credential을
  // 키에서 걸러낸다(#494). 여기서 다루는 값은 비밀이 아니라 "치환 플레이스홀더 이름"과
  // "등록이 필요한 키 이름"이라 가드에 걸리지 않는 이름을 쓴다 — 가드 자체는 우회하지 않는다.
  hooks.trace?.event("verify", "scan", "", {
    unresolved: verification.unresolved.length,
    requiredKeys: verification.secrets.size,
  });
  // 미치환 값은 배포 시점에 실패할 자리다 — 어느 파일 몇 번째 줄인지 로그에 남긴다.
  for (const u of verification.unresolved) {
    hooks.trace?.event("verify", "unresolved", u.filename, { line: u.line, placeholder: u.token });
  }
  for (const [name, users] of verification.secrets) {
    hooks.trace?.event("verify", "required-key", name, { workflows: users });
  }

  return { workflows: wfCounters, verification };
}
