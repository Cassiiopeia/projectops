"""copy-lint: 문구 후보의 기계적 검사 (em dash · 가운뎃점 · 금지어 · 번역투 · 과장)"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.emit import emit


# =========================================================================
# copy-lint — 기계적으로 짚을 수 있는 것만. 좋은 문구는 agent 가 쓴다
# =========================================================================

_TRANSLATIONESE = [
    (r"하실 수 있습니다", "translationese: shorten it, like '~할 수 있어요'"),
    (r"되었습니다", "passive, stiff: try '~했어요'"),
    (r"에 대한", "translationese '에 대한': check whether it reads fine without it"),
    (r"을 통해|를 통해", "translationese '~을 통해'"),
    (r"것입니다", "stiff: in 해요체 use '~예요'"),
]
_HYPE = ["혁신적", "완벽한", "완벽하게", "최고의", "놀라운", "획기적", "압도적"]


def lint_text(text: str, banned: list[str]) -> list[str]:
    found = []
    if "—" in text or "–" in text:
        found.append("em dash: reads as AI-written; use a comma or split the sentence")
    if text.count("·") >= 2:
        found.append("too many middle dots (·)")
    for pat, why in _TRANSLATIONESE:
        if re.search(pat, text):
            found.append(why)
    for w in _HYPE:
        if w in text:
            found.append(f"overstated '{w}'")
    for w in banned:
        if w and _banned_hit(w, text):
            found.append(f"word the repo decided not to use '{w}'")
    return found


# 금지어 뒤에 붙어도 같은 말로 보는 조사. 이것 말고 한글이 이어지면 다른 낱말이다
# ("아이" 금지인데 "아이콘" 을 잡으면 안 된다 — 실측 오탐, #636).
_JOSA = ("은", "는", "이", "가", "을", "를", "의", "에", "에게", "께", "와", "과", "도", "만",
         "로", "으로", "랑", "이랑", "들", "한테", "보다", "처럼", "까지", "부터", "라고", "야", "아")


def _banned_hit(word: str, text: str) -> bool:
    for m in re.finditer(re.escape(word), text):
        before = text[m.start() - 1] if m.start() > 0 else ""
        # 앞이 한글·영숫자면 다른 낱말의 일부다 ("우리아이" 처럼 붙여 쓴 것은 놓친다 — 오탐보다 낫다)
        if before and re.match(r"[가-힣A-Za-z0-9]", before):
            continue
        tail = re.match(r"[가-힣A-Za-z0-9]*", text[m.end():]).group(0)
        # 바로 끝나거나, 붙은 것이 조사 그대로거나, 복수·여격으로 시작하면 같은 말이다
        if not tail or tail in _JOSA or tail.startswith(("들", "에게", "한테")):
            return True
    return False


def cmd_copy_lint(args) -> int:
    try:
        rows = json.loads(Path(args.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return emit({"ok": False, "code": "bad_file", "error": str(e)})
    if isinstance(rows, dict):
        rows = rows.get("copy") or []
    if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
        return emit({"ok": False, "code": "bad_data",
                     "error": "The copy table must be an array of objects or an object with a copy array",
                     "next": 'e.g. [{"where":"button","current":"OK","candidates":["Save"]}]'})
    banned = []
    if args.banned:
        bf = Path(args.banned)
        banned = ([l.strip() for l in bf.read_text(encoding="utf-8").splitlines() if l.strip()]
                  if bf.is_file() else [w.strip() for w in args.banned.split(",") if w.strip()])
    issues, checked = [], 0
    for r in rows:
        if r.get("legal"):
            continue   # 법적 문구는 후보를 내지 않는다 — 검사 대상도 아니다
        for kind, texts in (("current", [r.get("current")]), ("candidate", r.get("candidates") or [])):
            for t in texts:
                if not t:
                    continue
                checked += 1
                hits = lint_text(str(t), banned)
                if hits:
                    issues.append({"where": r.get("where"), "kind": kind, "text": t, "problems": hits})
    cand_issues = [i for i in issues if i["kind"] == "candidate"]
    return emit({"ok": not cand_issues, "code": "ok" if not cand_issues else "candidate_issues",
                 "checked": checked, "issues": issues,
                 "summary": f"{len(issues)} of {checked} sentence(s) flagged"
                            + (f" ({len(cand_issues)} candidate(s))" if cand_issues else ""),
                 "next": ("Fix the flagged candidates and run again. Flags on the current copy are material for the 'reason' column"
                          if issues else None)})
