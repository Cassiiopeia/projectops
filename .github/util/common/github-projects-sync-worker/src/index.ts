// ===================================================================
// GitHub Projects Sync Worker
// ===================================================================
//
// Detects GitHub Projects Status changes and syncs issue labels automatically.
//
// How it works:
// 1. Receive the GitHub webhook (projects_v2_item) event
// 2. Verify the webhook secret
// 3. Check it is a Status field change (other field changes are ignored)
// 4. Look up the current Status with the GraphQL API
// 5. Sync issue labels (remove the old Status label → add the new one)
//
// ===================================================================

// In-memory cache of the Status field ID
let cachedStatusFieldId: string | null = null;
let cacheTimestamp = 0;
const CACHE_TTL = 3600000; // 1 hour

export interface Env {
  // Secrets (set with wrangler secret put)
  GITHUB_TOKEN: string;
  WEBHOOK_SECRET: string;

  // Variables (set in wrangler.toml)
  PROJECT_NUMBER: string;
  STATUS_FIELD: string;
  STATUS_LABELS: string;
  ORG_NAME: string;
}

interface WebhookPayload {
  action: string;
  projects_v2_item?: {
    id: number;
    node_id: string;
    project_node_id: string;
    content_node_id?: string;
    content_type?: string;
  };
  changes?: {
    field_value?: {
      field_node_id: string;
      field_type: string;
    };
  };
  sender?: {
    login: string;
    type: string;
  };
}

interface GraphQLResponse {
  data?: {
    node?: {
      content?: {
        __typename: string;
        number?: number;
        title?: string;
        repository?: {
          name: string;
          owner: {
            login: string;
          };
        };
        labels?: {
          nodes: Array<{ name: string }>;
        };
      };
      fieldValueByName?: {
        name?: string;
      };
    };
    organization?: {
      projectV2?: {
        field?: {
          id?: string;
        };
      };
    };
    user?: {
      projectV2?: {
        field?: {
          id?: string;
        };
      };
    };
  };
  errors?: Array<{ message: string }>;
}

// ===================================================================
// Verify the webhook secret (HMAC-SHA256)
// ===================================================================
async function verifySignature(
  body: string,
  signature: string | null,
  secret: string
): Promise<boolean> {
  if (!signature) {
    console.log('❌ Signature header missing');
    return false;
  }

  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    'raw',
    encoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  );

  const signatureBuffer = await crypto.subtle.sign('HMAC', key, encoder.encode(body));
  const hashArray = Array.from(new Uint8Array(signatureBuffer));
  const hashHex = hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  const expectedSignature = `sha256=${hashHex}`;

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

