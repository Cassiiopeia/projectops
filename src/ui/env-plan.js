// @wizard env 계획 질문 UI (.sh wf_scope_string/wf_collect_asks/_wf_print_field_card/
// _wf_prefill_all/_wf_prefill_interactive/wf_prompt_env_plan 등가).
// 실측 기준: template_integrator.sh 3059~3085(scope), 3087~3143(collect), 3152~3169(card),
//           3220~3280(prompt 본체 wf_prompt_env_plan).
// io 주입식 — 테스트는 {select, multiselect, text} 스텁을 넘긴다. 기본은 readline-engine 실물.
import { join } from "node:path";
import { readFileSync } from "node:fs";
import { stdin, stderr } from "node:process";
import { PATHS } from "../core/paths.js";
import { exists, listYamlFiles } from "../core/fsutil.js";
import { parseWizardLine, resolveToken, resolveGlobalTokens } from "../core/wizard-env.js";
import { loadWizardPrompts, wfField, workflowDisplayName } from "../core/wizard-labels.js";
import * as engine from "./readline-engine.js";
import { t } from "../i18n/index.js";

const CANCEL = engine.CANCEL;

// 진행 안내는 stderr로 출력 (.sh print_to_user가 >&2인 것과 동일 — stdout 파이프 오염 방지).
const defaultLog = (s = "") => stderr.write(s + "\n");

// 사용처 문자열 조립 (.sh wf_scope_string 등가).
// usages: [{type, workflowName}] — 타입이 여러 개면 타입만 "t1·t2", 하나면 "타입 name1·name2".
export function scopeString(usages = []) {
  const types = []; const names = [];
  for (const { type, workflowName } of usages) {
    if (!types.includes(type)) types.push(type);
    if (!names.includes(workflowName)) names.push(workflowName);
  }
  if (types.length > 1) return types.join("·");
  return `${types.join("·")} ${names.join("·")}`.trim();
}

// ask KEY 수집 (.sh wf_collect_asks 등가) — 실제 설치되는 워크플로우와 같은 소스를 스캔한다.
// tempDir: 다운로드 원본 루트. types: 설치 대상 타입 목록.
// opts:
//   resolvers      - @접두 기본값(@repo 등) 해석용 (.sh는 수집 시점에 resolve_token — 동일)
//   deployTarget   - #439 배포 축: docker-ssh(기본)일 때만 server-deploy 스캔 (복사 엔진과 일치)
//   publishTargets - #439 publish 축: 선택된 타겟의 publish/<target>/ 스캔
//   prompts        - wizard-labels 파싱 객체 (워크플로우 표시명용, null이면 확장자 제거 폴백)
// 반환: { keys:[], defaults:Map<key,default>, typeDefaults:Map<"type|key",default>,
//        usages:Map<key,[{type,workflowName}]> }
export function collectAsks(tempDir, types = [], opts = {}) {
  const { resolvers = {}, deployTarget = "docker-ssh", publishTargets = [], prompts = null, repoName = "" } = opts;
  const baseDir = join(tempDir, PATHS.workflowsDir, PATHS.projectTypesDir);
  const keys = [];
  const defaults = new Map();
  const typeDefaults = new Map();
  const usages = new Map();

  for (const type of types) {
    const typeDir = join(baseDir, type);
    if (!exists(typeDir)) continue;
    // 복사 엔진과 동일한 폴더 구성: 타입 직하위 + (docker-ssh면) server-deploy + 선택된 publish/<target>
    const dirs = [typeDir];
    if ((deployTarget || "docker-ssh") === "docker-ssh") dirs.push(join(typeDir, "server-deploy"));
    for (const pt of publishTargets) dirs.push(join(typeDir, "publish", pt));

    for (const dir of dirs) {
      if (!exists(dir)) continue;
      for (const filename of listYamlFiles(dir)) {
        const content = readFileSync(join(dir, filename), "utf8");
        if (!content.includes("@wizard")) continue;
        const workflowName = workflowDisplayName(prompts, filename);
        for (const line of content.split(/\r?\n/)) {
          const p = parseWizardLine(line); // KEY 정규식 [A-Z_]+ (.sh와 동일)
          if (!p || p.action !== "ask") continue;
          // 타입별 기본값: @접두면 resolver 해석, 아니면 리터럴 (.sh _type_default 등가)
          // #489 — __PROJECT_NAME__ 등 전역 토큰은 카드 표시 전에 미리 해석한다.
          //        설치본(파일 복사 시 전역 치환)과 동일한 값을 보여주지 않으면
          //        사용자가 "리터럴이 그대로 박히나?" 오해하게 된다.
          const typeDefault = resolveGlobalTokens(
            p.arg.startsWith("@") ? resolveToken(p.arg.slice(1), type, resolvers) : p.arg,
            repoName,
          );
          typeDefaults.set(`${type}|${p.key}`, typeDefault);
          if (!defaults.has(p.key)) { keys.push(p.key); defaults.set(p.key, typeDefault); }
          const list = usages.get(p.key) || [];
          list.push({ type, workflowName });
          usages.set(p.key, list);
        }
      }
    }
  }
  return { keys, defaults, typeDefaults, usages };
}

