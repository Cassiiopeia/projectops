"""pro-launch 공식 트러블슈팅 — 실패 응답의 known_fix, kb 명령, 항목 품질 계약 (#889).

품질 계약: 항목이 가리키는 code 와 명령이 지금 코드에 실제로 있어야 한다. 코드가 바뀌어
낡은 지식이 되면 이 테스트가 먼저 드러낸다. 상태는 conftest 가 PROJECTOPS_HOME 을 임시로 돌린다.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = SKILL_DIR.parents[1]
sys.path.insert(0, str(SKILL_DIR / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import knowledge  # noqa: E402
from common import troubleshoot  # noqa: E402
from test_launch_cli import _j, _repo, run_cli  # noqa: E402


# ── kb 명령 ─────────────────────────────────────────────────────────────

def kb(tmp_path, *args):
    repo = tmp_path / "proj"
    if not repo.exists():
        _repo(tmp_path)
    _, out, _ = run_cli("kb", *args, "--root", str(repo))
    return _j(out)


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


def test_every_match_code_is_emitted_by_the_cli():
    patterns = _emitted_code_patterns()
    missing = [(e["id"], code) for e in _entries() for code in e["match"]["codes"]
               if not any(p.match(code) for p in patterns)]
    assert missing == [], f"코드에 없는 code 를 가리킨다 (낡은 지식): {missing}"
