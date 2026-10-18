"""pro-launch 공식 트러블슈팅 — 실패 응답의 known_fix, kb 명령, 항목 품질 계약 (#889).

품질 계약: 항목이 가리키는 code 와 명령이 지금 코드에 실제로 있어야 한다. 코드가 바뀌어
낡은 지식이 되면 이 테스트가 먼저 드러낸다. 상태는 conftest 가 PROJECTOPS_HOME 을 임시로 돌린다.
"""
from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import knowledge  # noqa: E402
from common import troubleshoot  # noqa: E402
from pro_launch import cli as launch_cli_module  # noqa: E402
from pro_launch.runtime import output as rt_output  # noqa: E402
from test_launch_cli import _j, _repo, run_cli  # noqa: E402

BROWSER_ENTRY = "browser-start-stale-process-or-lock"


def _out_payload(payload: dict, capsys) -> dict:
    rt_output.out(payload)
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


# ── 실패 응답의 known_fix ──────────────────────────────────────────────

def test_failure_with_known_code_carries_known_fix(capsys):
    got = _out_payload({"ok": False, "code": "browser_start_failed", "error": "브라우저가 뜨지 않았습니다"}, capsys)
    assert got["known_fix"][0]["id"] == BROWSER_ENTRY
    # 항목 문구는 바뀔 수 있다 — 응답의 해결 요약이 색인의 fix_short 와 같은지 본다
    index = json.loads((SKILL_DIR / "troubleshooting" / "index.json").read_text(encoding="utf-8"))
    assert got["known_fix"][0]["fix"] == index["entries"][BROWSER_ENTRY]["fix_short"]
    assert len(got["known_fix"]) <= troubleshoot.DEFAULT_FIND_LIMIT
    assert "kb show" in got["known_fix_note"]


def test_success_and_unknown_failure_have_no_known_fix(capsys):
    assert "known_fix" not in _out_payload({"ok": True, "code": "browser_start_failed"}, capsys)
    assert "known_fix" not in _out_payload({"ok": False, "code": "nothing_matches_this"}, capsys)