// KEY가 처음 등장한 type (.sh _wf_first_type_for — 라벨 조회 시 타입 오버라이드 우선순위용)
function firstTypeFor(usages, key) {
  return usages.get(key)?.[0]?.type ?? "";
}

// KEY 1개를 'label·사용처·설명·예시·기본값' 카드로 출력 (.sh _wf_print_field_card 등가).
// info: { default, usages } — idx/tot 있으면 "(i/t)" 진행 표시. log 주입 가능(테스트 무음화).
export function printFieldCard(prompts, key, info, idx = null, tot = null, log = defaultLog) {
  const ty = info.usages?.[0]?.type ?? "";
  const label = wfField(prompts, ty, key, "label");
  const help = wfField(prompts, ty, key, "help");
  const ex = wfField(prompts, ty, key, "example");
  const scope = scopeString(info.usages || []);
  const head = idx != null && tot != null
    ? `   ▸ (${idx}/${tot}) ${label}  [${scope}]`
    : `   ▸ ${label}  [${scope}]`;
  log(head);
  if (help) log(`       ${help}`);
  if (ex) log(t("envPlan.example", { ex }));
  log(t("envPlan.default", { value: info.default ?? "" }));
  log("");
}

// 지정 KEY들을 하나씩 입력받아 values에 기록 (.sh _wf_prefill_interactive 등가).
// 빈 입력(Enter)/ESC → KEY 공통 기본값 유지 (.sh safe_read || _in="" 등가).
async function promptEach(io, prompts, asks, todoKeys, values, log) {
  const tot = todoKeys.length;
  if (tot === 0) return;
  log("");
  log(t("envPlan.enterValues"));
  log("");
  let i = 0;
  for (const key of todoKeys) {
    i++;
    const def = asks.defaults.get(key) ?? "";
    printFieldCard(prompts, key, { default: def, usages: asks.usages.get(key) || [] }, i, tot, log);
    let input = await io.text({ message: t("envPlan.valuePrompt", { def }), defaultValue: def });
    if (input === CANCEL || input == null || input === "") input = def;
    values.set(key, input);
    const label = wfField(prompts, firstTypeFor(asks.usages, key), key, "label");
    log(`         → ${label} = ${input}`);
    log("");
  }
}

