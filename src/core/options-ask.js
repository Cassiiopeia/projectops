// 배포/publish 축(#439) + Secret 백업 opt-in 질문 (.sh ask_deploy_publish /
// ask_optional_workflow / ask_all_optional_workflows 등가).
//
// io 주입 계약(readline-engine 시그니처):
//   io.confirm({message, initialValue})            → bool | CANCEL(symbol)
//   io.select({message, options})                  → value | CANCEL   (deploy 택1)
//   io.multiselect({message, options, initialValues}) → value[] | CANCEL (publish 다중)
//   io.log(line)                                   → 안내 출력 (없으면 stderr)
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { listYamlFiles } from "./fsutil.js";
import { PATHS } from "./paths.js";
import { t as msg } from "../i18n/index.js";
import { parseTemplateOptions, inferIntent } from "./version-yml.js";
import { branchStatus, createBranch, pushBranch } from "./git-branch.js";

// 개발(배포) 브랜치 존재 확인 + 생성 제안 (#477) — 대화형 전용.
// 로컬에 없고 원격에도 없(거나 불명이)면 기본 브랜치에서 생성을 제안하고, 생성 후 push 여부도 묻는다.
// git 미설치·비레포·질문 불가(io.confirm 없음)면 조용히 통과 — 마법사 진행을 막지 않는다.
// 반환 ready (#490 — 완료 요약이 "브랜치 만들어라" 재지시를 접을지 판단):
//   true  = 브랜치가 이미 있거나 이번 실행에서 생성함 → 요약에서 생성 안내 불필요
//   false = 없는데 사용자가 거절/생성 실패 → 안내 유지
//   null  = 확인 자체를 못 함(비레포·질문 불가) → 안내 유지(보수적)
export async function ensureDeployBranch({ targetRoot = ".", deployBranch = "", defaultBranch = "", io = {}, say = () => {} }) {
  if (!deployBranch || typeof io.confirm !== "function") return { created: false, pushed: false, ready: null };
  const st = branchStatus(targetRoot, deployBranch);
  if (!st.isRepo) return { created: false, pushed: false, ready: null };
  if (st.local) return { created: false, pushed: false, ready: true };
  if (st.remote === true) {
    say(msg("options.branch.remoteOnly", { branch: deployBranch }));
    return { created: false, pushed: false, ready: true };
  }
  say(msg("options.branch.missing", { branch: deployBranch, base: defaultBranch || msg("options.branch.baseFallback") }));
  const mk = await io.confirm({ message: msg("options.branch.createPrompt", { base: defaultBranch || msg("options.branch.currentFallback"), branch: deployBranch }), initialValue: true });
  if (mk !== true) {
    say(msg("options.branch.skipped", { branch: deployBranch }));
    return { created: false, pushed: false, ready: false };
  }
  if (!createBranch(targetRoot, deployBranch, defaultBranch)) {
    say(msg("options.branch.createFailed", { branch: deployBranch, from: defaultBranch ? ` ${defaultBranch}` : "" }));
    return { created: false, pushed: false, ready: false };
  }
  say(msg("options.branch.created", { branch: deployBranch }));
  // #481 — push 질문에 브랜치명 명시 ("어느 브랜치를 push하는지" 불명확 방지)
  const up = await io.confirm({ message: msg("options.branch.pushPrompt", { branch: deployBranch }), initialValue: true });
  if (up !== true) return { created: true, pushed: false, ready: true };
  if (pushBranch(targetRoot, deployBranch)) {
    say(msg("options.branch.pushed", { branch: deployBranch }));
    return { created: true, pushed: true, ready: true };
  }
  say(msg("options.branch.pushFailed", { branch: deployBranch }));
  return { created: true, pushed: false, ready: true };
}

// 재노출 — 파서 본체는 version-yml.js에 있다 (순환 import 방지: options-ask → version-yml 방향만 허용)
export { parseTemplateOptions };

export const DEPLOY_TARGETS = ["docker-ssh", "vercel", "none"];
export const PUBLISH_TARGETS = ["nexus", "npm", "github-packages"];

