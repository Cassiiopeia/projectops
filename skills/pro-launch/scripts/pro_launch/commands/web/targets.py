"""web 에서 요소를 고르고 읽기 전용 세션이 막을 것을 가르는 규칙 — find · inspect · 조작 동작이 함께 쓴다."""
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
  // 이름: aria-label > aria-labelledby > title > 안의 img alt — 아이콘 버튼을 서로 가른다 (#879)
  const nameOf = e => { const by = e.getAttribute('aria-labelledby');
    const labelled = by ? by.split(/\\s+/).map(id => document.getElementById(id)).filter(Boolean).map(x => x.innerText).join(' ') : '';
    const img = e.querySelector('img[alt]');
    return (e.getAttribute('aria-label') || labelled || e.getAttribute('title') || (img && img.getAttribute('alt')) || '')
      .replace(/\\s+/g, ' ').trim() || null; };
  // 아이콘 글꼴 리거처(Material Icons 의 delete · close 등) — 글자로 보이지만 그림이다
  const ICON_CLASS = /material-icons|material-symbols|(^|\\s)(icon|icons)(\\s|$)/i;
  const isIconNode = n => { const c = typeof n.className === 'string' ? n.className : '';
    return ICON_CLASS.test(c) || /material (icons|symbols)/i.test(getComputedStyle(n).fontFamily || ''); };
  // 자손은 앞 20개만 — 큰 행마다 전부 스타일을 읽으면 느리다
  const iconsOf = e => [e, ...[...e.querySelectorAll('*')].slice(0, 20)].filter(isIconNode)
    .map(n => (n.innerText || '').trim()).filter(t => /^[a-z0-9_]+$/.test(t));
  const textOf = e => { let t = (e.innerText || e.value || '').replace(/\\s+/g, ' ').trim();
    const icons = iconsOf(e);
    for (const name of icons) t = t.split(' ').filter(w => w !== name).join(' ');
    if (!t && icons.length) t = icons.map(name => 'icon:' + name).join(' ');
    return { text: t.slice(0, 120), icons }; };
  const label = e => (textOf(e).text + ' ' + (nameOf(e) || '')).replace(/\\s+/g, ' ').trim();
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
    const shown = textOf(e);
    const item = { ref, tag: e.tagName.toLowerCase(), role: e.getAttribute('role'),
      text: shown.text, aria: nameOf(e), href: e.getAttribute('href'),
      clickable: e.matches(o.clickable),
      disabled: !!e.disabled || e.getAttribute('aria-disabled') === 'true' };
    if (shown.icons.length) item.icons = shown.icons;
    items.push(item);
  }
  return { items, total: els.length, fallback };
}"""


# ── 폼 읽기 (#899) — web inspect 와 조작 실패 때의 후보(element.py, #888)가 함께 쓴다 ──

# 역할 이름 → 고를 요소. all 은 전부
ROLE_SELECTORS = {
    "input": ("input:not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit])"
              ":not([type=button]):not([type=reset]):not([type=image]),textarea,[contenteditable=''],"
              "[contenteditable=true],[role=textbox],[role=searchbox],[role=spinbutton]"),
    "button": "button,[role=button],input[type=submit],input[type=button],input[type=reset],input[type=image]",
    "checkbox": "input[type=checkbox],input[type=radio],[role=checkbox],[role=radio],[role=switch]",
    "select": "select,[role=listbox],[role=combobox]",
    "link": "a[href],[role=link]",
}
ROLE_CHOICES = (*ROLE_SELECTORS, "all")
# 흔히 짐작하는 역할 이름 > ROLE_SELECTORS 키. ARIA textbox 만 보면 그냥 <input> 이 안 잡혔다 (#930, npm OTP 실측)
ROLE_ALIASES = {"textbox": "input", "searchbox": "input", "textarea": "input", "combobox": "select",
                "radio": "checkbox", "switch": "checkbox"}


def role_selector(role: str | None) -> str | None:
    """역할 이름 > 실제 요소 선택자. link · button 은 find 가 따로 고르므로 None (그 밖의 모르는 이름도 None)"""
    key = ROLE_ALIASES.get(role or "", role)
    if key in ("link", "button"):
        return None
    return ROLE_SELECTORS.get(key)


# ── 선택자 문법 오류 (#931) — 모든 동작이 같은 안내를 쓴다 ──
# Playwright 선택자 문법 오류 문구 (css 파싱 · querySelectorAll · 없는 엔진) — 기다려도 안 풀린다
SELECTOR_SYNTAX_ERROR_MARKERS = ("while parsing", "is not a valid selector", "Unknown engine")
SELECTOR_SYNTAX_HINT = ("Selector syntax error. Do not mix CSS and text= in one selector — for text use text=Login or "
                        "button:has-text('Login'); comma lists are CSS only. --ref from web find or web inspect beats guessing")


def is_selector_syntax_error(message: str) -> bool:
    return any(marker in message for marker in SELECTOR_SYNTAX_ERROR_MARKERS)
# select 하나에서 돌려줄 선택지 수
MAXIMUM_OPTIONS = 30

INSPECT_JS = """(o) => {
  const ATTR = o.attr;
  document.querySelectorAll('[' + ATTR + ']').forEach(e => e.removeAttribute(ATTR));
  const clean = t => (t || '').replace(/\\s+/g, ' ').trim();
  const visible = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const kindOf = e => { for (const [k, sel] of Object.entries(o.roles)) if (e.matches(sel)) return k; return null; };
  const labelOf = e => {
    const aria = e.getAttribute('aria-label'); if (aria) return clean(aria);
    const by = e.getAttribute('aria-labelledby');
    if (by) { const t = by.split(/\\s+/).map(id => document.getElementById(id)).filter(Boolean)
      .map(x => x.innerText).join(' '); if (clean(t)) return clean(t); }
    if (e.id) { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l && clean(l.innerText)) return clean(l.innerText); }
    const wrap = e.closest('label'); if (wrap && clean(wrap.innerText)) return clean(wrap.innerText);
    if (['input', 'textarea', 'select'].includes(e.tagName.toLowerCase()))
      return clean(e.getAttribute('placeholder') || e.getAttribute('title') || e.getAttribute('name'));
    return clean(e.innerText || e.value || e.getAttribute('title'));
  };
  const selector = o.role === 'all' ? Object.values(o.roles).join(',') : o.roles[o.role];
  let els = [...document.querySelectorAll(selector)].filter(visible);
  let anchorFound = null;
  if (o.near) {
    const t = o.near.toLowerCase();
    // 그 글자를 가진 가장 안쪽 요소들이 기준점이다
    const anchors = [...document.querySelectorAll('body *')].filter(e => visible(e) &&
      (e.innerText || '').toLowerCase().includes(t) &&
      ![...e.children].some(c => (c.innerText || '').toLowerCase().includes(t)));
    anchorFound = anchors.length > 0;
    const center = e => { const r = e.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; };
    const distance = e => {
      if (labelOf(e).toLowerCase().includes(t)) return 0;
      const [x, y] = center(e);
      return Math.min(...anchors.map(a => { const [ax, ay] = center(a); return Math.hypot(ax - x, ay - y); }), Infinity);
    };
    els = els.map(e => [e, distance(e)]).filter(x => x[1] !== Infinity).sort((a, b) => a[1] - b[1]).map(x => x[0]);
  }
  const items = [];
  for (const e of els) {
    if (items.length >= o.limit) break;
    const ref = items.length + 1;
    e.setAttribute(ATTR, String(ref));
    const tag = e.tagName.toLowerCase(); const type = e.getAttribute('type');
    const item = { ref, role: kindOf(e), tag, label: labelOf(e).slice(0, 120) };
    if (type) item.type = type;
    if (e.id) item.id = e.id;
    if (e.getAttribute('name')) item.name = e.getAttribute('name');
    const isCheck = item.role === 'checkbox';
    if (isCheck) item.checked = ('checked' in e && typeof e.checked === 'boolean') ? e.checked
      : e.getAttribute('aria-checked') === 'true';
    else if (type === 'password') item.has_value = !!e.value;   // 비밀번호 값은 돌려주지 않는다
    else if (tag === 'input' || tag === 'textarea') item.value = (e.value || '').slice(0, 200);
    else if (tag === 'select') {
      item.value = e.value;
      item.options = [...e.options].slice(0, o.maxOptions).map(op => ({ value: op.value,
        label: clean(op.label || op.text).slice(0, 80), selected: op.selected }));
      if (e.options.length > o.maxOptions) item.options_truncated = true;
    } else if (e.isContentEditable) item.value = clean(e.innerText).slice(0, 200);
    if (item.role === 'link') item.href = e.getAttribute('href');
    item.disabled = !!e.disabled || e.getAttribute('aria-disabled') === 'true' || !!e.closest('fieldset[disabled]');
    if (e.required || e.getAttribute('aria-required') === 'true') item.required = true;
    items.push(item);
  }
  return { items, total: els.length, anchor_found: anchorFound };
}"""
