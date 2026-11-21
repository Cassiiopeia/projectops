// Deploy/publish axes (#439) + secret backup opt-in questions.
//
// io injection contract (readline-engine signatures):
//   io.confirm({message, initialValue})            → bool | CANCEL(symbol)
//   io.select({message, options})                  → value | CANCEL   (deploy, pick one)
//   io.multiselect({message, options, initialValues}) → value[] | CANCEL (publish, multiple)
//   io.log(line)                                   → notice output (stderr if missing)
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { listYamlFiles } from "./fsutil.js";
import { PATHS } from "./paths.js";
import { t as msg } from "../i18n/index.js";
import { parseTemplateOptions, inferIntent } from "./version-yml.js";
import { branchStatus, createBranch, pushBranch } from "./git-branch.js";
import { DEPLOY_TARGETS, PUBLISH_TARGETS, CHANGELOG_PROVIDERS, DEFAULT_CODE_REVIEW_CODERABBIT } from "./constants.js";
import { PROJECT_TYPES } from "./project-types.js";

// Check the development (release) branch exists + offer to create it (#477) — interactive only.
// If missing locally and missing (or unknown) on the remote, offer to create it from the default branch, then ask whether to push.
// No git, not a repo, or cannot ask (no io.confirm) → pass quietly — never block the wizard.
// Returns ready (#490 — lets the finish summary decide whether to drop the "create the branch" reminder):
//   true  = the branch already existed or was created in this run → no creation notice in the summary
//   false = missing and the user declined or creation failed → keep the notice
//   null  = could not check at all (not a repo, cannot ask) → keep the notice (conservative)
// Returns state (#715 — for recording non-interactive results): not-checked · not-a-repo · exists-local · exists-remote ·
//   declined · create-failed · push-declined · pushed · push-failed
// isNonInteractive: blocks credential prompts in remote lookup and push (#988 — interactive unchanged)
// missingMessageKey · createInitialValue · pushInitialValue: the deploy branch (#1248) reuses this flow with its own
//   notice and both answers defaulting to no (its first push runs the deploy workflows)
export async function ensureDeployBranch({
  targetRoot = ".", deployBranch = "", defaultBranch = "", io = {}, say = () => {}, isNonInteractive = false,
  missingMessageKey = "options.branch.missing", createInitialValue = true, pushInitialValue = true,
}) {
  if (!deployBranch || typeof io.confirm !== "function") return { created: false, pushed: false, ready: null, state: "not-checked" };
  const st = branchStatus(targetRoot, deployBranch, { isNonInteractive });
  if (!st.isRepo) return { created: false, pushed: false, ready: null, state: "not-a-repo" };
  if (st.local) return { created: false, pushed: false, ready: true, state: "exists-local" };
  if (st.remote === true) {
    say(msg("options.branch.remoteOnly", { branch: deployBranch }));
    return { created: false, pushed: false, ready: true, state: "exists-remote" };
  }
  say(msg(missingMessageKey, { branch: deployBranch, base: defaultBranch || msg("options.branch.baseFallback") }));
  const mk = await io.confirm({ message: msg("options.branch.createPrompt", { base: defaultBranch || msg("options.branch.currentFallback"), branch: deployBranch }), initialValue: createInitialValue });
  if (mk !== true) {
    say(msg("options.branch.skipped", { branch: deployBranch }));
    return { created: false, pushed: false, ready: false, state: "declined" };
  }
  if (!createBranch(targetRoot, deployBranch, defaultBranch)) {
    say(msg("options.branch.createFailed", { branch: deployBranch, from: defaultBranch ? ` ${defaultBranch}` : "" }));
    return { created: false, pushed: false, ready: false, state: "create-failed" };
  }
  say(msg("options.branch.created", { branch: deployBranch }));
  // #481 — name the branch in the push question (avoids "which branch is being pushed" confusion)
  const up = await io.confirm({ message: msg("options.branch.pushPrompt", { branch: deployBranch }), initialValue: pushInitialValue });
  if (up !== true) return { created: true, pushed: false, ready: true, state: "push-declined" };
  if (pushBranch(targetRoot, deployBranch, { isNonInteractive })) {
    say(msg("options.branch.pushed", { branch: deployBranch }));
    return { created: true, pushed: true, ready: true, state: "pushed" };
  }
  say(msg("options.branch.pushFailed", { branch: deployBranch }));
  return { created: true, pushed: false, ready: true, state: "push-failed" };
}

