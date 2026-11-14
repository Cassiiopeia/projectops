"""Rules for picking elements in web and deciding what read-only sessions block — shared by find, inspect and the actions."""
from __future__ import annotations

from pro_launch.runtime.mutating import NAV_ROLES, is_mutating_label


# ── Let the agent drive the browser on its own (#825) ───────────────────────────
#
# With only screenshots and "is it there (assert)" the agent couldn't read the screen, so it **guessed** selectors.
# Guessed clicks hit the wrong menu and still returned ok (observed in Play Console). So the loop changes.
#
#   web find  → returns candidates with a number (ref), text and link URL (tags elements with data-pops-ref)
#   web click --ref N --expect-url/--expect-text → clicks only that element and reports failure if the result doesn't come
#   web text  → reads visible text (much cheaper than a screenshot)
#
# Admin consoles (Play Console, App Store Connect) are opened with `web open --readonly`.
# In a read-only session, buttons that do irreversible things are not clicked without --confirm-mutating.
REF_ATTR = "data-pops-ref"


# Blocking phrases and navigation element lists live in runtime/mutating.py — desktop uses the same rules (#985).
def is_mutating_target(info: dict) -> bool:
    """Decide using the element kind too. Links, tabs and rows navigate so they pass; only button-like elements are checked by text."""
    tag, role = (info.get("tag") or ""), (info.get("role") or "")
    if (tag == "a" and info.get("href")) or role in NAV_ROLES:
        return False
    return is_mutating_label(f"{info.get('text') or ''} {info.get('aria') or ''}")


# Elements considered clickable. Table rows (role=row) are included — consoles often make the whole row a link.
CLICKABLE = ("a[href],button,[role=button],[role=link],[role=tab],[role=menuitem],[role=row],"
              "[role=option],[role=checkbox],[role=switch],[onclick],input[type=submit],"
              "input[type=button],input[type=checkbox],summary")


