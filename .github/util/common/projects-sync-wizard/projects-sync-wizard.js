/**
 * GitHub Projects Sync Wizard v3.0.0
 *
 * Single-page version:
 * - every setting is completed on one page
 * - the script output contains all the guidance
 */

// ============================================
// State management
// ============================================

// Default Status Labels from issue-labels.yml
const DEFAULT_STATUS_LABELS = [
    '작업전',
    '작업중',
    '담당자확인',
    '피드백',
    '작업완료',
    '보류',
    '취소'
];

let state = {
    projectUrl: '',
    projectType: 'org',    // Organization only (User Projects not supported)
    ownerName: '',         // Organization name
    orgName: '',           // kept for backward compatibility
    projectNumber: '',
    workerName: 'github-projects-sync-worker',
    statusLabels: [...DEFAULT_STATUS_LABELS],
    webhookSecret: '',
    skipProjectsGuide: false,  // skip the Projects creation guide
    githubToken: ''        // GitHub PAT (repo, project scopes)
};

// ============================================
// Initialization
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    // Show version info
    displayVersion();

    // Initialize dark mode
    initDarkMode();

    // Restore saved state
    loadState();

    // Generate the Webhook Secret automatically (if missing)
    if (!state.webhookSecret) {
        generateWebhookSecret();
    }

    // Render labels
    renderLabels();
    renderDefaultLabelNames();

    // Worker name input event - auto-lowercase + update commands
    document.getElementById('workerName').addEventListener('input', (e) => {
        // Cloudflare naming rule: only lowercase letters, digits and hyphens
        const sanitized = sanitizeWorkerName(e.target.value);
        e.target.value = sanitized;
        state.workerName = sanitized || 'github-projects-sync-worker';
        saveState();
        scheduleCommandUpdate();
    });

    // Webhook Secret change event - update commands automatically
    document.getElementById('webhookSecret').addEventListener('input', (e) => {
        state.webhookSecret = e.target.value;
        saveState();
        scheduleCommandUpdate();
    });

    // GitHub Token input event - update commands automatically
    document.getElementById('githubToken').addEventListener('input', (e) => {
        state.githubToken = e.target.value;
        saveState();
        scheduleCommandUpdate();
    });

    // Show the initial commands
    updateInstallCommands();
});

// ============================================
// Version info
// ============================================

function displayVersion() {
    try {
        const versionJson = JSON.parse(document.getElementById('versionJson').textContent);
        const versionBadge = document.getElementById('versionBadge');
        if (versionBadge) {
            versionBadge.textContent = `v${versionJson.version}`;
        }
    } catch (e) {
        console.error('[projects sync] version load failed:', e);
    }
}

// ============================================
// Look up version data
// ============================================

function getVersionData() {
    try {
        const versionEl = document.getElementById('versionJson');
        if (versionEl) {
            return JSON.parse(versionEl.textContent);
        }
    } catch (e) {
        console.error('[projects sync] version parse failed:', e);
    }
    return null;
}

// ============================================
// Changelog modal
// ============================================

function openChangelogModal() {
    const modal = document.getElementById('changelogModal');
    const content = document.getElementById('changelogContent');
    const lastUpdated = document.getElementById('changelogLastUpdated');

    const data = getVersionData();
    if (!data) {
        content.innerHTML = `<div class="text-center text-red-500 py-4">${escapeHtml(translate('toast.versionLoadFailed'))}</div>`;
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        return;
    }

    // Build changelog HTML
    let html = '';
    data.changelog.forEach((release, index) => {
        const isLatest = index === 0;

        html += `
            <div class="pb-4 ${index < data.changelog.length - 1 ? 'border-b border-gray-200 dark:border-slate-700 mb-4' : ''}">
                <div class="flex items-center gap-2 mb-2">
                    <span class="text-gray-900 dark:text-white font-semibold">v${release.version}</span>
                    ${isLatest ? '<span class="px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 rounded-full">Latest</span>' : ''}
                    <span class="text-gray-400 dark:text-slate-500 text-xs">${release.date}</span>
                </div>
                <ul class="space-y-1.5 pl-2">
                    ${release.changes.map(change => `
                        <li class="text-sm text-gray-600 dark:text-slate-400 flex items-start gap-2">
                            <span class="text-gray-400 dark:text-slate-600 mt-1">•</span>
                            <span>${change}</span>
                        </li>
                    `).join('')}
                </ul>
            </div>
        `;
    });

    content.innerHTML = html;
    lastUpdated.textContent = `Last updated: ${data.lastUpdated}`;

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

function closeChangelogModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('changelogModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

// Close the changelog modal with ESC
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        const changelogModal = document.getElementById('changelogModal');
        if (changelogModal && !changelogModal.classList.contains('hidden')) {
            closeChangelogModal();
        }
    }
});

// ============================================
// Dark mode
// ============================================

