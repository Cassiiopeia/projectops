// workflows 모드 (.sh execute_integration workflows case 등가) — template_integrator.sh 4523~4531.
// 순서: copy_workflows → update_version_yml_deploy(version.yml 있을 때만) → scripts → config → util(타입별) → setup_guide.
// (version.yml 생성 안 함 — 기존 version.yml이 있을 때만 deploy 블록 추가.)
import { join } from "node:path";
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { PATHS } from "../core/paths.js";
import { copyWorkflows } from "../core/copy/workflows.js";
import { copyScripts, copyConfigFolder, copySetupGuide } from "../core/copy/simple.js";
import { copyUtilModules } from "../core/copy/util.js";
import { convertLegacySingularType } from "../core/version-yml.js";
import { verifyInstall } from "../core/verify.js";

export function runWorkflows(context, tempDir, targetRoot = ".", hooks = {}) {
  const { types = [], force = true } = context;
  const wf = copyWorkflows(context, tempDir, targetRoot, hooks);

  const vy = join(targetRoot, PATHS.versionFile);

  // v4.1.0 이전 단수 project_type 최소 변환 (#471) — 여기서 복사되는 신형 version_manager가
  // 단수 키를 거부하므로, 변환 없이 두면 버전 워크플로우가 전부 실패하는 깨진 상태가 된다.
  if (existsSync(vy)) {
    const converted = convertLegacySingularType(readFileSync(vy, "utf8"));
    if (converted !== null) writeFileSync(vy, converted);
  }

  // update_version_yml_deploy: 기존 version.yml이 있고 ask 값이 있을 때만 deploy 블록 갱신
  if (existsSync(vy) && wf.deployValues && wf.deployValues.size) {
    writeFileSync(vy, upsertDeployBlock(readFileSync(vy, "utf8"), wf.deployValues));
  }

  copyScripts(tempDir, targetRoot);
  copyConfigFolder(tempDir, targetRoot);
  for (const t of types) copyUtilModules(tempDir, t, { force }, targetRoot);
  copySetupGuide(tempDir, targetRoot);

  // 설치 후 검증 (#549) — 워크플로우만 설치하는 모드라 오히려 더 필요하다.
  const verification = verifyInstall(targetRoot);
  hooks.trace?.emit?.("verify", "scan", {
    unresolved: verification.unresolved.length,
    secrets: verification.secrets.size,
  });

  return { workflows: wf, verification };
}

// 기존 version.yml에서 deploy: 블록을 제거하고 새로 append (.sh update_version_yml_deploy 멱등).
export function upsertDeployBlock(content, deployValues) {
  // 기존 deploy: 블록 제거 (deploy: 라인 ~ 다음 최상위 키 전까지)
  const lines = content.split(/\r?\n/);
  const out = [];
  let inDeploy = false;
  for (const line of lines) {
    if (/^deploy:/.test(line)) { inDeploy = true; continue; }
    if (inDeploy) {
      if (/^\s/.test(line) || line === "") continue; // 들여쓰기/빈줄 = deploy 내부
      inDeploy = false;
    }
    out.push(line);
  }
  let text = out.join("\n").replace(/\n+$/, "\n");
  // 새 deploy 블록 append
  const deployTypes = [...deployValues.keys()].filter((t) => deployValues.get(t)?.size);
  if (deployTypes.length) {
    text += `\ndeploy:                          # 마법사가 기억하는 배포 설정 (비민감 / 직접 수정 가능)\n`;
    for (const t of deployTypes) {
      text += `  ${t}:\n`;
      for (const [k, v] of deployValues.get(t)) text += `    ${k}: "${v}"\n`;
    }
  }
  return text;
}
