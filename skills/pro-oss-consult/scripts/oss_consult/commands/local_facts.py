"""local-facts: 로컬 clone 측정 (git 확인 > 추적 파일·커밋 > 소스·매니페스트 읽기 > 측정)
"""
from __future__ import annotations

from pathlib import Path

from oss_consult import local_git
from oss_consult.local_git import _MANIFEST_MAX_BYTES, _SOURCE_MAX_BYTES, _gitfile_target, _safe_read
from oss_consult.local_measure import (_CATALOG_DIRS, _SOURCE_EXT, co_change, committed_secret_paths,
                                       dependency_names, is_manifest, is_unsupported_manifest,
                                       natural_language_strings)
from oss_consult.output import _LOCAL_UNTRUSTED, _UNTRUSTED_NOTICE, _fail, _out


def cmd_local_facts(args) -> int:
    given = Path(args.path).expanduser()
    if not given.is_dir():
        return _fail("not_a_git_repo", f"Not a directory: {given}", "Pass the path of a clone")
    rc, top, err = local_git._git_raw(given.resolve(), "rev-parse", "--show-toplevel")
    if rc != 0:
        if "not a git repository" in err.lower():
            return _fail("not_a_git_repo", f"Not a git repository: {given.resolve()}", "Pass the path of a clone")
        return _fail("git_error", f"Could not run git: {err.strip()[:200]}",
                     "Check the git install and repository ownership (dubious ownership). Global git config is ignored for safety")
    root = Path(top.strip()).resolve()
    ok, gitfile = _gitfile_target(root)
    if not ok:
        return _fail("unsafe_gitfile", "The .git file does not point at an existing git directory",
                     "Make sure it is a trusted clone and pass it again")
    rc, out, err = local_git._git_raw(root, "ls-files", "-z")
    if rc != 0:
        return _fail("git_error", f"Could not read the tracked file list: {err.strip()[:200]}", "Check the repository state and run again")
    tracked = [t for t in out.split("\0") if t]

    # 커밋별 변경 파일 (최근 N개). 커밋 사이는 %x01 로, 파일은 줄바꿈으로 자른다 (quotepath=false 라 한글 경로 그대로)
    rc, raw, lerr = local_git._git_raw(root, "log", f"-{args.commits}", "--name-only", "--format=%x01", "--no-merges")
    git_error = None
    if rc != 0:
        # 커밋이 하나도 없는 저장소는 오류가 아니라 '커밋 0개'다
        if "does not have any commits" not in lerr and "bad default revision" not in lerr:
            git_error = {"log": lerr.strip()[:200]}
        raw = ""
    commits = [[f for f in chunk.split("\n") if f.strip()] for chunk in raw.split("\x01")[1:]]

    budget = local_git._Budget()
    sources: dict[str, str] = {}
    for t in tracked:
        if Path(t).suffix in _SOURCE_EXT:
            text = _safe_read(root, t, _SOURCE_MAX_BYTES, budget)
            if text is not None:
                sources[t] = text
    manifests: dict[str, str] = {}
    manifests_seen: list[str] = []
    unsupported: list[str] = []
    for t in tracked:
        if any(p in ("node_modules", "vendor", "Pods") for p in t.split("/")):
            continue
        if is_manifest(t):
            manifests_seen.append(t)
            text = _safe_read(root, t, _MANIFEST_MAX_BYTES, budget)
            if text is not None:
                manifests[t] = text
        elif is_unsupported_manifest(t):
            unsupported.append(t)
    catalog = sorted({p for t in tracked for p in Path(t).parts[:-1] if p in _CATALOG_DIRS})
    data = {
        "root": str(root),
        "gitfile": gitfile,
        "co_change": co_change(commits),
        "natural_language_strings": natural_language_strings(sources),
        "string_catalog_dirs": catalog,
        # {} 는 '의존성 없음'이 아니다: manifests_seen 에 있는데 여기 없으면 파싱 결과가 비었거나 읽지 못한 것
        "dependency_manifests": dependency_names(manifests),
        "manifests_seen": manifests_seen,
        "unsupported_manifests": unsupported,
        "committed_secret_paths": committed_secret_paths(tracked),
        "tracked_files": len(tracked),
        "skipped": dict(budget.skipped),
        "capped": {"bytes": budget.capped_bytes, "files": budget.capped_files},
        "git_error": git_error,
    }
    warn = " — files that may be secrets are tracked. Report this before anything else" if data["committed_secret_paths"] else ""
    if budget.capped_bytes or budget.capped_files:
        warn += " — hit the read limit and skipped some files (capped)"
    if git_error:
        warn += " — commit measurements are empty because of a git log error"
    return _out({"data": data, "summary": f"Analyzed {len(tracked)} tracked file(s) and {data['co_change']['commits']} recent commit(s){warn}",
                 "untrusted": _LOCAL_UNTRUSTED, "untrusted_notice": _UNTRUSTED_NOTICE,
                 "next": "Use references/contributor.md to judge change amplification and dependency licenses (the agent decides)"})
