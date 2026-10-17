// 경로 상수
export const PATHS = {
  tempDir: ".template_download_temp",
  versionFile: "version.yml",
  workflowsDir: ".github/workflows",
  scriptsDir: ".github/scripts",
  projectTypesDir: "project-types",
};

// 템플릿 레포 주소 정본: 소유자/이름 > 웹·git·raw 주소 (src/ 직접 기재는 no-repo-url-literal 규칙이 막는다)
export const TEMPLATE_REPO_OWNER = "Cassiiopeia";
export const TEMPLATE_REPO_SLUG = `${TEMPLATE_REPO_OWNER}/projectops`;
export const TEMPLATE_REPO_WEB_URL = `https://github.com/${TEMPLATE_REPO_SLUG}`;
export const TEMPLATE_RAW_URL = `https://raw.githubusercontent.com/${TEMPLATE_REPO_SLUG}/main`;
export const TEMPLATE_REPO = `${TEMPLATE_REPO_WEB_URL}.git`;
export const WORKFLOW_PREFIX = "PROJECT";
export const WORKFLOW_COMMON_PREFIX = "PROJECT-COMMON";
export const WORKFLOW_TEMPLATE_INIT = "PROJECT-TEMPLATE-INITIALIZER.yaml";
