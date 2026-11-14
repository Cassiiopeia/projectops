// The single place that decides install option values (#851).
//
// Non-interactive (src/index.js) and interactive (src/commands/interactive.js) use the same result.
// Deciding separately splits the rules: the interactive PR summary choice was lost (aiPrSummary),
// and version mode, which skips questions, left deploy: docker-ssh in mobile-only repos.
// The rule is the same for every option: CLI flag > saved version.yml value > default.
// Interactive uses this result as initial values and overwrites only what the user answered.
import { existsSync } from "node:fs";
import { join } from "node:path";
import { applicableTargets, migrateProvider } from "./options-ask.js";
import { DEFAULT_CODE_REVIEW_CODERABBIT } from "./constants.js";
import { resolveLabelStyle } from "./label-style.js";
import { resolveRepoLanguage } from "./repo-language.js";

// File that marks Projects sync as on when already installed (#716)
export const PROJECTS_SYNC_WORKFLOW = ".github/workflows/PROJECT-COMMON-PROJECTS-SYNC-MANAGER.yaml";

// Clean up axis values that do not apply to the type (#498). Mobile app or basic alone leaves both axes empty
// and intent settles as none. Kept separate so the same rule can be reapplied to values from questions.
export function normalizeAxes({ deploy, publish, intent, types }) {
  const applicable = applicableTargets(types);
  const outDeploy = deploy !== "none" && !applicable.deploy.includes(deploy) ? "none" : deploy;
  const outPublish = publish.filter((t) => applicable.publish.includes(t));
  const noAxes = types.length > 0 && applicable.deploy.length === 0 && applicable.publish.length === 0;
  return { deploy: outDeploy, publish: outPublish, intent: noAxes ? "none" : intent, applicable };
}

// flags: option-related values from parseArgs (none → {} — interactive initial values)
// existing: parseExisting result or null
// Returns { values, sources } — sources lets the trace record "why this value" (#561).
export function resolveOptions({ flags = {}, existing = null, types = [], cwd = "." }) {
  const stored = existing?.options ?? {};
  const applicable = applicableTargets(types);

  // Project nature (#485): CLI --intent → saved value. Basis for deriving deploy/publish.
  let intent = flags.intent ?? stored.intent ?? null;
  // Deploy/publish axes (#439): flag → saved value → default (docker-ssh only when applicable — #498).
  let deploy = flags.deployTarget ?? stored.deploy
    ?? (applicable.deploy.includes("docker-ssh") ? "docker-ssh" : "none");
  let publish = flags.publishTargets ?? stored.publish ?? [];
  // With --intent and no flag for that axis, intent derives the axis (#485 non-interactive)
  if (flags.intent != null) {
    if ((intent === "library" || intent === "none") && flags.deployTarget == null) deploy = "none";
    if ((intent === "app" || intent === "none") && flags.publishTargets == null) publish = [];
  }
  const before = { deploy, publish: [...publish] };
  ({ deploy, publish, intent } = normalizeAxes({ deploy, publish, intent, types }));

  const values = {
    intent, deployTarget: deploy, publishTargets: publish,
    includeSecretBackup: flags.includeSecretBackup ?? stored.secretBackup ?? false,
    // #566 — works with no setup, so on by default
    aiPrSummary: flags.aiPrSummary ?? stored.aiPrSummary ?? true,
    // #716 — installed in a new repo without setup (Secret, PROJECT_URL) it only piles up notices. Existing installs keep it.
    projectsSync: flags.projectsSync ?? stored.projectsSync ?? existsSync(join(cwd, PROJECTS_SYNC_WORKFLOW)),
    // #502 — keeps version mode from downgrading an existing full integration record (full wins)
    recordMode: existing?.templateMode === "full" ? "full" : "version",
    // #456 — not written to version.yml when empty (skills fall back to develop). Records only what the user chose or passed as a flag.
    deployBranch: flags.deployBranch || stored.deployBranch || "",
    // #1114 — when empty, workflows are untouched and nothing is written to version.yml (existing repos unchanged)
    deployTriggerBranch: flags.deployTriggerBranch || stored.deployTriggerBranch || "",
    // #1114 — recorded and substituted only when on. When off, install output is byte-identical
    ciMinutesSaver: flags.ciMinutesSaver ?? stored.ciMinutesSaver ?? false,
    // #455 — prevents the bug where null flowed through and was recorded as provider:"null"
    changelogProvider: migrateProvider(stored.changelogProvider) ?? "commit",
    changelogBaseUrl: stored.changelogBaseUrl ?? "",
    codeReviewCoderabbit: flags.codeReviewCoderabbit ?? stored.codeReviewCoderabbit ?? DEFAULT_CODE_REVIEW_CODERABBIT,
    // #546, #814 — an explicit false is respected; when the key is missing, on for both new and existing
    semverAuto: stored.semverAuto ?? true,
    // Values the wizard does not ask about keep only the saved value (full regeneration drops anything not passed)
    appRelease: stored.appRelease ?? null,                 // #553
    excludedWorkflows: stored.excludedWorkflows ?? null,   // #810
    storeLocales: stored.storeLocales ?? null,             // #829
    storeLocalesIos: stored.storeLocalesIos ?? null,
    storeLocalesPlay: stored.storeLocalesPlay ?? null,
    // #771 — on for new installs only. Existing repos get no key and keep current behavior
    closeOnRelease: stored.closeOnRelease ?? (existing ? null : true),
    // #769, #776 — new en / existing ko. An update alone never changes existing repo text or labels
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
    // Whether semver_auto was turned on for the first time in an existing repo — the finish screen reports it
    semverAutoNewlyOn: !!existing && stored.semverAuto == null,
  };
  return { values, sources };
}

// Values recorded as version.yml options (same names as the resolveOptions result)
// If each entry point (full, version) picked its own, missing options revert to generator defaults (#909: version mode ai_summary false > true)
const TEMPLATE_OPTION_FIELDS = [
  "intent", "deployTarget", "publishTargets", "includeSecretBackup", "aiPrSummary", "projectsSync",
  "changelogProvider", "changelogBaseUrl", "codeReviewCoderabbit", "semverAuto", "appRelease",
  "excludedWorkflows", "storeLocales", "storeLocalesIos", "storeLocalesPlay", "closeOnRelease", "language", "labelStyle",
  "deployTriggerBranch", "ciMinutesSaver",
];

/** Run context (resolveOptions values spread out) > buildVersionYml templateOptions */
export function toTemplateOptions(context, { mode, optionsDate }) {
  const options = Object.fromEntries(TEMPLATE_OPTION_FIELDS.map((field) => [field, context[field]]));
  return { ...options, templateVersion: context.templateVersion, mode, optionsDate };
}
