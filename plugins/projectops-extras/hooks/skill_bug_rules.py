"""Source of truth for projectops tool anomaly rules (#997·#1000): one Bash call > classification, session state + classification > rules to fire
No I/O (judgment only). Thresholds tuned on a scan of 1,941 sessions across all accounts.
"""
from __future__ import annotations

import re
import time

# projectops CLI call: {tool}_cli.py {word1} [{word2}] [{word3}]
PROJECTOPS_CLI_PATTERN = re.compile(
    r"\b(launch_cli|projectops_cli|github_cli|commit_cli|changelog_cli|report_cli|e2e_cli|figma_cli|worktree_cli"
    r"|ui_design_cli|oss_cli|review_cli|testcase_cli)\.py\s+([a-z][\w-]*)(?:\s+([a-z][\w-]*))?(?:\s+([a-z][\w-]*))?")
# Calls made by the report itself (prevents recursion)
REPORT_CALL_MARKERS = ("bug_cli.py", "Cassiiopeia projectops", "pro-skill-bug")
# Failure codes that are normal by design (waiting for user confirmation, etc.)
BY_DESIGN_CODES = {"ok", "needs_user", "needs_user_approval", "needs_confirmation"}
# Calls the user rejected or the harness blocked
NOT_A_TOOL_FAILURE_MARKERS = ("doesn't want to proceed", "Blocked:", "was rejected")

# Failure: JSON ok:false, a usage error, or an exception inside a projectops file (Traceback text inside CI logs excluded)
FAILURE_PATTERN = re.compile(r'"ok":\s*false')
USAGE_ERROR_PATTERN = re.compile(r"usage: \w+_cli|error: (argument|unrecognized arguments|the following arguments)"
                                 r"|invalid choice")
CODE_PATTERN = re.compile(r'"code":\s*"([\w-]+)"')
# Help request (-h/--help): normal when argparse prints usage: without an error line (#1003)
HELP_FLAG_PATTERN = re.compile(r"(?:^|\s)(?:-h|--help)(?:\s|$)")
ARGPARSE_ERROR_LINE_PATTERN = re.compile(r"^\S*: error: |\berror: ", re.MULTILINE)
# Exceptions raised inside projectops files (pipe parsers the agent added, <stdin>/<string>, excluded)
CLI_CRASH_PATTERN = re.compile(r'File "[^"]*(?:_cli\.py|/pro_[a-z_]+/|/scripts/common/|/git_worktree/|/figma_tools/|/oss_consult/)[^"]*", line')
# Codes where the tool itself says "not available": report on 1st hit / subcommand missing in argparse: classify only (often name typos, so 1 hit does not fire)
MISSING_FEATURE_CODES = {"not_supported"}
MISSING_FEATURE_CODE_PREFIXES = ("unsupported_", "unknown_")
INVALID_CHOICE_MARKER = "invalid choice"

# Tool > skill name (title [<skill>] · dedup key). For projectops_cli the first word is the skill
SKILL_BY_TOOL = {"launch_cli": "launch", "e2e_cli": "agent-test", "github_cli": "github",
                 "changelog_cli": "changelog-deploy", "commit_cli": "commit", "report_cli": "report",
                 "figma_cli": "figma", "worktree_cli": "init-worktree", "ui_design_cli": "ui-design",
                 "oss_cli": "oss-consult", "review_cli": "review", "testcase_cli": "testcase"}
# Subcommand groups read as two words (launch web click · github actions joblog). Otherwise the second word is an argument
NESTED_SUBCOMMAND_GROUPS = {"web", "app", "device", "desktop", "db", "logs", "cred", "ssh", "local", "kb", "access",
                            "http", "render", "actions", "explore", "secrets"}
# Skill > workaround group (for workaround table lookup only). Skills not listed are caught only by the repeat-failure, exception and missing-feature rules
WORKAROUND_GROUP_BY_SKILL = {"launch": "launch", "agent-test": "launch", "github": "github",
                             "changelog-deploy": "github", "report": "github", "oss-consult": "github",
                             "commit": "commit", "init-worktree": "worktree", "figma": "figma"}