// Re-export — the parser itself lives in version-yml.js (avoids circular import: only options-ask → version-yml is allowed)
export { parseTemplateOptions };

// core/constants.js owns the value lists. Re-exported so existing import paths keep working.
export { DEPLOY_TARGETS, PUBLISH_TARGETS, CHANGELOG_PROVIDERS };

// #498 — deploy/publish targets applicable per type.
// Empty array = the axis does not apply to that type. Mobile apps (flutter/react-native/expo) always include store deploy
// (Play Store/TestFlight/Firebase, etc.) workflows in the type itself, so the server deploy axis does not
// apply and there is no registry publish either. If only types with both axes empty are selected, the questions are skipped.
// Server types keep all current choices (behavior unchanged — per-type refinement is follow-up work).
// Values come from the registry axes (src/core/project-types.json).
export const TYPE_DEPLOY_TARGETS = Object.fromEntries(PROJECT_TYPES.map((type) => [type.id, [...type.axes.deploy]]));
export const TYPE_PUBLISH_TARGETS = Object.fromEntries(PROJECT_TYPES.map((type) => [type.id, [...type.axes.publish]]));

// Applicable targets = union over the selected types (#498). 'none' is always allowed, so it is left out of the list.
// Undeclared types allow everything conservatively (question kept); registered types always declare their axes.
export function applicableTargets(types = []) {
  const deployAll = DEPLOY_TARGETS.filter((t) => t !== "none");
  return {
    deploy: deployAll.filter((t) => types.some((ty) => (TYPE_DEPLOY_TARGETS[ty] ?? deployAll).includes(t))),
    publish: PUBLISH_TARGETS.filter((t) => types.some((ty) => (TYPE_PUBLISH_TARGETS[ty] ?? PUBLISH_TARGETS).includes(t))),
  };
}
// changelog generator provider (#455, reworked in #566).
// Default is commit — no external dependency, so it works in any environment. To use AI,
// register a per-service key (GEMINI_API_KEY, etc.) and the ladder picks it up (the wizard does not ask).
// MODEL_API_KEY is the old name and is read only for backward compatibility.
// github-ai was dropped because GitHub Models shut down (2026-07-30).

// Move saved values that no longer work to working ones (#566).
// The only way an existing repo escapes a dead setting just by running an update.
const RETIRED_PROVIDERS = { "github-ai": "commit" };
export function migrateProvider(saved) {
  if (saved == null) return null;
  return RETIRED_PROVIDERS[saved] ?? saved;
}

const isCancel = (v) => typeof v === "symbol";

