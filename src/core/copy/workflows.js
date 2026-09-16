// 워크플로우 복사 엔진 (.sh copy_workflows + _copy_workflows_for_type 등가).
// 실측: template_integrator.sh 3398~3815.
// 대화형 3지선(기존 파일 충돌)은 copyWorkflowsInteractive(async)가 결정 Map을 만들어
// 동기 엔진(copyWorkflows)에 hooks.decisions로 전달한다 — 기존 시그니처·force 동작 무변경.
import { join, basename } from "node:path";
import { existsSync, readFileSync, writeFileSync, renameSync } from "node:fs";
import { PATHS } from "../paths.js";
import { exists, copyFileSync, listYamlFiles } from "../fsutil.js";
import { isUnchanged, substituteEnv } from "../wizard-env.js";
import { isUserModified, readBaseline, writeBaseline, sha256 } from "../baseline.js";
import { substituteBranches } from "../branch-sub.js";

// 한 파일에 env 치환을 적용해 대상 파일을 갱신 (.sh configure_workflow_env 등가).
// values/useDefaults: env 계획(promptEnvPlan) 결과 — 미지정이면 기본값 경로(현행 force 동작).
// trace(#494): 치환 1건당 env.substituted 이벤트 (before/after 포함 — 치환 불일치류 버그의 즉시 발견 근거).
function configureEnv(targetPath, filename, { type, projectPath = ".", repoName = "", resolvers = {}, collectAsks = null, values = new Map(), useDefaults = true, trace = null }) {
  const content = readFileSync(targetPath, "utf8");
  if (!content.includes("@wizard")) return;
  const collectSubs = trace ? [] : null;
  const out = substituteEnv(content, { type, useDefaults, values, projectPath, repoName, resolvers, collectAsks, collectSubs });
  writeFileSync(targetPath, out);
  if (trace && collectSubs) {
    for (const s of collectSubs) trace.event("env", "substituted", filename, { type, ...s });
  }
}

// util 버전 동기화 워크플로우 (#491) — .github/util/ 모듈(version.json)이 있는 레포에서만 의미가 있다.
// util이 없는 레포(예: spring 단독)에 복사하면 트리거가 영원히 안 걸리는 no-op 오염이 된다.
const UTIL_VERSION_SYNC = "PROJECT-COMMON-TEMPLATE-UTIL-VERSION-SYNC.yml";

// 이 통합에서 util 모듈이 존재하게 되는가 — 대상에 이미 있거나(업데이트),
// 선택 타입의 util이 템플릿에 있어 곧 복사될 예정(runFull 6단계)이면 true.
function utilSyncApplies(tempDir, targetRoot, types) {
  if (exists(join(targetRoot, ".github", "util"))) return true;
  return types.some((t) => exists(join(tempDir, ".github", "util", t)));
}

// 4분류 (신규/unchanged/upstream/changed) — 대상 워크플로우 디렉토리 기준.
//
// upstream(#557): 사용자가 손대지 않았는데 템플릿만 바뀐 파일. 질문할 이유가 없으므로
// 그냥 최신으로 올린다. baseline(설치 시점 해시)이 있어야 판정할 수 있다.
// baseline이 없거나 그 파일 기록이 없으면 판정 불가 → 종전대로 changed로 떨어뜨린다
// (기존 통합 레포의 동작이 바뀌지 않는다).
function classify(srcDir, workflowsDir, envOpts, baseline = null) {
  const result = { newFiles: [], unchanged: [], changed: [], upstream: [] };
  for (const filename of listYamlFiles(srcDir)) {
    const src = join(srcDir, filename);
    const dst = join(workflowsDir, filename);
    if (existsSync(dst)) {
      const tpl = readFileSync(src, "utf8");
      const inst = readFileSync(dst, "utf8");
      if (isUnchanged(tpl, inst, envOpts)) { result.unchanged.push(filename); continue; }
      // 여기 왔다는 건 "지금 템플릿 렌더 결과 ≠ 설치본" — 사용자 수정이거나 업스트림 변경이다.
      // baseline이 그 둘을 가른다.
      const modified = isUserModified(baseline, filename, inst);
      if (modified === false) result.upstream.push(filename);
      else result.changed.push(filename);
    } else {
      result.newFiles.push(filename);
    }
  }
  return result;
}