# 4 checks per workaround group: first-word tool, git subcommand (+next word), executed-piece pattern, whole-command pattern (including heredoc code)
WORKAROUND_RULES_BY_GROUP = {
    "launch": {"tools": ("adb", "xcrun", "idb", "maestro", "osascript"),
               "command_pattern": re.compile(r"remote-debugging-port|playwright\.sync_api|connect_over_cdp")},
    "github": {"tools": ("gh",), "segment_pattern": re.compile(r"^curl\b.*api\.github\.com"),
               "command_pattern": re.compile(r"(?s)(?=.*api\.github\.com)(?=.*\b(?:urllib|requests)\b)")},
    "commit": {"git": (("commit",),)},
    "worktree": {"git": (("worktree", "add"),)},
    "figma": {"segment_pattern": re.compile(r"^curl\b.*api\.figma\.com"),
              "command_pattern": re.compile(r"(?s)(?=.*api\.figma\.com)(?=.*\b(?:urllib|requests)\b)")},
}
# Subcommands whose success clears the group's pending workaround: a new device leased via the skill > later raw tool calls target that device (#1128)
FRESH_START_SUBCOMMANDS_BY_GROUP = {"launch": ("device acquire",)}
_SEGMENT_SEPARATOR_PATTERN =re.compile(r"&&|\|\||[;|\n()]")
_ENV_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
_COMMAND_PREFIX_WORDS = ("sudo", "env", "exec", "time", "timeout")

# Thresholds: Bash calls watched for a workaround after a failure (including projectops calls, #1022), same usage-error count, same-code failure count, reports per session cap
WORKAROUND_WINDOW_CALLS = 7
USAGE_ERROR_REPEAT_COUNT = 2
SAME_FAILURE_REPEAT_COUNT = 3
MAX_REPORTS_PER_SESSION = 3
# Length of the result head the hook keeps (bug_cli reads the full text from the transcript)
EXCERPT_CHARS = 2000


def classify_call(command: str, output: str, tool_use_id: str | None = None) -> dict | None:
    """One Bash call > {kind: projectops|other, skill, subcommand, group, is_failure, failure_kind, code, ...} (None for report calls)"""
    if any(marker in command for marker in REPORT_CALL_MARKERS):
        return None
    match = PROJECTOPS_CLI_PATTERN.search(command)
    if not match:
        return {"kind": "other"}
    tool = match.group(1)
    skill, subcommand = _skill_and_subcommand(tool, [word for word in match.groups()[1:] if word])
    head = output[:6000]
    code_match = CODE_PATTERN.search(head)
    code = code_match.group(1) if code_match else None
    is_help_request = bool(HELP_FLAG_PATTERN.search(command)) and not ARGPARSE_ERROR_LINE_PATTERN.search(head)
    is_usage_error = bool(USAGE_ERROR_PATTERN.search(head)) and not is_help_request
    is_crash = bool(CLI_CRASH_PATTERN.search(head))
    is_failure = ((bool(FAILURE_PATTERN.search(head)) or is_usage_error or is_crash) and code not in BY_DESIGN_CODES
                  and not any(marker in head for marker in NOT_A_TOOL_FAILURE_MARKERS))
    return {"kind": "projectops", "tool": tool, "skill": skill, "subcommand": subcommand,
            "group": WORKAROUND_GROUP_BY_SKILL.get(skill), "is_failure": is_failure,
            "failure_kind": _failure_kind(head, code, is_usage_error, is_crash) if is_failure else None,
            "code": code, "is_usage_error": is_failure and is_usage_error, "is_crash": is_failure and is_crash,
            "tool_use_id": tool_use_id, "excerpt": head[:EXCERPT_CHARS]}