function initDarkMode() {
    if (localStorage.getItem('darkMode') === 'true' ||
        (!localStorage.getItem('darkMode') && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
        document.documentElement.classList.add('dark');
    }
}

function toggleDarkMode() {
    document.documentElement.classList.toggle('dark');
    localStorage.setItem('darkMode', document.documentElement.classList.contains('dark'));
}

// ============================================
// Save/restore state
// ============================================

function saveState() {
    localStorage.setItem('projectsSyncWizardState', JSON.stringify(state));
}

function loadState() {
    try {
        const saved = localStorage.getItem('projectsSyncWizardState');
        if (saved) {
            const parsed = JSON.parse(saved);
            state = { ...state, ...parsed };

            // Reflect state in the UI
            document.getElementById('projectUrl').value = state.projectUrl || '';
            document.getElementById('ownerName').value = state.ownerName || state.orgName || '';
            document.getElementById('orgName').value = state.orgName || '';
            document.getElementById('projectNumber').value = state.projectNumber || '';
            document.getElementById('workerName').value = state.workerName || 'github-projects-sync-worker';
            document.getElementById('webhookSecret').value = state.webhookSecret || '';

            // Skip-Projects-guide checkbox
            const skipGuideCheckbox = document.getElementById('skipProjectsGuide');
            if (skipGuideCheckbox) {
                skipGuideCheckbox.checked = state.skipProjectsGuide || false;
                toggleProjectsGuide();
            }

            // GitHub Token (not saved for security - must be re-entered after a page refresh)
            // state.githubToken lives only for the session
            const githubTokenInput = document.getElementById('githubToken');
            if (githubTokenInput && state.githubToken) {
                githubTokenInput.value = state.githubToken;
            }

            // Update the UI by type
            updateUIForProjectType();

            // Show commands if already generated
            updateInstallCommands();
        }
    } catch (e) {
        console.error('[projects sync] state restore failed:', e);
    }
}

function resetWizard() {
    if (confirm(translate('confirm.reset'))) {
        localStorage.removeItem('projectsSyncWizardState');
        state = {
            projectUrl: '',
            projectType: 'org',
            ownerName: '',
            orgName: '',
            projectNumber: '',
            workerName: 'github-projects-sync-worker',
            statusLabels: [...DEFAULT_STATUS_LABELS],
            webhookSecret: '',
            skipProjectsGuide: false,
            githubToken: ''
        };
        generateWebhookSecret();
        renderLabels();

        // Reset input fields
        document.getElementById('projectUrl').value = '';
        document.getElementById('ownerName').value = '';
        document.getElementById('orgName').value = '';
        document.getElementById('projectNumber').value = '';
        document.getElementById('workerName').value = 'github-projects-sync-worker';

        // Hide the User Projects warning
        const userWarning = document.getElementById('userProjectsWarning');
        if (userWarning) {
            userWarning.classList.add('hidden');
        }

        // Reset the Projects guide checkbox
        const skipGuideCheckbox = document.getElementById('skipProjectsGuide');
        if (skipGuideCheckbox) {
            skipGuideCheckbox.checked = false;
        }

        // Reset the GitHub Token
        const githubTokenInput = document.getElementById('githubToken');
        if (githubTokenInput) {
            githubTokenInput.value = '';
        }

        // Reset the UI
        updateUIForProjectType();
        toggleProjectsGuide();
        updateInstallCommands();

        showToast(translate('toast.resetDone'));
    }
}

// ============================================
// Worker name utilities
// ============================================

// Make the Worker name follow Cloudflare rules (lowercase letters, digits, hyphens only)
function sanitizeWorkerName(name) {
    if (!name) return '';
    return name
        .toLowerCase()
        .replace(/[^a-z0-9-]/g, '-')  // disallowed characters → hyphen
        .replace(/-+/g, '-')           // collapse repeated hyphens
        .replace(/^-|-$/g, '');        // remove leading/trailing hyphens
}

// Build the default Worker name (from the Organization name)
function generateDefaultWorkerName() {
    // Use the Organization name
    if (!state.ownerName) {
        return 'github-projects-sync-worker';
    }

    // github-projects-{org}-sync-worker format
    const sanitized = sanitizeWorkerName(state.ownerName);
    return `github-projects-${sanitized}-sync-worker`;
}

// Set the Worker name automatically (called after URL parsing)
function autoSetWorkerName() {
    const workerInput = document.getElementById('workerName');
    if (!workerInput) return;

    // Set it automatically only if the user never edited it or it is the default
    const currentValue = workerInput.value.trim();
    const isDefault = currentValue === 'github-projects-sync-worker' || currentValue === '';

    if (isDefault) {
        const defaultName = generateDefaultWorkerName();
        workerInput.value = defaultName;
        state.workerName = defaultName;
        saveState();
    }
}

// ============================================
// Parse the Project URL
// ============================================

function parseProjectUrl() {
    const url = document.getElementById('projectUrl').value.trim();
    state.projectUrl = url;

    // User Projects warning element
    const userWarning = document.getElementById('userProjectsWarning');

    // Detect a User Projects URL → show a warning and block
    // https://github.com/users/USERNAME/projects/NUMBER[/views/VIEW_ID]
    const userMatch = url.match(/github\.com\/users\/([^\/]+)\/projects\/(\d+)(?:\/views\/\d+)?/);

    if (userMatch) {
        // User Projects detected - show the warning
        if (userWarning) {
            userWarning.classList.remove('hidden');
        }
        // Reset the parse result (User Projects not supported)
        state.projectType = 'org';
        state.ownerName = '';
        state.orgName = '';
        state.projectNumber = '';
        updateUIForProjectType();
        saveState();
        scheduleCommandUpdate();
        return;
    }

    // Hide the User Projects warning (when another URL is entered)
    if (userWarning) {
        userWarning.classList.add('hidden');
    }

    // Parse an Organization Projects URL
    // https://github.com/orgs/ORG-NAME/projects/NUMBER[/views/VIEW_ID]
    const orgMatch = url.match(/github\.com\/orgs\/([^\/]+)\/projects\/(\d+)(?:\/views\/\d+)?/);

    if (orgMatch) {
        state.projectType = 'org';
        state.ownerName = orgMatch[1];
        state.orgName = orgMatch[1]; // backward compatibility
        state.projectNumber = orgMatch[2];
        updateUIForProjectType();
        autoSetWorkerName();
        saveState();
        scheduleCommandUpdate();
        return;
    }

    // No match - reset
    state.projectType = 'org';
    state.ownerName = '';
    state.orgName = '';
    state.projectNumber = '';
    updateUIForProjectType();
    saveState();
    scheduleCommandUpdate();
}

// Update the UI by project type (Organization only)
function updateUIForProjectType() {
    const ownerNameInput = document.getElementById('ownerName');
    const projectNumberInput = document.getElementById('projectNumber');
    const projectTypeBadge = document.getElementById('projectTypeBadge');
    const parseResultSection = document.getElementById('parseResult');

    // Update the parse result fields
    if (ownerNameInput) {
        ownerNameInput.value = state.ownerName || '';
    }
    if (projectNumberInput) {
        projectNumberInput.value = state.projectNumber || '';
    }

    // Show/hide the parse result section
    if (parseResultSection) {
        if (state.ownerName && state.projectNumber) {
            parseResultSection.classList.remove('hidden');
        } else {
            parseResultSection.classList.add('hidden');
        }
    }

    // Update the project type badge (Organization only)
    if (projectTypeBadge) {
        if (state.ownerName && state.projectNumber) {
            projectTypeBadge.textContent = 'Organization';
            projectTypeBadge.className = 'px-3 py-1 rounded-full text-sm font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800';
        } else {
            projectTypeBadge.textContent = '-';
            projectTypeBadge.className = 'px-3 py-1 rounded-full text-sm font-medium bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400';
        }
    }

    // Also update the orgName field for backward compatibility
    const orgNameInput = document.getElementById('orgName');
    if (orgNameInput) {
        orgNameInput.value = state.orgName || '';
    }
}

// Projects guide toggle
function toggleProjectsGuide() {
    const checkbox = document.getElementById('skipProjectsGuide');
    const guideContent = document.getElementById('projectsGuideContent');

    if (checkbox && guideContent) {
        state.skipProjectsGuide = checkbox.checked;
        if (checkbox.checked) {
            guideContent.classList.add('hidden');
        } else {
            guideContent.classList.remove('hidden');
        }
        saveState();
    }
}


// ============================================
// Label management
// ============================================

/** Label names in the mapping guide table = DEFAULT_STATUS_LABELS (no copy kept in the HTML) */
function renderDefaultLabelNames() {
    document.querySelectorAll('[data-default-label-index]').forEach((element) => {
        element.textContent = DEFAULT_STATUS_LABELS[Number(element.dataset.defaultLabelIndex)] || '';
    });
}

function renderLabels() {
    const container = document.getElementById('labelsContainer');
    container.innerHTML = state.statusLabels.map((label, index) => `
        <div class="label-item flex items-center gap-2">
            <input type="text" value="${escapeHtml(label)}"
                class="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
                onchange="updateLabel(${index}, this.value)">
            <button onclick="removeLabel(${index})" class="p-2 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/>
                </svg>
            </button>
        </div>
    `).join('');
}

function addLabel() {
    state.statusLabels.push(translate('labels.newLabel'));
    renderLabels();
    saveState();
    scheduleCommandUpdate();
}

function updateLabel(index, value) {
    state.statusLabels[index] = value;
    saveState();
    scheduleCommandUpdate();
}

function removeLabel(index) {
    if (state.statusLabels.length > 1) {
        state.statusLabels.splice(index, 1);
        renderLabels();
        saveState();
        scheduleCommandUpdate();
    } else {
        showToast(translate('toast.minimumOneLabel'), 'error');
    }
}

function resetLabels() {
    state.statusLabels = [...DEFAULT_STATUS_LABELS];
    renderLabels();
    saveState();
    scheduleCommandUpdate();
    showToast(translate('toast.labelsRestored'));
}

// ============================================
// Generate the Webhook Secret
// ============================================

function generateWebhookSecret() {
    const array = new Uint8Array(32);
    crypto.getRandomValues(array);
    state.webhookSecret = Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
    document.getElementById('webhookSecret').value = state.webhookSecret;
    saveState();
    scheduleCommandUpdate();
}

// ============================================
// Generated file templates
// ============================================

function generateWranglerToml() {
    return `# ============================================
# Cloudflare Worker 설정
# GitHub Projects Sync Worker
# ============================================

name = "${state.workerName}"
main = "src/index.ts"
compatibility_date = "2024-01-01"

[vars]
PROJECT_NUMBER = "${state.projectNumber}"
STATUS_FIELD = "Status"
STATUS_LABELS = '${JSON.stringify(state.statusLabels)}'
ORG_NAME = "${state.orgName}"
`;
}

function generatePackageJson() {
    return JSON.stringify({
        name: state.workerName,
        version: "1.0.0",
        private: true,
        scripts: {
            deploy: "wrangler deploy",
            dev: "wrangler dev",
            tail: "wrangler tail"
        },
        devDependencies: {
            "@cloudflare/workers-types": "^4.20240117.0",
            "typescript": "^5.3.3",
            "wrangler": "^3.22.1"
        }
    }, null, 2);
}

function generateTsconfig() {
    return JSON.stringify({
        compilerOptions: {
            target: "ES2021",
            module: "ESNext",
            moduleResolution: "node",
            lib: ["ES2021"],
            types: ["@cloudflare/workers-types"],
            strict: true,
            noEmit: true,
            skipLibCheck: true
        },
        include: ["src/**/*"]
    }, null, 2);
}

function generateWorkerCode() {
    return `/**
 * GitHub Projects Sync Worker
 *
 * Syncs issue labels automatically when a GitHub Projects Status changes.
 *
 * Env vars (set in wrangler.toml):
 * - PROJECT_NUMBER: GitHub Projects number
 * - STATUS_FIELD: Status field name (default: "Status")
 * - STATUS_LABELS: Status labels to sync (JSON array)
 * - ORG_NAME: GitHub Organization name
 *
 * Secrets (set with wrangler secret put):
 * - GITHUB_TOKEN: GitHub Personal Access Token (repo, project scopes)
 * - WEBHOOK_SECRET: secret for GitHub webhook verification
 */

export interface Env {
  GITHUB_TOKEN: string;
  WEBHOOK_SECRET: string;
  PROJECT_NUMBER: string;
  STATUS_FIELD: string;
  STATUS_LABELS: string;
  ORG_NAME: string;
}

// GitHub webhook event type definitions
interface WebhookPayload {
  action: string;
  projects_v2_item?: {
    id: number;
    node_id: string;
    project_node_id: string;
    content_node_id: string;
    content_type: string;
  };
  changes?: {
    field_value?: {
      field_node_id: string;
      field_type: string;
    };
  };
  organization?: {
    login: string;
  };
  sender?: {
    login: string;
  };
}

// GraphQL response types
interface ProjectItemResponse {
  data?: {
    node?: {
      content?: {
        number: number;
        title: string;
        labels: {
          nodes: Array<{ name: string }>;
        };
        repository: {
          name: string;
          owner: {
            login: string;
          };
        };
      };
      fieldValueByName?: {
        name?: string;
      };
    };
  };
  errors?: Array<{ message: string }>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Handle POST requests only
    if (request.method !== 'POST') {
      return new Response('Method Not Allowed', { status: 405 });
    }

    // Verify the webhook signature
    const signature = request.headers.get('X-Hub-Signature-256');
    if (!signature) {
      console.log('❌ Missing signature header');
      return new Response('Missing signature', { status: 401 });
    }

    const body = await request.text();
    const isValid = await verifySignature(body, signature, env.WEBHOOK_SECRET);
    if (!isValid) {
      console.log('❌ Invalid signature');
      return new Response('Invalid signature', { status: 401 });
    }

    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('🔄 GitHub Projects Sync Worker');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('✅ Webhook signature verified');

    // Check the event type
    const event = request.headers.get('X-GitHub-Event');
    console.log(\`📌 Event type: \${event}\`);

    if (event !== 'projects_v2_item') {
      console.log('⏭️ Skipping non-projects_v2_item event');
      return new Response('OK - Event ignored', { status: 200 });
    }

    const payload: WebhookPayload = JSON.parse(body);
    console.log(\`📌 Action: \${payload.action}\`);

    // Handle only the edited action (Status change)
    if (payload.action !== 'edited') {
      console.log('⏭️ Skipping non-edited action');
      return new Response('OK - Action ignored', { status: 200 });
    }

    // Check field changes
    if (!payload.changes?.field_value) {
      console.log('⏭️ No field value change detected');
      return new Response('OK - No field change', { status: 200 });
    }

    const itemNodeId = payload.projects_v2_item?.node_id;
    if (!itemNodeId) {
      console.log('❌ No item node ID found');
      return new Response('OK - No item ID', { status: 200 });
    }

    console.log(\`📌 Processing item: \${itemNodeId}\`);

    try {
      // Look up the current Status and issue info with GraphQL
      const itemInfo = await getProjectItemInfo(itemNodeId, env);

      if (!itemInfo?.data?.node?.content) {
        console.log('❌ Could not get item content');
        return new Response('OK - No content', { status: 200 });
      }

      const content = itemInfo.data.node.content;
      const currentStatus = itemInfo.data.node.fieldValueByName?.name;
      const issueNumber = content.number;
      const repoName = content.repository.name;
      const repoOwner = content.repository.owner.login;
      const currentLabels = content.labels.nodes.map(l => l.name);

      console.log(\`📌 Issue: \${repoOwner}/\${repoName}#\${issueNumber}\`);
      console.log(\`📌 Current Labels: \${currentLabels.join(', ')}\`);
      console.log(\`📌 New Status: "\${currentStatus}"\`);

      if (!currentStatus) {
        console.log('⏭️ No status value');
        return new Response('OK - No status', { status: 200 });
      }

      // Parse Status Labels
      const statusLabels: string[] = JSON.parse(env.STATUS_LABELS);

      // Find existing Status Labels to remove
      const labelsToRemove = currentLabels.filter(label =>
        statusLabels.includes(label) && label !== currentStatus
      );

      console.log(\`🗑️ Labels to remove: \${labelsToRemove.join(', ') || 'none'}\`);

      // Skip if the same label already exists (prevents infinite loops)
      if (currentLabels.includes(currentStatus) && labelsToRemove.length === 0) {
        console.log('⏭️ Label already synced, skipping');
        return new Response('OK - Already synced', { status: 200 });
      }

      // Remove the label
      for (const label of labelsToRemove) {
        await removeLabel(repoOwner, repoName, issueNumber, label, env);
        console.log(\`  ✅ Label "\${label}" removed\`);
      }

      // Add the label if the new Status is in statusLabels
      if (statusLabels.includes(currentStatus) && !currentLabels.includes(currentStatus)) {
        console.log(\`➕ Adding label: "\${currentStatus}"\`);
        await addLabel(repoOwner, repoName, issueNumber, currentStatus, env);
        console.log(\`  ✅ Label "\${currentStatus}" added\`);
      }

      console.log('🎉 Label sync completed!');
      console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

      return new Response('OK - Synced', { status: 200 });

    } catch (error) {
      console.error('❌ Error:', error);
      return new Response('Internal Server Error', { status: 500 });
    }
  }
};

/**
 * Verify the webhook signature (HMAC-SHA256)
 */
async function verifySignature(payload: string, signature: string, secret: string): Promise<boolean> {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const signatureBytes = await crypto.subtle.sign(
    'HMAC',
    key,
    encoder.encode(payload)
  );

  const expectedSignature = 'sha256=' + Array.from(new Uint8Array(signatureBytes))
    .map(b => b.toString(16).padStart(2, '0'))
    .join('');

  // Timing-safe comparison
  if (signature.length !== expectedSignature.length) {
    return false;
  }

  let result = 0;
  for (let i = 0; i < signature.length; i++) {
    result |= signature.charCodeAt(i) ^ expectedSignature.charCodeAt(i);
  }
  return result === 0;
}

/**
 * Look up Project Item info with the GraphQL API
 */
async function getProjectItemInfo(nodeId: string, env: Env): Promise<ProjectItemResponse> {
  const query = \`
    query($nodeId: ID!, $statusField: String!) {
      node(id: $nodeId) {
        ... on ProjectV2Item {
          content {
            ... on Issue {
              number
              title
              labels(first: 20) {
                nodes {
                  name
                }
              }
              repository {
                name
                owner {
                  login
                }
              }
            }
            ... on PullRequest {
              number
              title
              labels(first: 20) {
                nodes {
                  name
                }
              }
              repository {
                name
                owner {
                  login
                }
              }
            }
          }
          fieldValueByName(name: $statusField) {
            ... on ProjectV2ItemFieldSingleSelectValue {
              name
            }
          }
        }
      }
    }
  \`;

  const response = await fetch('https://api.github.com/graphql', {
    method: 'POST',
    headers: {
      'Authorization': \`Bearer \${env.GITHUB_TOKEN}\`,
      'Content-Type': 'application/json',
      'User-Agent': 'GitHub-Projects-Sync-Worker'
    },
    body: JSON.stringify({
      query,
      variables: {
        nodeId,
        statusField: env.STATUS_FIELD || 'Status'
      }
    })
  });

  return response.json();
}

/**
 * Add a label with the REST API
 */
async function addLabel(owner: string, repo: string, issueNumber: number, label: string, env: Env): Promise<void> {
  const response = await fetch(
    \`https://api.github.com/repos/\${owner}/\${repo}/issues/\${issueNumber}/labels\`,
    {
      method: 'POST',
      headers: {
        'Authorization': \`Bearer \${env.GITHUB_TOKEN}\`,
        'Content-Type': 'application/json',
        'User-Agent': 'GitHub-Projects-Sync-Worker'
      },
      body: JSON.stringify({ labels: [label] })
    }
  );

  if (!response.ok) {
    const error = await response.text();
    console.error(\`Failed to add label: \${error}\`);
  }
}

/**
 * Remove a label with the REST API
 */
async function removeLabel(owner: string, repo: string, issueNumber: number, label: string, env: Env): Promise<void> {
  const encodedLabel = encodeURIComponent(label);
  const response = await fetch(
    \`https://api.github.com/repos/\${owner}/\${repo}/issues/\${issueNumber}/labels/\${encodedLabel}\`,
    {
      method: 'DELETE',
      headers: {
        'Authorization': \`Bearer \${env.GITHUB_TOKEN}\`,
        'User-Agent': 'GitHub-Projects-Sync-Worker'
      }
    }
  );

  if (!response.ok && response.status !== 404) {
    const error = await response.text();
    console.error(\`Failed to remove label: \${error}\`);
  }
}
`;
}

function generateConfigJson() {
    return JSON.stringify({
        orgName: state.orgName,
        projectNumber: state.projectNumber,
        workerName: state.workerName,
        webhookSecret: state.webhookSecret,
        statusLabels: state.statusLabels
    }, null, 2);
}

function generateReadme() {
    return `# GitHub Projects Sync Worker

GitHub Projects Status → Issue Label 자동 동기화 Worker

## 설정 정보

- **Organization:** ${state.orgName}
- **Project Number:** ${state.projectNumber}
- **Worker Name:** ${state.workerName}

## 설치 방법

### 1. 스크립트 실행 (권장)

\`\`\`bash
# Mac/Linux
./projects-sync-worker-setup.sh

# Windows PowerShell
.\\projects-sync-worker-setup.ps1
\`\`\`

스크립트가 자동으로:
1. npm 의존성 설치
2. Cloudflare 로그인
3. Worker 배포
4. Secrets 설정

### 2. 수동 설치

\`\`\`bash
# 의존성 설치
npm config set strict-ssl false
npm install
npm config set strict-ssl true

# Cloudflare 로그인
export NODE_TLS_REJECT_UNAUTHORIZED=0  # Mac/Linux
# $env:NODE_TLS_REJECT_UNAUTHORIZED=0  # Windows PowerShell
npx wrangler login

# Worker 배포
npx wrangler deploy

# Secrets 설정
npx wrangler secret put GITHUB_TOKEN
npx wrangler secret put WEBHOOK_SECRET
\`\`\`

## GitHub Webhook 설정

1. https://github.com/organizations/${state.orgName}/settings/hooks 이동
2. "Add webhook" 클릭
3. 설정:
   - **Payload URL:** Worker URL
   - **Content type:** application/json
   - **Secret:** config.json의 webhookSecret 값
   - **Events:** "Project v2 items" 선택

## 테스트

1. Projects Board에서 Issue 카드 이동
2. Issue Label 자동 변경 확인
3. 문제 시 로그 확인: \`npx wrangler tail\`

## Secrets

| Secret | 설명 |
|--------|------|
| GITHUB_TOKEN | GitHub PAT (repo, project 권한) |
| WEBHOOK_SECRET | config.json의 webhookSecret 값 |

---

Generated by GitHub Projects Sync Wizard v2.0.0
`;
}

function generateSetupScriptSh() {
    return `#!/bin/bash
# ============================================
# GitHub Projects Sync Worker 설치 스크립트
#
# 사용법: ./projects-sync-worker-setup.sh
# ============================================

set -e

RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
BLUE='\\033[0;34m'
CYAN='\\033[0;36m'
NC='\\033[0m'

echo ""
echo -e "\${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\${NC}"
echo -e "\${CYAN}   🔄 GitHub Projects Sync Worker 설치 스크립트\${NC}"
echo -e "\${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\${NC}"
echo ""

if [ ! -f "config.json" ]; then
    echo -e "\${RED}❌ config.json 파일을 찾을 수 없습니다.\${NC}"
    exit 1
fi

ORG_NAME=$(cat config.json | grep -o '"orgName"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
WORKER_NAME=$(cat config.json | grep -o '"workerName"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)
WEBHOOK_SECRET=$(cat config.json | grep -o '"webhookSecret"[[:space:]]*:[[:space:]]*"[^"]*"' | cut -d'"' -f4)

echo -e "\${BLUE}📋 설정 정보:\${NC}"
echo -e "   Organization: \${GREEN}$ORG_NAME\${NC}"
echo -e "   Worker 이름: \${GREEN}$WORKER_NAME\${NC}"
echo ""

echo -e "\${YELLOW}[1/4]\${NC} 📦 의존성 설치 중..."
npm config set strict-ssl false 2>/dev/null || true
npm install && echo -e "\${GREEN}✅ 의존성 설치 완료\${NC}" || { echo -e "\${RED}❌ npm install 실패\${NC}"; exit 1; }
npm config set strict-ssl true 2>/dev/null || true
echo ""

echo -e "\${YELLOW}[2/4]\${NC} 🔐 Cloudflare 로그인 중..."
export NODE_TLS_REJECT_UNAUTHORIZED=0
npx wrangler login && echo -e "\${GREEN}✅ Cloudflare 로그인 완료\${NC}" || { echo -e "\${RED}❌ 로그인 실패\${NC}"; exit 1; }
echo ""

echo -e "\${YELLOW}[3/4]\${NC} 🚀 Worker 배포 중..."
DEPLOY_SUCCESS=false
WORKER_URL=""

while [ "$DEPLOY_SUCCESS" = false ]; do
    DEPLOY_OUTPUT=$(npx wrangler deploy 2>&1) || true
    if echo "$DEPLOY_OUTPUT" | grep -q "https://.*workers.dev"; then
        WORKER_URL=$(echo "$DEPLOY_OUTPUT" | grep -o 'https://[^[:space:]]*workers.dev' | head -1)
        DEPLOY_SUCCESS=true
        echo -e "\${GREEN}✅ Worker 배포 완료\${NC}"
        echo -e "   URL: \${CYAN}$WORKER_URL\${NC}"
    else
        echo -e "\${RED}❌ Worker 배포 실패\${NC}"
        echo "$DEPLOY_OUTPUT" | tail -5
        echo ""
        echo -e "새 Worker 이름을 입력하세요 (q로 종료):"
        read -r NEW_NAME
        [ "$NEW_NAME" = "q" ] && exit 1
        [ -n "$NEW_NAME" ] && sed -i.bak "s/^name = \\".*\\"/name = \\"$NEW_NAME\\"/" wrangler.toml && rm -f wrangler.toml.bak
    fi
done
echo ""

echo -e "\${YELLOW}[4/4]\${NC} 🔑 Secrets 설정 중..."
echo -e "\${CYAN}GitHub PAT을 입력하세요 (repo, project 권한):\${NC}"
npx wrangler secret put GITHUB_TOKEN
echo "$WEBHOOK_SECRET" | npx wrangler secret put WEBHOOK_SECRET 2>/dev/null || npx wrangler secret put WEBHOOK_SECRET
echo ""

echo -e "\${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\${NC}"
echo -e "\${GREEN}🎉 설치 완료!\${NC}"
echo -e "📌 Worker URL: \${CYAN}$WORKER_URL\${NC}"
echo ""
echo -e "\${BLUE}📋 다음 단계: GitHub Webhook 설정\${NC}"
echo -e "   https://github.com/organizations/$ORG_NAME/settings/hooks"
echo -e "   Payload URL: $WORKER_URL"
echo -e "   Secret: config.json 참조"
echo -e "   Event: 'Project v2 items' 선택"
echo -e "\${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\${NC}"
`;
}

function generateSetupScriptPs1() {
    return `# GitHub Projects Sync Worker 설치 스크립트 (Windows)
$ErrorActionPreference = "Stop"

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "   🔄 GitHub Projects Sync Worker 설치" -ForegroundColor Cyan
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan

if (-not (Test-Path "config.json")) { Write-Host "❌ config.json 없음" -ForegroundColor Red; exit 1 }

$config = Get-Content "config.json" -Raw | ConvertFrom-Json

Write-Host "[1/4] 📦 의존성 설치..." -ForegroundColor Yellow
npm config set strict-ssl false 2>$null
npm install
npm config set strict-ssl true 2>$null

Write-Host "[2/4] 🔐 Cloudflare 로그인..." -ForegroundColor Yellow
$env:NODE_TLS_REJECT_UNAUTHORIZED = "0"
npx wrangler login

Write-Host "[3/4] 🚀 Worker 배포..." -ForegroundColor Yellow
$success = $false
while (-not $success) {
    $output = npx wrangler deploy 2>&1 | Out-String
    if ($output -match "https://[^\\s]*workers\\.dev") {
        $url = $Matches[0]
        $success = $true
        Write-Host "✅ 배포 완료: $url" -ForegroundColor Green
    } else {
        Write-Host "❌ 배포 실패" -ForegroundColor Red
        $new = Read-Host "새 Worker 이름 (q로 종료)"
        if ($new -eq "q") { exit 1 }
        if ($new) { (Get-Content wrangler.toml) -replace 'name = "[^"]*"', "name = \`"$new\`"" | Set-Content wrangler.toml }
    }
}

Write-Host "[4/4] 🔑 Secrets 설정..." -ForegroundColor Yellow
npx wrangler secret put GITHUB_TOKEN
$config.webhookSecret | npx wrangler secret put WEBHOOK_SECRET

Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
Write-Host "🎉 설치 완료!" -ForegroundColor Green
Write-Host "Worker URL: $url" -ForegroundColor Cyan
Write-Host "다음: GitHub Webhook 설정" -ForegroundColor Blue
Write-Host "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━" -ForegroundColor Cyan
`;
}

// ============================================
// ZIP download
// ============================================

async function downloadAllAsZip() {
    // Validation
    const orgName = document.getElementById('orgName').value.trim();
    const projectNumber = document.getElementById('projectNumber').value.trim();

    if (!orgName || !projectNumber) {
        showToast(translate('toast.ownerAndNumberRequired'), 'error');
        return;
    }

    // Update state
    state.orgName = orgName;
    state.projectNumber = projectNumber;
    state.workerName = document.getElementById('workerName').value.trim() || 'github-projects-sync-worker';
    saveState();

    try {
        const zip = new JSZip();
        const folderName = 'github-projects-sync-worker';

        // Add files
        zip.file(`${folderName}/wrangler.toml`, generateWranglerToml());
        zip.file(`${folderName}/package.json`, generatePackageJson());
        zip.file(`${folderName}/tsconfig.json`, generateTsconfig());
        zip.file(`${folderName}/src/index.ts`, generateWorkerCode());
        zip.file(`${folderName}/config.json`, generateConfigJson());
        zip.file(`${folderName}/README.md`, generateReadme());
        zip.file(`${folderName}/projects-sync-worker-setup.sh`, generateSetupScriptSh());
        zip.file(`${folderName}/projects-sync-worker-setup.ps1`, generateSetupScriptPs1());

        // Build and download the ZIP
        const content = await zip.generateAsync({ type: 'blob' });
        const url = URL.createObjectURL(content);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${folderName}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast(translate('toast.zipDownloaded'));
    } catch (error) {
        console.error('[projects sync] ZIP creation failed:', error);
        showToast(translate('toast.zipFailed'), 'error');
    }
}

// ============================================
// Utility functions
// ============================================

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        showToast(translate('toast.copied'));
    }).catch(() => {
        showToast(translate('toast.copyFailed'), 'error');
    });
}