// copy_workflows 본체 (동기 — 기존 호출부 무변경).
// context: { types:[], paths:Map, deployTarget, publishTargets:[], includeSecretBackup, force, repoName, resolvers,
//            envValues?:Map<key,value>, envUseDefaults?:boolean }  ← env 계획(promptEnvPlan) 결과 주입점
//   deployTarget(#439 택1): 'docker-ssh'(기본) | 'vercel' | 'none' — server-deploy는 docker-ssh일 때만,
//   common/deploy/<target>/은 해당 타겟일 때 복사. publishTargets(#439 다중): 'nexus'|'npm'|'github-packages'.
// hooks: { decisions?: Map<filename, 'skip'|'backup'|'template'> } — 기존 파일(changed) 충돌 결정.
// 반환: {copied, skipped, templateAdded, optionalCopied, copiedFiles[]} — copiedFiles는 실제 복사·교체된 파일명 (#473 요약용)
export function copyWorkflows(context, tempDir, targetRoot = ".", hooks = {}) {
  const { types = [], paths = new Map(), deployTarget = "docker-ssh", publishTargets = [], includeSecretBackup = false, repoName = "", resolvers = {}, envValues = new Map(), envUseDefaults = true, branch = "", deployBranch = "" } = context;
  const decisions = hooks.decisions instanceof Map ? hooks.decisions : new Map();
  const trace = hooks.trace ?? null; // #494 — 실행 트레이스 (null-safe: 미주입이면 전 이벤트 no-op)
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  // 설치 시점 기준점(#557) — 없으면 null이고 classify가 종전 2-way로 폴백한다.
  const baseline = readBaseline(targetRoot);
  const projectTypesDir = join(tempDir, PATHS.workflowsDir, PATHS.projectTypesDir);
  if (!exists(projectTypesDir)) throw new Error("템플릿 저장소 구조 오류 — project-types 폴더를 찾지 못했습니다.");

  const counters = { copied: 0, skipped: 0, templateAdded: 0, optionalCopied: 0, copiedFiles: [] };
  const deployValues = new Map(); // Map<type, Map<key,value>> — deploy 블록용 ask 값
  counters.deployValues = deployValues;
  // 브랜치 전략 (#477) — 표준(main/develop)이면 치환·가상비교 모두 no-op
  const branches = { defaultBranch: branch || "main", deployBranch: deployBranch || "develop" };
  // values/useDefaults는 치환 경로에서만 의미 (isUnchanged는 내부에서 useDefaults:true 강제 — 가상 비교 무손상)
  const envOptsFor = (type) => ({ type, projectPath: paths.get(type) || ".", repoName, resolvers, values: envValues, useDefaults: envUseDefaults, branches });

  // (1) common — 타입별과 동일한 판정·보호를 받는다 (#560).
  //
  // 종전에는 "unchanged면 스킵, 아니면 무조건 덮어쓰기"였다. 그런데 릴리스 파이프라인처럼
  // 프로젝트마다 뒤에 붙일 일이 다른 워크플로우는 common에 있어도 사용자가 고쳐 쓸 수밖에
  // 없다. 고치지 않고는 쓸 수 없는 파일을, 고치면 백업도 없이 날아가는 규칙으로 관리하고
  // 있었다. common/deploy조차 .bak을 남기는데 본체만 아무것도 남기지 않았다.
  const commonDir = join(projectTypesDir, "common");
  if (exists(commonDir)) {
    const commonEnv = envOptsFor("common");
    const commonClass = classify(commonDir, workflowsDir, commonEnv, baseline);
    for (const filename of listYamlFiles(commonDir)) {
      // #491 — util 동기화 워크플로우는 util 모듈이 있(게 되)는 레포에만 복사
      if (filename === UTIL_VERSION_SYNC && !utilSyncApplies(tempDir, targetRoot, types)) {
        trace?.event("copy", "excluded", filename, { reason: "util-modules-absent" });
        continue;
      }
      if (commonClass.unchanged.includes(filename)) {
        counters.skipped++;
        trace?.event("copy", "skipped-unchanged", filename, { group: "common" });
        continue;
      }
      // 사용자가 손댄 적 없고 템플릿만 바뀐 파일 — 물어볼 것 없이 최신으로 올린다(종전과 동일).
      if (commonClass.newFiles.includes(filename) || commonClass.upstream.includes(filename)) {
        copyFileSync(join(commonDir, filename), join(workflowsDir, filename));
        counters.copied++;
        counters.copiedFiles.push(filename);
        trace?.event("copy", commonClass.upstream.includes(filename) ? "upstream-updated" : "copied",
                     filename, { group: "common" });
        continue;
      }
      // 여기부터는 changed — "지금 템플릿 렌더 결과 ≠ 설치본"이다. 둘로 갈린다.
      const dst = join(workflowsDir, filename);
      const modified = isUserModified(baseline, filename, readFileSync(dst, "utf8"));
      if (modified === null) {
        // 판정 불가(기준점 없음 = 기존 통합 레포). common의 종전 계약은 "항상 최신으로 갱신"이라
        // 여기서 skip하면 기존 레포가 업데이트를 영영 못 받는다. 계약은 지키되 되돌릴 수단을
        // 남긴다 — 덮어쓰기 전 .bak. (#560: common/deploy조차 .bak을 남기는데 본체만 없었다)
        renameSync(dst, dst + ".bak");
        copyFileSync(join(commonDir, filename), dst);
        counters.copied++;
        counters.copiedFiles.push(filename);
        trace?.event("copy", "replaced-bak", filename, { group: "common", reason: "baseline-absent" });
        continue;
      }
      // 사용자가 손댄 것이 확인된 파일 — 결정에 따라 처리(미지정이면 유지).
      applyDecision(decisions.get(filename), commonDir, workflowsDir, filename, counters, trace);
    }
  }

  // (2~4) 타입별
  for (const type of types) {
    const asks = new Map();
    copyWorkflowsForType(type, projectTypesDir, workflowsDir, { deployTarget, publishTargets, ...context, envOptsFor, collectAsks: asks, decisions, trace, baseline }, counters);
    if (asks.size) deployValues.set(type, asks);
  }

  // (4.5) common/deploy/<target> — 타입 비종속 배포 타겟 (vercel 등, #439)
  const commonDeployDir = join(commonDir, "deploy", deployTarget || "docker-ssh");
  if (exists(commonDeployDir)) {
    for (const filename of listYamlFiles(commonDeployDir)) {
      const src = join(commonDeployDir, filename);
      const dst = join(workflowsDir, filename);
      if (existsSync(dst) && isUnchanged(readFileSync(src, "utf8"), readFileSync(dst, "utf8"), envOptsFor("common"))) {
        counters.skipped++;
        trace?.event("copy", "skipped-unchanged", filename, { group: "common-deploy" });
        continue;
      }
      const backedUp = existsSync(dst);
      if (backedUp) renameSync(dst, dst + ".bak");
      copyFileSync(src, dst);
      counters.optionalCopied++;
      counters.copied++;
      counters.copiedFiles.push(filename);
      trace?.event("copy", backedUp ? "replaced-bak" : "copied", filename, { group: "common-deploy" });
    }
  }

  // (5) common/secret-backup — 있으면 무조건 스킵/신규만 복사
  const secretDir = join(commonDir, "secret-backup");
  if (exists(secretDir) && includeSecretBackup) {
    for (const filename of listYamlFiles(secretDir)) {
      const dst = join(workflowsDir, filename);
      if (existsSync(dst)) continue; // 이미 존재하면 스킵
      copyFileSync(join(secretDir, filename), dst);
      counters.optionalCopied++;
      counters.copied++;
      counters.copiedFiles.push(filename);
      trace?.event("copy", "copied", filename, { group: "secret-backup" });
    }
  }

  // (6) 브랜치 치환 post-pass (#477) — 표준과 다른 브랜치 전략일 때만 복사된 파일에 적용.
  // isUnchanged 가상 비교에도 같은 branches가 들어가므로 다음 업데이트에서 재복사 churn이 없다.
  if (branches.defaultBranch !== "main" || branches.deployBranch !== "develop") {
    for (const f of counters.copiedFiles) {
      const p = join(workflowsDir, f);
      if (!existsSync(p)) continue;
      const before = readFileSync(p, "utf8");
      const after = substituteBranches(before, branches);
      if (after !== before) {
        writeFileSync(p, after);
        trace?.event("env", "branch-substituted", f, { defaultBranch: branches.defaultBranch, deployBranch: branches.deployBranch });
      }
    }
  }

  // (7) 기준점 기록 (#557) — 다음 업데이트가 "누가 바꿨는지"를 가릴 근거.
  //     이번에 실제로 쓴 파일만 installed를 갱신한다. 유지(skip)한 파일에 우리가 쓴 것처럼
  //     기록하면 다음 업데이트에서 사용자 수정이 조용히 덮인다.
  recordBaseline(workflowsDir, targetRoot, counters, baseline, context.templateVersion, context.now, trace);

  return counters;
}