def _skill_and_subcommand(tool: str, words: list[str]) -> tuple[str, str]:
    """Tool + following words > (skill, subcommand). For projectops_cli, take the first word as the skill and apply the same rule to the rest"""
    if tool == "projectops_cli":
        skill, words = (words[0], words[1:]) if words else ("unknown", [])
    else:
        skill = SKILL_BY_TOOL.get(tool, tool)
    if not words:
        return skill, ""
    if words[0] in NESTED_SUBCOMMAND_GROUPS and len(words) > 1:
        return skill, f"{words[0]} {words[1]}"
    return skill, words[0]


def _failure_kind(head: str, code: str | None, is_usage_error: bool, is_crash: bool) -> str:
    """One failure kind (priority: crash > missing_feature > usage > failure)"""
    if is_crash:
        return "crash"
    if is_missing_feature_code(code) or INVALID_CHOICE_MARKER in head:
        return "missing_feature"
    if is_usage_error:
        return "usage"
    return "failure"


def is_missing_feature_code(code: str | None) -> bool:
    return bool(code) and (code in MISSING_FEATURE_CODES or code.startswith(MISSING_FEATURE_CODE_PREFIXES))


def evaluate(state: dict, call: dict, command: str) -> list[dict]:
    """Update session state + rules fired by this call > [alarm] (after cap and dedup)"""
    state.setdefault("counts", {})
    state.setdefault("reported_keys", [])
    state.setdefault("report_count", 0)
    if call["kind"] == "other":
        fired = _check_workaround(state, command)
    else:
        fired = _check_projectops_call(state, call)
    accepted = []
    for alarm in fired:
        if state["report_count"] >= MAX_REPORTS_PER_SESSION or alarm["key"] in state["reported_keys"]:
            continue
        state["reported_keys"].append(alarm["key"])
        state["report_count"] += 1
        accepted.append(alarm)
    return accepted


def _check_projectops_call(state: dict, call: dict) -> list[dict]:
    """projectops call: check exception, missing feature, repeated usage error, repeated same failure; register a pending workaround on failure"""
    name = f"{call['skill']}:{call['subcommand']}"
    _advance_workaround_window(state, call)
    if not call["is_failure"]:
        state["counts"].pop(f"same:{name}", None)
        return []
    # Same-failure count (restarts when the code changes)
    same_key = f"same:{name}"
    if state.get("last_failure_code_by_name", {}).get(name) != call["code"]:
        state["counts"][same_key] = 0
    state.setdefault("last_failure_code_by_name", {})[name] = call["code"]
    same_count = _increment(state, same_key)

    alarms = []
    if call["is_crash"]:
        alarms.append(_alarm("cli_crash", call, same_count))
    if is_missing_feature_code(call["code"]):
        alarms.append(_alarm("missing_feature_reported", call, same_count))
    # Calls with an unreadable subcommand (shell function wrappers "$@" etc.) lump different calls under one key and look repeated > not counted (#1003)
    # The alarm's failure_count is the usage-error count this rule tracked (writing same_count reads as "2-hit rule fired after 1 hit", #1016)
    if call["is_usage_error"] and call["subcommand"]:
        usage_error_count = _increment(state, f"usage:{name}")
        if usage_error_count >= USAGE_ERROR_REPEAT_COUNT:
            alarms.append(_alarm("usage_error_repeated", call, usage_error_count))
    if same_count >= SAME_FAILURE_REPEAT_COUNT:
        alarms.append(_alarm("same_failure_repeated", call, same_count))
    # Pending workaround: only skills with a workaround group
    if call["group"]:
        state["pending_failure"] = {key: call[key] for key in
                                    ("skill", "subcommand", "group", "code", "failure_kind", "tool_use_id", "excerpt")}
        state["pending_failure"].update({"failure_count": same_count, "calls_seen": 0})
    return alarms