// 배포 env 설정 계획 (.sh wf_prompt_env_plan 등가).
// 반환: { values: Map<key,value>, useDefaults: boolean }
//  - useDefaults=true  → 호출부는 substituteEnv에 그대로 넘기면 타입별 기본값 경로(.sh _wf_prefill_all 등가)
//  - useDefaults=false → values에 담긴 키만 사용자 확정값으로 치환, 나머지는 기본값
//    (⚠️ substituteEnv는 useDefaults=false일 때만 values를 참조하므로 이 플래그를 반드시 함께 전달)
// 인자:
//   tempDir/types/resolvers/deployTarget/publishTargets — collectAsks와 동일 의미
//   targetRoot — wizard-prompts.yml 1차 탐색 위치(기본 ".")
//   force      — true면 질문 없이 전부 기본값 (.sh FORCE_MODE 등가)
//   io         — {select, multiselect, text} 주입 (기본 readline-engine). 테스트 스텁 지점.
//   log        — 카드·안내 출력 함수 주입 (기본 stderr)
export async function promptEnvPlan({
  tempDir, types = [], io = null, force = false, resolvers = {},
  deployTarget = "docker-ssh", publishTargets = [], targetRoot = ".", repoName = "", log = defaultLog,
} = {}) {
  const prompts = loadWizardPrompts(targetRoot, tempDir);
  const asks = collectAsks(tempDir, types, { resolvers, deployTarget, publishTargets, prompts, repoName });
  const defaults = asks.defaults;

  // 수집 키 0개 → 질문 자체가 없음 (.sh `[ ${#WF_ASK_KEYS[@]} -eq 0 ]` 등가)
  if (asks.keys.length === 0) return { values: new Map(), useDefaults: true };

  // 비대화형: force 또는 (io 미주입 && 비TTY) → 전부 기본값 (.sh FORCE_MODE/TTY_AVAILABLE 분기 등가)
  // io가 주입돼 있으면(테스트/상위 마법사) TTY 여부와 무관하게 대화형으로 진행한다.
  const interactive = !force && (io != null || stdin.isTTY);
  if (!interactive) return { values: new Map(defaults), useDefaults: true };

  const ui = io ?? engine;

  // 기본값 미리보기 카드 전체 출력 (.sh 3237~3251)
  log("");
  log(t("envPlan.title"));
  log("");
  log(t("envPlan.intro1"));
  log(t("envPlan.intro2"));
  log("");
  const tot = asks.keys.length;
  asks.keys.forEach((key, i) => {
    printFieldCard(prompts, key, { default: defaults.get(key), usages: asks.usages.get(key) || [] }, i + 1, tot, log);
  });
  log("   ─────────────────────────────────────────────");

  const choice = await ui.select({
    message: t("envPlan.how"),
    options: [
      { value: "all", label: t("envPlan.optAll") },
      { value: "each", label: t("envPlan.optEach") },
      { value: "some", label: t("envPlan.optSome") },
    ],
  });
  // ESC/취소 → 전부 기본값 (.sh `if [ "$_rc" -ne 0 ]` 등가)
  if (choice === CANCEL || choice == null || choice === "all") {
    return { values: new Map(defaults), useDefaults: true };
  }

  // 사용자가 확정한 키만 values에 담는다 — substituteEnv(useDefaults:false)가
  // values에 없는 키는 타입별 기본값으로 채우므로 .sh(_wf_prefill_all 후 덮어쓰기)와 등가.
  const values = new Map();
  if (choice === "each") {
    await promptEach(ui, prompts, asks, asks.keys, values, log);
    return { values, useDefaults: false };
  }

  // some: 바꿀 항목만 멀티선택 → 고른 것만 입력 (.sh 3266~3277)
  const options = asks.keys.map((key) => ({
    value: key,
    label: `${wfField(prompts, firstTypeFor(asks.usages, key), key, "label")}  ${t("envPlan.defaultTag", { value: defaults.get(key) })}`,
  }));
  const selected = await ui.multiselect({
    message: t("envPlan.pickPrompt"),
    options,
    initialValues: [],
  });
  // ESC/빈 선택 → 전부 기본값 (.sh: _wf_prefill_all만 수행)
  if (selected === CANCEL || !Array.isArray(selected) || selected.length === 0) {
    return { values: new Map(defaults), useDefaults: true };
  }
  // 수집 키 순서 유지 + WF_ASK_KEYS 멤버만 인정 (.sh _wf_prefill_interactive 필터 등가)
  const todo = asks.keys.filter((k) => selected.includes(k));
  await promptEach(ui, prompts, asks, todo, values, log);
  return { values, useDefaults: false };
}
