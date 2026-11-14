// pro-skill-bug report notice (#997): issue URL from the report call result > toast + status line
// Holds no detection rules (source of truth is skill_bug_rules.py). Looks only at the result text.
import type { Register } from 'claude-code'

// Report call: create-issue / add-comment with a pro-skill-bug draft folder as the body
const REPORT_COMMAND_PATTERN = /(create-issue|add-comment)[\s\S]*cache\/pro-skill-bug\//
const REPORTED_ISSUE_URL_PATTERN = /https:\/\/github\.com\/Cassiiopeia\/projectops\/issues\/(\d+)/
// Toast display time (8 seconds)
const TOAST_TIMEOUT_MILLISECONDS = 8000

export const register: Register = on => {
  on('tool.call', { tool: 'Bash' }, async ($, e, next) => {
    const ran = await next(e)
    if (ran.deny !== undefined || ran.isError || !REPORT_COMMAND_PATTERN.test(e.command)) {
      return ran
    }
    const issueMatch = REPORTED_ISSUE_URL_PATTERN.exec(JSON.stringify(ran.result ?? ''))
    if (issueMatch) {
      const action = e.command.includes('add-comment') ? 'commented on' : 'reported'
      $.ui.toast(`projectops bug ${action}: #${issueMatch[1]} (${issueMatch[0]})`, { timeoutMs: TOAST_TIMEOUT_MILLISECONDS })
      $.ui.status(`projectops bug #${issueMatch[1]} ${action}`)
    }
    return ran
  }).catch(($, e, next) => next(e))   // A notice failure must not change the command result (replay the result if it was called)
}