def _advance_workaround_window(state: dict, call: dict) -> None:
    """projectops calls also count toward the workaround window (window used up, same command succeeds, or new device lease succeeds > clear pending, #1022·#1128)"""
    pending = state.get("pending_failure")
    if not pending:
        return
    pending["calls_seen"] = pending.get("calls_seen", 0) + 1
    # For commit, checking usage then succeeding with another subcommand is normal: success in the same skill resolves it (#1072)
    is_same_skill_recovered = (not call["is_failure"] and call["skill"] == pending.get("skill")
                               and (call["subcommand"] == pending.get("subcommand") or pending.get("group") == "commit"))
    is_fresh_start = (not call["is_failure"] and call["group"] == pending.get("group")
                      and call["subcommand"] in FRESH_START_SUBCOMMANDS_BY_GROUP.get(call["group"], ()))
    if is_same_skill_recovered or is_fresh_start or pending["calls_seen"] >= WORKAROUND_WINDOW_CALLS:
        state.pop("pending_failure", None)


def _check_workaround(state: dict, command: str) -> list[dict]:
    """Non-projectops call: if a recent failure is pending, check whether it is a raw command of the same group"""
    pending = state.get("pending_failure")
    if not pending or not pending.get("group"):
        state.pop("pending_failure", None)
        return []
    pending["calls_seen"] = pending.get("calls_seen", 0) + 1
    if is_workaround_command(command, pending["group"]):
        state.pop("pending_failure", None)
        return [_alarm("workaround_after_failure", pending, pending.get("failure_count", 1),
                       workaround=command[:1000], calls_between=pending["calls_seen"] - 1)]
    if pending["calls_seen"] >= WORKAROUND_WINDOW_CALLS:
        state.pop("pending_failure", None)
    return []


def is_workaround_command(command: str, group: str) -> bool:
    """Command > whether it is a raw workaround of the same group (non-executed text like heredoc bodies is not a first word, so excluded)"""
    rules = WORKAROUND_RULES_BY_GROUP.get(group) or {}
    command_pattern = rules.get("command_pattern")
    if command_pattern and command_pattern.search(command):
        return True
    for segment in _SEGMENT_SEPARATOR_PATTERN.split(command.split("<<", 1)[0]):
        words = _strip_command_prefix(segment.split())
        if not words:
            continue
        if words[0].strip("\"'").rsplit("/", 1)[-1] in rules.get("tools", ()):
            return True
        # git commit --no-edit: finishes a merge, which pro-commit cannot do (#1072)
        if words[0] == "git" and "--no-edit" not in words and _is_git_subcommand(words, rules.get("git", ())):
            return True
        segment_pattern = rules.get("segment_pattern")
        if segment_pattern and segment_pattern.search(" ".join(words)):
            return True
    return False


def _strip_command_prefix(words: list[str]) -> list[str]:
    """Strip leading env assignments and prefix words like sudo/env/timeout"""
    while words and (_ENV_ASSIGNMENT_PATTERN.match(words[0]) or words[0] in _COMMAND_PREFIX_WORDS):
        words.pop(0)
        if words and words[0].isdigit():
            words.pop(0)
    return words


def _is_git_subcommand(words: list[str], expected: tuple) -> bool:
    """Whether git [-C path] subcommand [next word] matches one of expected"""
    rest = words[1:]
    while rest[:1] in (["-C"], ["-c"]):
        rest = rest[2:]
    return any(tuple(rest[:len(parts)]) == parts for parts in expected)


def _increment(state: dict, key: str) -> int:
    state["counts"][key] = state["counts"].get(key, 0) + 1
    return state["counts"][key]


def _alarm(rule: str, source: dict, failure_count: int, workaround: str | None = None,
           calls_between: int | None = None) -> dict:
    """One alarm (key: <rule>|<skill>:<subcommand>|<code or none>) + evidence"""
    code = source.get("code") or "none"
    alarm = {"rule": rule, "key": f"{rule}|{source['skill']}:{source['subcommand']}|{code}",
             "skill": source["skill"], "subcommand": source["subcommand"], "code": source.get("code"),
             "kind": source.get("failure_kind"), "tool_use_id": source.get("tool_use_id"),
             "excerpt": source.get("excerpt", ""), "failure_count": failure_count, "at": int(time.time())}
    if workaround:
        alarm["workaround"] = workaround
        alarm["calls_between"] = calls_between
    return alarm
