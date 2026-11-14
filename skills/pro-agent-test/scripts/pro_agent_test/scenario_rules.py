"""Scenario shape: per-target templates, target and expected-result rules, runnability validation"""
from __future__ import annotations

import re


# =========================================================================
# Bootstrap — read from the code what this app looks like
# =========================================================================

_SHARED_DIR = "_shared"
_FLOWS_DIR = "flows"




def _template_for(target: str) -> dict:
    """Scenario template for the target. Each target has its own step unit and evidence."""
    base = {
        "name": "{one line on what this walks}",
        "description": "{why this path matters}",
        "target": target,
        "precondition": None,   # e.g. "_shared/login-kakao" — flow to prepend
        "steps": [dict(_STEP_TEMPLATES[target])],
    }
    if target == "app":
        # Fill only when there are two or more participants. Left empty, it runs on one device as before.
        # Keys use the same value as the device subcommand's --role (#583).
        base["roles"] = {}
        base["reset"] = {
            "device": "pm clear",
            "server": "{command that deletes the test account. null if none}",
        }
        # Environment conditions can only be changed on a device
        base["conditions"] = [
            {"name": "Large text", "apply": "settings put system font_scale 1.3",
             "revert": "settings put system font_scale 1.0"},
            {"name": "Dark mode", "apply": "cmd uimode night yes",
             "revert": "cmd uimode night no"},
        ]
    elif target == "web":
        base["reset"] = {
            "browser": "{how to clear cookies and local storage. Usually a new context}",
            "server": "{command that deletes the test account. null if none}",
        }
        base["conditions"] = [
            {"name": "Narrow screen", "apply": "viewport 390x844", "revert": "viewport 1280x800"},
            {"name": "Dark mode", "apply": "colorScheme dark", "revert": "colorScheme light"},
        ]
    else:  # server
        base["base_url"] = "{API address. Empty uses the value detect found}"
        base["reset"] = {"server": "{command that deletes test data. null if none}"}
    return base


_REQUIRED_STEP_KEYS = ("screen", "do")

# Per-target step templates. One shared template would make web and server users delete half and rewrite it.
_STEP_TEMPLATES = {
    "app": {
        "screen": "{screen name}",
        "do": "{what to do — tap 'Start' / input 'value' / back}",
        "expect_screen": "{what should show next}",
        "expect_device": ["{key to check in the log, e.g. app.refreshToken}"],
        "expect_server": "{query to check on the server. null if none}",
        "human": None,
    },
    "web": {
        "screen": "{page name}",
        "do": "{click 'Log in' / type #email 'value' / goto /signup}",
        "expect_url": "{path it should go to, e.g. /home}",
        "expect_text": "{text that should show on screen}",
        "expect_server": "{query to check on the server. null if none}",
        "human": None,
    },
    "other": {
        "screen": "{name of this step}",
        "do": "{the exact command to run, e.g. npx projectops --type spring --yes}",
        "expect_exit": 0,
        "expect_output": "{text the output must contain. null if none}",
        "expect_file": "{path that must exist after the run. null if none}",
        "expect_absent": "{path that must **not** exist after the run. null if none}",
        "human": None,
    },
    "server": {
        "screen": "-",
        "do": "{POST /api/auth/login {\"id\":\"...\"}}",
        "auth": "{{token} to use the token from an earlier step. null if none}",
        "expect_status": 200,
        "expect_json": "{what to check in the response, e.g. $.accessToken is not empty}",
        "save": {"token": "$.accessToken"},
        "expect_server": "{query to check in the DB. null if none}",
        "human": None,
    },
}

# ── Target = what drives the steps ─────────────────────────────────────────────
#
# **target only decides who runs `do`.** expect_* applies regardless of target.
# So "drive the web while checking the server DB" is expressed naturally —
# what you drive and what you judge by are separate things.
TARGETS = ("app", "web", "server", "other")
# Old scenarios without a value fall here — so existing files need no change at all.
DEFAULT_TARGET = "app"

