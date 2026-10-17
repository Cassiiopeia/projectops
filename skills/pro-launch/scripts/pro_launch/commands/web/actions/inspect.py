"""`web inspect` — 입력창·버튼·체크·선택·링크를 이름·값·상태와 함께 읽는다 (읽기 전용, #899).

`web find` 는 누를 것을 고르고, 이것은 **폼을 읽는다** — 무엇을 채워야 하고 무엇이 비활성인지.
돌려준 `ref` 는 click · type · check · select · hover 의 --ref 로 그대로 쓴다 (find 와 같은 data-pops-ref).
임의 JS 실행 창구는 두지 않는다 — 읽는 항목이 고정돼 있다.
"""
from __future__ import annotations


from pro_launch.commands.web.session import safe_title
from pro_launch.commands.web.targets import REF_ATTR
from pro_launch.registry import Action

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
# 한 번에 돌려줄 최대 개수 — 넘으면 truncated 로 알린다
MAXIMUM_LIMIT = 100
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


def _web_inspect(page, args) -> dict:
    limit = max(1, min(args.limit, MAXIMUM_LIMIT))
    res = page.evaluate(INSPECT_JS, {"attr": REF_ATTR, "roles": ROLE_SELECTORS, "role": args.role,
                                      "near": args.near, "limit": limit, "maxOptions": MAXIMUM_OPTIONS})
    items = res.get("items") or []
    total = res.get("total") or 0
    if args.near and res.get("anchor_found") is False:
        return {"ok": False, "code": "near_not_found", "action": "inspect", "url": page.url,
                "error": f"'{args.near}' 글자가 화면에 없습니다",
                "next": f'web text --grep "{args.near}"  # 화면에 실제로 있는 글자를 확인한다'}
    if not items:
        return {"ok": False, "code": "nothing_found", "action": "inspect", "url": page.url,
                "title": safe_title(page), "error": f"보이는 {args.role} 요소가 없습니다",
                "next": "web inspect --role all"}
    return {"action": "inspect", "role": args.role, "near": args.near, "items": items,
            "shown": len(items), "total": total, "truncated": total > len(items),
            "url": page.url, "title": safe_title(page),
            "summary": f"{args.role} {len(items)}개 (전체 {total})",
            "next": "web type --ref <번호> --text <값> · web check --ref <번호> · web select --ref <번호> --value <값>"}


def configure(p) -> None:
    p.add_argument("--role", choices=ROLE_CHOICES, default="all", help="읽을 종류 (기본 all)")
    p.add_argument("--near", default=None, help="이 글자 가까이 있는 것부터 (라벨에 그 글자가 있으면 맨 앞)")
    p.add_argument("--limit", type=int, default=40, help=f"돌려줄 최대 개수 (최대 {MAXIMUM_LIMIT})")


def execute(page, args, state: dict) -> dict:
    return _web_inspect(page, args)


ACTION = Action(name="inspect", run=execute, configure=configure, options=(),
                help="입력창·버튼·체크·선택·링크를 이름·값·상태·ref 와 함께 읽는다 (읽기 전용)",
                example='web inspect --role input --near "이메일"')