// ===================================================================
// GraphQL API call
// ===================================================================
async function graphqlQuery(
  query: string,
  variables: Record<string, unknown>,
  token: string
): Promise<GraphQLResponse> {
  const response = await fetch('https://api.github.com/graphql', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': 'GitHub-Projects-Sync-Worker',
    },
    body: JSON.stringify({ query, variables }),
  });

  if (!response.ok) {
    throw new Error(`GraphQL request failed: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

// ===================================================================
// Look up the Status field ID (in-memory cache)
// ===================================================================
async function getStatusFieldId(env: Env): Promise<string | null> {
  const now = Date.now();

  // Reuse while the cache is valid
  if (cachedStatusFieldId && now - cacheTimestamp < CACHE_TTL) {
    console.log(`📌 Status field ID (cached): ${cachedStatusFieldId}`);
    return cachedStatusFieldId;
  }

  console.log('📌 Looking up the Status field ID...');

  // Organization project query
  const orgQuery = `
    query($org: String!, $number: Int!, $fieldName: String!) {
      organization(login: $org) {
        projectV2(number: $number) {
          field(name: $fieldName) {
            ... on ProjectV2SingleSelectField {
              id
            }
          }
        }
      }
    }
  `;

  // User project query
  const userQuery = `
    query($user: String!, $number: Int!, $fieldName: String!) {
      user(login: $user) {
        projectV2(number: $number) {
          field(name: $fieldName) {
            ... on ProjectV2SingleSelectField {
              id
            }
          }
        }
      }
    }
  `;

  const projectNumber = parseInt(env.PROJECT_NUMBER);

  // Try the Organization project first
  try {
    const orgResult = await graphqlQuery(
      orgQuery,
      {
        org: env.ORG_NAME,
        number: projectNumber,
        fieldName: env.STATUS_FIELD,
      },
      env.GITHUB_TOKEN
    );

    const orgFieldId = orgResult.data?.organization?.projectV2?.field?.id;
    if (orgFieldId) {
      cachedStatusFieldId = orgFieldId;
      cacheTimestamp = now;
      console.log(`✅ Status field ID found (Organization): ${orgFieldId}`);
      return orgFieldId;
    }
  } catch {
    console.log('ℹ️ Not an Organization project, trying as a User project...');
  }

  // Try as a User project
  try {
    const userResult = await graphqlQuery(
      userQuery,
      {
        user: env.ORG_NAME,
        number: projectNumber,
        fieldName: env.STATUS_FIELD,
      },
      env.GITHUB_TOKEN
    );

    const userFieldId = userResult.data?.user?.projectV2?.field?.id;
    if (userFieldId) {
      cachedStatusFieldId = userFieldId;
      cacheTimestamp = now;
      console.log(`✅ Status field ID found (User): ${userFieldId}`);
      return userFieldId;
    }
  } catch (error) {
    console.warn(`⚠️ User project lookup failed: ${error}`);
  }

  console.warn('⚠️ Status field ID not found');
  return null;
}

// ===================================================================
// Update issue labels (REST API)
// ===================================================================
async function removeLabel(
  owner: string,
  repo: string,
  issueNumber: number,
  label: string,
  token: string
): Promise<void> {
  const url = `https://api.github.com/repos/${owner}/${repo}/issues/${issueNumber}/labels/${encodeURIComponent(label)}`;

  const response = await fetch(url, {
    method: 'DELETE',
    headers: {
      Authorization: `Bearer ${token}`,
      'User-Agent': 'GitHub-Projects-Sync-Worker',
      Accept: 'application/vnd.github.v3+json',
    },
  });

  if (response.ok || response.status === 404) {
    console.log(`  ✅ Label "${label}" removed (or already absent)`);
  } else {
    console.warn(`  ⚠️ Failed to remove label "${label}": ${response.status}`);
  }
}

async function addLabel(
  owner: string,
  repo: string,
  issueNumber: number,
  label: string,
  token: string
): Promise<void> {
  const url = `https://api.github.com/repos/${owner}/${repo}/issues/${issueNumber}/labels`;

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'User-Agent': 'GitHub-Projects-Sync-Worker',
      Accept: 'application/vnd.github.v3+json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ labels: [label] }),
  });

  if (response.ok) {
    console.log(`  ✅ Label "${label}" added`);
  } else {
    const errorText = await response.text();
    console.error(`  ❌ Failed to add label "${label}": ${response.status} - ${errorText}`);
    throw new Error(`Failed to add label: ${response.status}`);
  }
}