def test_broken_knowledge_never_breaks_the_command(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(rt_output, "SKILL_DIR", tmp_path)   # 색인 없음
    assert "known_fix" not in _out_payload({"ok": False, "code": "browser_start_failed"}, capsys)

    def explode(*_args, **_kwargs):
        raise RuntimeError("broken")
    monkeypatch.setattr(rt_output.troubleshoot, "find_known_fixes", explode)
    got = _out_payload({"ok": False, "code": "browser_start_failed"}, capsys)
    assert got["code"] == "browser_start_failed" and "known_fix" not in got


def test_bad_args_path_also_carries_known_fix(capsys, monkeypatch):
    fake = [{"id": "x", "title": "t", "fix": ["launch_cli.py doctor"]}]
    monkeypatch.setattr(rt_output.troubleshoot, "find_known_fixes", lambda *a, **k: fake)
    launch_cli_module.main(["web", "nosuch"])
    got = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert got["code"] == "bad_args" and got["known_fix"] == fake


# ── kb 명령 ─────────────────────────────────────────────────────────────

def kb(tmp_path, *args):
    repo = tmp_path / "proj"
    if not repo.exists():
        _repo(tmp_path)
    _, out, _ = run_cli("kb", *args, "--root", str(repo))
    return _j(out)


def test_kb_list_search_show(tmp_path):
    assert {e["id"] for e in kb(tmp_path, "list")["entries"]} >= {BROWSER_ENTRY}
    assert all(e["area"] == "ios" for e in kb(tmp_path, "list", "--area", "ios")["entries"])
    found = kb(tmp_path, "search", "--code", "browser_start_failed")
    assert found["matches"][0]["id"] == BROWSER_ENTRY and found["next"].startswith("kb show")
    shown = kb(tmp_path, "show", BROWSER_ENTRY)
    assert shown["entry"]["cause"] and shown["entry"]["refs"]


def test_kb_errors_are_json(tmp_path):
    assert kb(tmp_path, "show", "no-such-entry")["code"] == "not_found"
    assert kb(tmp_path, "show")["code"] == "id_required"
    assert kb(tmp_path, "search")["code"] == "query_required"
    assert kb(tmp_path, "search", "전혀 관계없는 문장")["code"] == "empty"


def _save_memory(entries: list[dict]) -> None:
    rows = [{"key": key, "area": area, "how": how, "ok": ok, "fail": fail, "last_seen": "2026-10-01"}
            for key, area, how, ok, fail in entries]
    knowledge.save(knowledge.store_path("machine", Path(".")), rows)


def test_kb_propose_drafts_only_proven_memories_and_drops_secrets(tmp_path):
    _save_memory([
        ("web.google-login", "web", "Google 로그인은 web open --headed 로 띄운다", 3, 0),
        ("web.weak", "web", "두 번만 먹힌 방법", 2, 0),
        ("ios.flaky", "ios", "실패가 성공만큼 많은 방법", 3, 3),
        ("server.leak", "server", "로그인 password: hunter2-real 로 붙는다", 5, 0),
    ])
    got = kb(tmp_path, "propose")
    assert [d["draft"]["id"] for d in got["drafts"]] == ["web-google-login"]
    draft = got["drafts"][0]
    assert draft["path"] == "troubleshooting/web/web-google-login.json"
    assert draft["draft"]["fix"] == ["Google 로그인은 web open --headed 로 띄운다"]
    assert "symptom" in draft["todo"] and "PR" in got["next"]
    assert got["skipped"] == [{"key": "server.leak", "scope": "machine", "reason": "secret_detected"}]
    assert "hunter2" not in json.dumps(got["drafts"], ensure_ascii=False)
    # 초안은 파일로 쓰지 않는다
    assert not (SKILL_DIR / "troubleshooting" / "web" / "web-google-login.json").exists()


def test_kb_propose_filters_by_key_and_area(tmp_path):
    _save_memory([("web.a", "web", "방법 에이", 4, 0), ("ios.b", "ios", "방법 비", 4, 0)])
    assert [d["draft"]["id"] for d in kb(tmp_path, "propose", "--key", "ios.b")["drafts"]] == ["ios-b"]
    assert [d["draft"]["id"] for d in kb(tmp_path, "propose", "--area", "web")["drafts"]] == ["web-a"]


# ── 품질 계약 ───────────────────────────────────────────────────────────

def _emitted_code_patterns() -> list[re.Pattern]:
    """스크립트가 응답 code 로 내는 값 — {"code": ...} 와 code=... 의 문자열·f-문자열."""
    patterns = []

    def add(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            patterns.append(re.compile(re.escape(node.value) + r"\Z"))
        elif isinstance(node, ast.IfExp):   # "a" if ok else "b" — 두 갈래 모두 나올 수 있는 code
            add(node.body)
            add(node.orelse)
        elif isinstance(node, ast.JoinedStr):
            parts = [re.escape(v.value) if isinstance(v, ast.Constant) else r"[a-z0-9_]+" for v in node.values]
            patterns.append(re.compile("".join(parts) + r"\Z"))

    for path in (SKILL_DIR / "scripts").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "code":
                        add(value)
            elif isinstance(node, ast.keyword) and node.arg == "code":
                add(node.value)
    return patterns


def _entries() -> list[dict]:
    rows, problems = troubleshoot.read_entries(SKILL_DIR)
    assert problems == []
    return [entry for _, entry in rows]


def test_entries_are_valid_unique_and_secret_free():
    assert troubleshoot.validate_entries(SKILL_DIR) == []
    ids = [e["id"] for e in _entries()]
    assert len(ids) == len(set(ids))


def test_every_match_code_is_emitted_by_the_cli():
    patterns = _emitted_code_patterns()
    missing = [(e["id"], code) for e in _entries() for code in e["match"]["codes"]
               if not any(p.match(code) for p in patterns)]
    assert missing == [], f"코드에 없는 code 를 가리킨다 (낡은 지식): {missing}"


def _subparsers() -> dict:
    parser = launch_cli_module.build_parser()
    group = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
    return group.choices


def test_every_launch_cli_command_in_fix_exists():
    subparsers = _subparsers()
    problems = []
    for entry in _entries():
        for step in entry["fix"]:
            match = re.search(r"launch_cli(?:\.py)?\s+(.+)", step)
            if not match:
                continue
            tokens = shlex.split(match.group(1).replace("<", "").replace(">", ""))
            name, rest = tokens[0], tokens[1:]
            sub = subparsers.get(name)
            if sub is None:
                problems.append(f"{entry['id']}: 없는 서브커맨드 {name}")
                continue
            positional = next((a for a in sub._actions if not a.option_strings and a.choices), None)
            if positional and rest and not rest[0].startswith("-") and rest[0] not in positional.choices:
                problems.append(f"{entry['id']}: {name} 에 없는 동작 {rest[0]}")
            # web 처럼 동작마다 하위 파서가 있으면 그 동작의 옵션으로 본다 (#896)
            if positional and rest and isinstance(positional.choices, dict) and rest[0] in positional.choices:
                sub = positional.choices[rest[0]]
            options = {o for a in sub._actions for o in a.option_strings}
            problems += [f"{entry['id']}: {name} 에 없는 옵션 {t}" for t in rest
                         if t.startswith("--") and t.split("=")[0] not in options]
    assert problems == [], problems


def test_generated_index_and_doc_are_fresh():
    result = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "build_troubleshooting.py"),
                             str(SKILL_DIR), "--check"], capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("folder", sorted(p.name for p in (SKILL_DIR / "troubleshooting").iterdir() if p.is_dir()))
def test_area_folders_are_known_areas(folder):
    assert folder in troubleshoot.AREAS