# Modal first (projectops#1023) — the confirm modal's load button was pushed past the limit (20) by 60 same-text buttons in the panel behind.
#   Modal: topmost of dialog[open], role=dialog/alertdialog, aria-modal=true (higher z-index > later in the document)
#   Otherwise a fixed layer (z-index > 0) covering the screen center counts as a modal. Don't mistake a fixed frame wrapping the whole page for a modal
#   Accepted only if there are also visible click targets outside it
#   Order: inside modal > element kind (rank) > document order. Candidates inside get in_modal: true, the result gets a modal summary
FIND_JS = """(o) => {
  const ATTR = o.attr;
  document.querySelectorAll('[' + ATTR + ']').forEach(e => e.removeAttribute(ATTR));
  const visible = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  // Name: aria-label > aria-labelledby > title > inner img alt — tells icon buttons apart (#879)
  const nameOf = e => { const by = e.getAttribute('aria-labelledby');
    const labelled = by ? by.split(/\\s+/).map(id => document.getElementById(id)).filter(Boolean).map(x => x.innerText).join(' ') : '';
    const img = e.querySelector('img[alt]');
    return (e.getAttribute('aria-label') || labelled || e.getAttribute('title') || (img && img.getAttribute('alt')) || '')
      .replace(/\\s+/g, ' ').trim() || null; };
  // Icon font ligatures (Material Icons delete, close etc.) — look like text but are pictures
  const ICON_CLASS = /material-icons|material-symbols|(^|\\s)(icon|icons)(\\s|$)/i;
  const isIconNode = n => { const c = typeof n.className === 'string' ? n.className : '';
    return ICON_CLASS.test(c) || /material (icons|symbols)/i.test(getComputedStyle(n).fontFamily || ''); };
  // Only the first 20 descendants — reading styles of everything in every big row is slow
  const iconsOf = e => [e, ...[...e.querySelectorAll('*')].slice(0, 20)].filter(isIconNode)
    .map(n => (n.innerText || '').trim()).filter(t => /^[a-z0-9_]+$/.test(t));
  const textOf = e => { let t = (e.innerText || e.value || '').replace(/\\s+/g, ' ').trim();
    const icons = iconsOf(e);
    for (const name of icons) t = t.split(' ').filter(w => w !== name).join(' ');
    if (!t && icons.length) t = icons.map(name => 'icon:' + name).join(' ');
    return { text: t.slice(0, 120), icons }; };
  const label = e => (textOf(e).text + ' ' + (nameOf(e) || '')).replace(/\\s+/g, ' ').trim();
  // open modal first (see the note above FIND_JS)
  const zOf = e => { let n = e, best = 0; while (n && n !== document.body) {
    const z = parseInt(getComputedStyle(n).zIndex, 10); if (!isNaN(z) && z > best) best = z; n = n.parentElement; } return best; };
  const topModal = () => {
    const dialogs = [...document.querySelectorAll('dialog[open],[role=dialog],[role=alertdialog],[aria-modal=true]')]
      .filter(e => visible(e) && e.getAttribute('aria-hidden') !== 'true');
    if (dialogs.length) return { el: dialogs.map((e, i) => [e, zOf(e), i]).sort((a, b) => b[1] - a[1] || b[2] - a[2])[0][0], kind: 'dialog' };
    const hit = document.elementFromPoint ? document.elementFromPoint(innerWidth / 2, innerHeight / 2) : null;
    for (let n = hit; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.position === 'fixed' && parseInt(s.zIndex, 10) > 0) {
        const outside = [...document.querySelectorAll(o.clickable)].some(e => !n.contains(e) && visible(e));
        return outside ? { el: n, kind: 'overlay' } : null;
      }
    }
    return null;
  };
  const modal = topModal();
  const inModal = e => !!modal && modal.el.contains(e);
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
      // If the clickable element doesn't contain the text, find the innermost element holding it and climb to the nearest click target
      const leaves = [...document.querySelectorAll('body *')].filter(e =>
        (e.innerText || '').toLowerCase().includes(t) &&
        ![...e.children].some(c => (c.innerText || '').toLowerCase().includes(t)));
      hit = [...new Set(leaves.map(e => e.closest(o.clickable) || e))];
      fallback = true;
    }
    els = hit;
  }
  // Most specific first — real links and buttons must come before the rows wrapping them so clicking the first candidate isn't a dud.
  // (Observed in Play Console: the row came first and clicking it did nothing; the real link was the arrow inside the row)
  const rank = e => (e.matches('a[href]') ? 0 : e.matches('button,input[type=submit],input[type=button]') ? 1
    : e.matches('[role=link],[role=button],[role=tab],[role=menuitem]') ? 2 : e.matches('[role=row]') ? 4 : 3);
  els = els.map((e, i) => [e, i, inModal(e) ? 0 : 1])
    .sort((a, b) => a[2] - b[2] || rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(x => x[0]);
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
    if (inModal(e)) item.in_modal = true;
    items.push(item);
  }
  const modalInfo = modal ? { kind: modal.kind, role: modal.el.getAttribute('role'),
    label: (nameOf(modal.el) || (modal.el.innerText || '').replace(/\\s+/g, ' ').trim()).slice(0, 80),
    candidates: els.filter(inModal).length } : null;
  return { items, total: els.length, fallback, modal: modalInfo };
}"""


# ── Form reading (#899) — shared by web inspect and the candidates shown on action failure (element.py, #888) ──

# Role name → elements to pick. all means everything
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
# Commonly guessed role names > ROLE_SELECTORS keys. ARIA textbox alone missed a plain <input> (#930, observed with npm OTP)
ROLE_ALIASES = {"textbox": "input", "searchbox": "input", "textarea": "input", "combobox": "select",
                "radio": "checkbox", "switch": "checkbox"}


def role_selector(role: str | None) -> str | None:
    """Role name > actual element selector. None for link and button since find picks them separately (and for other unknown names)"""
    key = ROLE_ALIASES.get(role or "", role)
    if key in ("link", "button"):
        return None
    return ROLE_SELECTORS.get(key)


# ── Selector syntax errors (#931) — every action uses the same hint ──
# Playwright selector syntax error messages (css parse, querySelectorAll, unknown engine) — waiting won't fix them
SELECTOR_SYNTAX_ERROR_MARKERS = ("while parsing", "is not a valid selector", "Unknown engine")
SELECTOR_SYNTAX_HINT = ("Selector syntax error. Do not mix CSS and text= in one selector — for text use text=Login or "
                        "button:has-text('Login'); comma lists are CSS only. --ref from web find or web inspect beats guessing")


def is_selector_syntax_error(message: str) -> bool:
    return any(marker in message for marker in SELECTOR_SYNTAX_ERROR_MARKERS)
# Number of options returned per select
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
    // Innermost elements holding that text are the anchors
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
    else if (type === 'password') item.has_value = !!e.value;   // never return password values
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
