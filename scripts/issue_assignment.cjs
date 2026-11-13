// Issue assignment for this repository's community issues (#1155).
// Called by .github/workflows/PROJECT-TEMPLATE-ISSUE-ASSIGNMENT.yaml through actions/github-script.
//   handleClaimComment: /assign > assign the commenter, /unassign > release, free-form claim > hint
//   releaseStaleClaims: daily > unassign claims older than 7 days with no open linked PR
// Template-only: scripts/ is never copied into user repositories.

// Labels whose issues are open for outside contributors
const CLAIMABLE_LABELS = ["good first issue", "help wanted"];
// Days a claim may sit without an open pull request
const CLAIM_EXPIRY_DAYS = 7;
const MILLISECONDS_PER_DAY = 24 * 60 * 60 * 1000;
// Commands (one per comment, first line): "/assign" takes the issue, "/unassign" gives it back
const ASSIGN_COMMAND = /^\s*\/assign\s*$/im;
const UNASSIGN_COMMAND = /^\s*\/unassign\s*$/im;
// Free-form claims ("I'm on it", "can I take this") get a hint to use /assign, nothing else
const CLAIM_PHRASE =
  /\b(i'?m|i am) on it\b|\bi('d| would) (like|love) to (work on|take|tackle|pick up)\b|\b(can|could|may) i (work on|take|tackle|pick up|have)\b|\bi('ll| will) (work on|take|tackle|pick up)\b|\bassign (this|it) to me\b|\bplease assign me\b/i;
// Marker so the bot can find its own comments
const BOT_MARKER = "<!-- projectops:issue-assignment -->";

function hasClaimableLabel(issue) {
  return (issue.labels || []).some((label) => CLAIMABLE_LABELS.includes((label.name || label).toLowerCase()));
}

// Comment > "assign" · "unassign" · "hint" (free-form claim) · null
function classifyComment(body) {
  const text = body || "";
  if (UNASSIGN_COMMAND.test(text)) return "unassign";
  if (ASSIGN_COMMAND.test(text)) return "assign";
  return CLAIM_PHRASE.test(text) ? "hint" : null;
}

// Owner and bots never get an issue through this workflow (the owner assigns themselves by hand)
function isAssignableUser(user, ownerLogin) {
  if (!user || user.type === "Bot" || user.login.endsWith("[bot]")) return false;
  return user.login.toLowerCase() !== ownerLogin.toLowerCase();
}

async function comment(github, repo, issueNumber, text) {
  await github.rest.issues.createComment({ ...repo, issue_number: issueNumber, body: `${BOT_MARKER}\n${text}` });
}

function welcomeText(login, issueNumber) {
  return [
    `Thanks @${login}, this issue is now assigned to you. 🙌`,
    "",
    `- Open your pull request against \`develop\` and write \`Fixes #${issueNumber}\` in its description.`,
    `- If there is no open pull request linked to this issue within ${CLAIM_EXPIRY_DAYS} days, the assignment is released so someone else can pick it up. You can claim it again at any time.`,
    "- Changed your mind? Comment `/unassign` and the issue is free again.",
    "- Questions are welcome right here. [CONTRIBUTING.md](https://github.com/Cassiiopeia/projectops/blob/main/CONTRIBUTING.md) has the setup and checks.",
  ].join("\n");
}

function takenText(login, assignees) {
  const owners = assignees.map((name) => `@${name}`).join(", ");
  return [
    `Thanks for your interest, @${login}! This issue is already assigned to ${owners}.`,
    "Other open issues labeled [`good first issue`](https://github.com/Cassiiopeia/projectops/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22+no%3Aassignee) are free to claim.",
  ].join("\n");
}

function hintText(login) {
  return `Thanks @${login}! To take this issue, comment \`/assign\` on its own line and the bot will assign it to you.`;
}

function unassignedText(login) {
  return `@${login} has released this issue, so it is free to claim with \`/assign\`. Thanks!`;
}

function releasedText(login, issueNumber) {
  return [
    `@${login}, this issue was assigned to you ${CLAIM_EXPIRY_DAYS}+ days ago with no open pull request linked to it, so I've released the assignment and it is free to claim again.`,
    `If you are still working on it, comment \`/assign\` to take it back, or open the pull request with \`Fixes #${issueNumber}\`. Thanks for your interest!`,
  ].join("\n");
}

/**
 * One comment: /unassign > release own claim · taken > say who has it · free-form claim > /assign hint · /assign > assign + welcome
 */
async function handleClaimComment({ github, context, core }) {
  const { issue, comment: claim } = context.payload;
  const repo = context.repo;
  // Target check (issue, open, label, claim wording, assignable person)
  if (issue.pull_request || issue.state !== "open" || !hasClaimableLabel(issue)) return core.info("skip: not a claimable issue");
  const kind = classifyComment(claim.body);
  if (!kind) return core.info("skip: not a claim comment");
  if (!isAssignableUser(claim.user, repo.owner)) return core.info(`skip: ${claim.user.login} is the owner or a bot`);
  const login = claim.user.login;
  const assignees = (issue.assignees || []).map((user) => user.login);
  const isMine = assignees.some((name) => name.toLowerCase() === login.toLowerCase());
  if (kind === "unassign") {
    if (!isMine) return core.info("skip: /unassign from someone not assigned");
    await github.rest.issues.removeAssignees({ ...repo, issue_number: issue.number, assignees: [login] });
    await comment(github, repo, issue.number, unassignedText(login));
    return core.info(`unassigned: #${issue.number} < ${login}`);
  }
  if (isMine) return core.info("skip: already assigned to the commenter");
  if (assignees.length > 0) {
    await comment(github, repo, issue.number, takenText(login, assignees));
    return core.info(`taken: #${issue.number} belongs to ${assignees.join(", ")}`);
  }
  if (kind === "hint") {
    await comment(github, repo, issue.number, hintText(login));
    return core.info(`hint: #${issue.number} > ${login}`);
  }
  // Assign (GitHub accepts only people who commented — confirm from the response)
  const { data } = await github.rest.issues.addAssignees({ ...repo, issue_number: issue.number, assignees: [login] });
  const isAssigned = (data.assignees || []).some((user) => user.login.toLowerCase() === login.toLowerCase());
  if (!isAssigned) return core.warning(`GitHub did not assign ${login} to #${issue.number}`);
  await comment(github, repo, issue.number, welcomeText(login, issue.number));
  core.info(`assigned: #${issue.number} > ${login}`);
}

// When this person was last assigned (timeline 'assigned' events)
function lastAssignedAt(timeline, login) {
  const times = timeline
    .filter((event) => event.event === "assigned" && event.assignee && event.assignee.login.toLowerCase() === login.toLowerCase())
    .map((event) => Date.parse(event.created_at));
  return times.length ? Math.max(...times) : null;
}

// Is an open pull request linked to this issue? (Fixes #N or a link > 'cross-referenced' event)
function hasOpenLinkedPullRequest(timeline) {
  return timeline.some((event) => event.event === "cross-referenced" && event.source && event.source.issue
    && event.source.issue.pull_request && event.source.issue.state === "open");
}

/**
 * Stale claims: labeled issues > assigned time per assignee > older than 7 days, no open linked PR > unassign + comment
 */
async function releaseStaleClaims({ github, context, core, isDryRun = false, now = Date.now() }) {
  const repo = context.repo;
  const released = [];
  for (const label of CLAIMABLE_LABELS) {
    const issues = await github.paginate(github.rest.issues.listForRepo, { ...repo, state: "open", labels: label, per_page: 100 });
    for (const issue of issues) {
      if (issue.pull_request || !(issue.assignees || []).length) continue;
      const timeline = await github.paginate(github.rest.issues.listEventsForTimeline, { ...repo, issue_number: issue.number, per_page: 100 });
      if (hasOpenLinkedPullRequest(timeline)) continue;
      for (const user of issue.assignees) {
        // Never touch issues the owner took
        if (!isAssignableUser(user, repo.owner)) continue;
        const assignedAt = lastAssignedAt(timeline, user.login);
        if (assignedAt === null || now - assignedAt < CLAIM_EXPIRY_DAYS * MILLISECONDS_PER_DAY) continue;
        const key = `#${issue.number}:${user.login}`;
        if (released.includes(key)) continue;
        released.push(key);
        if (isDryRun) continue;
        await github.rest.issues.removeAssignees({ ...repo, issue_number: issue.number, assignees: [user.login] });
        await comment(github, repo, issue.number, releasedText(user.login, issue.number));
      }
    }
  }
  core.info(`${isDryRun ? "would release" : "released"} ${released.length}: ${released.join(", ") || "none"}`);
  return released;
}

module.exports = { handleClaimComment, releaseStaleClaims, classifyComment, hasClaimableLabel, CLAIM_EXPIRY_DAYS };
