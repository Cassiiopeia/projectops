"""개인 설정 층(preferences) 병합 계약.

층 순서: 기본값 → preferences → skills.<id> → repos[].preferences → repos[].skills.<id>.
표현 키만 받는다 — 안전 규칙(승인·dry-run 등)을 끄는 키는 ignored 로 빠진다.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from common.preferences import resolve  # noqa: E402

DATA = {
    "preferences": {"language": "ko", "tone": "간결하게", "rules": ["이모지 금지"]},
    "skills": {"pro-commit": {"preset": "projectops", "tone": "명령형"}},
    "github": {"repos": [
        {"owner": "Acme", "repo": "Web", "preferences": {"language": "en"},
         "skills": {"pro-commit": {"preset": "conventional"}}},
    ]},
}


def test_missing_config_returns_defaults():
    r = resolve("pro-report", data=None)
    assert r["values"] == {} and r["sources"] == {} and r["ignored"] == []


def test_layer_order_global_then_skill():
    r = resolve("pro-commit", data=DATA)
    assert r["values"]["language"] == "ko"
    assert r["values"]["tone"] == "명령형"          # 스킬 층이 공통 층을 덮는다
    assert r["values"]["preset"] == "projectops"
    assert r["sources"]["tone"] == "skills.pro-commit"
    assert r["sources"]["language"] == "preferences"


def test_repo_layers_win():
    r = resolve("pro-commit", owner="Acme", repo="Web", data=DATA)
    assert r["values"]["language"] == "en"
    assert r["values"]["preset"] == "conventional"
    assert r["sources"]["preset"] == "repos[Acme/Web].skills.pro-commit"


def test_repo_match_is_case_insensitive():
    r = resolve("pro-commit", owner="acme", repo="web", data=DATA)
    assert r["values"]["language"] == "en"


def test_other_skill_gets_only_common_layer():
    r = resolve("pro-report", data=DATA)
    assert r["values"] == {"language": "ko", "tone": "간결하게", "rules": ["이모지 금지"]}


def test_unknown_and_safety_keys_are_ignored():
    data = {"preferences": {"auto_approve": True, "dry_run": False, "tone": "x"}}
    r = resolve("pro-github", data=data)
    assert r["values"] == {"tone": "x"}
    assert sorted(r["ignored"]) == ["preferences.auto_approve", "preferences.dry_run"]


def test_wrong_types_are_ignored():
    r = resolve("pro-report", data={"preferences": {"rules": "문자열", "language": 3}})
    assert r["values"] == {}
    assert sorted(r["ignored"]) == ["preferences.language", "preferences.rules"]


def test_cli_emits_json(tmp_path):
    home = tmp_path / "home"
    (home / ".projectops" / "config").mkdir(parents=True)
    (home / ".projectops" / "config" / "config.json").write_text(json.dumps(DATA), encoding="utf-8")
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "prefs_cli.py"), "resolve", "--skill", "pro-commit", "--repo", "Acme/Web"],
        capture_output=True, text=True, env={"HOME": str(home), "USERPROFILE": str(home), "PYTHONIOENCODING": "utf-8"},
    )
    payload = json.loads(out.stdout)
    assert out.returncode == 0 and payload["ok"] is True
    assert payload["values"]["preset"] == "conventional"


def test_malformed_sections_fall_back():
    """손으로 고친 config 의 깨진 섹션이 예외 없이 기본값으로 떨어지고, 멀쩡한 층은 그대로 적용된다."""
    # skills 가 문자열 — 스킬 층만 버리고 공통 층은 살아야 한다
    r = resolve("pro-commit", data={"preferences": {"tone": "x"}, "skills": "x"})
    assert r["values"] == {"tone": "x"}

    # github 이 리스트 — 레포 층 없이 공통 층만
    r = resolve("pro-commit", owner="Acme", repo="Web",
                data={"preferences": {"tone": "x"}, "github": []})
    assert r["values"] == {"tone": "x"}

    # repos 가 리스트가 아님 — 레포 매칭 자체를 건너뛴다
    r = resolve("pro-commit", owner="Acme", repo="Web",
                data={"preferences": {"tone": "x"}, "github": {"repos": "x"}})
    assert r["values"] == {"tone": "x"}

    # 레포 항목의 skills 가 문자열 — 레포 공통 층(preferences)은 여전히 적용된다
    data = {"github": {"repos": [
        {"owner": "Acme", "repo": "Web", "preferences": {"language": "en"}, "skills": "x"},
    ]}}
    r = resolve("pro-commit", owner="Acme", repo="Web", data=data)
    assert r["values"] == {"language": "en"}
    assert r["sources"]["language"] == "repos[Acme/Web].preferences"