function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toastMessage');

    toastMessage.textContent = message;

    if (type === 'error') {
        toast.classList.remove('bg-gray-800');
        toast.classList.add('bg-red-600');
    } else {
        toast.classList.remove('bg-red-600');
        toast.classList.add('bg-gray-800');
    }

    toast.classList.remove('translate-y-full', 'opacity-0');
    toast.classList.add('translate-y-0', 'opacity-100');

    setTimeout(() => {
        toast.classList.remove('translate-y-0', 'opacity-100');
        toast.classList.add('translate-y-full', 'opacity-0');
    }, 3000);
}

// ============================================
// Generate install commands automatically (per OS)
// ============================================

// Update commands automatically (debounced)
let commandUpdateTimer = null;

function scheduleCommandUpdate() {
    if (commandUpdateTimer) {
        clearTimeout(commandUpdateTimer);
    }
    commandUpdateTimer = setTimeout(() => {
        updateInstallCommands();
    }, 300);
}

function updateInstallCommands() {
    const commandSection = document.getElementById('installCommandSection');
    const waitingMessage = document.getElementById('commandWaitingMessage');
    const bashCommandCode = document.getElementById('bashCommandCode');
    const powershellCommandCode = document.getElementById('powershellCommandCode');

    if (!commandSection || !waitingMessage) return;

    // Check required fields
    const ownerName = state.ownerName || '';
    const projectNumber = state.projectNumber || '';
    const webhookSecret = state.webhookSecret || '';
    const githubToken = state.githubToken || '';

    if (!ownerName || !projectNumber || !webhookSecret || !githubToken) {
        // Show the waiting-for-input message
        waitingMessage.classList.remove('hidden');
        commandSection.classList.add('hidden');
        return;
    }

    // Generate and show the commands
    waitingMessage.classList.add('hidden');
    commandSection.classList.remove('hidden');

    if (bashCommandCode) {
        bashCommandCode.textContent = buildBashCommand();
    }
    if (powershellCommandCode) {
        powershellCommandCode.textContent = buildPowerShellCommand();
    }
}