// 설치 직후의 디스크 내용을 기준점으로 남긴다. 실패해도 통합을 막지 않는다 —
// 기준점이 없으면 다음 업데이트가 종전 2-way 판정으로 폴백할 뿐이다.
function recordBaseline(workflowsDir, targetRoot, counters, previous, templateVersion, now, trace = null) {
  try {
    const entries = new Map();
    for (const f of counters.copiedFiles || []) {
      const p = join(workflowsDir, f);
      if (!existsSync(p)) continue;
      const content = readFileSync(p, "utf8");
      // 치환까지 끝난 최종 디스크 내용이 곧 우리가 쓴 것이자, 이 시점의 렌더 결과다.
      entries.set(f, { installed: sha256(content), rendered: sha256(content) });
    }
    if (entries.size === 0 && previous) return; // 새로 쓴 게 없으면 기존 기준점을 건드리지 않는다
    trace?.event("baseline", "recorded", "", { files: entries.size, hadPrevious: !!previous });
    writeBaseline(targetRoot, {
      templateVersion: templateVersion || "unknown",
      installedAt: now || "",
      entries,
      previous,
    });
  } catch {
    // 기준점 기록 실패는 통합 실패가 아니다
  }
}

// changed(기존에 있고 내용이 바뀐) 파일 1개를 결정에 따라 처리 (.sh 3440~3508 3지선 case 등가).
// 'skip'(기본): 기존 유지. 'backup': 기존→.bak 후 교체. 'template': 기존 유지 + 새 버전을 .template.yaml로.
function applyDecision(decision, srcDir, workflowsDir, filename, counters, trace = null) {
  const src = join(srcDir, filename);
  const dst = join(workflowsDir, filename);
  if (decision === "backup") {
    // .sh O) mv → cp: 기존을 .bak으로 백업 후 새 버전으로 교체
    renameSync(dst, dst + ".bak");
    copyFileSync(src, dst);
    counters.copied++;
    counters.copiedFiles?.push(filename);
    trace?.event("copy", "replaced-bak", filename, { decision });
    return;
  }
  if (decision === "template") {
    // .sh T) `${filename%.yaml}.template.yaml` — .yaml만 strip (.yml은 그대로 뒤에 붙음, .sh 동일)
    const templateName = (filename.endsWith(".yaml") ? filename.slice(0, -".yaml".length) : filename) + ".template.yaml";
    copyFileSync(src, join(workflowsDir, templateName)); // cp가 기존 .template.yaml 덮어씀(.sh rm -f + cp 등가)
    counters.templateAdded++;
    trace?.event("copy", "template-added", templateName, { original: filename });
    return;
  }
  counters.skipped++; // 'skip'/미지정/ESC → 기존 유지 (.sh S)·force 기본)
  trace?.event("copy", "skipped-conflict", filename, { decision: decision ?? "skip", note: "사용자 수정본 유지 — 병합 검토 후보" });
}

