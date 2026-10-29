"""projectops 도구 이상 감지 규칙 정본 (#997·#1000): Bash 호출 1건 > 분류, 세션 상태 + 분류 > 울릴 규칙
입출력 없음 (판정만). 문턱값은 전 계정 세션 1,941개 스캔에 맞춘 값.
"""
from __future__ import annotations

import re
import time

# projectops CLI 호출: {도구}_cli.py {단어1} [{단어2}] [{단어3}]
PROJECTOPS_CLI_PATTERN = re.compile(
    r"\b(launch_cli|projectops_cli|github_cli|commit_cli|changelog_cli|report_cli|e2e_cli|figma_cli|worktree_cli"
    r"|design_brief_cli|oss_cli|review_cli|testcase_cli)\.py\s+([a-z][\w-]*)(?:\s+([a-z][\w-]*))?(?:\s+([a-z][\w-]*))?")
# 보고 자체의 호출 (재귀 방지)
REPORT_CALL_MARKERS = ("bug_cli.py", "Cassiiopeia projectops", "pro-skill-bug")
# 설계상 정상인 실패 code (사용자 확인 대기 등)
BY_DESIGN_CODES = {"ok", "needs_user", "needs_user_approval", "needs_confirmation"}
# 사용자가 거절했거나 하네스가 막은 호출
NOT_A_TOOL_FAILURE_MARKERS = ("doesn't want to proceed", "Blocked:", "was rejected")

# 실패 판정: JSON ok:false 또는 사용법 오류 또는 projectops 파일 안 예외 (CI 로그 속 Traceback 글자는 제외)
FAILURE_PATTERN = re.compile(r'"ok":\s*false')
USAGE_ERROR_PATTERN = re.compile(r"usage: \w+_cli|error: (argument|unrecognized arguments|the following arguments)"
                                 r"|invalid choice")
CODE_PATTERN = re.compile(r'"code":\s*"([\w-]+)"')
# 도움말 요청 (-h/--help): argparse 가 usage: 를 찍어도 오류 줄 없으면 정상 (#1003)
HELP_FLAG_PATTERN = re.compile(r"(?:^|\s)(?:-h|--help)(?:\s|$)")
ARGPARSE_ERROR_LINE_PATTERN = re.compile(r"^\S*: error: |\berror: ", re.MULTILINE)
# projectops 파일 안에서 난 예외 (에이전트가 붙인 파이프 파서 <stdin>/<string> 은 제외)
CLI_CRASH_PATTERN = re.compile(r'File "[^"]*(?:_cli\.py|/pro_[a-z_]+/|/scripts/common/|/git_worktree/|/figma_tools/|/oss_consult/)[^"]*", line')
# 도구가 스스로 "없다"고 답한 code: 1회로 보고 / argparse 없는 서브커맨드: 분류만 (이름 오타가 많아 1회로는 안 울림)
MISSING_FEATURE_CODES = {"not_supported"}
MISSING_FEATURE_CODE_PREFIXES = ("unsupported_", "unknown_")
INVALID_CHOICE_MARKER = "invalid choice"

# 도구 > 스킬 이름 (제목 [<skill>] · 중복 key). projectops_cli 는 첫 단어가 스킬
SKILL_BY_TOOL = {"launch_cli": "launch", "e2e_cli": "agent-test", "github_cli": "github",
                 "changelog_cli": "changelog-deploy", "commit_cli": "commit", "report_cli": "report",
                 "figma_cli": "figma", "worktree_cli": "init-worktree", "design_brief_cli": "design-brief",
                 "oss_cli": "oss-consult", "review_cli": "review", "testcase_cli": "testcase"}
# 두 단어로 보는 서브커맨드 그룹 (launch web click · github actions joblog). 그 외 둘째 단어는 인자
NESTED_SUBCOMMAND_GROUPS = {"web", "app", "device", "desktop", "db", "logs", "cred", "ssh", "local", "kb", "access",
                            "http", "render", "actions", "explore", "secrets"}
# 스킬 > 우회 그룹 (우회 표 찾기 전용). 없는 스킬은 반복 실패·예외·기능 없음 규칙으로만 잡힘
WORKAROUND_GROUP_BY_SKILL = {"launch": "launch", "agent-test": "launch", "github": "github",
                             "changelog-deploy": "github", "report": "github", "oss-consult": "github",
                             "commit": "commit", "init-worktree": "worktree", "figma": "figma"}
# 우회 그룹별 판정 4종: 첫 단어 도구, git 서브커맨드(+다음 단어), 실행 조각 패턴, 명령 전체 패턴(heredoc 코드 포함)
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
_SEGMENT_SEPARATOR_PATTERN = re.compile(r"&&|\|\||[;|\n()]")
_ENV_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
_COMMAND_PREFIX_WORDS = ("sudo", "env", "exec", "time", "timeout")

