// version 모드 (.sh execute_integration version case 등가) — template_integrator.sh 4517~4530.
// 순서: version.yml → readme → scripts → config → gitignore → setup_guide.
// (워크플로우 미복사 → deploy 블록 없음. util·issue·coderabbit도 없음.)
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { writeText } from "../core/fsutil.js";
import { PATHS } from "../core/paths.js";
import { installAgentGuide } from "../core/agent-guide.js";
import { buildVersionYml, mergeDeployValues, resolveUpdatedBy, customYml } from "../core/version-yml.js";
import { markerForType } from "../core/detect.js";
import { addVersionSectionToReadme } from "../core/copy/readme.js";
import { applyLabelStyle } from "../core/label-style.js";
import { copyScripts, copyConfigFolder, copySetupGuide } from "../core/copy/simple.js";
import { ensureGitignore } from "../core/copy/gitignore.js";
import { toTemplateOptions } from "../core/resolve-options.js";

export function runVersion(context, tempDir, targetRoot = ".") {
  // 옵션 값은 resolveOptions 가 정해 context 에 넣는다 — 여기서 기본값을 다시 고르지 않는다
  const { version, types = [], paths = new Map(), branch = "main", versionCode = 1,
    now, today, templateVersion, deployBranch = "", recordMode = "version", labelStyle } = context;

  const pathMarkers = new Map();
  for (const [t] of paths) pathMarkers.set(t, markerForType(t));

  // version.yml 은 전체 재생성이라, 읽지 않으면 이전 통합이 남긴 deploy 값(사용자 수정 포함)이 사라진다 (#670)
  const vyFile = join(targetRoot, PATHS.versionFile);
  const deployValues = mergeDeployValues(existsSync(vyFile) ? readFileSync(vyFile, "utf8") : "", new Map());

  writeText(vyFile,
    buildVersionYml({
      version, types, paths, pathMarkers, branch, deployBranch, versionCode, now, today,
      deployValues,
      // 생성기가 모르는 키(issue_helper 등)를 지킨다 — version.yml 을 매번 다시 쓰므로 안 그러면 업데이트마다 사라진다 (#835)
      ...customYml(vyFile),
      updatedBy: resolveUpdatedBy(existsSync(vyFile) ? readFileSync(vyFile, "utf8") : "", targetRoot), // #811
      // mode(#502): version 모드가 기존 full 통합 기록을 "version"으로 강등하지 않도록
      // 호출부가 recordMode로 기존 값을 넘긴다 (full이 우세 — 업데이트 재실행 범위 축소 방지).
      templateOptions: toTemplateOptions(context, { mode: recordMode, optionsDate: today }),
    }));
  addVersionSectionToReadme(version, targetRoot);
  copyScripts(tempDir, targetRoot);
  copyConfigFolder(tempDir, targetRoot);
  applyLabelStyle(targetRoot, labelStyle); // #776
  ensureGitignore(targetRoot);
  copySetupGuide(tempDir, targetRoot);
  installAgentGuide(targetRoot, templateVersion);
}
