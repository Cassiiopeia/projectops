"""대상을 못 찾았거나 기다리다 시간이 다 됐을 때 돌려줄 후보 — 화면에 실제로 있는 입력창·버튼·링크 (#888).

추측한 선택자가 빗나가면 agent 는 다른 추측으로 같은 대기를 되풀이했다(세션 기록 80건).
실패 결과에 후보와 ref 를 실어 다음 호출이 `--ref` 로 바로 가게 한다.
흐름: inspect 와 같은 스캔(ref 달기) > 추측한 선택자 낱말·동작 종류로 순위 > 상위 몇 개만
"""
from __future__ import annotations

import re

from pro_launch.commands.web.targets import INSPECT_JS, REF_ATTR, ROLE_SELECTORS

# 실패 결과에 싣는 후보 수
MAXIMUM_CANDIDATES = 10
# 순위를 매기려고 훑는 요소 수 (ref 는 이만큼 달린다)
CANDIDATE_SCAN_LIMIT = 60
# 후보에 싣는 필드 — 값(value)은 싣지 않는다 (입력된 개인정보가 결과에 남지 않게)
CANDIDATE_FIELDS = ("ref", "role", "tag", "label", "type", "name", "id", "href")

# 선택자 문법에서 나온 낱말 — 화면 글자와 견주지 않는다
SELECTOR_SYNTAX_WORDS = frozenset({
    "has", "text", "type", "nth", "child", "of", "first", "last", "not", "is", "visible", "class", "id",
    "name", "aria", "label", "role", "placeholder", "data", "testid", "test", "value", "contains", "css",
    "xpath", "internal", "control", "enter", "frame",
})
# 선택자 낱말 → 그 낱말이 가리키는 요소 종류 (inspect 의 role 이름)
ROLE_HINT_BY_WORD = {
    "input": "input", "textarea": "input", "textbox": "input", "searchbox": "input", "email": "input",
    "password": "input", "search": "input", "tel": "input", "number": "input",
    "button": "button", "submit": "button", "btn": "button",
    "a": "link", "link": "link", "href": "link",
    "select": "select", "combobox": "select", "listbox": "select", "option": "select",
    "checkbox": "checkbox", "radio": "checkbox", "switch": "checkbox",
}
# 종류만 가리키는 낱말 — 글자로는 견주지 않는다 (button 이 type="button" 과 겹쳐 두 번 세지 않게)
KIND_ONLY_WORDS = frozenset({"input", "textarea", "textbox", "searchbox", "button", "btn", "a", "link", "href",
                             "select", "combobox", "listbox", "option", "checkbox", "radio", "switch"})
# 동작마다 먼저 보여 줄 요소 종류
PREFERRED_ROLES_BY_ACTION = {
    "type": ("input",), "select": ("select",), "check": ("checkbox",),
    "click": ("button", "link", "checkbox"), "download": ("link", "button"),
    "hover": ("link", "button"), "press": ("input", "button", "link"),
}
# next 에 붙일 그 동작의 필수 인자
REQUIRED_ARGUMENT_BY_ACTION = {"type": " --text <value>", "select": " --value <value>", "press": " --key <key>"}

# 점수: 선택자 낱말이 이름·속성에 있음 3 · 선택자가 가리킨 종류 2 · 동작이 다루는 종류 1 · 비활성 -1
WORD_MATCH_SCORE, SELECTOR_ROLE_SCORE, ACTION_ROLE_SCORE, DISABLED_PENALTY = 3, 2, 1, 1


def selector_words(selector: str | None) -> list[str]:
    """선택자에서 화면 글자와 견줄 낱말 (소문자, 문법 낱말 제외). `button:has-text('Next')` > ['button', 'next']"""
    words = []
    for word in re.findall(r"[^\W_]+", (selector or "").lower()):
        is_meaningful = (len(word) >= 2 or not word.isascii()) and word not in SELECTOR_SYNTAX_WORDS
        if is_meaningful and word not in words:
            words.append(word)
    # 'a' 는 한 글자지만 링크 태그를 가리킨다 — 종류 힌트로만 쓴다
    if re.match(r"\s*a(\[|$|\s|:)", (selector or "").lower()):
        words.append("a")
    return words


def candidate_score(item: dict, words: list[str], action: str) -> int:
    """후보 하나가 추측한 선택자·동작에 얼마나 가까운가."""
    haystack = " ".join(str(item.get(field) or "") for field in ("label", "name", "id", "type", "href")).lower()
    hinted_roles = {ROLE_HINT_BY_WORD[word] for word in words if word in ROLE_HINT_BY_WORD}
    score = sum(WORD_MATCH_SCORE for word in words if word not in KIND_ONLY_WORDS and word in haystack)
    if item.get("role") in hinted_roles:
        score += SELECTOR_ROLE_SCORE
    if item.get("role") in PREFERRED_ROLES_BY_ACTION.get(action, ()):
        score += ACTION_ROLE_SCORE
    if item.get("disabled"):
        score -= DISABLED_PENALTY
    return score


def rank_candidates(items: list[dict], selector: str | None, action: str) -> list[dict]:
    """가까운 순(같으면 화면 순서)으로 상위 MAXIMUM_CANDIDATES 개. 필드는 CANDIDATE_FIELDS + disabled 만 남긴다."""
    words = selector_words(selector)
    ordered = sorted(items, key=lambda item: -candidate_score(item, words, action))
    return [{field: item[field] for field in CANDIDATE_FIELDS if item.get(field) not in (None, "")}
            | {"disabled": bool(item.get("disabled"))}
            for item in ordered[:MAXIMUM_CANDIDATES]]


def scan_candidates(page, selector: str | None, action: str) -> list[dict]:
    """지금 화면의 보이는 입력창·버튼·체크·선택·링크에 ref 를 달고 순위를 매긴다. 못 읽으면 빈 목록."""
    try:
        scanned = page.evaluate(INSPECT_JS, {"attr": REF_ATTR, "roles": ROLE_SELECTORS, "role": "all",
                                             "near": None, "limit": CANDIDATE_SCAN_LIMIT, "maxOptions": 0})
    except Exception:   # 이동 중이라 문서가 사라졌다 — 후보 없이 원래 실패만 낸다
        return []
    return rank_candidates((scanned or {}).get("items") or [], selector, action)


def child_frame_count(page) -> int:
    """iframe 수. 후보는 최상위 문서만 훑으므로 대상이 iframe 안일 수 있음을 알리는 데 쓴다."""
    try:
        return max(0, len(page.frames) - 1)
    except Exception:
        return 0


def attach_candidates(failure: dict, page, selector: str | None, action: str) -> dict:
    """실패 결과에 candidates · next(맨 앞 후보의 --ref) · iframe 수를 싣는다. code 는 그대로 둔다."""
    candidates = scan_candidates(page, selector, action)
    if candidates:
        failure["candidates"] = candidates
        # 비활성 후보를 안내하면 element_disabled 로 한 번 더 돈다 — 쓸 수 있는 것 중 맨 앞
        suggested = next((c for c in candidates if not c["disabled"]), candidates[0])
        failure["next"] = (f"web {action} --ref {suggested['ref']}"
                           f"{REQUIRED_ARGUMENT_BY_ACTION.get(action, '')}"
                           "  # picked from candidates (earlier ones are closer to the guessed selector)")
    iframe_count = child_frame_count(page)
    if iframe_count:
        failure["iframe_count"] = iframe_count
        failure["hint"] = "Candidates come from the top-level document only. If the target is inside an iframe, call again with --frame <name|iframe selector|part of url>"
    return failure