// ===================================================================
// Main sync logic
// ===================================================================
async function syncLabelFromStatus(payload: WebhookPayload, env: Env): Promise<void> {
  const itemNodeId = payload.projects_v2_item?.node_id;

  if (!itemNodeId) {
    console.log('⚠️ Item node_id not found');
    return;
  }

  console.log(`📌 Processing item: ${itemNodeId}`);

  // 1. Look up item info with GraphQL
  const query = `
    query($itemId: ID!, $statusField: String!) {
      node(id: $itemId) {
        ... on ProjectV2Item {
          content {
            __typename
            ... on Issue {
              number
              title
              repository {
                name
                owner {
                  login
                }
              }
              labels(first: 20) {
                nodes {
                  name
                }
              }
            }
            ... on PullRequest {
              number
              title
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
  `;

  const result = await graphqlQuery(
    query,
    { itemId: itemNodeId, statusField: env.STATUS_FIELD },
    env.GITHUB_TOKEN
  );

  if (result.errors) {
    console.error('❌ GraphQL errors:', result.errors);
    throw new Error(result.errors[0].message);
  }

  const content = result.data?.node?.content;
  const newStatus = result.data?.node?.fieldValueByName?.name;

  // 2. Skip if not an issue
  if (!content || content.__typename !== 'Issue') {
    console.log(`ℹ️ Skipping: Not an Issue (type: ${content?.__typename || 'unknown'})`);
    return;
  }

  if (!content.repository || !content.number) {
    console.log('⚠️ Issue repository info not found');
    return;
  }

  const owner = content.repository.owner.login;
  const repo = content.repository.name;
  const issueNumber = content.number;
  const currentLabels = content.labels?.nodes.map((l) => l.name) || [];

  console.log(`📌 Issue: ${owner}/${repo}#${issueNumber}`);
  console.log(`📌 Current Labels: ${currentLabels.join(', ') || '(none)'}`);
  console.log(`📌 New Status: "${newStatus}"`);

  if (!newStatus) {
    console.log('⚠️ Status value not found');
    return;
  }

  // 3. Parse Status Labels
  let statusLabels: string[];
  try {
    statusLabels = JSON.parse(env.STATUS_LABELS);
  } catch {
    console.error('❌ Failed to parse STATUS_LABELS');
    statusLabels = ['작업전', '작업중', '담당자확인', '피드백', '작업완료', '보류', '취소'];
  }

  // 4. Check the new Status is managed
  if (!statusLabels.includes(newStatus)) {
    console.log(`⚠️ "${newStatus}" is not a managed status label`);
    return;
  }

  // 5. Check whether the same label already exists (prevents infinite loops)
  if (currentLabels.includes(newStatus)) {
    console.log(`✅ Label "${newStatus}" already exists. No sync needed.`);
    return;
  }

  // 6. Remove the old Status label
  const labelsToRemove = currentLabels.filter(
    (label) => statusLabels.includes(label) && label !== newStatus
  );

  console.log(`🗑️ Labels to remove: ${labelsToRemove.join(', ') || '(none)'}`);

  for (const label of labelsToRemove) {
    await removeLabel(owner, repo, issueNumber, label, env.GITHUB_TOKEN);
  }

  // 7. Add the new Status label
  console.log(`➕ Adding label: "${newStatus}"`);
  await addLabel(owner, repo, issueNumber, newStatus, env.GITHUB_TOKEN);

  console.log('🎉 Label sync completed!');
}

// ===================================================================
// Worker Entry Point
// ===================================================================
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
    console.log('🔄 GitHub Projects Sync Worker');
    console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');

    // 1. Handle POST requests only
    if (request.method !== 'POST') {
      console.log(`⚠️ Method not allowed: ${request.method}`);
      return new Response('Method not allowed', { status: 405 });
    }

    // 2. Read the body
    const body = await request.text();

    // 3. Verify the webhook secret
    const signature = request.headers.get('X-Hub-Signature-256');

    if (!(await verifySignature(body, signature, env.WEBHOOK_SECRET))) {
      console.log('❌ Invalid webhook signature');
      return new Response('Invalid signature', { status: 401 });
    }

    console.log('✅ Webhook signature verified');

    // 4. Check the event type
    const event = request.headers.get('X-GitHub-Event');
    console.log(`📌 Event type: ${event}`);

    if (event === 'ping') {
      console.log('🏓 Ping event received');
      return new Response('Pong', { status: 200 });
    }

    if (event !== 'projects_v2_item') {
      console.log(`ℹ️ Ignoring event: ${event}`);
      return new Response('Ignored event', { status: 200 });
    }

    // 5. Parse the payload
    let payload: WebhookPayload;
    try {
      payload = JSON.parse(body);
    } catch {
      console.error('❌ Failed to parse JSON body');
      return new Response('Invalid JSON', { status: 400 });
    }

    console.log(`📌 Action: ${payload.action}`);

    // 6. Handle only the edited action (Status change)
    if (payload.action !== 'edited') {
      console.log(`ℹ️ Ignoring action: ${payload.action}`);
      return new Response('Ignored action', { status: 200 });
    }

    // 7. Check it is a Status field change
    if (payload.changes?.field_value) {
      const changedFieldId = payload.changes.field_value.field_node_id;
      const statusFieldId = await getStatusFieldId(env);

      if (statusFieldId && changedFieldId !== statusFieldId) {
        console.log(`ℹ️ Not a Status field change. Skipping`);
        console.log(`   Changed field: ${changedFieldId}`);
        console.log(`   Status field: ${statusFieldId}`);
        return new Response('Ignored: not status field change', { status: 200 });
      }

      console.log(`✅ Status field change confirmed`);
    } else {
      console.log(`ℹ️ No field_value change info, syncing anyway`);
    }

    // 8. Run the label sync
    try {
      await syncLabelFromStatus(payload, env);
      console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
      return new Response('OK', { status: 200 });
    } catch (error) {
      console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
      console.error('❌ Error:', error);
      console.error('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━');
      return new Response('Internal error', { status: 500 });
    }
  },
};