// #498 — 타입별 적용 가능 deploy/publish 타겟 선언.
// 빈 배열 = 그 축이 개념상 성립하지 않는 타입. 모바일 앱(flutter/react-native/expo)은 스토어 배포
// (Play Store/TestFlight/Firebase 등) 워크플로우가 타입 자체에 항상 포함되므로 서버 deploy 축과
// 무관하고, 레지스트리 publish 개념도 없다. 두 축이 모두 빈 타입만 선택되면 질문 자체를 스킵한다.
// 서버형 타입은 현행 선택지 전체를 유지한다 (동작 무변경 — 타입별 세분화는 후속 과제).
export const TYPE_DEPLOY_TARGETS = {
  spring: ["docker-ssh", "vercel"],
  react: ["docker-ssh", "vercel"],
  node: ["docker-ssh", "vercel"],
  python: ["docker-ssh", "vercel"],
  flutter: [],
  "react-native": [],
  "react-native-expo": [],
  basic: [],
};
export const TYPE_PUBLISH_TARGETS = {
  spring: ["nexus", "npm", "github-packages"],
  react: ["nexus", "npm", "github-packages"],
  node: ["nexus", "npm", "github-packages"],
  python: ["nexus", "npm", "github-packages"],
  flutter: [],
  "react-native": [],
  "react-native-expo": [],
  basic: [],
};

// 선택된 타입 집합의 합집합으로 적용 가능 타겟 산출 (#498). 'none'은 항상 허용이라 목록에서 제외.
// 미선언 타입은 보수적으로 전체 허용(질문 유지) — 새 타입 추가 시 위 선언도 함께 넣는 게 원칙.
export function applicableTargets(types = []) {
  const deployAll = DEPLOY_TARGETS.filter((t) => t !== "none");
  return {
    deploy: deployAll.filter((t) => types.some((ty) => (TYPE_DEPLOY_TARGETS[ty] ?? deployAll).includes(t))),
    publish: PUBLISH_TARGETS.filter((t) => types.some((ty) => (TYPE_PUBLISH_TARGETS[ty] ?? PUBLISH_TARGETS).includes(t))),
  };
}
// changelog 생성기 provider (#455, #566에서 재정비).
// 기본값은 commit — 외부 의존이 없어 어떤 환경에서도 결과가 나온다. AI를 쓰려면
// MODEL_API_KEY를 등록하면 사다리가 자동으로 집어 쓴다(마법사는 묻지 않는다).
// github-ai는 GitHub Models 종료(2026-07-30)로 제외됐다.
export const CHANGELOG_PROVIDERS = ["copilot", "coderabbit", "openai", "gemini", "claude", "groq", "mistral", "ollama", "commit"];

// 더 이상 동작하지 않는 저장값을 살아있는 값으로 옮긴다 (#566).
// 기존 저장소가 업데이트만 돌려도 죽은 설정에서 벗어나게 하는 유일한 경로다.
const RETIRED_PROVIDERS = { "github-ai": "commit" };
export function migrateProvider(saved) {
  if (saved == null) return null;
  return RETIRED_PROVIDERS[saved] ?? saved;
}

const isCancel = (v) => typeof v === "symbol";

// Secret 백업 등 폴더 기반 opt-in 1종 질문 (.sh ask_optional_workflow 등가).
// 반환: true/false/null(폴더 없음·파일 0개로 질문 자체 생략 → 현재값 유지).
async function askOptionalWorkflow({ dir, icon, short, desc, current, force, tty, io, forceAsk, say }) {
  // 폴더가 없거나 yaml이 0개면 조용히 건너뜀 — 질문 자체가 성립 안 함
  if (!existsSync(dir)) return current;
  const files = listYamlFiles(dir);
  if (files.length === 0) return current;

  // 이미 값이 설정돼 있고 force-ask 아니면 유지 (CLI/version.yml 우선)
  if (!forceAsk && (current === true || current === false)) return current;

  // 비대화형(--force 또는 TTY 없음)이면 기본 제외
  if (force || !tty) return false;

  say("");
  say(msg("options.optional.found", { icon, name: short, count: files.length }));
  say(`   ${desc}`);
  say("");
  say(msg("options.optional.included"));
  for (const f of files) say(`     • ${f}`);
  say("");

  const ans = await io.confirm({ message: msg("options.optional.prompt", { name: short }), initialValue: false });
  const include = ans === true && !isCancel(ans);
  say(include
    ? msg("options.optional.yes", { name: short })
    : msg("options.optional.no", { name: short }));
  return include;
}