// 대상 워크플로우 디렉토리에서 changed(충돌) 파일 목록만 뽑는다 — copyWorkflowsInteractive의 사전 조사용.
// copyWorkflows 본체와 동일한 classify 기준을 써야 결정 Map이 실제 처리 대상과 1:1로 맞는다.
export function listWorkflowConflicts(context, tempDir, targetRoot = ".") {
  const { types = [], paths = new Map(), deployTarget = "docker-ssh", repoName = "", resolvers = {}, branch = "", deployBranch = "" } = context;
  const workflowsDir = join(targetRoot, PATHS.workflowsDir);
  // 설치 시점 기준점(#557) — 없으면 null이고 classify가 종전 2-way로 폴백한다.
  const baseline = readBaseline(targetRoot);
  const projectTypesDir = join(tempDir, PATHS.workflowsDir, PATHS.projectTypesDir);
  const conflicts = []; // [{ filename, type }] — 엔진 처리 순서와 동일 (common → 타입 순회 → server-deploy)
  const branches = { defaultBranch: branch || "main", deployBranch: deployBranch || "develop" }; // #477 — 엔진과 동일 기준

  // common (#560) — 사용자가 손댄 것이 "확인된" 파일만 질문 대상이다.
  // 기준점이 없어 판정 불가인 파일은 엔진이 .bak을 남기고 덮어쓰므로 질문하지 않는다.
  const commonDir = join(projectTypesDir, "common");
  if (exists(commonDir)) {
    const commonEnv = { type: "common", projectPath: ".", repoName, resolvers, branches };
    for (const f of classify(commonDir, workflowsDir, commonEnv, baseline).changed) {
      const dst = join(workflowsDir, f);
      if (!existsSync(dst)) continue;
      if (isUserModified(baseline, f, readFileSync(dst, "utf8")) !== true) continue;
      conflicts.push({ filename: f, type: "common" });
    }
  }

  for (const type of types) {
    const envOpts = { type, projectPath: paths.get(type) || ".", repoName, resolvers, branches };
    const typeDir = join(projectTypesDir, type);
    if (exists(typeDir)) {
      for (const f of classify(typeDir, workflowsDir, envOpts, baseline).changed) conflicts.push({ filename: f, type });
    }
    const serverDeployDir = join(typeDir, "server-deploy");
    if (exists(serverDeployDir) && (deployTarget || "docker-ssh") === "docker-ssh") {
      for (const f of classify(serverDeployDir, workflowsDir, envOpts, baseline).changed) conflicts.push({ filename: f, type });
    }
  }
  return conflicts;
}

