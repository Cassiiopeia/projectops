// @wizard env plan question UI: build usages, collect ask KEYs, field cards, defaults and per-field input.
// io-injected — tests pass {select, multiselect, text} stubs. Default is the real readline-engine.
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

// Progress notices go to stderr (keeps the stdout pipe clean).
const defaultLog = (s = "") => stderr.write(s + "\n");

// Build the usages string.
// usages: [{type, workflowName}] — with several types, just "t1·t2"; with one, "type name1·name2".
export function scopeString(usages = []) {
  const types = []; const names = [];
  for (const { type, workflowName } of usages) {
    if (!types.includes(type)) types.push(type);
    if (!names.includes(workflowName)) names.push(workflowName);
  }
  if (types.length > 1) return types.join("·");
  return `${types.join("·")} ${names.join("·")}`.trim();
}

// Collect ask KEYs — scans the same source as the workflows actually installed.
// tempDir: downloaded source root. types: list of types to install.
// opts:
//   resolvers      - for resolving @-prefixed defaults (@repo, etc.) (resolved at collection time)
//   deployTarget   - #439 deploy axis: scan server-deploy only for docker-ssh (default) (matches the copy engine)
//   publishTargets - #439 publish axis: scan publish/<target>/ of the selected targets
//   prompts        - wizard-labels parsed object (for workflow display names; null falls back to stripping the extension)
// Returns { keys:[], defaults:Map<key,default>, typeDefaults:Map<"type|key",default>,
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
    // Same folder set as the copy engine: type direct children + (with docker-ssh) server-deploy + selected publish/<target>
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
          const p = parseWizardLine(line); // KEY regex [A-Z_]+
          if (!p || p.action !== "ask") continue;
          // Per-type default: resolve via resolver if @-prefixed, else literal
          // #489 — global tokens like __PROJECT_NAME__ are resolved before showing the card.
          //        Not showing the same value as the install (global substitution when copying files)
          //        would make users think "the literal gets written as is?".
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

// The type where the KEY first appeared (for type override priority in label lookup)
function firstTypeFor(usages, key) {
  return usages.get(key)?.[0]?.type ?? "";
}

// Print one KEY as a 'label · usages · description · example · default' card.
// info: { default, usages } — with idx/tot, shows "(i/t)" progress. log is injectable (silenced in tests).
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

// Ask for the given KEYs one by one and record them in values.
// Empty input (Enter)/ESC → keep the KEY's shared default.
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

// Deploy env setup plan.
// Returns { values: Map<key,value>, useDefaults: boolean }
//  - useDefaults=true  → the caller passes it as is to substituteEnv for the per-type default path
//  - useDefaults=false → only keys in values are substituted with confirmed user values; the rest use defaults
//    (⚠️ substituteEnv reads values only when useDefaults=false, so always pass this flag along)
// Arguments:
//   tempDir/types/resolvers/deployTarget/publishTargets — same meaning as in collectAsks
//   targetRoot — first place to look for wizard-prompts.yml (default ".")
//   force      — when true, all defaults without questions
//   io         — {select, multiselect, text} injection (default readline-engine). Test stub point.
//   log        — injected output function for cards and notices (default stderr)
export async function promptEnvPlan({
  tempDir, types = [], io = null, force = false, resolvers = {},
  deployTarget = "docker-ssh", publishTargets = [], targetRoot = ".", repoName = "", log = defaultLog,
} = {}) {
  const prompts = loadWizardPrompts(targetRoot, tempDir);
  const asks = collectAsks(tempDir, types, { resolvers, deployTarget, publishTargets, prompts, repoName });
  const defaults = asks.defaults;

  // 0 collected keys → no questions at all
  if (asks.keys.length === 0) return { values: new Map(), useDefaults: true };

  // Non-interactive: force or (no io injected && non-TTY) → all defaults
  // If io is injected (tests/parent wizard), proceed interactively regardless of TTY.
  const interactive = !force && (io != null || stdin.isTTY);
  if (!interactive) return { values: new Map(defaults), useDefaults: true };

  const ui = io ?? engine;

  // Print the whole default preview card
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
  // ESC/cancel → all defaults
  if (choice === CANCEL || choice == null || choice === "all") {
    return { values: new Map(defaults), useDefaults: true };
  }

  // Only keys the user confirmed go into values — substituteEnv (useDefaults:false)
  // fills keys missing from values with per-type defaults (input overrides defaults).
  const values = new Map();
  if (choice === "each") {
    await promptEach(ui, prompts, asks, asks.keys, values, log);
    return { values, useDefaults: false };
  }

  // some: multi-select only the items to change → input only those
  const options = asks.keys.map((key) => ({
    value: key,
    label: `${wfField(prompts, firstTypeFor(asks.usages, key), key, "label")}  ${t("envPlan.defaultTag", { value: defaults.get(key) })}`,
  }));
  const selected = await ui.multiselect({
    message: t("envPlan.pickPrompt"),
    options,
    initialValues: [],
  });
  // ESC/empty selection → all defaults
  if (selected === CANCEL || !Array.isArray(selected) || selected.length === 0) {
    return { values: new Map(defaults), useDefaults: true };
  }
  // Keep the collected key order + accept only collected ask KEYs
  const todo = asks.keys.filter((k) => selected.includes(k));
  await promptEach(ui, prompts, asks, todo, values, log);
  return { values, useDefaults: false };
}
