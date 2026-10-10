// 선택형 워크플로 그룹의 켜짐/꺼짐을 정하는 단 한 곳 (#851).
//
// 예전에는 복사(copy/workflows.js), 충돌 목록(listWorkflowConflicts), 고아 감지(orphan-workflows.js)가
// 같은 조건을 각자 들고 있었다. 한쪽만 고치면 "켰는데 안 깔림" 또는 "껐는데 계속 돎"이 된다 (#567).
// 새 조건부 폴더를 만들면 여기에 한 줄을 넣는다. 세 곳이 함께 따라온다.
import { readdirSync } from "node:fs";
import { join } from "node:path";
import { exists } from "./fsutil.js";

// 서버 배포(<type>/server-deploy/)는 docker-ssh 일 때만 깐다 (#439)
export const SERVER_DEPLOY_DIR = "server-deploy";
export function serverDeployEnabled(deployTarget) {
  return (deployTarget || "docker-ssh") === "docker-ssh";
}

// common/ 아래 선택형 폴더 목록. 순서가 복사 순서다 (기록·요약에 나오는 순서를 바꾸지 않는다).
//   policy: "bak-replace" — 템플릿과 다르면 .bak 으로 남기고 교체
//           "new-only"    — 이미 있으면 건드리지 않는다 (secret-backup: 서버 경로를 사용자가 고쳐 쓴다)
//   copyLabel / orphanLabel — trace 그룹 이름과 고아 안내 이름. 기존 기록과 같게 둔다.
export function commonOptionalGroups(commonDir, opts = {}) {
  const { includeSecretBackup = false, aiPrSummary = true, projectsSync = true, deployTarget = "docker-ssh" } = opts;
  const selectedDeploy = deployTarget || "docker-ssh";
  const groups = [];

  // deploy/<target> — 타입 비종속 배포 타겟(vercel 등). 고른 타겟 폴더만 켠다.
  const deployRoot = join(commonDir, "deploy");
  const deployNames = exists(deployRoot)
    ? readdirSync(deployRoot, { withFileTypes: true }).filter((e) => e.isDirectory()).map((e) => e.name)
    : [];
  if (!deployNames.includes(selectedDeploy)) deployNames.push(selectedDeploy); // 폴더가 없으면 아래에서 exists 로 걸러진다
  for (const name of deployNames) {
    groups.push({ dir: join("deploy", name), enabled: name === selectedDeploy, policy: "bak-replace",
      copyLabel: "common-deploy", orphanLabel: `deploy/${name}` });
  }
  groups.push(
    // #566 — AI 변경 요약. 설정 없이 바로 동작
    { dir: "pr-summary", enabled: aiPrSummary === true, policy: "bak-replace", copyLabel: "pr-summary", orphanLabel: "pr-summary" },
    // #716 — Projects 보드 동기화. Secret·변수를 등록해야 동작해 신규는 기본 꺼짐
    { dir: "projects-sync", enabled: projectsSync === true, policy: "bak-replace", copyLabel: "projects-sync", orphanLabel: "projects-sync" },
    // Secret 서버 백업
    { dir: "secret-backup", enabled: includeSecretBackup === true, policy: "new-only", copyLabel: "secret-backup", orphanLabel: "secret-backup" },
  );
  return groups;
}