# 문턱값: 실패 후 우회를 찾는 Bash 호출 수, 같은 사용법 오류 횟수, 같은 code 실패 횟수, 세션당 보고 상한
WORKAROUND_WINDOW_CALLS = 7
USAGE_ERROR_REPEAT_COUNT = 2
SAME_FAILURE_REPEAT_COUNT = 3
MAX_REPORTS_PER_SESSION = 3
# 훅이 남기는 결과 머리 길이 (상세 원문은 bug_cli 가 기록에서 읽는다)
EXCERPT_CHARS = 2000


def classify_call(command: str, output: str, tool_use_id: str | None = None) -> dict | None:
    """Bash 호출 1건 > {kind: projectops|other, skill, subcommand, group, is_failure, failure_kind, code, ...} (보고 호출은 None)"""
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
    """도구 + 뒤 단어 > (스킬, 서브커맨드). projectops_cli 는 첫 단어를 스킬로 떼고 나머지를 같은 규칙으로"""
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
    """실패 분류 1개 (우선순위: crash > missing_feature > usage > failure)"""
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
    """세션 상태 갱신 + 이번 호출로 울린 규칙 목록 > [alarm] (상한·중복 제외 후)"""
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
    """projectops 호출: 예외 · 기능 없음 · 사용법 오류 반복 · 같은 실패 반복 판정, 실패면 우회 대기 등록"""
    name = f"{call['skill']}:{call['subcommand']}"
    if not call["is_failure"]:
        state["counts"].pop(f"same:{name}", None)
        return []
    # 같은 실패 횟수 (code 가 바뀌면 다시 셈)
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
    # 서브커맨드를 못 읽은 호출(셸 함수 래퍼 "$@" 등)은 서로 다른 호출이 한 키로 묶여 반복으로 오탐 > 세지 않음 (#1003)
    if (call["is_usage_error"] and call["subcommand"]
            and _increment(state, f"usage:{name}") >= USAGE_ERROR_REPEAT_COUNT):
        alarms.append(_alarm("usage_error_repeated", call, same_count))
    if same_count >= SAME_FAILURE_REPEAT_COUNT:
        alarms.append(_alarm("same_failure_repeated", call, same_count))
    # 우회 대기: 우회 그룹이 있는 스킬만
    if call["group"]:
        state["pending_failure"] = {key: call[key] for key in
                                    ("skill", "subcommand", "group", "code", "failure_kind", "tool_use_id", "excerpt")}
        state["pending_failure"].update({"failure_count": same_count, "calls_seen": 0})
    return alarms


def _check_workaround(state: dict, command: str) -> list[dict]:
    """projectops 아닌 호출: 직전 실패가 대기 중이면 같은 그룹 raw 명령인지 판정"""
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
    """명령 > 같은 그룹 raw 우회 여부 (heredoc 본문 등 실행되지 않는 글자는 첫 단어가 아니라 제외)"""
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
        if words[0] == "git" and _is_git_subcommand(words, rules.get("git", ())):
            return True
        segment_pattern = rules.get("segment_pattern")
        if segment_pattern and segment_pattern.search(" ".join(words)):
            return True
    return False


def _strip_command_prefix(words: list[str]) -> list[str]:
    """앞의 환경변수 대입 · sudo/env/timeout 같은 접두 단어 제거"""
    while words and (_ENV_ASSIGNMENT_PATTERN.match(words[0]) or words[0] in _COMMAND_PREFIX_WORDS):
        words.pop(0)
        if words and words[0].isdigit():
            words.pop(0)
    return words


def _is_git_subcommand(words: list[str], expected: tuple) -> bool:
    """git [-C 경로] 서브커맨드 [다음 단어] 가 expected 중 하나와 맞는지"""
    rest = words[1:]
    while rest[:1] in (["-C"], ["-c"]):
        rest = rest[2:]
    return any(tuple(rest[:len(parts)]) == parts for parts in expected)


def _increment(state: dict, key: str) -> int:
    state["counts"][key] = state["counts"].get(key, 0) + 1
    return state["counts"][key]


def _alarm(rule: str, source: dict, failure_count: int, workaround: str | None = None,
           calls_between: int | None = None) -> dict:
    """경보 1건 (key: <rule>|<skill>:<subcommand>|<code 또는 none>) + 근거"""
    code = source.get("code") or "none"
    alarm = {"rule": rule, "key": f"{rule}|{source['skill']}:{source['subcommand']}|{code}",
             "skill": source["skill"], "subcommand": source["subcommand"], "code": source.get("code"),
             "kind": source.get("failure_kind"), "tool_use_id": source.get("tool_use_id"),
             "excerpt": source.get("excerpt", ""), "failure_count": failure_count, "at": int(time.time())}
    if workaround:
        alarm["workaround"] = workaround
        alarm["calls_between"] = calls_between
    return alarm
