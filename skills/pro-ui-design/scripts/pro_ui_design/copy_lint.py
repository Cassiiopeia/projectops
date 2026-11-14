"""copy-lint: mechanical checks on copy candidates (em dash, middle dot, banned words, translationese, hype)"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.emit import emit


# =========================================================================
# copy-lint — only what can be flagged mechanically. The agent writes good copy
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


# Particles that still count as the banned word when attached. Any other following Hangul makes a different word
# (banning "아이" must not flag "아이콘" — real false positive, #636).
_JOSA = ("은", "는", "이", "가", "을", "를", "의", "에", "에게", "께", "와", "과", "도", "만",
         "로", "으로", "랑", "이랑", "들", "한테", "보다", "처럼", "까지", "부터", "라고", "야", "아")


def _banned_hit(word: str, text: str) -> bool:
    for m in re.finditer(re.escape(word), text):
        before = text[m.start() - 1] if m.start() > 0 else ""
        # Preceded by Hangul or alphanumerics means part of another word (misses joined forms like "우리아이" — better than false positives)
        if before and re.match(r"[가-힣A-Za-z0-9]", before):
            continue
        tail = re.match(r"[가-힣A-Za-z0-9]*", text[m.end():]).group(0)
        # Same word if it ends there, the suffix is exactly a particle, or it starts with a plural/dative
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
            continue   # Legal text gets no candidates — not checked either
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
