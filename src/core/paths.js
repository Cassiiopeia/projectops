// Path constants
export const PATHS = {
  tempDir: ".template_download_temp",
  versionFile: "version.yml",
  workflowsDir: ".github/workflows",
  scriptsDir: ".github/scripts",
  projectTypesDir: "project-types",
};

// Template repo address source of truth: owner/name > web, git, raw URLs (the no-repo-url-literal rule blocks literals in src/)
export const TEMPLATE_REPO_OWNER = "Cassiiopeia";
export const TEMPLATE_REPO_SLUG = `${TEMPLATE_REPO_OWNER}/projectops`;
export const TEMPLATE_REPO_WEB_URL = `https://github.com/${TEMPLATE_REPO_SLUG}`;
export const TEMPLATE_RAW_URL = `https://raw.githubusercontent.com/${TEMPLATE_REPO_SLUG}/main`;
export const TEMPLATE_REPO = `${TEMPLATE_REPO_WEB_URL}.git`;
export const WORKFLOW_PREFIX = "PROJECT";
export const WORKFLOW_COMMON_PREFIX = "PROJECT-COMMON";
export const WORKFLOW_TEMPLATE_INIT = "PROJECT-TEMPLATE-INITIALIZER.yaml";
