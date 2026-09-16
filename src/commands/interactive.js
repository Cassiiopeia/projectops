// 대화형 마법사 (.sh interactive_mode 등가) — template_integrator.sh 4262~4411 + #446 UI 5층.
// io 주입으로 테스트 가능. 실제 실행은 src/ui/prompts.js 함수를 io로 넘긴다.
// 새 시각 층(banner/detectionLog/analysisCard/ideStatus/installKind/summary)과 저수준 엔진(engineIo)은
// io의 "옵셔널 멤버" — 스텁이 생략하면 해당 층만 건너뛰고 실행 계약은 동일하다.
import { join } from "node:path";
import { existsSync, readFileSync } from "node:fs";
import { PATHS } from "../core/paths.js";
import { remove } from "../core/fsutil.js";
import { acquireTemplate, readTemplateVersion } from "../core/assets.js";
import { detectTypes, detectVersion, detectDefaultBranch, detectRepoName, makeResolvers } from "../core/detect-fs.js";
import { parseExisting } from "../core/version-yml.js";
import { runBreakingCheck } from "../core/breaking-check.js";
import { runMigrations } from "../core/migrations/index.js";
import { detectOrphanWorkflows, applyOrphanCleanup } from "../core/orphan-workflows.js";
import { resolveProjectPaths, filterExcludedTypes } from "../core/paths-resolve.js";
import { askAllOptionalWorkflows, OPTION_AXES, applicableTargets, migrateProvider } from "../core/options-ask.js";
import { createRunTrace, MIGRATION_DIR } from "../core/run-trace.js";
import { appendGuideEntry } from "../core/migration-guide.js";
import { promptEnvPlan } from "../ui/env-plan.js";
import { listWorkflowConflicts } from "../core/copy/workflows.js";
import { extractEnvValues } from "../core/wizard-env.js";
import { createContext, VALID_TYPES } from "../context.js";
import { runFull } from "./full.js";
import { runVersion } from "./version.js";
import { runWorkflows } from "./workflows.js";
import { runIssues } from "./issues.js";
import { runSkills } from "./skills.js";
import * as prompts from "../ui/prompts.js";

const CANCEL = prompts.CANCEL;
const isCancel = (v) => v === CANCEL || typeof v === "symbol";

