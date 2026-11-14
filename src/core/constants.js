// Source of truth for value lists that several files must share.
//
// Why one place: the deploy/publish lists were written separately in five places: CLI arg checks (args.js), wizard questions (options-ask.js),
// the copy engine (copy/workflows.js), the version.yml parser (version-yml.js) and the option table (options-schema.js).
// Fixing only one causes silent mismatches like "the CLI accepts it but the parser drops it".
// To add a value, change one line here and create the workflow folder for that value
// (deploy: project-types/common/deploy/<value>/ · publish: project-types/<type>/publish/<value>/).
//
// This file imports nothing — so it never causes a circular import wherever it is loaded.
// The repo text language list is owned by REPO_LANGUAGES in repo-language.js (checked together with the translation files).

/** Where the build output is deployed — pick one (#439) */
export const DEPLOY_TARGETS = Object.freeze(["docker-ssh", "vercel", "none"]);

/** Which registries a library is published to — 0..n (#439) */
export const PUBLISH_TARGETS = Object.freeze(["nexus", "npm", "github-packages"]);

/** Project nature — drives the deploy/publish questions (#485) */
export const INTENT_VALUES = Object.freeze(["app", "library", "both", "none", "manual"]);

/** Status label style — en: `status: todo`, ko: legacy Korean `작업전` (#776) */
export const LABEL_STYLES = Object.freeze(["en", "ko"]);

/**
 * Default for installing the CodeRabbit code review config when nothing is saved (#832).
 * Off — CodeRabbit needs a separate GitHub app, so turning it on without that leaves a config file and no reviewer.
 * Interactive (version/issues modes that do not ask) and non-interactive each had their own default and split into `true`/`false`; now in one place.
 */
export const DEFAULT_CODE_REVIEW_CODERABBIT = false;

/**
 * Release note generator (#455, #566). Default is commit — no external dependency, so it produces a result anywhere.
 * The implementations live in .github/scripts/changelog_providers/; a test checks this list matches them.
 */
export const CHANGELOG_PROVIDERS = Object.freeze(["copilot", "coderabbit", "openai", "gemini", "claude", "groq", "mistral", "ollama", "commit"]);