function buildBashCommand() {
    // Mac/Linux bash script URL
    const scriptUrl = 'https://raw.githubusercontent.com/Cassiiopeia/projectops/main/.github/util/common/projects-sync-wizard/projects-sync-wizard-setup.sh';

    // Build arguments (Organization only)
    const args = [];
    args.push(`--owner "${state.ownerName}"`);
    args.push(`--project "${state.projectNumber}"`);
    args.push(`--worker-name "${state.workerName}"`);
    args.push(`--webhook-secret "${state.webhookSecret}"`);
    args.push(`--github-token "${state.githubToken}"`);
    args.push(`--labels "${state.statusLabels.join(',')}"`);

    // Build the curl command
    return `curl -fsSL ${scriptUrl} | bash -s -- \\
  ${args.join(' \\\n  ')}`;
}

function buildPowerShellCommand() {
    // Env var settings (Organization only)
    const envVars = [];
    envVars.push(`$env:WIZARD_OWNER='${state.ownerName}'`);
    envVars.push(`$env:WIZARD_PROJECT='${state.projectNumber}'`);
    envVars.push(`$env:WIZARD_WORKER_NAME='${state.workerName}'`);
    envVars.push(`$env:WIZARD_WEBHOOK_SECRET='${state.webhookSecret}'`);
    envVars.push(`$env:WIZARD_GITHUB_TOKEN='${state.githubToken}'`);
    envVars.push(`$env:WIZARD_LABELS='${state.statusLabels.join(',')}'`);

    // PowerShell script URL
    const scriptUrl = 'https://raw.githubusercontent.com/Cassiiopeia/projectops/main/.github/util/common/projects-sync-wizard/projects-sync-wizard-setup.ps1';

    // Build the PowerShell command
    return `${envVars.join('; ')}; irm '${scriptUrl}' | iex`;
}

function copyCommand(type) {
    let command = '';
    if (type === 'bash') {
        command = buildBashCommand();
    } else if (type === 'powershell') {
        command = buildPowerShellCommand();
    }
    copyToClipboard(command);
}
