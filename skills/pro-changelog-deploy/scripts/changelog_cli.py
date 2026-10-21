#!/usr/bin/env python3
"""changelog_cli — changelog-deploy skill 전용 CLI.

deploy PR 자동화 + Actions/CodeRabbit 상태 종합.
서브커맨드: actions, deploy-status, list-prs, update-pr, create-pr, sync-base, detect-release-context

사용법:
    cd skills/pro-changelog-deploy/scripts
    python changelog_cli.py <subcommand> [args]
"""
from __future__ import annotations

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
    list_pulls, update_pull_request,
    get_run, get_job_log, list_failed_runs, resolve_pr_runs, resolve_branch_runs,
)

# 파일 경로로 불러와도(테스트·하네스) 옆 모듈을 찾게 한다
sys.path.insert(0, str(Path(__file__).resolve().parent))
from deploy_status import cmd_deploy_status  # noqa: E402,F401
from release_tools import branches_check, cmd_sync_base, detect_release_shape, wrap_release_notes  # noqa: E402,F401
from release_context import collect_app_signals, load_config as _load_config  # noqa: E402
from release_language import collect_release_language  # noqa: E402
from release_pr import cmd_create_pr, _resolve_body_file  # noqa: E402,F401


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


def cmd_update_pr(args) -> int:
    pat = get_github_pat(args.owner, args.repo)
    if not pat:
        return emit({"ok": False, "code": "missing_pat", "error": "PAT 없음"})
    body = None
    if args.body_file:
        body_path = _resolve_body_file(args.body_file)
        body = body_path.read_text(encoding="utf-8") if body_path else None
    # 바꿀 값이 없으면 PATCH 하지 않고 알린다 — "수정 완료" 로 오보하지 않는다 (#699)
    if args.title is None and body is None and args.state is None:
        return emit({
            "ok": False,
            "code": "nothing_to_update",
            "error": "바꿀 값이 없습니다 (--title/--body-file/--state 중 하나 필요)",
        })
    try:
        result = update_pull_request(
            args.owner, args.repo, args.number, pat,
            title=args.title, body=body, state=args.state,
        )
        return emit({**result, "summary": f"PR #{args.number} 수정 완료"})
    except GitHubAPIError as e:
        return emit({"ok": False, "code": f"github_api_{e.status_code}", "error": str(e)})


def _normalize_provider(provider: str, project_root: Path) -> str:
    """provider 미설정·종료값을 워크플로우와 같은 규칙으로 정리한다 (#821).

    미설정 판정은 워크플로우(RELEASE-CHANGELOG)와 같은 3단 규칙이어야 한다:
    명시값 → (.coderabbit.yaml 있으면) coderabbit → commit. 어긋나면 스킬과 워크플로우 판단이 갈린다."""
    if not provider:
        provider = "coderabbit" if (project_root / ".coderabbit.yaml").is_file() else "commit"
    if provider == "github-ai":
        # 서비스 종료(2026-07-30) — ladder.py와 같게 commit으로 흡수한다 (#821).
        # 그대로 넘기면 스킬이 종료된 생성기를 정상 provider로 안내한다.
        provider = "commit"
    return provider


def _parse_release_branches(project_root: Path) -> tuple[dict, dict]:
    """version.yml을 읽어 (값, 명시 여부)를 돌려준다.

    명시 여부(explicit)는 version.yml에 키가 실제로 적혀 있었는지다 — 폴백값과 config 값이
    어긋날 때 "version.yml이 정말 그렇게 말하는지"를 agent가 구분할 수 있게 한다 (#842)."""
    vy = project_root / "version.yml"
    text = ""
    if vy.exists():
        try:
            text = vy.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

    def _find(pattern):
        m = re.search(pattern, text, re.MULTILINE)
        return m.group(1) if m else None

    # 개발 브랜치 키: development_branch(정본) > deploy_branch(구 이름) (#915)
    head = (_find(r"^\s*development_branch\s*:\s*[\"']?([A-Za-z0-9._/-]+)")
            or _find(r"^\s*deploy_branch\s*:\s*[\"']?([A-Za-z0-9._/-]+)"))
    base = _find(r"^\s*default_branch\s*:\s*[\"']?([A-Za-z0-9._/-]+)")
    provider = _find(r"^\s*provider\s*:\s*[\"']?([a-z-]+)")
    values = {
        "head": head or "develop",
        "base": base or "main",
        "provider": _normalize_provider(provider or "", project_root),
    }
    explicit = {"head": head is not None, "base": base is not None, "provider": provider is not None}
    return values, explicit


def _read_release_branches(project_root: Path) -> dict:
    """version.yml에서 릴리스 브랜치·changelog provider를 읽는다 (#456, SSOT).

    - head = metadata.development_branch (릴리스 PR head) > 구 키 deploy_branch > 'develop' 폴백.
    - base = metadata.default_branch (레포 기본) — 없으면 'main' 폴백.
    - provider = metadata.template.options.changelog.provider — 없으면 레포 루트에
      .coderabbit.yaml 이 있을 때 'coderabbit', 아니면 'commit' (#821, 워크플로우와 동일).
      종료된 'github-ai' 저장값은 'commit' 으로 돌려준다.
    yaml 의존 없이 정규식으로만 파싱한다 (폐쇄망·표준 라이브러리 우선)."""
    return _parse_release_branches(project_root)[0]