// One folder-based opt-in question, such as secret backup.
// Returns true/false/null (no folder or 0 files skips the question → keep the current value).
async function askOptionalWorkflow({ dir, icon, short, desc, current, force, tty, io, forceAsk, say }) {
  // Skip quietly when the folder is missing or has 0 yaml files — the question does not apply
  if (!existsSync(dir)) return current;
  const files = listYamlFiles(dir);
  if (files.length === 0) return current;

  // Keep an already-set value unless force-ask (CLI/version.yml first)
  if (!forceAsk && (current === true || current === false)) return current;

  // Non-interactive (--force or no TTY) excludes by default
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

/**
 * Deploy (trigger) branch question (#1248): explain the 3 branches > typed value > existence check (create only if asked)
 * Default = current value, else the default branch. Answering the default branch means no separate deploy branch ("").
 * Returns { deployTriggerBranch, deployTriggerBranchReady }
 */
async function askDeployTriggerBranch({ targetRoot, defaultBranch, current, io, say }) {
  say("");
  say(msg("options.deployBranch.intro"));
  say(msg("options.deployBranch.roles", { base: defaultBranch }));
  say(msg("options.deployBranch.why", { base: defaultBranch }));
  const ans = await io.text({ message: msg("options.deployBranch.prompt"), initialValue: current || defaultBranch });
  const typed = (typeof ans === "string" && !isCancel(ans) && ans.trim()) ? ans.trim() : (current || defaultBranch);
  if (typed === defaultBranch) {
    say(msg("options.deployBranch.chosenDefault", { base: defaultBranch }));
    return { deployTriggerBranch: "", deployTriggerBranchReady: null };
  }
  say(msg("options.deployBranch.chosen", { value: typed }));
  const br = await ensureDeployBranch({
    targetRoot, deployBranch: typed, defaultBranch, io, say,
    missingMessageKey: "options.deployBranch.missing", createInitialValue: false, pushInitialValue: false,
  });
  return { deployTriggerBranch: typed, deployTriggerBranchReady: br.ready };
}

// Axis keys of the option questions (#483 edit scope unit) — the edit menu re-asks one axis at a time.
// intent (#485) is the project nature — re-asking it re-derives the deploy/publish axes.
export const OPTION_AXES = ["intent", "deploy", "publish", "code-review", "changelog", "release-branch", "secret"];

// intent → which deploy axes to ask (#485). manual asks both (old sequential questions); the rest are derived.
const INTENT_ASKS_DEPLOY = { app: true, both: true, manual: true, library: false, none: false };
const INTENT_ASKS_PUBLISH = { library: true, both: true, manual: true, app: false, none: false };

// Ask the deploy/publish axes + secret backup in order.
// tempDir: template download root — project-types is at {tempDir}/.github/workflows/project-types
// current: { deploy: string|null, publish: string[]|null, secretBackup: bool|null } — explicit CLI values
// scope: null means all axes (initial integration, re-ask all). A Set/array limits forceAsk to those axes (#483 edit menu isolation).
//        Axes outside the scope keep current/saved values even with forceAsk and are not asked again.
// Returns { deploy, publish, secretBackup, codeReviewCoderabbit, aiPrSummary, changelogProvider, changelogBaseUrl, deployBranch, deployTriggerBranch }
export async function askAllOptionalWorkflows({
  tempDir, types = [], current = {}, targetRoot = ".",
  force = false, tty = true, io = {}, forceAsk = false, defaultBranch = "", scope = null,
}) {
  const say = io.log || ((m) => process.stderr.write(`${m}\n`));
  // Per-axis re-ask: forced only with global forceAsk and when scope is absent or includes that axis.
  const scopeSet = scope == null ? null : new Set(scope);
  const ask = (axis) => forceAsk && (scopeSet === null || scopeSet.has(axis));
  let deploy = current.deploy ?? null;
  let publish = current.publish ?? null;
  let secretBackup = current.secretBackup ?? null;
  let codeReviewCoderabbit = current.codeReviewCoderabbit ?? null;
  let aiPrSummary = current.aiPrSummary ?? null;
  let changelogProvider = current.changelogProvider ?? null;
  let changelogBaseUrl = current.changelogBaseUrl ?? null;
  let deployBranch = current.deployBranch ?? null; // #456 release PR head branch
  let deployBranchReady = null; // #490 — whether the branch was confirmed/created in this run (null = not checked)
  let deployBranchCreated = null; // #493 — whether the wizard created it in this run (for the guide record)
  let deployTriggerBranch = current.deployTriggerBranch ?? null; // #1248 deploy branch ("" = the default branch)
  let deployTriggerBranchReady = null; // #1248 — same meaning as deployBranchReady
  let intent = current.intent ?? null; // #485 project nature (app/library/both/none/manual)

  // Type combinations with both axes empty (#498 — basic alone, or a mobile app like flutter alone) have neither server deploy
  // nor library publish. Skip every question and settle quietly on none·[]
  // (mobile store deploy is always included by the type workflows, so no notice is needed — re-asked when the type changes).
  // A generalization of the old isBasicOnly special case.
  const applicable = applicableTargets(types);
  const noAxes = types.length > 0 && applicable.deploy.length === 0 && applicable.publish.length === 0;

  // ① Unless --force-ask, read saved version.yml values first to skip re-asking.
  //    Explicit CLI values (current) win — saved values only fill the gaps.
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
      // #455 reuse saved changelog/code_review values
      if (codeReviewCoderabbit === null && saved.codeReviewCoderabbit !== null) codeReviewCoderabbit = saved.codeReviewCoderabbit;
      if (aiPrSummary === null && saved.aiPrSummary != null) aiPrSummary = saved.aiPrSummary;
      if (changelogProvider === null && saved.changelogProvider !== null) changelogProvider = saved.changelogProvider;
      if (changelogBaseUrl === null && saved.changelogBaseUrl !== null) changelogBaseUrl = saved.changelogBaseUrl;
      // #456 reuse the saved development branch
      if (deployBranch === null && saved.deployBranch != null) deployBranch = saved.deployBranch;
      if (deployTriggerBranch === null && saved.deployTriggerBranch != null) deployTriggerBranch = saved.deployTriggerBranch;
      // #485 reuse the saved intent — if missing, infer it from saved deploy/publish (compat with old version.yml)
      if (intent === null) intent = saved.intent ?? inferIntent(saved.deploy, saved.publish);
    }
  }

  // Quietly clean up non-applicable targets (#498) — meaningless values saved by old versions (e.g. flutter alone + docker-ssh)
  // produce the same copy result anyway, so they are reduced to none/the intersection without warning (SSOT — no meaningless leftovers).
  if (deploy !== null && deploy !== "none" && !applicable.deploy.includes(deploy)) deploy = "none";
  if (Array.isArray(publish)) publish = publish.filter((t) => applicable.publish.includes(t));

  // ── ② intent (project nature) first → derive the deploy axes (#485) ──
  // For type combinations with both axes empty, intent does not apply: skip the question and settle on none/[] (#498).
  if (noAxes) {
    if (deploy === null) deploy = "none";
    if (publish === null) publish = [];
    intent = "none";
  } else {
    // When the edit menu targets only the deploy/publish axis (that axis in scope, no intent),
    // skip the intent question and gating and edit that axis directly (#483 isolation). intent keeps its value or is inferred.
    const scopedAxisOnly = scopeSet !== null && !scopeSet.has("intent");
    if (scopedAxisOnly) {
      if (intent === null) intent = inferIntent(deploy, publish) ?? "manual";
    } else {
      // intent question: when unsettled (initial integration) or the intent axis is force re-asked (edit menu "project nature").
      const askIntent = ask("intent") || intent === null;
      if (askIntent) {
        if (force || !tty || typeof io.select !== "function") {
          // Non-interactive: if the CLI gave no intent, infer from deploy/publish; failing that, manual (old behavior)
          // If the axes are not set yet, infer from the same default axes as non-interactive (resolve-options.js) (#851).
          // Inferring from null would record "manual", splitting the results of the two paths for the same repo.
          const defaultDeploy = applicable.deploy.includes("docker-ssh") ? "docker-ssh" : "none";
          intent = intent ?? inferIntent(deploy ?? defaultDeploy, publish ?? []) ?? "manual";
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
        // After intent is settled: axes not asked get their values settled; asked axes go back to be re-asked.
        if (!INTENT_ASKS_DEPLOY[intent]) deploy = "none";
        if (!INTENT_ASKS_PUBLISH[intent]) publish = [];
        if (INTENT_ASKS_DEPLOY[intent] && ask("intent")) deploy = null;
        if (INTENT_ASKS_PUBLISH[intent] && ask("intent")) publish = null;
      }
    }
    // Once intent is set, decide per axis whether to ask, by the derivation rules (#485).
    // With scopedAxisOnly (single axis from the edit menu), ignore the intent gate and edit that axis.
    const deployGate = scopedAxisOnly ? true : INTENT_ASKS_DEPLOY[intent];
    const publishGate = scopedAxisOnly ? true : INTENT_ASKS_PUBLISH[intent];
    const willAskDeploy = deployGate && (ask("deploy") || deploy === null);
    const willAskPublish = publishGate && (ask("publish") || publish === null);
    // Axes not asked by derivation get their defaults.
    if (!deployGate && deploy === null) deploy = "none";
    if (!publishGate && publish === null) publish = [];
    // When manual (pick yourself) asks both, explain once that the two axes are separate (carried over from #480).
    if (intent === "manual" && willAskDeploy && willAskPublish && tty && typeof io.select === "function") {
      say("");
      say(msg("options.axes.intro"));
      say(msg("options.axes.one"));
      say(msg("options.axes.two"));
    }
    // Non-interactive/fallback default (#498) — docker-ssh only when applicable, else none.
    const deployDefault = applicable.deploy.includes("docker-ssh") ? "docker-ssh" : "none";
    if (willAskDeploy) {
      if (force || !tty || typeof io.select !== "function") {
        deploy = deploy ?? deployDefault;
      } else {
        say("");
        say(msg("options.deploy.intro"));
        say(msg("options.deploy.hint"));
        // Filter choices to applicable targets (#498) — 'none' is always shown.
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

    // ── ③ publish targets (multi-select) ──
    if (willAskPublish) {
      if (force || !tty || typeof io.multiselect !== "function") {
        publish = publish ?? [];
      } else {
        say("");
        say(msg("options.publish.intro"));
        say(msg("options.publish.hint"));
        // Filter choices to applicable targets (#498)
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

  // ── pr_comment: review and summary posted on PRs (merged in #566) ──
  // CodeRabbit and the AI change summary compete for the same spot (PR comments), so they are chosen together
  // (asking separately leaves repos with neither).
  if (ask("code-review") || codeReviewCoderabbit === null || aiPrSummary === null) {
    if (force || !tty || typeof io.select !== "function") {
      // Non-interactive default: CodeRabbit works only with a separate app install, so
      // turning it on in automation is pointless. Only the summary, which works with no setup, is on.
      codeReviewCoderabbit = codeReviewCoderabbit ?? DEFAULT_CODE_REVIEW_CODERABBIT;
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
      // Cancel or no answer → the recommended value — the same defensive pattern as the other axes.
      const PR_COMMENT_CHOICES = ["summary", "coderabbit", "both", "none"];
      const pick = (!isCancel(ans) && PR_COMMENT_CHOICES.includes(ans)) ? ans : "summary";
      codeReviewCoderabbit = pick === "coderabbit" || pick === "both";
      aiPrSummary = pick === "summary" || pick === "both";
      say(msg("options.pr.chosen", { value: msg(`options.pr.label.${pick}`) }));
      // #481 — "use" alone is not enough. Reviews appear only with the app installed and repo access granted.
      if (codeReviewCoderabbit) {
        say(msg("options.pr.crWarn"));
        say(msg("options.pr.crStep1"));
        say(msg("options.pr.crStep2"));
        say(msg("options.pr.crStep3"));
      }
    }
  }

  // ── changelog: the generator is not asked (#566) ──
  // The user wants "good release notes", not a provider choice. Nobody knew what to pick,
  // and even the default (github-ai) was dead. Now the workflow finds the best option
  // itself — respect the PR body → Copilot → external AI (if a key exists) → commit analysis.
  // Saved values stay; only dead values are moved to working ones.
  changelogProvider = migrateProvider(changelogProvider) ?? "commit";

  // Ask base_url only when ollama is chosen (other providers get a preset base_url — #455)
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

  // ── Release source (development) branch (#456, version.yml development_branch — #915) ──
  //    This is the head of the release PR (development → default), the branch that collects work and goes up to the default branch.
  //    Not a "deploy branch" — deploys run on the default branch side. See #482.
  if (ask("release-branch") || deployBranch === null) {
    if (force || !tty || typeof io.text !== "function") {
      // Do not make up a value when we could not ask (#851) — if empty, nothing is recorded and skills fall back to develop.
      deployBranch = deployBranch ?? "";
    } else {
      const base = defaultBranch || "main"; // Default branch detected via git (#481 dynamic notice)
      say("");
      say(msg("options.devBranch.intro"));
      say(msg("options.devBranch.detected", { base }));
      say(msg("options.devBranch.hint"));
      const ans = await io.text({ message: msg("options.devBranch.prompt"), initialValue: deployBranch ?? "develop" });
      deployBranch = (typeof ans === "string" && !isCancel(ans) && ans.trim()) ? ans.trim() : (deployBranch ?? "develop");
      say(msg("options.devBranch.chosen", { value: deployBranch }));
      // Check the branch exists + offer to create it (#477) — otherwise the release pipeline sits idle silently
      // #490 — pass the result (ready) to the finish summary so an already created/confirmed branch is not re-requested
      const br = await ensureDeployBranch({ targetRoot, deployBranch, defaultBranch, io, say });
      deployBranchReady = br.ready;
      deployBranchCreated = br.created;
      // Deploy branch right after the development branch (#1248) — typed by the user, never created without asking
      ({ deployTriggerBranch, deployTriggerBranchReady } = await askDeployTriggerBranch({
        targetRoot, defaultBranch: base, current: deployTriggerBranch, io, say }));
    }
  }

  // ── ④ Secret backup: common folder (not a deploy axis — keeps the existing folder question) ──
  const real = join(tempDir, PATHS.workflowsDir, PATHS.projectTypesDir);
  const ptDir = existsSync(real) ? real : join(tempDir, PATHS.projectTypesDir);
  secretBackup = await askOptionalWorkflow({
    dir: join(ptDir, "common", "secret-backup"), icon: "🔐", short: msg("options.secret.short"),
    desc: msg("options.secret.desc"),
    current: secretBackup, force, tty, io, forceAsk: ask("secret"), say,
  });

  // The final fallback also uses applicable targets (#498) — so docker-ssh does not leak into mobile/basic combinations.
  const finalDeploy = deploy ?? (applicable.deploy.includes("docker-ssh") ? "docker-ssh" : "none");
  const finalPublish = publish ?? [];
  return {
    deploy: finalDeploy, publish: finalPublish, secretBackup: secretBackup === true,
    codeReviewCoderabbit: codeReviewCoderabbit === true,
    // #566 — whether the AI change summary workflow is included. Default true (works with no extra setup).
    aiPrSummary: aiPrSummary !== false,
    changelogProvider: changelogProvider ?? "commit",
    changelogBaseUrl: changelogBaseUrl ?? "",
    deployBranch: deployBranch ?? "",
    deployBranchReady, // #490 — true = confirmed/created, false = declined/failed, null = not checked
    deployBranchCreated, // #493 — true = created by the wizard in this run, null = not checked
    deployTriggerBranch: deployTriggerBranch ?? "", // #1248 — "" = deploys run on the default branch
    deployTriggerBranchReady, // #1248 — null = not asked or not checked

    // #485 intent — settled value first, else inferred from the final deploy/publish (fixes basic and non-interactive paths)
    intent: intent ?? inferIntent(finalDeploy, finalPublish) ?? "manual",
  };
}
