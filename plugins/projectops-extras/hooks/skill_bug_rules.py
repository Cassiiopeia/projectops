"""projectops 도구 이상 감지 규칙 정본 (#997): Bash 호출 1건 > 분류, 세션 상태 + 분류 > 울릴 규칙
입출력 없음 (판정만). 문턱값은 전 계정 세션 1,941개 스캔에 맞춘 값.
"""
from __future__ import annotations

import re

# projectops CLI 호출: {도구}_cli.py {서브커맨드} [{하위 서브커맨드}]
PROJECTOPS_CLI_PATTERN = re.compile(
    r"\b(launch_cli|projectops_cli|github_cli|commit_cli|changelog_cli|report_cli|e2e_cli|figma_cli|worktree_cli"
    r"|design_brief_cli|oss_cli|review_cli|testcase_cli)\.py\s+([a-z][\w-]*)(?:\s+([a-z][\w-]*))?")
# 보고 자체의 호출 (재귀 방지)
REPORT_CALL_MARKERS = ("bug_cli.py", "Cassiiopeia projectops", "pro-skill-bug")
# 설계상 정상인 실패 code (사용자 확인 대기 등)
BY_DESIGN_CODES = {"ok", "needs_user", "needs_user_approval", "needs_confirmation"}
# 사용자가 거절했거나 하네스가 막은 호출
NOT_A_TOOL_FAILURE_MARKERS = ("doesn't want to proceed", "Blocked:", "was rejected")

# 실패 판정: JSON ok:false 또는 사용법 오류 또는 projectops 파일 안 예외 (CI 로그 속 Traceback 글자는 제외)
FAILURE_PATTERN = re.compile(r'"ok":\s*false')
USAGE_ERROR_PATTERN = re.compile(r"usage: \w+_cli|error: (argument|unrecognized arguments|the following arguments)")
CODE_PATTERN = re.compile(r'"code":\s*"([\w-]+)"')
# projectops 파일 안에서 난 예외 (에이전트가 붙인 파이프 파서 <stdin>/<string> 은 제외)
CLI_CRASH_PATTERN = re.compile(r'File "[^"]*(?:_cli\.py|/pro_[a-z_]+/|/scripts/common/|/git_worktree/|/figma_tools/|/oss_consult/)[^"]*", line')

# 영역별 우회로 보는 raw 명령 (실행되는 조각의 첫 단어 기준): launch 는 기기·브라우저, 그 외는 GitHub 직접 호출
WORKAROUND_TOOLS_BY_AREA = {"launch": ("adb", "xcrun", "idb", "maestro", "osascript"), "github": ("gh",)}
# 첫 단어와 무관하게 우회로 보는 표시: 브라우저 직접 조종, GitHub API 직접 호출
WORKAROUND_MARKER_PATTERN_BY_AREA = {
    "launch": re.compile(r"remote-debugging-port|playwright\.sync_api|connect_over_cdp"),
    "github": re.compile(r"^curl\b.*api\.github\.com"),
}
_SEGMENT_SEPARATOR_PATTERN = re.compile(r"&&|\|\||[;|\n()]")
_ENV_ASSIGNMENT_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=\S*$")
AREA_BY_TOOL = {"launch_cli": "launch", "e2e_cli": "launch", "github_cli": "github", "changelog_cli": "github",
                "commit_cli": "github", "report_cli": "github"}

# 문턱값: 실패 후 우회를 찾는 Bash 호출 수, 같은 사용법 오류 횟수, 같은 code 실패 횟수, 세션당 보고 상한
WORKAROUND_WINDOW_CALLS = 7
USAGE_ERROR_REPEAT_COUNT = 2
SAME_FAILURE_REPEAT_COUNT = 3
MAX_REPORTS_PER_SESSION = 3


def classify_call(command: str, output: str) -> dict | None:
    """Bash 호출 1건 > {kind: projectops|other, tool, subcommand, area, is_failure, code, is_usage_error, is_crash} (보고 호출은 None)"""
    if any(marker in command for marker in REPORT_CALL_MARKERS):
        return None
    match = PROJECTOPS_CLI_PATTERN.search(command)
    if not match:
        return {"kind": "other"}
    tool = match.group(1)
    subcommand = " ".join(part for part in match.groups()[1:] if part)
    # projectops_cli 진입점은 첫 단어가 하위 스킬 이름 (github, launch ...)
    area = AREA_BY_TOOL.get(tool) or ("launch" if subcommand.startswith("launch") else "github")
    head = output[:6000]
    code_match = CODE_PATTERN.search(head)
    code = code_match.group(1) if code_match else None
    is_usage_error = bool(USAGE_ERROR_PATTERN.search(head))
    is_crash = bool(CLI_CRASH_PATTERN.search(head))
    is_failure = ((bool(FAILURE_PATTERN.search(head)) or is_usage_error or is_crash) and code not in BY_DESIGN_CODES
                  and not any(marker in head for marker in NOT_A_TOOL_FAILURE_MARKERS))
    return {"kind": "projectops", "tool": tool, "subcommand": subcommand, "area": area, "is_failure": is_failure,
            "code": code, "is_usage_error": is_failure and is_usage_error, "is_crash": is_failure and is_crash,
            "excerpt": head[:600]}