// 옵션 질문의 축 키 (#483 수정 스코프 단위) — 수정 메뉴가 이 단위로 한 축만 재질문한다.
// intent(#485)는 프로젝트 성격 — 재질문 시 deploy/publish 축을 재유도한다.
export const OPTION_AXES = ["intent", "deploy", "publish", "code-review", "changelog", "release-branch", "secret"];

// intent → 어떤 배포 축을 물을지 (#485). manual은 둘 다(기존 순차 질문), 나머지는 유도.
const INTENT_ASKS_DEPLOY = { app: true, both: true, manual: true, library: false, none: false };
const INTENT_ASKS_PUBLISH = { library: true, both: true, manual: true, app: false, none: false };

// 배포/publish 축 + Secret 백업을 순서대로 질문 (.sh ask_all_optional_workflows 등가).
// tempDir: 템플릿 다운로드 루트 — project-types는 {tempDir}/.github/workflows/project-types
// current: { deploy: string|null, publish: string[]|null, secretBackup: bool|null } — CLI 명시값
// scope: null이면 전 축(초기 통합·전체 재질문). Set/배열이면 그 축만 forceAsk 대상 (#483 수정 메뉴 격리).
//        스코프 밖 축은 forceAsk여도 current/저장값을 그대로 유지하고 다시 묻지 않는다.
// 반환: { deploy, publish, secretBackup, codeReviewCoderabbit, aiPrSummary, changelogProvider, changelogBaseUrl, deployBranch }
export async function askAllOptionalWorkflows({
  tempDir, types = [], current = {}, targetRoot = ".",
  force = false, tty = true, io = {}, forceAsk = false, defaultBranch = "", scope = null,
}) {
  const say = io.log || ((m) => process.stderr.write(`${m}\n`));
  // 축별 재질문 여부: 전역 forceAsk이고, scope가 없거나 그 축을 포함할 때만 강제 질문.
  const scopeSet = scope == null ? null : new Set(scope);
  const ask = (axis) => forceAsk && (scopeSet === null || scopeSet.has(axis));
  let deploy = current.deploy ?? null;
  let publish = current.publish ?? null;
  let secretBackup = current.secretBackup ?? null;
  let codeReviewCoderabbit = current.codeReviewCoderabbit ?? null;
  let aiPrSummary = current.aiPrSummary ?? null;
  let changelogProvider = current.changelogProvider ?? null;
  let changelogBaseUrl = current.changelogBaseUrl ?? null;
  let deployBranch = current.deployBranch ?? null; // #456 릴리스 PR head 브랜치
  let deployBranchReady = null; // #490 — 이번 실행에서 브랜치 존재/생성이 확인됐는지 (null=확인 안 함)
  let deployBranchCreated = null; // #493 — 이번 실행에서 마법사가 직접 생성했는지 (가이드 기록용)
  let intent = current.intent ?? null; // #485 프로젝트 성격 (app/library/both/none/manual)

  // 두 축이 모두 빈 타입 조합(#498 — basic 단독, flutter 등 모바일 앱 단독)은 서버 배포도
  // 라이브러리 publish도 개념상 성립하지 않는다. 질문을 전부 건너뛰고 none·[]로 조용히 확정한다
  // (모바일 스토어 배포는 타입 워크플로우가 항상 포함되므로 안내조차 불필요 — 타입 변경 시 재질문됨).
  // 구 isBasicOnly 특례를 일반화한 판정이다.
  const applicable = applicableTargets(types);
  const noAxes = types.length > 0 && applicable.deploy.length === 0 && applicable.publish.length === 0;

  // ① --force-ask가 아니면 version.yml 저장값을 먼저 읽어 재질문을 건너뛴다.
  //    CLI 명시값(current)이 이미 있으면 그쪽이 우선 — 저장값은 빈 자리만 채운다.
  if (!forceAsk) {
    const vy = join(targetRoot, PATHS.versionFile);
    if (existsSync(vy)) {
      const saved = parseTemplateOptions(readFileSync(vy, "utf8"));
      if (deploy === null && saved.deploy !== null) {
        deploy = saved.deploy;
        say(msg("options.saved.deploy", { value: deploy }));
      }
      if (publish === null && saved.publish !== null) {
        publish = saved.publish;
        say(msg("options.saved.publish", { value: publish.join(",") || msg("options.saved.none") }));
      }
      if (secretBackup === null && saved.secretBackup !== null) {
        secretBackup = saved.secretBackup;
        say(msg("options.saved.secret", { value: secretBackup }));
      }
      // #455 changelog/code_review 저장값 재사용
      if (codeReviewCoderabbit === null && saved.codeReviewCoderabbit !== null) codeReviewCoderabbit = saved.codeReviewCoderabbit;
      if (aiPrSummary === null && saved.aiPrSummary != null) aiPrSummary = saved.aiPrSummary;
      if (changelogProvider === null && saved.changelogProvider !== null) changelogProvider = saved.changelogProvider;
      if (changelogBaseUrl === null && saved.changelogBaseUrl !== null) changelogBaseUrl = saved.changelogBaseUrl;
      // #456 deploy_branch 저장값 재사용
      if (deployBranch === null && saved.deployBranch != null) deployBranch = saved.deployBranch;
      // #485 intent 저장값 재사용 — 없으면 저장된 deploy/publish에서 역추론(구 version.yml 하위호환)
      if (intent === null) intent = saved.intent ?? inferIntent(saved.deploy, saved.publish);
    }
  }

  // 적용 불가 타겟 조용한 정리 (#498) — 구버전에서 저장된 무의미 값(예: flutter 단독 + docker-ssh)은
  // 어차피 복사 결과가 동일하므로 경고 없이 none/교집합으로 정리한다 (SSOT — 무의미 값 잔존 금지).
  if (deploy !== null && deploy !== "none" && !applicable.deploy.includes(deploy)) deploy = "none";
  if (Array.isArray(publish)) publish = publish.filter((t) => applicable.publish.includes(t));

  // ── ② intent(프로젝트 성격) 우선 분기 → 배포 축 유도 (#485) ──
  // 두 축 모두 빈 타입 조합이면 intent 개념 자체가 없어 질문 스킵, none/[]로 확정 (#498).
  if (noAxes) {
    if (deploy === null) deploy = "none";
    if (publish === null) publish = [];
    intent = "none";
  } else {
    // 수정 메뉴에서 deploy/publish 축만 콕 집어 고칠 때(scope에 그 축이 있고 intent는 없음)는
    // intent 질문·게이팅을 건너뛰고 그 축만 바로 편집한다 (#483 격리 존중). intent는 값 유지·역추론.
    const scopedAxisOnly = scopeSet !== null && !scopeSet.has("intent");
    if (scopedAxisOnly) {
      if (intent === null) intent = inferIntent(deploy, publish) ?? "manual";
    } else {
      // intent 질문: 미확정이거나(초기 통합) intent 축을 강제 재질문(수정 메뉴 "프로젝트 성격")일 때.
      const askIntent = ask("intent") || intent === null;
      if (askIntent) {
        if (force || !tty || typeof io.select !== "function") {
          // 비대화형: CLI intent 미지정이면 deploy/publish에서 역추론, 그래도 없으면 manual(기존 동작)
          intent = intent ?? inferIntent(deploy, publish) ?? "manual";
        } else {
          say("");
          say(msg("options.intent.intro"));
          const ans = await io.select({
            message: msg("options.intent.prompt"),
            options: [
              { value: "app", label: msg("options.intent.app") },
              { value: "library", label: msg("options.intent.library") },
              { value: "both", label: msg("options.intent.both") },
              { value: "none", label: msg("options.intent.none") },
              { value: "manual", label: msg("options.intent.manual") },
            ],
          });
          intent = (!isCancel(ans) && INTENT_ASKS_DEPLOY[ans] !== undefined) ? ans : (intent ?? "manual");
          say(msg("options.intent.chosen", { value: intent }));
        }
        // intent 확정 후 유도: 안 묻는 축은 값 확정, 묻는 축은 재질문 대상으로 되돌린다.
        if (!INTENT_ASKS_DEPLOY[intent]) deploy = "none";
        if (!INTENT_ASKS_PUBLISH[intent]) publish = [];
        if (INTENT_ASKS_DEPLOY[intent] && ask("intent")) deploy = null;
        if (INTENT_ASKS_PUBLISH[intent] && ask("intent")) publish = null;
      }
    }
    // intent가 정해진 뒤, 유도 규칙에 따라 각 축을 물을지 결정 (#485).
    // scopedAxisOnly(수정 메뉴 단일 축)면 intent 게이트를 무시하고 그 축을 편집하게 한다.
    const deployGate = scopedAxisOnly ? true : INTENT_ASKS_DEPLOY[intent];
    const publishGate = scopedAxisOnly ? true : INTENT_ASKS_PUBLISH[intent];
    const willAskDeploy = deployGate && (ask("deploy") || deploy === null);
    const willAskPublish = publishGate && (ask("publish") || publish === null);
    // 유도로 안 묻는 축은 기본값 확정.
    if (!deployGate && deploy === null) deploy = "none";
    if (!publishGate && publish === null) publish = [];
    // manual(직접 고르기)에서 둘 다 물을 땐 두 축이 별개임을 한 번 안내 (#480 계승).
    if (intent === "manual" && willAskDeploy && willAskPublish && tty && typeof io.select === "function") {
      say("");
      say(msg("options.axes.intro"));
      say(msg("options.axes.one"));
      say(msg("options.axes.two"));
    }
    // 비대화형/폴백 기본값 (#498) — docker-ssh가 적용 가능할 때만 기본, 아니면 none.
    const deployDefault = applicable.deploy.includes("docker-ssh") ? "docker-ssh" : "none";
    if (willAskDeploy) {
      if (force || !tty || typeof io.select !== "function") {
        deploy = deploy ?? deployDefault;
      } else {
        say("");
        say(msg("options.deploy.intro"));
        say(msg("options.deploy.hint"));
        // 선택지는 적용 가능 타겟으로 필터링 (#498) — 'none'은 항상 노출.
        const deployLabels = [
          { value: "docker-ssh", label: msg("options.deploy.dockerSsh") },
          { value: "vercel", label: "Vercel" },
        ];
        const ans = await io.select({
          message: msg("options.deploy.prompt"),
          options: [
            ...deployLabels.filter((o) => applicable.deploy.includes(o.value)),
            { value: "none", label: msg("options.deploy.none") },
          ],
        });
        deploy = (!isCancel(ans) && (ans === "none" || applicable.deploy.includes(ans))) ? ans : (deploy ?? deployDefault);
        say(msg("options.deploy.chosen", { value: deploy }));
      }
    }

    // ── ③ publish 타겟 (다중 선택) ──
    if (willAskPublish) {
      if (force || !tty || typeof io.multiselect !== "function") {
        publish = publish ?? [];
      } else {
        say("");
        say(msg("options.publish.intro"));
        say(msg("options.publish.hint"));
        // 선택지는 적용 가능 타겟으로 필터링 (#498)
        const publishLabels = [
          { value: "nexus", label: msg("options.publish.nexus") },
          { value: "npm", label: msg("options.publish.npm") },
          { value: "github-packages", label: msg("options.publish.githubPackages") },
        ];
        const ans = await io.multiselect({
          message: msg("options.publish.prompt"),
          options: publishLabels.filter((o) => applicable.publish.includes(o.value)),
          initialValues: publish ?? [],
          required: false,
        });
        publish = (!isCancel(ans) && Array.isArray(ans))
          ? ans.filter((t) => applicable.publish.includes(t))
          : (publish ?? []);
        say(publish.length ? msg("options.publish.chosen", { value: publish.join(", ") }) : msg("options.publish.chosenNone"));
      }
    }
  }

  // ── pr_comment: PR에 달 리뷰·요약 (#566에서 통합) ──
  // 종전에는 CodeRabbit 여부만 예/아니오로 물었고, AI 변경 요약은 물어보지도 않은 채
  // 항상 복사된 뒤 런타임에 스스로 빠졌다. 그 결과 "CodeRabbit도 안 달고 요약도 안 다는"
  // 저장소가 생겼다. 둘은 같은 자리(PR 댓글)를 놓고 경쟁하므로 한 번에 고르게 한다.
  if (ask("code-review") || codeReviewCoderabbit === null || aiPrSummary === null) {
    if (force || !tty || typeof io.select !== "function") {
      // 비대화형 기본값: CodeRabbit은 별도 앱 설치가 있어야 실제로 동작하므로
      // 자동화 환경에서 켜봐야 의미가 없다. 설정 없이 바로 도는 요약만 켠다.
      codeReviewCoderabbit = codeReviewCoderabbit ?? false;
      aiPrSummary = aiPrSummary ?? true;
    } else {
      say("");
      say(msg("options.pr.intro"));
      say(msg("options.pr.hint1"));
      say(msg("options.pr.hint2"));
      say(msg("options.pr.hint3"));
      const ans = await io.select({
        message: msg("options.pr.prompt"),
        options: [
          { value: "both", label: msg("options.pr.both") },
          { value: "summary", label: msg("options.pr.summary") },
          { value: "coderabbit", label: msg("options.pr.coderabbit") },
          { value: "none", label: msg("options.pr.none") },
        ],
      });
      // 취소·미응답은 추천값으로 — 다른 축과 같은 방어 패턴이다.
      const PR_COMMENT_CHOICES = ["summary", "coderabbit", "both", "none"];
      const pick = (!isCancel(ans) && PR_COMMENT_CHOICES.includes(ans)) ? ans : "summary";
      codeReviewCoderabbit = pick === "coderabbit" || pick === "both";
      aiPrSummary = pick === "summary" || pick === "both";
      say(msg("options.pr.chosen", { value: msg(`options.pr.label.${pick}`) }));
      // #481 — "사용"만으로는 안 붙는다. 앱 설치 + 레포 접근 권한이 있어야 실제로 리뷰가 달린다.
      if (codeReviewCoderabbit) {
        say(msg("options.pr.crWarn"));
        say(msg("options.pr.crStep1"));
        say(msg("options.pr.crStep2"));
        say(msg("options.pr.crStep3"));
      }
    }
  }

  // ── changelog: 생성기를 묻지 않는다 (#566) ──
  // 사용자의 목적은 "릴리스 노트가 잘 나오는 것"이지 provider 선택이 아니다. 무엇을 고를지
  // 알 수 없는 질문이었고 기본값(github-ai)마저 죽어 있었다. 이제 워크플로우가 스스로
  // 최선을 찾는다 — PR 본문 존중 → Copilot → 외부 AI(키 있으면) → 커밋 분석.
  // 저장값은 그대로 두되 죽은 값만 살아있는 것으로 옮긴다.
  changelogProvider = migrateProvider(changelogProvider) ?? "commit";

  // ollama 선택 시에만 base_url 질문 (나머지 provider는 preset base_url 자동 — #455)
  if (changelogProvider === "ollama" && (ask("changelog") || changelogBaseUrl === null || changelogBaseUrl === "")) {
    if (force || !tty || typeof io.text !== "function") {
      changelogBaseUrl = changelogBaseUrl ?? "";
    } else {
      const ans = await io.text({ message: msg("options.ollama.prompt") });
      changelogBaseUrl = (typeof ans === "string" && !isCancel(ans)) ? ans.trim() : "";
      say(msg("options.ollama.chosen", { value: changelogBaseUrl || msg("options.ollama.unset") }));
    }
  } else if (changelogBaseUrl === null) {
    changelogBaseUrl = "";
  }

  // ── 릴리스 소스(개발) 브랜치 (#456 필드 deploy_branch — 이름과 달리 "개발 브랜치"다, #482) ──
  //    이 값은 릴리스 PR(개발→기본)의 head, 즉 개발한 걸 모아 기본 브랜치로 올리는 브랜치다.
  //    "배포 브랜치"가 아니다 — 배포가 도는 곳은 기본 브랜치(default) 쪽 개념. #482 참조.
  if (ask("release-branch") || deployBranch === null) {
    if (force || !tty || typeof io.text !== "function") {
      deployBranch = deployBranch ?? "develop";
    } else {
      const base = defaultBranch || "main"; // git으로 감지된 기본 브랜치 (#481 동적 안내)
      say("");
      say(msg("options.devBranch.intro"));
      say(msg("options.devBranch.detected", { base }));
      say(msg("options.devBranch.hint"));
      const ans = await io.text({ message: msg("options.devBranch.prompt"), initialValue: deployBranch ?? "develop" });
      deployBranch = (typeof ans === "string" && !isCancel(ans) && ans.trim()) ? ans.trim() : (deployBranch ?? "develop");
      say(msg("options.devBranch.chosen", { value: deployBranch }));
      // 브랜치 존재 확인 + 생성 제안 (#477) — 없으면 릴리스 파이프라인이 조용히 놀게 된다
      // #490 — 결과(ready)를 완료 요약에 전달해 이미 생성/확인한 브랜치를 재지시하지 않는다
      const br = await ensureDeployBranch({ targetRoot, deployBranch, defaultBranch, io, say });
      deployBranchReady = br.ready;
      deployBranchCreated = br.created;
    }
  }

  // ── ④ Secret 백업: 공통 폴더 (배포축 아님 — 기존 폴더 질문 유지) ──
  const real = join(tempDir, PATHS.workflowsDir, PATHS.projectTypesDir);
  const ptDir = existsSync(real) ? real : join(tempDir, PATHS.projectTypesDir);
  secretBackup = await askOptionalWorkflow({
    dir: join(ptDir, "common", "secret-backup"), icon: "🔐", short: msg("options.secret.short"),
    desc: msg("options.secret.desc"),
    current: secretBackup, force, tty, io, forceAsk: ask("secret"), say,
  });

  // 최종 폴백도 적용 가능 타겟 기준 (#498) — 모바일/basic 조합에서 docker-ssh가 새어 나가지 않게.
  const finalDeploy = deploy ?? (applicable.deploy.includes("docker-ssh") ? "docker-ssh" : "none");
  const finalPublish = publish ?? [];
  return {
    deploy: finalDeploy, publish: finalPublish, secretBackup: secretBackup === true,
    codeReviewCoderabbit: codeReviewCoderabbit === true,
    // #566 — AI 변경 요약 워크플로우 포함 여부. 기본 true(추가 설정 없이 바로 동작).
    aiPrSummary: aiPrSummary !== false,
    changelogProvider: changelogProvider ?? "commit",
    changelogBaseUrl: changelogBaseUrl ?? "",
    deployBranch: deployBranch ?? "develop",
    deployBranchReady, // #490 — true=존재/생성 확인됨, false=거절/실패, null=확인 안 함
    deployBranchCreated, // #493 — true=이번 실행에서 마법사가 생성, null=확인 안 함

    // #485 intent — 확정값 우선, 없으면 최종 deploy/publish에서 역추론(basic·비대화형 경로 보정)
    intent: intent ?? inferIntent(finalDeploy, finalPublish) ?? "manual",
  };
}