# Expected results accepted per target. With none, it ends as "the screen showed, so pass", so it is blocked.
_EXPECT_KEYS = {
    "app": ("expect_screen", "expect_device", "expect_server"),
    "web": ("expect_screen", "expect_url", "expect_text", "expect_server"),
    "server": ("expect_status", "expect_json", "expect_server"),
    # other has no screen and no response. What is left is **what was produced**.
    # expect_absent matters most — so far the skill only checked "what must exist",
    # with no eye for what must not appear (leaked test code, leftover temp files, old files).
    "other": ("expect_exit", "expect_output", "expect_file", "expect_absent"),
}


def scenario_target(data: dict) -> str:
    """The scenario's drive target. An unknown value is returned as is, not replaced by the default
    — _validate must catch it and tell the user, so the wrong thing is never driven silently."""
    return data.get("target") or DEFAULT_TARGET

def _validate(data: dict) -> list[str]:
    """Check the scenario is runnable. Filter before driving so it does not stop midway."""
    problems = []
    if not data.get("name"):
        problems.append("name is empty")

        # Settle the axis first. An unknown value is blocked here instead of silently using the default —
        # if one typo sends a web scenario through adb, the cause is hard to find.
    target = scenario_target(data)
    if target not in TARGETS:
        problems.append(f"Unknown target '{target}' — must be one of {'·'.join(TARGETS)}")
        target = DEFAULT_TARGET
    expect_keys = _EXPECT_KEYS[target]

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        problems.append("steps is empty — at least one step to walk is needed")
        return problems
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            problems.append(f"step {i} is not an object")
            continue
        for k in _REQUIRED_STEP_KEYS:
            if not st.get(k):
                problems.append(f"step {i} has no {k}")
        # ⚠️ Do not use a falsy check. `expect_exit: 0` is **the most common expected value**,
        #    but 0 is falsy, so it reads as "no expected result" and a valid scenario is rejected.
        #    Empty strings and empty lists count as not written.
        if not any(st.get(k) not in (None, "", [], {}) for k in expect_keys):
            problems.append(
                f"step {i} ({st.get('screen','?')}) has no expected result — "
                f"one of {'·'.join(k.replace('expect_', '') for k in expect_keys)} "
                "is needed to judge a pass")

    problems += _validate_roles(data, steps, target)
    return problems


# Values are passed as ${name}. The scenario template already uses {braces} as a "fill this in" marker,
# so using the same symbol would leave the validator unable to tell them apart (#583).
_CAPTURE_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _validate_roles(data: dict, steps: list, target: str) -> list[str]:
    """Check a scenario with two or more participants is actually runnable.

    - If `device` points at an undeclared role, the target device is undetermined.
    - If no earlier step produced `${name}`, an empty value gets typed. "Put the value made in A
      into B" would silently run with a blank without this check.
    """
    problems: list[str] = []
    roles = data.get("roles") or {}
    if roles and not isinstance(roles, dict):
        return ["roles must be shaped {role_key: {...}}"]

    used = {st.get("device") for st in steps
            if isinstance(st, dict) and st.get("device")}
    unknown = sorted(d for d in used if d not in roles)
    if unknown:
        problems.append(
            f"step device is not in roles: {', '.join(unknown)} — "
            f"declare it in roles or remove device "
            f"(declared roles: {', '.join(roles) or 'none'})")

    if len(roles) > 1 and target != "app":
        problems.append(
            f"{len(roles)} roles but target is '{target}' — "
            "multiple devices only work for app so far")

    produced: set[str] = set()
    for i, st in enumerate(steps, 1):
        if not isinstance(st, dict):
            continue
        for field in ("do", "text", "expect_screen", "expect_server"):
            for ref in _CAPTURE_REF.findall(str(st.get(field) or "")):
                if ref not in produced:
                    problems.append(
                        f"step {i} uses ${{{ref}}} but no earlier step has "
                        f"capture: \"{ref}\" — it would be walked with an empty value")
        cap = st.get("capture")
        if cap:
            produced.add(cap)
    return problems