def evaluate(state: dict, call: dict, command: str) -> list[dict]:
    """세션 상태 갱신 + 이번 호출로 울린 규칙 목록 > [{rule, key, detail}] (상한·중복 제외 후)"""
    state.setdefault("counts", {})
    state.setdefault("reported_keys", [])
    state.setdefault("report_count", 0)
    fired = []
    if call["kind"] == "other":
        fired += _check_workaround(state, command)
    else:
        fired += _check_projectops_call(state, call)
    accepted = []
    for alarm in fired:
        if state["report_count"] >= MAX_REPORTS_PER_SESSION or alarm["key"] in state["reported_keys"]:
            continue
        state["reported_keys"].append(alarm["key"])
        state["report_count"] += 1
        accepted.append(alarm)
    return accepted


def _check_projectops_call(state: dict, call: dict) -> list[dict]:
    """projectops 호출: 충돌(Traceback) · 사용법 오류 반복 · 같은 실패 반복 판정, 실패면 우회 대기 등록"""
    name = f"{call['tool']}:{call['subcommand']}"
    if not call["is_failure"]:
        state["counts"].pop(f"same:{name}", None)
        return []
    alarms = []
    if call["is_crash"]:
        alarms.append(_alarm("cli_crash", name, call["excerpt"]))
    if call["is_usage_error"]:
        usage_count = _increment(state, f"usage:{name}")
        if usage_count >= USAGE_ERROR_REPEAT_COUNT:
            alarms.append(_alarm("usage_error_repeated", name, call["excerpt"]))
    same_key = f"same:{name}"
    if state.get("last_failure_code_by_name", {}).get(name) != call["code"]:
        state["counts"][same_key] = 0
    state.setdefault("last_failure_code_by_name", {})[name] = call["code"]
    if _increment(state, same_key) >= SAME_FAILURE_REPEAT_COUNT:
        alarms.append(_alarm("same_failure_repeated", name, call["excerpt"]))
    state["pending_failure"] = {"name": name, "area": call["area"], "excerpt": call["excerpt"], "calls_left": WORKAROUND_WINDOW_CALLS}
    return alarms


def _check_workaround(state: dict, command: str) -> list[dict]:
    """projectops 아닌 호출: 직전 실패가 대기 중이면 같은 영역 raw 명령인지 판정"""
    pending = state.get("pending_failure")
    if not pending:
        return []
    if is_workaround_command(command, pending["area"]):
        state.pop("pending_failure", None)
        return [_alarm("workaround_after_failure", pending["name"], pending["excerpt"], workaround=command[:300])]
    pending["calls_left"] -= 1
    if pending["calls_left"] <= 0:
        state.pop("pending_failure", None)
    return []


def is_workaround_command(command: str, area: str) -> bool:
    """명령 > 같은 영역 raw 우회 여부 (heredoc 본문 등 실행되지 않는 글자는 첫 단어가 아니라 제외)"""
    tools = WORKAROUND_TOOLS_BY_AREA.get(area, ())
    marker_pattern = WORKAROUND_MARKER_PATTERN_BY_AREA.get(area)
    if area == "launch" and marker_pattern and marker_pattern.search(command):
        return True
    for segment in _SEGMENT_SEPARATOR_PATTERN.split(command.split("<<", 1)[0]):
        words = segment.split()
        while words and (_ENV_ASSIGNMENT_PATTERN.match(words[0]) or words[0] in ("sudo", "env", "exec", "time", "timeout")):
            words.pop(0)
            if words and words[0].isdigit():
                words.pop(0)
        if not words:
            continue
        if words[0].strip("\"'").rsplit("/", 1)[-1] in tools:
            return True
        if area == "github" and marker_pattern and marker_pattern.search(" ".join(words)):
            return True
    return False


def _increment(state: dict, key: str) -> int:
    state["counts"][key] = state["counts"].get(key, 0) + 1
    return state["counts"][key]


def _alarm(rule: str, name: str, excerpt: str, workaround: str | None = None) -> dict:
    alarm = {"rule": rule, "key": f"{rule}|{name}", "tool": name, "excerpt": excerpt}
    if workaround:
        alarm["workaround"] = workaround
    return alarm
