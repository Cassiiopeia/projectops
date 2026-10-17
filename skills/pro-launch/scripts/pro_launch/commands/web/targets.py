"""web 에서 요소를 고르고 읽기 전용 세션이 막을 것을 가르는 규칙 — find 와 click 이 함께 쓴다."""
from __future__ import annotations

import re


# ── agent 가 혼자 브라우저를 몰 수 있게 (#825) ───────────────────────────
#
# 스크린샷과 "있나 없나(assert)"만으로는 화면을 읽을 수 없어서 agent 가 선택자를 **추측**했다.
# 추측한 클릭은 엉뚱한 메뉴를 누르고도 ok 를 돌려줬다(Play Console 실측). 그래서 루프를 바꾼다.
#
#   web find  → 후보를 번호(ref)·글자·링크 주소와 함께 돌려준다 (요소에 data-pops-ref 를 단다)
#   web click --ref N --expect-url/--expect-text → 그 요소만 누르고, 결과가 안 오면 실패로 보고한다
#   web text  → 보이는 글자를 읽는다 (스크린샷보다 훨씬 싸다)
#
# 관리 콘솔(Play Console · App Store Connect)은 `web open --readonly` 로 연다.
# 읽기 전용 세션에서는 되돌릴 수 없는 일을 하는 버튼을 --confirm-mutating 없이 누르지 않는다.
REF_ATTR = "data-pops-ref"


# 읽기 전용 세션에서 막는 버튼 문구. "취소·확인"은 대화상자를 닫는 데도 쓰여 넣지 않았다.
_MUTATING_RE = re.compile(
    r"(삭제|제거|출시|게시|제출|전송|보내기|저장|승인|결제|구매|업로드|배포|폐기|롤아웃|"
    r"\b(delete|remove|publish|release|roll ?out|submit|send|save|approve|pay|purchase|upload|deploy|discard)\b)",
    re.IGNORECASE)


def _is_mutating(label: str) -> bool:
    """버튼 문구가 되돌리기 어려운 동작인가. 읽기 전용 세션에서 클릭을 막는 기준이다."""
    return bool(_MUTATING_RE.search(label or ""))


# 화면 이동으로 보는 요소 — 문구에 "제출·게시"가 있어도 막지 않는다.
# Play Console 의 "제출 활동"·"게시 개요"는 기록을 보는 링크인데, 문구만 보면 위험 버튼으로 걸렸다(실측).
_NAV_ROLES = {"link", "tab", "row", "menuitem", "treeitem", "option"}


def is_mutating_target(info: dict) -> bool:
    """요소 종류까지 보고 판단한다. 링크·탭·행은 이동이라 허용하고, 버튼류만 문구로 검사한다."""
    tag, role = (info.get("tag") or ""), (info.get("role") or "")
    if (tag == "a" and info.get("href")) or role in _NAV_ROLES:
        return False
    return _is_mutating(f"{info.get('text') or ''} {info.get('aria') or ''}")


# 클릭할 수 있는 것으로 보는 요소. 표의 행(role=row)도 넣는다 — 콘솔은 행 전체가 링크인 경우가 많다.
CLICKABLE = ("a[href],button,[role=button],[role=link],[role=tab],[role=menuitem],[role=row],"
              "[role=option],[role=checkbox],[role=switch],[onclick],input[type=submit],"
              "input[type=button],input[type=checkbox],summary")


FIND_JS = """(o) => {
  const ATTR = o.attr;
  document.querySelectorAll('[' + ATTR + ']').forEach(e => e.removeAttribute(ATTR));
  const visible = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const label = e => ((e.innerText || e.value || '') + ' ' + (e.getAttribute('aria-label') || '')).replace(/\\s+/g, ' ').trim();
  let els;
  if (o.selector) els = [...document.querySelectorAll(o.selector)];
  else if (o.role === 'link') els = [...document.querySelectorAll('a[href],[role=link]')];
  else if (o.role === 'button') els = [...document.querySelectorAll('button,[role=button],input[type=submit],input[type=button]')];
  else if (o.role) els = [...document.querySelectorAll('[role=' + o.role + ']')];
  else els = [...document.querySelectorAll(o.clickable)];
  let fallback = false;
  if (o.text) {
    const t = o.text.toLowerCase();
    let hit = els.filter(e => label(e).toLowerCase().includes(t));
    if (!hit.length && !o.selector && !o.role) {
      // 클릭 가능한 요소 안에 그 글자가 없으면, 글자를 가진 가장 안쪽 요소를 찾아 가장 가까운 클릭 대상으로 올린다
      const leaves = [...document.querySelectorAll('body *')].filter(e =>
        (e.innerText || '').toLowerCase().includes(t) &&
        ![...e.children].some(c => (c.innerText || '').toLowerCase().includes(t)));
      hit = [...new Set(leaves.map(e => e.closest(o.clickable) || e))];
      fallback = true;
    }
    els = hit;
  }
  // 구체적인 것부터 — 진짜 링크·버튼이 그것을 감싼 행보다 먼저 나와야 첫 후보를 눌러도 헛클릭이 안 된다.
  // (Play Console 실측: 행이 먼저 나와 눌렀더니 아무 일도 없었고, 실제 링크는 행 안의 화살표였다)
  const rank = e => (e.matches('a[href]') ? 0 : e.matches('button,input[type=submit],input[type=button]') ? 1
    : e.matches('[role=link],[role=button],[role=tab],[role=menuitem]') ? 2 : e.matches('[role=row]') ? 4 : 3);
  els = els.map((e, i) => [e, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(x => x[0]);
  const items = [];
  for (const e of els) {
    if (items.length >= o.limit) break;
    if (!visible(e)) continue;
    const ref = items.length + 1;
    e.setAttribute(ATTR, String(ref));
    items.push({ ref, tag: e.tagName.toLowerCase(), role: e.getAttribute('role'),
      text: (e.innerText || e.value || '').replace(/\\s+/g, ' ').trim().slice(0, 120),
      aria: e.getAttribute('aria-label'), href: e.getAttribute('href'),
      clickable: e.matches(o.clickable),
      disabled: !!e.disabled || e.getAttribute('aria-disabled') === 'true' });
  }
  return { items, total: els.length, fallback };
}"""