// io 기본값 = 실제 prompts. 테스트는 스텁 io 주입.
// skills = runSkills 주입 지점(테스트가 실제 IDE CLI를 안 건드리게). 기본은 실제 runSkills.
export async function runInteractive(baseCtx, { cwd = process.cwd(), source = { type: "git" }, clock, io = prompts, skills = runSkills } = {}) {
  const tempDir = join(cwd, PATHS.tempDir);
  // 실행 트레이스 (#494) — 실제 CLI(io=prompts)에서만 터미널 미러를 켠다 (테스트 스텁 io는 이벤트만).
  const trace = createRunTrace();
  // Ctrl+C로 끊어도 기록이 남는다 (#561) — 대화형은 사람이 중간에 끊는 일이 잦다.
  const disarmSignals = trace.armSignals({ targetRoot: cwd, now: clock?.now || "" });
  // finally에서 기록할 때 쓰는 값 — try 안에서 확정되기 전에 취소될 수 있으므로 바깥에 둔다 (#561).
  let traceFrom = "";
  let traceTo = "";
  // 기록 파일을 남기는 모드인지 — 모드 선택 전에 취소될 수 있어 기본값은 false.
  let recordArtifacts = false;
  // 기록을 남기지 않고 끝낼 경우(version/issues 모드의 정상 완주)에만 true.
  // 취소·예외는 모드와 무관하게 남긴다 — 끊겼을 때가 "어디까지 갔는지"가 가장 궁금한 순간이다.
  let skipRecord = false;
  if (io === prompts) trace.mirrorStart();
  try {
    // 템플릿 먼저 획득 — 배너에 실제 템플릿 버전을 표시 (.sh는 원격 version.yml fetch L4270~4280 등가)
    trace.step("acquire-template", () => acquireTemplate({ tempDir, source }), { source: source?.type || "git" });
    const templateVersion = readTemplateVersion(tempDir);
    traceTo = templateVersion;

    // 층1 — 시작 배너 (#446 확정 시안 A). 스텁엔 banner 없음 → intro 폴백.
    if (io.banner) io.banner({ version: templateVersion, modeLabel: "대화형 통합 마법사" });
    else io.intro?.("projectops — 대화형 통합 마법사");

    // 기존 version.yml — version/version_code/paths/옵션 보존의 단일 진실 (.sh SSoT L2208~2239)
    const vyPath = join(cwd, "version.yml");
    const existing = existsSync(vyPath) ? parseExisting(readFileSync(vyPath, "utf8")) : null;
    traceFrom = existing?.templateVersion || "";

    // 층4 — IDE Skills 현재 상태 · 층5 — 신규/업데이트 판별 (#446)
    io.ideStatus?.();
    io.installKind?.({ currentTemplateVersion: existing?.templateVersion || "", templateVersion });

    // 1) 모드 선택 — 기존 통합 레포면 업데이트 항목을 맨 위에 노출 (#502)
    const updateInfo = existing?.templateVersion ? { from: existing.templateVersion, to: templateVersion } : null;
    // 실행 경계(#561) — 대화형은 사람이 무엇을 골랐는지가 핵심 기록이다.
    trace.event("run", "start", "interactive", { templateVersion, isUpdate: !!updateInfo });
    const picked = await io.selectMode(updateInfo ? { update: updateInfo } : {});
    trace.event("prompt", "mode", String(picked ?? ""), { update: !!updateInfo });
    if (picked === CANCEL || picked == null) { trace.event("run", "cancelled", "mode-select", { reason: "user-cancel" }); io.cancelMessage?.("설치를 취소했습니다."); return 0; }
    // 업데이트 모드(#502): 저장된 통합 범위(templateMode, 없으면 full)를 재실행하고
    // 이하 updateRun 분기가 질문을 최소화한다 ("저장된 설정 그대로 반영"이 계약).
    const updateRun = picked === "update";
    const mode = updateRun ? (existing?.templateMode || "full") : picked;

    // Breaking Changes 게이트 (.sh execute_integration L4415~4420 — 모든 모드 공통, 대화형은 확인 질문)
    let breakingReport = null; // #493 — 통과 구간 항목을 가이드에 조치 방법 전문으로 임베드
    const proceed = await trace.stepAsync("breaking-check", () => runBreakingCheck({
      cwd, tempDir, templateVersion,
      askYesNo: (msg, def) => io.askYesNo(msg, def),
      onItems: (items) => { breakingReport = items; },
    }));
    if (!proceed) { trace.event("run", "cancelled", "breaking-gate", { reason: "user-declined" }); io.cancelMessage?.("통합을 안전하게 취소했습니다."); return 0; }

    // skills 모드 — IDE 스킬 설치 (템플릿 통합 없음). 대화형으로 실행.
    if (mode === "skills") {
      await skills({ templateVersion, tempDir, interactive: true });
      io.outro?.("AI 스킬 설치를 마쳤습니다.");
      return 0;
    }

    // issues 모드는 정보 수집 없이 바로 실행
    if (mode === "issues") {
      const ctx = createContext({ ...baseCtx, mode, force: true });
      runIssues(ctx, tempDir, cwd);
      io.summary?.({ mode, types: [], version: "", counters: {} }, cwd);
      io.outro?.("이슈·PR 템플릿을 설치했습니다.");
      return 0;
    }

    // full/version/workflows — 감지 (version은 기존 version.yml 최우선)
    let types = detectTypes(cwd);
    // 업데이트 모드 — 저장된 타입 우선 (재감지로 타입 집합이 흔들리지 않게, #502)
    if (updateRun && existing?.types?.length) {
      const saved = existing.types.filter((t) => VALID_TYPES.includes(t));
      if (saved.length) types = saved;
    }
    let version = (existing?.version) || detectVersion(cwd);
    let branch = detectDefaultBranch(cwd);
    const repoName = detectRepoName(cwd);
    const versionCode = existing?.versionCode ?? 1; // 기존 빌드번호 보존
    // 배포/publish 축 초기값(#439): version.yml 저장 옵션 (구 키 자동 마이그레이션 포함)
    let deployTarget = existing?.options?.deploy ?? "docker-ssh";
    let publishTargets = existing?.options?.publish ?? [];
    let includeSecretBackup = existing?.options?.secretBackup ?? false;
    let aiPrSummary = existing?.options?.aiPrSummary ?? null;   // null = 아직 안 물음 (#566)
    let codeReviewCoderabbit = existing?.options?.codeReviewCoderabbit ?? true;
    let changelogProvider = migrateProvider(existing?.options?.changelogProvider) ?? "commit";
    let changelogBaseUrl = existing?.options?.changelogBaseUrl ?? "";
    let deployBranch = existing?.options?.deployBranch ?? "develop"; // #456
    let deployBranchReady = null; // #490 — 이번 실행에서 개발 브랜치 존재/생성이 확인됐는지
    let deployBranchCreated = null; // #493 — 마법사가 직접 생성했는지 (가이드 기록용)
    let intent = existing?.options?.intent ?? null; // #485 프로젝트 성격
    // semver 자동 승격(#546) — 질문하지 않는다(#485 질문 부담 축소 방향 유지).
    // 저장값이 있으면 보존, 없으면 신규 통합만 ON. 기존 레포는 업데이트만으로 버전이 튀지 않는다.
    const semverAuto = existing?.options?.semverAuto ?? (existing ? false : true);
    const appRelease = existing?.options?.appRelease ?? null; // #553 저장값 보존 (묻지 않음)
    const showOptional = mode === "full" || mode === "workflows";
    const realTty = process.stdout.isTTY === true;

    // 층2 — 감지 로그 (#446)
    io.detectionLog?.({ types, version, branch });

    // 배포/publish 축 + Secret 백업 질문 (#439 — full/workflows만)
    if (showOptional) {
      const r = await askAllOptionalWorkflows({
        tempDir, types, targetRoot: cwd, defaultBranch: branch,
        current: {
          deploy: existing?.options?.deploy ?? null, publish: existing?.options?.publish ?? null, secretBackup: existing?.options?.secretBackup ?? null,
          codeReviewCoderabbit: existing?.options?.codeReviewCoderabbit ?? null,
          changelogProvider: existing?.options?.changelogProvider ?? null,
          changelogBaseUrl: existing?.options?.changelogBaseUrl ?? null,
          deployBranch: existing?.options?.deployBranch ?? null,
          intent: existing?.options?.intent ?? null,
        },
        force: false, tty: realTty,
        io: {
          confirm: ({ message, initialValue }) => io.askYesNo(message, initialValue),
          select: io.engineIo?.select,
          multiselect: io.engineIo?.multiselect,
          text: io.engineIo?.text ?? (({ message }) => io.askText?.(message, "")),
        },
      });
      deployTarget = r.deploy;
      publishTargets = r.publish;
      includeSecretBackup = r.secretBackup;
      codeReviewCoderabbit = r.codeReviewCoderabbit;
      changelogProvider = r.changelogProvider;
      changelogBaseUrl = r.changelogBaseUrl;
      deployBranch = r.deployBranch;
      deployBranchReady = r.deployBranchReady ?? deployBranchReady; // #490
      deployBranchCreated = r.deployBranchCreated ?? deployBranchCreated; // #493
      intent = r.intent;
    }

    // 확인/수정 루프 — ESC는 '머무르기' (.sh L1877~1881: 명시적 '아니오'만 종료)
    let paths = new Map();
    let confirmed = false;
    // 업데이트 모드 — 카드는 보여주되 확인 루프 생략 (#502: 설정 변경은 기존 모드의 몫)
    if (updateRun) {
      if (io.analysisCard) {
        io.analysisCard({ mode, modeLabel: `업데이트 (${modeLabel(mode)} 범위)`, types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, paths });
      } else {
        io.note?.(summarize({ mode, types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, changelogProvider, codeReviewCoderabbit }), "업데이트 — 저장된 설정으로 진행");
      }
      confirmed = true;
    }
    while (!confirmed) {
      // 층3 — 프로젝트 분석 개요 카드 (#446). 스텁엔 없음 → note 폴백.
      if (io.analysisCard) {
        io.analysisCard({ mode, modeLabel: modeLabel(mode), types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, paths });
      } else {
        io.note?.(summarize({ mode, types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, changelogProvider, codeReviewCoderabbit }), "프로젝트 분석 결과");
      }
      const choice = await io.confirmProjectMenu();
      if (choice === "cancel") { trace.event("run", "cancelled", "confirm-loop", { reason: "user-cancel" }); io.cancelMessage?.("설치를 취소했습니다."); return 0; }
      if (isCancel(choice) || choice == null) continue; // ESC = 머무르기 (루프 재출력)
      if (choice === "continue") { confirmed = true; break; }
      // edit 루프
      let editing = true;
      while (editing) {
        // #498 — 타입에 적용 불가한 배포 축 항목은 메뉴에서 숨김 (타입을 바꾸면 다음 진입부터 다시 노출)
        const what = await io.editMenu({ showOptional, axes: applicableTargets(types) });
        if (isCancel(what) || what === "done") { editing = false; break; }
        if (what === "type") {
          const t = await io.selectTypes(types);
          trace.event("prompt", "types", (Array.isArray(t) ? t : []).join(",") || "", { before: types });
          if (!isCancel(t) && Array.isArray(t) && t.length) {
            // 타입 집합이 실제로 바뀌면 경로 재해석 대상으로 초기화 (.sh L1984~1992 — 정렬 집합 비교)
            const oldSorted = [...types].sort().join(",");
            types = t.filter((x) => VALID_TYPES.includes(x));
            if ([...types].sort().join(",") !== oldSorted) paths = new Map();
          }
        } else if (what === "version") {
          const v = await io.askText("새 버전 (예: 1.0.0)", version);
          if (!isCancel(v) && v !== version) {
            // semver 형식 검증 (.sh L2010~2015)
            if (/^\d+\.\d+\.\d+$/.test(v)) version = v;
            else io.note?.("버전 형식이 올바르지 않습니다 (x.y.z 형태) — 기존 값을 유지합니다.", "⚠ 버전");
          }
        } else if (what === "branch") {
          const b = await io.askText("기본 브랜치", branch);
          if (!isCancel(b) && b) branch = b;
        } else if (OPTION_AXES.includes(what)) {
          // #483 — 선택한 축 하나만 재질문 (scope). 나머지 옵션은 현재값 그대로 유지.
          const r = await askAllOptionalWorkflows({
            tempDir, types, targetRoot: cwd, defaultBranch: branch,
            current: {
              deploy: deployTarget, publish: publishTargets, secretBackup: includeSecretBackup,
              codeReviewCoderabbit, changelogProvider, changelogBaseUrl, deployBranch, intent,
            },
            force: false, tty: realTty, forceAsk: true, scope: [what],
            io: {
              confirm: ({ message, initialValue }) => io.askYesNo(message, initialValue),
              select: io.engineIo?.select,
              multiselect: io.engineIo?.multiselect,
              text: io.engineIo?.text ?? (({ message }) => io.askText?.(message, "")),
            },
          });
          deployTarget = r.deploy;
          publishTargets = r.publish;
          includeSecretBackup = r.secretBackup;
          codeReviewCoderabbit = r.codeReviewCoderabbit;
          changelogProvider = r.changelogProvider;
          changelogBaseUrl = r.changelogBaseUrl;
          deployBranch = r.deployBranch;
          deployBranchReady = r.deployBranchReady ?? deployBranchReady; // #490
          deployBranchCreated = r.deployBranchCreated ?? deployBranchCreated; // #493
          intent = r.intent;
        }
      }
    }

    // 경로 확정 (.sh resolve_project_paths L1362~1589 — full/version만. 저장값·후보 스캔·질문)
    if (mode === "full" || mode === "version") {
      paths = await resolveProjectPaths({
        root: cwd, types, paths, existingPaths: existing?.paths ?? new Map(),
        force: false, tty: realTty, io: io.engineIo ?? {},
      });
      // 타입 탈출구 (#487) — 경로 단계에서 제외된 타입은 version.yml·복사·env 전 단계에서 뺀다
      types = filterExcludedTypes(types, paths);
    } else {
      for (const t of types) if (t !== "basic" && !paths.has(t)) paths.set(t, existing?.paths.get(t) || ".");
    }

    // @wizard env 계획 질문 (.sh wf_prompt_env_plan L3220 — full/workflows만).
    // 업데이트 모드는 생략 — 신규 파일은 기본값, 교체 파일은 아래 carryover가 기존 실값을 이월한다.
    const resolvers = makeResolvers(cwd, repoName, paths);
    let envValues = new Map(), envUseDefaults = true;
    if (showOptional && !updateRun) {
      const plan = await promptEnvPlan({
        tempDir, types, io: io.engineIo ?? null, force: false,
        resolvers, deployTarget, publishTargets, targetRoot: cwd, repoName,
      });
      envValues = plan.values;
      envUseDefaults = plan.useDefaults;
    }

    // 업데이트 모드 충돌 처리 (#502) — 타입별 3지선다 대신 일괄 확인 1회(기본 Y: .bak 백업 후 교체).
    // 교체를 선택하면 기존 설치본의 env 실값을 추출해 새 파일에 이월(carryover)한다 —
    // 기본값 재치환으로 사용자가 채운 값(FIREBASE_APP_ID 등)이 초기화되는 것을 막는 핵심.
    let updateDecisions = null;
    if (showOptional && updateRun) {
      const liteCtx = { types, paths, deployTarget, publishTargets, repoName, resolvers, branch, deployBranch };
      const conflicts = listWorkflowConflicts(liteCtx, tempDir, cwd);
      if (conflicts.length) {
        io.note?.(conflicts.map((c) => `• ${c.filename}`).join("\n"), `♻️ 템플릿이 갱신된 워크플로우 ${conflicts.length}개`);
        const yes = await io.askYesNo(`위 ${conflicts.length}개를 .bak 백업 후 새 버전으로 교체할까요? (기존 설정값은 유지됩니다)`, true);
        trace.event("prompt", "conflict-bulk", yes ? "backup" : "skip", { count: conflicts.length, files: conflicts.map((c) => c.filename) });
        const decision = yes === true ? "backup" : "skip";
        updateDecisions = new Map();
        for (const { filename } of conflicts) updateDecisions.set(filename, decision);
        if (decision === "backup") {
          const carried = new Map();
          for (const { filename } of conflicts) {
            const p = join(cwd, PATHS.workflowsDir, filename);
            if (!existsSync(p)) continue;
            for (const [k, v] of extractEnvValues(readFileSync(p, "utf8"))) carried.set(k, v);
          }
          if (carried.size) { envValues = carried; envUseDefaults = false; }
        }
      }
    }

    const { now, today } = clock || utcNow();
    const ctx = createContext({
      mode, force: true, types, version, versionCode, branch, paths, deployTarget, publishTargets, includeSecretBackup,
      codeReviewCoderabbit, changelogProvider, changelogBaseUrl, deployBranch, intent, semverAuto, appRelease,
      repoName, templateVersion, resolvers, envValues, envUseDefaults, now, today,
      // #502 — version 모드가 기존 full 기록을 강등하지 않도록 (full이 우세)
      recordMode: existing?.templateMode === "full" ? "full" : "version",
    });
    ctx.templateVersion = templateVersion;

    // 기존 워크플로우 충돌 3지선 — 타입당 1회 결정을 파일에 캐시 적용 (.sh L3440~3508 UX 등가)
    // 업데이트 모드는 위에서 일괄 결정(updateDecisions)했으므로 3지선다를 건너뛴다 (#502).
    let hooks = updateDecisions ? { decisions: updateDecisions } : {};
    if (showOptional && io.engineIo?.select && !updateRun) {
      const conflicts = listWorkflowConflicts(ctx, tempDir, cwd);
      if (conflicts.length) {
        const perType = new Map();
        const decisions = new Map();
        for (const { filename, type } of conflicts) {
          if (!perType.has(type)) {
            const sel = await io.engineIo.select({
              message: `기존 워크플로우와 내용이 다른 파일이 있습니다 (${type}) — 어떻게 할까요?`,
              options: [
                { value: "skip", label: "건너뛰기 — 기존 파일 유지 (기본)" },
                { value: "backup", label: ".bak 백업 후 새 버전으로 교체" },
                { value: "template", label: "기존 유지 + 새 버전을 .template.yaml로 참고 추가" },
              ],
            });
            perType.set(type, isCancel(sel) || sel == null ? "skip" : sel); // ESC = 건너뛰기 (.sh L3463)
          }
          decisions.set(filename, perType.get(type));
        }
        hooks = { decisions };
      }
    }

    // 레거시 마이그레이션 (#470) — 워크플로우를 만지는 모드에서만. 대화형은 safe 티어 확인 1회.
    let migrationsResult = null; // #493 — 가이드 기록용
    if (mode === "full" || mode === "workflows") {
      migrationsResult = await runMigrations({
        targetRoot: cwd,
        askYesNo: (msg, def) => io.askYesNo(msg, def),
      });
      for (const a of migrationsResult.applied ?? []) trace.event("legacy", a.action === "error" ? "error" : "neutralized", a.from ?? a.id ?? "", { to: a.to ?? "", id: a.id ?? "" });
      for (const e of migrationsResult.confirmPending ?? []) trace.event("legacy", "leftover-old-gen", e.file, { replacement: e.replacedBy ?? "", reason: e.reason ?? "" });
    }

    // 고아 타입 워크플로우 정리 (#487) — 타입 변경으로 선택에서 빠진 타입의 잔존 워크플로우
    const orphanReport = { cleaned: [], pending: [] }; // #493 — 가이드 기록용
    if (mode === "full" || mode === "workflows") {
      const orphans = detectOrphanWorkflows({ tempDir, targetRoot: cwd, selectedTypes: types,
        // 껐는데 남아 계속 도는 워크플로우도 함께 잡는다 (#566)
        options: { includeSecretBackup, aiPrSummary: aiPrSummary !== false, deployTarget } });
      if (orphans.length > 0) {
        io.note?.(
          orphans.map((o) => `• ${o.filename} (${o.type} 타입 — 현재 미선택)`).join("\n"),
          `🧹 선택되지 않은 타입의 워크플로우 ${orphans.length}개 발견`,
        );
        const yes = await io.askYesNo(`위 ${orphans.length}개를 정리할까요? (.bak 무해화 — 복원 가능)`, true);
        trace.event("prompt", "orphan-cleanup", yes ? "clean" : "keep", { count: orphans.length });
        if (yes === true) {
          const results = applyOrphanCleanup(cwd, orphans);
          const ok = results.filter((r) => r.action === "bak");
          const failed = results.filter((r) => r.action === "error");
          orphanReport.cleaned = ok.map((r) => r.filename);
          for (const r of ok) trace.event("orphan", "neutralized", r.filename);
          io.note?.(`✅ 고아 워크플로우 정리: ${ok.length}개${failed.length ? ` (실패 ${failed.length}개)` : ""}`, "정리 완료");
        } else {
          orphanReport.pending = orphans.map((o) => o.filename);
        }
      }
    }

    let result = null;
    if (mode === "full") result = trace.step("install-full", () => runFull(ctx, tempDir, cwd, { ...hooks, trace }));
    else if (mode === "version") result = trace.step("install-version", () => runVersion(ctx, tempDir, cwd));
    else if (mode === "workflows") result = trace.step("install-workflows", () => runWorkflows(ctx, tempDir, cwd, { ...hooks, trace }));

    // 통합 후 IDE 스킬 제안 (.sh L4557 offer_ide_tools_install — 사전 질문 게이트, 기본 N)
    // 업데이트 모드(#502): 이미 설치된 IDE 스킬만 질문 없이 최신화 (미설치 IDE는 건드리지 않음)
    if (updateRun) {
      await skills({ templateVersion, tempDir, interactive: false, installedOnly: true });
    } else {
      const wantSkills = await io.askYesNo("AI 에이전트 스킬(Claude·Cursor·Gemini·Codex·PI)도 설치/업데이트할까요?", false);
      if (wantSkills === true) await skills({ templateVersion, tempDir, interactive: true });
    }

    // 마이그레이션 기록 (#493/#494) — Layer 2/3 트레이스 파일 + Layer 1 가이드 엔트리 (full/workflows만)
    let migrationGuidePath = null;
    recordArtifacts = mode === "full" || mode === "workflows";
    // 경로는 먼저 계산하고 실제 쓰기는 완료 화면 뒤로 미룬다 — 요약까지 터미널 미러에 담기 위함 (#561)
    const files = recordArtifacts
      ? trace.paths({ fromVersion: existing?.templateVersion || "", toVersion: templateVersion, now })
      : null;
    if (recordArtifacts) {
      migrationGuidePath = appendGuideEntry(cwd, {
        now, mode, types, repoName,
        templateFrom: existing?.templateVersion || "", templateTo: templateVersion,
        options: { deploy: deployTarget, publish: publishTargets, secretBackup: includeSecretBackup, coderabbit: codeReviewCoderabbit, changelogProvider, intent, semverAuto , appRelease },
        branches: { defaultBranch: branch, deployBranch, ready: deployBranchReady, created: deployBranchCreated },
        breaking: breakingReport, migrations: migrationsResult, orphans: orphanReport,
        events: trace.events, counters: { skipped: result?.workflows?.skipped ?? 0 },
        traceFile: files?.traceFile ?? "", logFile: files?.logFile ?? "",
      }).guidePath;
    }

    // 완료 요약 (.sh print_summary L5438)
    io.summary?.({
      mode, types, version, deployBranch, deployBranchReady, migrationGuidePath,
      counters: { workflows: result?.workflows?.copied ?? 0, workflowFiles: result?.workflows?.copiedFiles ?? [], utilModules: 0 },
      verification: result?.verification,      // #549 설치 검증 결과
      aiPrSummary, codeReviewCoderabbit,       // #569 — 고른 것만 안내
      logDir: files ? MIGRATION_DIR : null,    // #561 기록 위치 안내
      logFile: files?.logFile ?? null,
      traceFile: files?.traceFile ?? null,
    }, cwd);
    io.outro?.(`통합 완료 — ${mode} 모드로 설치했습니다.`);

    // 완료 화면까지 출력한 뒤 finally에서 닫는다 (#561) — 여기서 닫으면 이 아래 화면이 안 담긴다.
    trace.event("run", "end", mode || "", {
      workflowsCopied: result?.workflows?.copied ?? 0,
      workflowsSkipped: result?.workflows?.skipped ?? 0,
    });
    skipRecord = !recordArtifacts;
    return 0;
  } catch (err) {
    trace.event("run", "error", "interactive", {
      message: err?.message || String(err),
      stack: String(err?.stack || "").split("\n").slice(0, 3).join(" | "),
    });
    throw err;
  } finally {
    // 어떤 경로로 빠져나가든 기록을 남긴다 (#561) — 중간 취소·예외·Ctrl+C 포함.
    // 완료 화면 출력이 try 안에 있어야 그 화면까지 미러에 담긴 채로 여기서 닫힌다.
    if (skipRecord) trace.mirrorStop();
    else trace.finalize({ targetRoot: cwd, fromVersion: traceFrom, toVersion: traceTo, now: clock?.now || "" });
    disarmSignals();
    remove(tempDir);
  }
}

