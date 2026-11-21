// Wizard global state made explicit as one object (replaces the bash global variables)
// The next type was merged into react in v4.1.0 (breaking)
// Project types come from the registry (src/core/project-types.json, #1244)
export { VALID_TYPES } from "./core/project-types.js";

export const DEFAULT_VERSION = "1.3.14"; // When the template version is unknown (banner fallback — not used for breaking comparison)

export function createContext(overrides = {}) {
  return {
    mode: "interactive",
    force: false,
    types: [],
    version: "",
    branch: "",
    paths: new Map(),        // type -> path
    // Deploy/publish axes (#439 — type-independent. null = unset)
    deployTarget: null,      // 'docker-ssh' (default) | 'vercel' | 'none'
    publishTargets: null,    // subset of ['nexus','npm','github-packages']
    includeSecretBackup: null,
    projectsSync: null,  // Whether to include Projects board sync (#716). null = unset (new false / already-installed repos keep it)
    aiPrSummary: null,   // #566 — whether to include the AI change summary workflow
    // changelog provider axis (#455 — null = unset)
    changelogProvider: null, // 'commit' (default) | 'coderabbit' | 'openai' | 'gemini' | 'claude' | 'ollama' | 'commit'
    changelogBaseUrl: null,  // Only for ollama
    codeReviewCoderabbit: null,
    deployBranch: "",        // Release PR head branch (#456). Empty = metadata.development_branch not written
    deployTriggerBranch: "", // Branch whose push runs the deploy (#1114). Empty = same as the default branch (workflows as is)
    ciMinutesSaver: false,   // CI minutes saver substitution (#1114). false = workflows as is
    intent: null,            // Project nature (#485 — app/library/both/none/manual). null = unset (inferred)
    semverAuto: null,        // Automatic semver bump (#546). null = unset → true for new and existing (#814). Only an explicit false turns it off
    closeOnRelease: null,    // Close done issues on release (#771). null = unset (new true / no key in existing repos)
    language: null,          // Repo text language (#769). null = unset (new en / existing repos ko)
    labelStyle: null,        // Status label style (#776). null = unset (new en / existing repos ko)
    excludedWorkflows: null, // Workflow file names not to install (#810). null = none
    storeLocales: null,      // Store release note languages (#829). null = unset → current behavior kept
    storeLocalesIos: null,   // When only the App Store has a different language set (#829). null = use the shared store_locales
    storeLocalesPlay: null,  // When only Play has a different language set (#829)
    appRelease: null,        // Whether the repo deploys through app review (#553). null = unset (no key written)
    templateVersion: "",
    tempDir: "",
    deployValues: new Map(), // "type.KEY" -> value
    counters: {},
    ...overrides,
  };
}
