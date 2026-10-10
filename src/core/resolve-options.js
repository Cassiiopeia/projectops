// 설치 옵션 값을 정하는 단 한 곳 (#851).
//
// 예전에는 비대화형(src/index.js)과 대화형(src/commands/interactive.js)이 같은 옵션을
// 각자 정했다. 그 사이 규칙이 갈라져 대화형에서 PR 요약 선택이 버려지고(aiPrSummary),
// 질문을 건너뛰는 version 모드가 모바일 단독 레포에 deploy: docker-ssh 를 남겼다.
// 규칙은 모든 옵션에 같다: CLI 플래그 > version.yml 저장값 > 기본값.
// 대화형은 이 결과를 초기값으로 쓰고, 사용자가 답한 것만 그 위에 덮어쓴다.
import { existsSync } from "node:fs";
import { join } from "node:path";
import { applicableTargets, migrateProvider } from "./options-ask.js";
import { DEFAULT_CODE_REVIEW_CODERABBIT } from "./constants.js";
import { resolveLabelStyle } from "./label-style.js";
import { resolveRepoLanguage } from "./repo-language.js";

// 이미 설치돼 있으면 Projects 동기화를 켜진 것으로 보는 기준 파일 (#716)
export const PROJECTS_SYNC_WORKFLOW = ".github/workflows/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml";

// 타입에 성립하지 않는 축 값을 정리한다 (#498). 모바일 앱·basic 단독은 두 축이 모두 비어
// intent 도 none 으로 확정된다. 질문을 거친 값에도 같은 규칙을 다시 적용할 수 있게 따로 둔다.
export function normalizeAxes({ deploy, publish, intent, types }) {
  const applicable = applicableTargets(types);
  const outDeploy = deploy !== "none" && !applicable.deploy.includes(deploy) ? "none" : deploy;
  const outPublish = publish.filter((t) => applicable.publish.includes(t));
  const noAxes = types.length > 0 && applicable.deploy.length === 0 && applicable.publish.length === 0;
  return { deploy: outDeploy, publish: outPublish, intent: noAxes ? "none" : intent, applicable };
}

// flags: parseArgs 결과 중 옵션 관련 값 (없으면 {} — 대화형 초기값)
// existing: parseExisting 결과 또는 null
// 반환: { values, sources } — sources 는 trace 가 "왜 이 값인가"를 남길 근거다 (#561).
export function resolveOptions({ flags = {}, existing = null, types = [], cwd = "." }) {
  const stored = existing?.options ?? {};
  const applicable = applicableTargets(types);

  // 프로젝트 성격(#485): CLI --intent → 저장값. deploy/publish 유도의 기준.
  let intent = flags.intent ?? stored.intent ?? null;
  // 배포/publish 축(#439): 플래그 → 저장값 → 기본값(적용 가능할 때만 docker-ssh — #498).
  let deploy = flags.deployTarget ?? stored.deploy
    ?? (applicable.deploy.includes("docker-ssh") ? "docker-ssh" : "none");
  let publish = flags.publishTargets ?? stored.publish ?? [];
  // --intent 를 줬고 해당 축 플래그가 없으면 intent 가 축을 유도한다 (#485 비대화형)
  if (flags.intent != null) {
    if ((intent === "library" || intent === "none") && flags.deployTarget == null) deploy = "none";
    if ((intent === "app" || intent === "none") && flags.publishTargets == null) publish = [];
  }
  const before = { deploy, publish: [...publish] };
  ({ deploy, publish, intent } = normalizeAxes({ deploy, publish, intent, types }));

  const values = {
    intent, deployTarget: deploy, publishTargets: publish,
    includeSecretBackup: flags.includeSecretBackup ?? stored.secretBackup ?? false,
    // #566 — 설정 없이 바로 동작하므로 기본 켜짐
    aiPrSummary: flags.aiPrSummary ?? stored.aiPrSummary ?? true,
    // #716 — 설정(Secret, PROJECT_URL) 없는 신규 레포에 깔면 알림만 쌓인다. 이미 깔린 레포는 유지.
    projectsSync: flags.projectsSync ?? stored.projectsSync ?? existsSync(join(cwd, PROJECTS_SYNC_WORKFLOW)),
    // #502 — version 모드가 기존 full 통합 기록을 강등하지 않게 (full 이 우세)
    recordMode: existing?.templateMode === "full" ? "full" : "version",
    // #456 — 비어 있으면 version.yml 에 쓰지 않는다 (스킬이 develop 으로 폴백). 사용자가 고르거나 플래그로 준 것만 기록.
    deployBranch: flags.deployBranch || stored.deployBranch || "",
    // #455 — null 이 흘러 provider:"null" 로 기록되던 버그 방지
    changelogProvider: migrateProvider(stored.changelogProvider) ?? "commit",
    changelogBaseUrl: stored.changelogBaseUrl ?? "",
    codeReviewCoderabbit: flags.codeReviewCoderabbit ?? stored.codeReviewCoderabbit ?? DEFAULT_CODE_REVIEW_CODERABBIT,
    // #546, #814 — 명시적 false 는 존중, 키가 없으면 신규·기존 모두 켠다
    semverAuto: stored.semverAuto ?? true,
    // 마법사가 묻지 않는 값은 저장값만 보존한다 (전체 재생성이라 안 넘기면 사라진다)
    appRelease: stored.appRelease ?? null,                 // #553
    excludedWorkflows: stored.excludedWorkflows ?? null,   // #810
    storeLocales: stored.storeLocales ?? null,             // #829
    storeLocalesIos: stored.storeLocalesIos ?? null,
    storeLocalesPlay: stored.storeLocalesPlay ?? null,
    // #771 — 신규만 켠다. 기존 레포는 키를 만들지 않아 현행 유지
    closeOnRelease: stored.closeOnRelease ?? (existing ? null : true),
    // #769, #776 — 신규 en / 기존 ko. 업데이트만으로 기존 레포 문구·라벨이 바뀌지 않는다
    language: resolveRepoLanguage({ flag: flags.language ?? null, stored: stored.language, existing: !!existing }),
    labelStyle: resolveLabelStyle({ flag: flags.labelStyle ?? null, stored: stored.labelStyle, existing: !!existing }),
  };

  const from = (flagVal, storedVal, flagName) =>
    flagVal != null ? `cli-flag(${flagName})` : (storedVal ? "version.yml(stored value)" : "default");
  const sources = {
    intent: flags.intent != null ? "cli-flag(--intent)"
      : (stored.intent ? "version.yml(stored value)" : "not given, inferred from deploy/publish"),
    deploy: from(flags.deployTarget, stored.deploy, "--deploy"),
    publish: from(flags.publishTargets, stored.publish, "--publish"),
    before, applicable,
    // 기존 레포에서 semver_auto 가 이번에 처음 켜졌는지 — 완료 화면이 알린다
    semverAutoNewlyOn: !!existing && stored.semverAuto == null,
  };
  return { values, sources };
}
