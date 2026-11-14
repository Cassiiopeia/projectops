"""Candidates returned when the target isn't found or waiting times out — inputs, buttons and links actually on screen (#888).

When a guessed selector missed, the agent repeated the same wait with another guess (80 cases in session logs).
Failure results carry candidates and refs so the next call can go straight to `--ref`.
Flow: same scan as inspect (attach refs) > rank by guessed selector words and action kind > keep the top few
"""
from __future__ import annotations

import re

from pro_launch.commands.web.targets import INSPECT_JS, REF_ATTR, ROLE_SELECTORS

# Number of candidates included in a failure result
MAXIMUM_CANDIDATES = 10
# Number of elements scanned for ranking (this many get refs)
CANDIDATE_SCAN_LIMIT = 60
# Fields included per candidate — no value (so typed personal data doesn't end up in results)
CANDIDATE_FIELDS = ("ref", "role", "tag", "label", "type", "name", "id", "href")

# Words that come from selector syntax — not compared with on-screen text
SELECTOR_SYNTAX_WORDS = frozenset({
    "has", "text", "type", "nth", "child", "of", "first", "last", "not", "is", "visible", "class", "id",
    "name", "aria", "label", "role", "placeholder", "data", "testid", "test", "value", "contains", "css",
    "xpath", "internal", "control", "enter", "frame",
})
# Selector word → element kind it points to (inspect role name)
ROLE_HINT_BY_WORD = {
    "input": "input", "textarea": "input", "textbox": "input", "searchbox": "input", "email": "input",
    "password": "input", "search": "input", "tel": "input", "number": "input",
    "button": "button", "submit": "button", "btn": "button",
    "a": "link", "link": "link", "href": "link",
    "select": "select", "combobox": "select", "listbox": "select", "option": "select",
    "checkbox": "checkbox", "radio": "checkbox", "switch": "checkbox",
}
# Words that only name a kind — not compared as text (so button doesn't count twice with type="button")
KIND_ONLY_WORDS = frozenset({"input", "textarea", "textbox", "searchbox", "button", "btn", "a", "link", "href",
                             "select", "combobox", "listbox", "option", "checkbox", "radio", "switch"})
# Element kinds shown first for each action
PREFERRED_ROLES_BY_ACTION = {
    "type": ("input",), "select": ("select",), "check": ("checkbox",),
    "click": ("button", "link", "checkbox"), "download": ("link", "button"),
    "hover": ("link", "button"), "press": ("input", "button", "link"),
}
# Required argument of that action appended to next
REQUIRED_ARGUMENT_BY_ACTION = {"type": " --text <value>", "select": " --value <value>", "press": " --key <key>"}

# Score: selector word in name/attributes 3, kind the selector pointed to 2, kind the action handles 1, disabled -1
WORD_MATCH_SCORE, SELECTOR_ROLE_SCORE, ACTION_ROLE_SCORE, DISABLED_PENALTY = 3, 2, 1, 1


def selector_words(selector: str | None) -> list[str]:
    """Words from the selector to compare with on-screen text (lowercase, syntax words removed). `button:has-text('Next')` > ['button', 'next']"""
    words = []
    for word in re.findall(r"[^\W_]+", (selector or "").lower()):
        is_meaningful = (len(word) >= 2 or not word.isascii()) and word not in SELECTOR_SYNTAX_WORDS
        if is_meaningful and word not in words:
            words.append(word)
    # 'a' is one letter but means the link tag — use only as a kind hint
    if re.match(r"\s*a(\[|$|\s|:)", (selector or "").lower()):
        words.append("a")
    return words


def candidate_score(item: dict, words: list[str], action: str) -> int:
    """How close one candidate is to the guessed selector and action."""
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
    """Top MAXIMUM_CANDIDATES by closeness (ties by screen order). Keeps only CANDIDATE_FIELDS + disabled."""
    words = selector_words(selector)
    ordered = sorted(items, key=lambda item: -candidate_score(item, words, action))
    return [{field: item[field] for field in CANDIDATE_FIELDS if item.get(field) not in (None, "")}
            | {"disabled": bool(item.get("disabled"))}
            for item in ordered[:MAXIMUM_CANDIDATES]]


def scan_candidates(page, selector: str | None, action: str) -> list[dict]:
    """Attach refs to visible inputs, buttons, checks, selects and links on the current screen and rank them. Empty list if unreadable."""
    try:
        scanned = page.evaluate(INSPECT_JS, {"attr": REF_ATTR, "roles": ROLE_SELECTORS, "role": "all",
                                             "near": None, "limit": CANDIDATE_SCAN_LIMIT, "maxOptions": 0})
    except Exception:   # document gone mid-navigation — return just the original failure without candidates
        return []
    return rank_candidates((scanned or {}).get("items") or [], selector, action)


def child_frame_count(page) -> int:
    """Number of iframes. Candidates scan only the top document, so this signals the target may be inside an iframe."""
    try:
        return max(0, len(page.frames) - 1)
    except Exception:
        return 0


def attach_candidates(failure: dict, page, selector: str | None, action: str) -> dict:
    """Add candidates, next (--ref of the top candidate) and iframe count to the failure result. Leaves code unchanged."""
    candidates = scan_candidates(page, selector, action)
    if candidates:
        failure["candidates"] = candidates
        # Suggesting a disabled candidate loops once more into element_disabled — use the first usable one
        suggested = next((c for c in candidates if not c["disabled"]), candidates[0])
        failure["next"] = (f"web {action} --ref {suggested['ref']}"
                           f"{REQUIRED_ARGUMENT_BY_ACTION.get(action, '')}"
                           "  # picked from candidates (earlier ones are closer to the guessed selector)")
    iframe_count = child_frame_count(page)
    if iframe_count:
        failure["iframe_count"] = iframe_count
        failure["hint"] = "Candidates come from the top-level document only. If the target is inside an iframe, call again with --frame <name|iframe selector|part of url>"
    return failure