function summarize({ mode, types, version, branch, deployTarget, publishTargets, includeSecretBackup, showOptional, changelogProvider, codeReviewCoderabbit }) {
  const lines = [
    `통합 모드 : ${modeLabel(mode)}`,
    `프로젝트 타입 : ${types.join(", ")}${types.length > 1 ? " (멀티)" : ""}`,
    `버전 : ${version}`,
    `기본 브랜치 : ${branch}`,
  ];
  if (showOptional) {
    lines.push(`배포 방식 : ${deployTarget || "docker-ssh"}`);
    lines.push(`Publish : ${(publishTargets ?? []).join(",") || "없음"}`);
    lines.push(`Secret 백업 : ${includeSecretBackup ? "포함" : "제외"}`);
    lines.push(`Changelog : ${changelogProvider || "commit"}`);
    lines.push(`CodeRabbit 리뷰 : ${codeReviewCoderabbit ? "사용" : "미사용"}`);
  }
  return lines.join("\n");
}

function modeLabel(m) {
  return {
    full: "전체 설치 (버전관리 + 워크플로우 + 템플릿)",
    version: "버전 관리 전용 (자동화 시스템)",
    workflows: "워크플로우 전용 (GitHub Actions 빌드, 배포)",
    issues: "이슈/PR 템플릿 전용",
    skills: "AI 스킬 전용 (Claude, Cursor, Gemini, Codex, PI)",
    update: "업데이트"
  }[m] || m;
}

function utcNow(date = new Date()) {
  const p = (n) => String(n).padStart(2, "0");
  const d = `${date.getUTCFullYear()}-${p(date.getUTCMonth() + 1)}-${p(date.getUTCDate())}`;
  const t = `${p(date.getUTCHours())}:${p(date.getUTCMinutes())}:${p(date.getUTCSeconds())}`;
  return { now: `${d} ${t}`, today: d };
}
