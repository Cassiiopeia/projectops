#!/usr/bin/env python3
"""changelog_cli — changelog-deploy skill 전용 CLI.

deploy PR 자동화 + Actions/CodeRabbit 상태 종합.
서브커맨드: actions, deploy-status, list-prs, update-pr, create-pr, detect-release-context

사용법:
    cd skills/pro-changelog-deploy/scripts
    python changelog_cli.py <subcommand> [args]
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_PROJECT_ROOT = _HERE.parents[3]
_SCRIPTS_ROOT = _PROJECT_ROOT / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from common.cli_parser import JSONArgumentParser, run_cli  # noqa: E402
from common.emit import emit  # noqa: E402
from common.config import get_github_pat  # noqa: E402
from common.gh_client import (  # noqa: E402
    GitHubAPIError,
    list_pulls, update_pull_request, create_pull_request,
    get_run, get_job_log, list_failed_runs, resolve_pr_runs, resolve_branch_runs,
    get_pull_detail, find_open_pr_by_base, get_branch_head,
)


def cmd_actions(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        if args.sub == "show-run":
            if args.arg is None:
                return emit({"ok": False, "code": "missing_argument", "error": "RUN_ID 필요"})
            data = get_run(args.owner, args.repo, int(args.arg), pat)
            if data.get("failed_job_ids"):
                data["next"] = f"actions joblog {args.owner} {args.repo} {data['failed_job_ids'][0]}"
            return emit(data)
        if args.sub == "joblog":
            if args.arg is None:
                return emit({"ok": False, "code": "missing_argument", "error": "JOB_ID 필요"})
            data = get_job_log(args.owner, args.repo, int(args.arg), pat, grep=args.grep, tail=args.tail)
            return emit(data)
        if args.sub == "list-failed":
            runs = list_failed_runs(args.owner, args.repo, pat, limit=args.limit)
            nxt = f"actions show-run {args.owner} {args.repo} {runs[0]['run_id']}" if runs else None
            return emit({"count": len(runs), "runs": runs, "next": nxt})
        if args.sub == "resolve-pr":
            if args.arg is None:
                return emit({"ok": False, "code": "missing_argument", "error": "PR_NUM 필요"})
            data = resolve_pr_runs(args.owner, args.repo, int(args.arg), pat)
            failed = [r for r in data["runs"] if r["conclusion"] == "failure"]
            data["next"] = f"actions show-run {args.owner} {args.repo} {failed[0]['run_id']}" if failed else None
            return emit(data)
        if args.sub == "resolve-branch":
            if args.arg is None:
                return emit({"ok": False, "code": "missing_argument", "error": "BRANCH 필요"})
            runs = resolve_branch_runs(args.owner, args.repo, args.arg, pat, limit=args.limit)
            failed = [r for r in runs if r["conclusion"] == "failure"]
            nxt = f"actions show-run {args.owner} {args.repo} {failed[0]['run_id']}" if failed else None
            return emit({"branch": args.arg, "count": len(runs), "runs": runs, "next": nxt})
        return emit({"ok": False, "code": "unknown_subcommand", "error": f"알 수 없음: {args.sub}"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})
    except ValueError as e:
        return emit({"ok": False, "code": "invalid_argument", "error": str(e)})


def cmd_deploy_status(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        if args.pr:
            pr = get_pull_detail(args.owner, args.repo, args.pr, pat)
        else:
            pr = find_open_pr_by_base(args.owner, args.repo, args.base, pat)
        branch_head = get_branch_head(args.owner, args.repo, args.base, pat)
        deploy_branch = {"name": args.base, "head_sha": branch_head}

        if pr is None:
            return emit({
                "pr": None,
                "workflow": None,
                "deploy_branch": deploy_branch,
                "verdict": "no_pr",
                "summary": f"base={args.base}로 들어오는 open PR 없음",
            })

        # 워크플로우 매칭 — name이 아니라 path로 매칭한다.
        # name 필드는 사람이 보는 라벨(예: "RELEASE CHANGELOG")이라 언제든 바뀌고,
        # 실제 파일 path(`.github/workflows/PROJECT-COMMON-RELEASE-CHANGELOG.yaml`)가 식별자다.
        # #455에서 구 PROJECT-COMMON-AUTO-CHANGELOG-CONTROL → RELEASE-CHANGELOG로 리네임됨.
        # 구 path도 폴백 지원(아직 리네임 안 된 레포 호환). name 매칭은 라벨이 바뀌어 실패한 이력 있어 path 우선.
        workflow = None
        try:
            run_data = resolve_pr_runs(args.owner, args.repo, pr["number"], pat)
            for r in run_data.get("runs", []):
                path = (r.get("path") or "").lower()
                name = (r.get("name") or "").upper()
                # 1순위: 파일 path(신·구 둘 다). 2순위(legacy fallback): name에 키워드.
                if path.endswith("project-common-release-changelog.yaml") \
                        or path.endswith("project-common-auto-changelog-control.yaml") \
                        or ("CHANGELOG" in name and ("AUTO" in name or "DEPLOY" in name or "RELEASE" in name)):
                    workflow = {
                        "name": r.get("name"),
                        "path": r.get("path"),
                        "status": r.get("status"),
                        "conclusion": r.get("conclusion"),
                        "run_url": r.get("url"),
                    }
                    break
        except GitHubAPIError:
            workflow = None

        body = pr.get("body") or ""
        has_summary = "Summary by CodeRabbit" in body
        pr_out = {
            "number": pr["number"],
            "state": pr["state"],
            "merged": pr["merged"],
            "mergeable_state": pr["mergeable_state"],
            "has_coderabbit_summary": has_summary,
            "head_sha": pr["head_sha"],
            "url": pr["url"],
            "created_at": pr.get("created_at"),
        }

        workflow_status = (workflow or {}).get("status")
        workflow_conclusion = (workflow or {}).get("conclusion")
        workflow_running = workflow_status in ("in_progress", "queued", "waiting", "requested")

        # PR 생성 후 얼마 안 지났으면(120초 이내) 워크플로우가 막 trigger되어 아직 API에
        # 반영되지 않았을 가능성을 가드한다. workflow=null이라도 PR이 갓 만들어진 상태면
        # missing 판정 대신 waiting으로 양보한다.
        import datetime as _dt
        pr_age_sec = None
        if pr.get("created_at"):
            try:
                created = _dt.datetime.fromisoformat(pr["created_at"].replace("Z", "+00:00"))
                now = _dt.datetime.now(_dt.timezone.utc)
                pr_age_sec = (now - created).total_seconds()
            except Exception:
                pr_age_sec = None
        pr_young = (pr_age_sec is not None and pr_age_sec < 120)

        next_hint = f"deploy-status {args.owner} {args.repo} --pr {pr['number']}"
        if pr["merged"]:
            verdict, summary, next_hint = "merged", f"PR #{pr['number']} automerge 완료", None
        elif pr["mergeable_state"] in ("dirty", "blocked", "behind"):
            verdict = "conflict"
            summary = f"PR #{pr['number']} mergeable_state={pr['mergeable_state']} — 충돌/차단"
        elif workflow and workflow_conclusion == "failure":
            verdict = "workflow_failed"
            summary = "RELEASE-CHANGELOG 워크플로우 실패"
        elif workflow_running:
            # 워크플로우 진행 중이면 body·has_summary가 일시적으로 비어 보여도 정상 대기로 본다 (race 가드)
            verdict = "waiting_for_automerge"
            summary = f"PR #{pr['number']} 워크플로우 진행 중({workflow_status}), automerge 대기"
        elif workflow is None and pr_young:
            # 워크플로우 매칭 못 했지만 PR이 갓 만들어진 상태 — API 반영 lag 가능, race 가드
            verdict = "waiting_for_automerge"
            summary = f"PR #{pr['number']} 생성 직후({int(pr_age_sec)}s), 워크플로우 trigger 대기"
        elif not has_summary:
            # 워크플로우가 진행 중이 아니고 PR도 갓 생성된 게 아니면 진짜 body 초기화 사고로 판정
            verdict = "missing_coderabbit_summary"
            summary = f"PR #{pr['number']} 본문에 'Summary by CodeRabbit' 없음 — fix 모드로 재작성"
        else:
            verdict = "waiting_for_automerge"
            summary = f"PR #{pr['number']} open·{pr['mergeable_state']}, automerge 대기"

        return emit({
            "pr": pr_out,
            "workflow": workflow,
            "deploy_branch": deploy_branch,
            "verdict": verdict,
            "summary": summary,
            "next": next_hint,
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_list_prs(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    try:
        result = list_pulls(args.owner, args.repo, pat, args.state)
        return emit({
            "count": len(result),
            "prs": result,
            "summary": f"{args.owner}/{args.repo} PR {len(result)}개 ({args.state})",
        })
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def _resolve_body_file(body_file: str | None) -> Path | None:
    """본문 파일 경로 해석 — 절대 경로면 그대로, 상대 경로면 여러 위치를 순서대로 탐색.

    SKILL.md 절차는 `~/.projectops/tmp/{owner}__{repo}__release_notes.md`(홈, 절대경로)에
    저장하고 cli에 그 절대경로를 넘긴다. 다만 누군가 파일명만(상대경로) 넘겨도 찾을 수 있도록
    홈 tmp → PROJECT_ROOT/scripts(구버전 하위호환) → cwd 순으로 보강 탐색한다.
    찾지 못하면 None을 반환한다 (호출자가 본문 없음을 판단).
    """
    if not body_file:
        return None
    raw = Path(body_file)
    if raw.is_absolute():
        return raw if raw.exists() else None
    for candidate in (
        raw,
        Path.home() / ".projectops" / "tmp" / raw.name,
        Path.home() / ".suh-template" / "tmp" / raw.name,  # 구 경로 과도기 폴백(#459 이주)
        _PROJECT_ROOT / "scripts" / raw.name,
        Path.cwd() / raw,
    ):
        if candidate.exists():
            return candidate
    return None


def cmd_update_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body = None
    if args.body_file:
        body_path = _resolve_body_file(args.body_file)
        body = body_path.read_text(encoding="utf-8") if body_path else None
    try:
        result = update_pull_request(
            args.owner, args.repo, args.number, pat,
            title=args.title, body=body, state=args.state,
        )
        return emit({**result, "summary": f"PR #{args.number} 수정 완료"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def cmd_create_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body_path = _resolve_body_file(args.body_file)
    if args.body_file and not body_path:
        return emit({
            "ok": False, "code": "body_file_not_found",
            "error": (
                f"본문 파일을 찾을 수 없습니다: {args.body_file} "
                f"(탐색: 절대경로 | ~/.projectops/tmp/ | {_PROJECT_ROOT / 'scripts'} | cwd={Path.cwd()})"
            ),
        })
    body = body_path.read_text(encoding="utf-8") if body_path else ""
    try:
        result = create_pull_request(args.owner, args.repo, args.title, body, args.head, args.base, pat)
        pr_number = result.get("number")

        # PR 생성 직후엔 RELEASE-CHANGELOG 워크플로우 step 2가 본문을 초기화할 수 있다.
        # step 2는 PR opened 후 보통 3~10초 안에 실행되므로, 워크플로우 본문 초기화가 끝난 뒤
        # (대기 후) 본문을 다시 확인해 비어 있으면 update-pr로 재주입한다. 이렇게 하면 step 8
        # (CodeRabbit Summary 폴링)이 첫 attempt(5초 간격)에서 즉시 본문을 잡고 빠르게 머지된다.
        # 본문이 비어 있지 않으면(워크플로우가 보존했거나 CodeRabbit이 자기 Summary 작성한 경우) skip.
        guard_summary = None
        if pr_number and body:
            import time
            time.sleep(15)
            try:
                detail = get_pull_detail(args.owner, args.repo, pr_number, pat)
                cur_body = detail.get("body") or ""
                if "Summary by CodeRabbit" not in cur_body:
                    update_pull_request(args.owner, args.repo, pr_number, pat, body=body)
                    guard_summary = "본문 재주입 (워크플로우 step 2 race 회복)"
                else:
                    guard_summary = "본문 보존 확인 — 재주입 불필요"
            except GitHubAPIError:
                guard_summary = "본문 재확인 실패 — 무시하고 진행"

        out = {
            **result,
            "summary": f"PR #{pr_number} 생성 완료" + (f" / {guard_summary}" if guard_summary else ""),
            "next": f"deploy-status {args.owner} {args.repo} --pr {pr_number}",
        }
        if guard_summary:
            out["body_guard"] = guard_summary
        return emit(out)
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


# 앱 스토어 심사로 직결되는 워크플로우 파일명 키워드 (대소문자 무시 부분일치).
# 새 스토어/플랫폼이 생기면 이 목록에 키워드만 추가하면 감지가 확장된다 (SKILL.md·판단 로직 무수정).
_STORE_WORKFLOW_KEYWORDS = ("PLAYSTORE", "TESTFLIGHT", "APPSTORE", "APP-STORE")
# 앱(스토어 배포) 성격이 강한 프로젝트 타입.
_APP_PROJECT_TYPES = ("flutter", "react-native", "react-native-expo")


def _read_project_types(project_root: Path) -> list[str]:
    """version.yml에서 project_types 배열을 추출한다 (yaml 의존성 없이 정규식).

    폐쇄망·표준 라이브러리 우선 원칙: PyYAML을 import하지 않고 `project_types: [...]` 라인을
    문자열로 파싱한다. 파일이 없거나 키가 없으면 빈 리스트를 반환한다 (오류 아님)."""
    vy = project_root / "version.yml"
    if not vy.exists():
        return []
    try:
        text = vy.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    # `project_types: ["spring", "react"]` 형태의 한 줄을 찾아 따옴표 안 토큰만 추출.
    m = re.search(r"^\s*project_types\s*:\s*\[([^\]]*)\]", text, re.MULTILINE)
    if m:
        return [t.strip().strip("\"'") for t in m.group(1).split(",") if t.strip()]
    # 배열이 아닌 단수 `project_type: "flutter"` 폴백.
    m2 = re.search(r"^\s*project_type\s*:\s*[\"']?([A-Za-z0-9_-]+)", text, re.MULTILINE)
    return [m2.group(1)] if m2 else []


def _read_release_branches(project_root: Path) -> dict:
    """version.yml에서 릴리스 브랜치·changelog provider를 읽는다 (#456, SSOT).

    - head = metadata.deploy_branch (릴리스 PR head) — 없으면 'develop' 폴백.
    - base = metadata.default_branch (레포 기본) — 없으면 'main' 폴백.
    - provider = metadata.template.options.changelog.provider — 없으면 'commit' 폴백.
      (#566 에서 기본 사다리가 commit 으로 바뀌었다. 예전 폴백은 coderabbit 이었고,
       그대로 두면 이 스킬만 "CodeRabbit 을 기다리는 레포"로 잘못 판정한다.)
    yaml 의존 없이 정규식으로만 파싱한다 (폐쇄망·표준 라이브러리 우선)."""
    vy = project_root / "version.yml"
    text = ""
    if vy.exists():
        try:
            text = vy.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

    def _find(pattern, default):
        m = re.search(pattern, text, re.MULTILINE)
        return m.group(1) if m else default

    return {
        "head": _find(r"^\s*deploy_branch\s*:\s*[\"']?([A-Za-z0-9._/-]+)", "develop"),
        "base": _find(r"^\s*default_branch\s*:\s*[\"']?([A-Za-z0-9._/-]+)", "main"),
        "provider": _find(r"^\s*provider\s*:\s*[\"']?([a-z-]+)", "commit"),
    }


def _scan_store_workflows(project_root: Path) -> list[str]:
    """.github/workflows 내 파일명을 스캔해 스토어 심사 워크플로우 파일명을 반환한다."""
    wf_dir = project_root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    found = []
    try:
        for entry in sorted(os.listdir(wf_dir)):
            upper = entry.upper()
            if any(kw in upper for kw in _STORE_WORKFLOW_KEYWORDS):
                found.append(entry)
    except OSError:
        return []
    return found


def cmd_detect_release_context(args) -> int:
    """이 레포가 앱 스토어 심사에 직결되는지 '신호'를 모아 JSON으로 반환한다.

    판단(앱 심사 레포 확정·사용자 확인·config 갱신)은 agent가 한다. py는 사실(signals)과
    약한 hint만 준다. GitHub API를 쓰지 않으므로 PAT가 필요 없다 (로컬 파일만 스캔)."""
    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd()

    project_types = _read_project_types(project_root)
    store_workflows = _scan_store_workflows(project_root)
    has_store_workflow = bool(store_workflows)
    has_app_type = any(t.lower() in _APP_PROJECT_TYPES for t in project_types)
    # version.yml·workflows를 둘 다 못 읽었으면 신호가 없는 unknown 상태.
    no_signals = not project_types and not (project_root / ".github" / "workflows").is_dir()

    if no_signals:
        hint = "unknown"
    elif has_store_workflow and has_app_type:
        hint = "strong_app"          # 앱 타입 + 스토어 워크플로우 → 앱 심사 거의 확실
    elif has_store_workflow:
        hint = "app_release_likely"  # 스토어 워크플로우는 있으나 타입 신호 약함
    elif has_app_type:
        hint = "app_release_likely"  # 앱 타입은 있으나 스토어 워크플로우 미발견 (TEST 빌드만 등)
    else:
        hint = "backend_only"        # 앱 신호 전무 → 백엔드로 간주

    next_hint = (
        "agent: app_release 기록 없으면 사용자에게 한 번 확인 후 config에 저장"
        if hint in ("strong_app", "app_release_likely", "unknown")
        else "agent: backend_only — 조용히 통과, 경고·질문 없음"
    )

    # 릴리스 브랜치·provider (#456) — 스킬이 develop/main 하드코딩 대신 이 값을 쓴다.
    branches = _read_release_branches(project_root)

    return emit({
        "ok": True,
        "project_root": str(project_root),
        "signals": {
            "project_types": project_types,
            "store_workflows": store_workflows,
            "has_store_workflow": has_store_workflow,
            "has_app_type": has_app_type,
        },
        "branches": branches,   # {head, base, provider} — head→base로 릴리스 PR 생성
        "hint": hint,
        "next": next_hint,
    })


def build_parser() -> JSONArgumentParser:
    parser = JSONArgumentParser(prog="changelog_cli", description="changelog-deploy skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_a = sub.add_parser("actions", help="GitHub Actions run/job/log 조회")
    p_a.add_argument("sub", choices=["show-run", "joblog", "list-failed", "resolve-pr", "resolve-branch"])
    p_a.add_argument("owner")
    p_a.add_argument("repo")
    p_a.add_argument("arg", nargs="?")
    p_a.add_argument("--limit", type=int, default=10)
    p_a.add_argument("--grep", default="error")
    p_a.add_argument("--tail", type=int, default=30)
    p_a.set_defaults(func=cmd_actions)

    p_ds = sub.add_parser("deploy-status", help="deploy PR 상태 종합 판정")
    p_ds.add_argument("owner")
    p_ds.add_argument("repo")
    p_ds.add_argument("--pr", type=int)
    p_ds.add_argument("--base", default="main")
    p_ds.set_defaults(func=cmd_deploy_status)

    p_lp = sub.add_parser("list-prs", help="PR 목록")
    p_lp.add_argument("owner")
    p_lp.add_argument("repo")
    p_lp.add_argument("--state", choices=["open", "closed", "all"], default="open")
    p_lp.set_defaults(func=cmd_list_prs)

    p_up = sub.add_parser("update-pr", help="PR 본문/상태 수정")
    p_up.add_argument("owner")
    p_up.add_argument("repo")
    p_up.add_argument("number", type=int)
    p_up.add_argument("body_file", nargs="?")
    p_up.add_argument("--title")
    p_up.add_argument("--state", choices=["open", "closed"])
    p_up.set_defaults(func=cmd_update_pr)

    p_cp = sub.add_parser("create-pr", help="deploy PR 재트리거용 생성")
    p_cp.add_argument("owner")
    p_cp.add_argument("repo")
    p_cp.add_argument("title")
    p_cp.add_argument("body_file")
    p_cp.add_argument("head")
    p_cp.add_argument("base")
    p_cp.set_defaults(func=cmd_create_pr)

    # 앱 스토어 심사 연관 레포인지 '신호'를 수집한다 (판단·확인은 agent). PAT 불필요 — 로컬 파일만 스캔.
    p_drc = sub.add_parser("detect-release-context", help="앱 심사 연관 레포 신호 수집 (signals/hint JSON)")
    p_drc.add_argument("--project-root", help="레포 루트 절대경로 (생략 시 cwd)")
    p_drc.set_defaults(func=cmd_detect_release_context)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