# branches 키 ↔ config changelog_deploy 키. config 는 사람이 읽는 이름(head_branch)을 쓴다.
_BRANCH_CONFIG_KEYS = (("head", "head_branch"), ("base", "base_branch"), ("provider", "provider"))


def _detect_owner_repo(project_root: Path) -> tuple[str | None, str | None]:
    """origin URL에서 owner/repo를 뽑는다. 실패하면 (None, None) — config 대조만 건너뛴다."""
    import subprocess
    try:
        url = subprocess.run(
            ["git", "-C", str(project_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None, None
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return (m.group(1), m.group(2)) if m else (None, None)


def _release_config_view(config: dict | None, owner: str | None, repo: str | None) -> dict:
    """config에서 이 레포의 브랜치·provider 기록과, 더는 읽지 않는 전역 키를 뽑는다 (#842).

    전역 `github.changelog_deploy.{head_branch,base_branch,provider}`는 레포 지식을 컴퓨터
    전체에 둔 것이라 다른 레포의 version.yml을 덮어썼다. 값은 쓰지 않고 '남아 있다'는 사실만 알린다."""
    gh = (config or {}).get("github") if isinstance(config, dict) else None
    gh = gh if isinstance(gh, dict) else {}
    glob = gh.get("changelog_deploy") if isinstance(gh.get("changelog_deploy"), dict) else {}
    ignored_global = sorted(k for _, k in _BRANCH_CONFIG_KEYS if k in glob)

    repo_values: dict = {}
    repo_entry = False
    if owner and repo:
        for r in gh.get("repos", []) or []:
            if isinstance(r, dict) and r.get("owner") == owner and r.get("repo") == repo:
                repo_entry = True
                cd = r.get("changelog_deploy") if isinstance(r.get("changelog_deploy"), dict) else {}
                repo_values = {k: cd[k] for _, k in _BRANCH_CONFIG_KEYS if cd.get(k)}
                break
    return {
        "found": config is not None,
        "repo_entry": repo_entry,
        "repo_values": repo_values,
        "ignored_global_keys": ignored_global,
    }


def cmd_detect_release_context(args) -> int:
    """이 레포가 앱 스토어 심사에 직결되는지 '신호'를 모아 JSON으로 반환한다.

    판단(앱 심사 레포 확정·사용자 확인·config 갱신)은 agent가 한다. py는 사실(signals)과
    약한 hint만 준다. GitHub API를 쓰지 않으므로 PAT가 필요 없다 (로컬 파일만 스캔)."""
    project_root = Path(args.project_root).resolve() if args.project_root else Path.cwd()
    if not project_root.is_dir():
        # 없는 경로를 빈 신호로 성공 처리하면 "앱 심사 레포 아님" 으로 오판한다 (#713)
        return emit({"ok": False, "code": "not_found",
                     "summary": "--project-root 경로가 없습니다",
                     "error": f"--project-root 경로가 없습니다: {project_root}"})

    signals, hint = collect_app_signals(project_root)

    next_hint = (
        "agent: app_release 기록 없으면 사용자에게 한 번 확인 후 config에 저장"
        if hint in ("strong_app", "app_release_likely", "unknown")
        else "agent: backend_only — 조용히 통과, 경고·질문 없음"
    )

    # 릴리스 브랜치·provider (#456) — 스킬이 develop/main 하드코딩 대신 이 값을 쓴다.
    # 정본은 version.yml이다 (#842). 워크플로우와 같은 곳을 읽어야 스킬과 워크플로우 판단이 안 갈린다.
    branches, explicit = _parse_release_branches(project_root)
    has_version_yml = (project_root / "version.yml").is_file()

    owner, repo = args.owner, args.repo
    if not (owner and repo):
        owner, repo = _detect_owner_repo(project_root)
    view = _release_config_view(_load_config(args.config), owner, repo)
    repo_values = view["repo_values"]

    conflict = []
    if has_version_yml:
        # version.yml 이 이긴다. 레포별 config 값은 낡은 캐시일 수 있으니 다르면 알리기만 한다.
        source = "version.yml"
        for key, cfg_key in _BRANCH_CONFIG_KEYS:
            if cfg_key in repo_values and repo_values[cfg_key] != branches[key]:
                conflict.append({
                    "key": cfg_key,
                    "version_yml": branches[key],
                    "config": repo_values[cfg_key],
                    "version_yml_explicit": explicit[key],
                })
    elif repo_values:
        # version.yml 이 없는 레포만 레포별 config 기록을 쓴다. 빠진 키는 폴백 규칙으로 채운다.
        source = "config"
        for key, cfg_key in _BRANCH_CONFIG_KEYS:
            if cfg_key in repo_values:
                value = repo_values[cfg_key]
                branches[key] = _normalize_provider(value, project_root) if key == "provider" else value
    else:
        source = "fallback"

    if conflict:
        next_hint = ("agent: version.yml 값으로 진행하고 차이를 사용자에게 한 줄로 알린다. "
                     "레포별 config 의 해당 키는 낡은 기록이다. " + next_hint)
    elif source == "fallback" and not has_version_yml:
        next_hint = ("agent: version.yml 없음 — 브랜치를 확정(애매하면 질문)해 레포별 config 에 기록한다. "
                     + next_hint)

    check = branches_check(project_root, branches["head"], branches["base"])
    # 개발 브랜치 없이 main > deploy 로 릴리스하는 레포 (#970)
    shape = detect_release_shape(project_root, branches, check)
    if shape["release_shape"] == "deploy_branch":
        next_hint = ("agent: deploy 브랜치형 레포 — branches 대신 release_branches 의 head/base 로 "
                     "release_steps 를 따른다. 이 쌍이 맞는지 사용자에게 한 번 확인. " + next_hint)

    return emit({
        "ok": True,
        # 항상 문자열 (#970)
        "summary": (f"릴리스 {branches['head']} > {branches['base']} ({source}), 앱 심사 hint={hint}"
                    if shape["release_shape"] == "standard" else
                    f"deploy 브랜치형: {shape['release_branches']['head']} > "
                    f"{shape['release_branches']['base']}, 앱 심사 hint={hint}"),
        "project_root": str(project_root),
        "signals": signals,
        "branches": branches,   # {head, base, provider} — head→base로 릴리스 PR 생성
        # version.yml(정본) | config(version.yml 없는 레포의 레포별 기록) | fallback(아무것도 없음)
        "branches_source": source,
        "conflict": conflict,   # version.yml ≠ 레포별 config 일 때만 채워진다
        "config": {
            "owner": owner,
            "repo": repo,
            "repo_entry": view["repo_entry"],
            # 더는 읽지 않는 전역 키 — 남아 있으면 사용자에게 정리 대상이다
            "ignored_global_keys": view["ignored_global_keys"],
        },
        "hint": hint,
        # 노트 언어·제목·스토어 언어·고정 스토어 문구 (#977) — 노트를 쓰기 전에 본다
        "release_language": collect_release_language(project_root),
        "branches_check": check,
        **shape,
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
    p_ds.add_argument("--wait", type=int, default=0, metavar="SECONDS",
                      help="automerge 대기 중이면 최대 이 초만큼 도구 안에서 폴링 (최대 540). sleep 대신 쓴다")
    p_ds.add_argument("--head", default=None, help="릴리스 PR의 head 브랜치 (없으면 의존성 봇 PR만 제외)")
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
    p_cp.add_argument("--allow-empty", action="store_true",
                      help="head 가 base 보다 앞선 커밋이 없어도 PR 을 만든다 (기본은 nothing_to_deploy 로 거절)")
    # 앱 심사 승인 게이트 (#970): 앱 신호 판정 위치와 사용자 승인 표시
    p_cp.add_argument("--project-root", help="앱 심사 신호를 볼 레포 루트 (생략 시 cwd)")
    p_cp.add_argument("--user-approved", action="store_true",
                      help="앱 심사 레포에서 사용자가 릴리스 노트를 보고 승인했을 때만 붙인다 (없으면 needs_user_approval)")
    p_cp.set_defaults(func=cmd_create_pr)

    p_sb = sub.add_parser("sync-base", help="배포 전 base 를 head 에 병합 (fetch > 차이 확인 > merge, 충돌은 멈춤)")
    p_sb.add_argument("--head", required=True, help="릴리스 head 브랜치 (현재 체크아웃돼 있어야 한다)")
    p_sb.add_argument("--base", required=True, help="릴리스 base 브랜치")
    p_sb.add_argument("--project-root", help="레포 루트 (생략 시 cwd)")
    p_sb.set_defaults(func=cmd_sync_base)

    # 앱 스토어 심사 연관 레포인지 '신호'를 수집한다 (판단·확인은 agent). PAT 불필요 — 로컬 파일만 스캔.
    p_drc = sub.add_parser("detect-release-context", help="앱 심사 연관 레포 신호 수집 (signals/hint JSON)")
    p_drc.add_argument("--project-root", help="레포 루트 절대경로 (생략 시 cwd)")
    # config 대조용 (#842) — 생략하면 origin URL·고정 config 경로를 쓴다. config는 읽기만 한다.
    p_drc.add_argument("--owner", help="레포 owner (생략 시 origin URL에서 추출)")
    p_drc.add_argument("--repo", help="레포 이름 (생략 시 origin URL에서 추출)")
    p_drc.add_argument("--config", help="config.json 경로 (생략 시 ~/.projectops/config/config.json)")
    p_drc.set_defaults(func=cmd_detect_release_context)

    return parser


def main() -> int:
    return run_cli(build_parser())


if __name__ == "__main__":
    sys.exit(main())