// 대화형 진입점 (async) — 충돌마다 onConflict(filename, type)를 await해 결정 Map을 만든 뒤
// 동기 엔진에 위임한다. WHY 분리: copyWorkflows를 async로 바꾸면 await 없이 호출하는
// 기존 호출부(runFull/runWorkflows)가 깨진다 — 시그니처 무변경 원칙.
// onConflict 반환값: 'template' | 'skip' | 'backup' (그 외/미지정 → 'skip').
export async function copyWorkflowsInteractive(context, tempDir, targetRoot = ".", { onConflict } = {}) {
  const decisions = new Map();
  if (typeof onConflict === "function") {
    for (const { filename, type } of listWorkflowConflicts(context, tempDir, targetRoot)) {
      if (decisions.has(filename)) continue; // 파일명은 PROJECT-{TYPE}- prefix로 타입 간 유일
      decisions.set(filename, await onConflict(filename, type));
    }
  }
  return copyWorkflows(context, tempDir, targetRoot, { decisions });
}

const PUBLISH_TARGETS = ["nexus", "npm", "github-packages"];

function copyWorkflowsForType(type, projectTypesDir, workflowsDir, ctx, counters) {
  const { deployTarget = "docker-ssh", publishTargets = [], force = false, paths = new Map(), repoName = "", resolvers = {}, envOptsFor, collectAsks = null, decisions = new Map(), trace = null, baseline = null } = ctx;
  const typeDir = join(projectTypesDir, type);
  const envOpts = envOptsFor(type);
  let unchangedNames = [];

  // 타입별 워크플로우 (직하위)
  if (exists(typeDir)) {
    const { newFiles, unchanged, changed, upstream } = classify(typeDir, workflowsDir, envOpts, baseline);
    unchangedNames = unchanged.slice();
    for (const f of unchanged) { counters.skipped++; trace?.event("copy", "skipped-unchanged", f, { group: type }); }
    for (const f of newFiles) { copyFileSync(join(typeDir, f), join(workflowsDir, f)); counters.copied++; counters.copiedFiles.push(f); trace?.event("copy", "copied", f, { group: type }); }
    // upstream(#557): 사용자가 손대지 않았고 템플릿만 바뀐 파일 — 물어볼 것 없이 최신으로 올린다.
    for (const f of upstream) { copyFileSync(join(typeDir, f), join(workflowsDir, f)); counters.copied++; counters.copiedFiles.push(f); trace?.event("copy", "upstream-updated", f, { group: type, reason: "baseline-match" }); }
    // changed: 결정 Map에 따라 처리 (미지정=skip → 현행 force 동작과 동일)
    for (const f of changed) applyDecision(decisions.get(f), typeDir, workflowsDir, f, counters, trace);
  }

  // server-deploy — deploy=docker-ssh일 때만 포함 (#439)
  const serverDeployDir = join(typeDir, "server-deploy");
  if (exists(serverDeployDir) && (deployTarget || "docker-ssh") === "docker-ssh") {
    const { newFiles, unchanged, changed, upstream } = classify(serverDeployDir, workflowsDir, envOpts, baseline);
    for (const f of unchanged) { counters.skipped++; trace?.event("copy", "skipped-unchanged", f, { group: `${type}/server-deploy` }); }
    for (const f of newFiles) { copyFileSync(join(serverDeployDir, f), join(workflowsDir, f)); counters.copied++; counters.copiedFiles.push(f); trace?.event("copy", "copied", f, { group: `${type}/server-deploy` }); }
    for (const f of upstream) { copyFileSync(join(serverDeployDir, f), join(workflowsDir, f)); counters.copied++; counters.copiedFiles.push(f); trace?.event("copy", "upstream-updated", f, { group: `${type}/server-deploy`, reason: "baseline-match" }); }
    for (const f of changed) applyDecision(decisions.get(f), serverDeployDir, workflowsDir, f, counters, trace);
  }

  // publish/<target> (opt-in — #439 publish 축. 타입은 파일 위치일 뿐 게이트가 아니다)
  const pubDirs = [];
  for (const target of PUBLISH_TARGETS) {
    const pubDir = join(typeDir, "publish", target);
    pubDirs.push(pubDir);
    if (!exists(pubDir) || !publishTargets.includes(target)) continue;
    for (const filename of listYamlFiles(pubDir)) {
      const src = join(pubDir, filename);
      const dst = join(workflowsDir, filename);
      if (existsSync(dst) && isUnchanged(readFileSync(src, "utf8"), readFileSync(dst, "utf8"), envOpts)) {
        counters.skipped++;
        trace?.event("copy", "skipped-unchanged", filename, { group: `${type}/publish/${target}` });
        continue;
      }
      const backedUp = existsSync(dst);
      if (backedUp) renameSync(dst, dst + ".bak");
      copyFileSync(src, dst);
      counters.optionalCopied++;
      counters.copied++;
      counters.copiedFiles.push(filename);
      trace?.event("copy", backedUp ? "replaced-bak" : "copied", filename, { group: `${type}/publish/${target}` });
    }
  }

  // env 치환 — 이 타입의 원본 디렉토리들에서 복사돼 존재하고 unchanged 아닌 파일만
  for (const srcDir of [typeDir, serverDeployDir, ...pubDirs]) {
    if (!exists(srcDir)) continue;
    for (const filename of listYamlFiles(srcDir)) {
      const target = join(workflowsDir, filename);
      if (!existsSync(target)) continue;            // 건너뛴 파일 제외
      if (unchangedNames.includes(filename)) continue; // unchanged 제외
      configureEnv(target, filename, { ...envOpts, collectAsks, trace }); // env 계획 values/useDefaults 포함
    }
  }
}
