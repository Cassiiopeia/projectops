// pro-skill-bug 보고 알림 (#997): 보고 호출 결과의 이슈 URL > 토스트 + 상태줄
// 판정 규칙은 갖지 않음 (정본은 skill_bug_rules.py). 결과 글자만 본다.
import type { Register } from 'claude-code'

// 보고 호출: pro-skill-bug 초안 폴더를 본문으로 넘긴 create-issue / add-comment
const REPORT_COMMAND_PATTERN = /(create-issue|add-comment)[\s\S]*cache\/pro-skill-bug\//
const REPORTED_ISSUE_URL_PATTERN = /https:\/\/github\.com\/Cassiiopeia\/projectops\/issues\/(\d+)/
// 토스트 유지 시간 (8초)
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
  }).catch(($, e, next) => next(e))   // 알림 실패가 명령 결과를 바꾸면 안 됨 (호출됐으면 결과 재생)
}
