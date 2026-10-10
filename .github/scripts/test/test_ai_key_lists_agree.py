"""AI 서비스 키 이름 목록이 코드 곳곳에서 같은지 (#832).

같은 목록이 ladder.py(실제로 키를 집는 곳), doctor.js(등록 여부 표시), summary.js(안내 문구),
워크플로우 env 블록에 따로 적혀 있다. 새 서비스를 한 곳에만 넣으면 "등록했는데 doctor 가 못 알아본다",
"안내에는 없는 키를 코드는 쓴다" 같은 조용한 불일치가 생긴다.
MODEL_API_KEY 는 구 이름이라 사다리(ladder.py)와 doctor 에만 있고 안내 문구에서는 뺀다.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
from changelog_providers import ladder  # noqa: E402

LADDER = {name for name, _ in ladder.KEY_ENVS}
NAME = re.compile(r"\b[A-Z]+_API_KEY\b")


def _names(path):
    return set(NAME.findall((ROOT / path).read_text(encoding="utf-8"))) - {"MODEL_API_KEY"}


def test_ladder_has_the_known_services():
    assert {"GEMINI_API_KEY", "GROQ_API_KEY", "MISTRAL_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"} <= LADDER


def test_doctor_recognises_every_key_the_ladder_uses():
    assert _names("src/commands/doctor.js") == LADDER


def test_setup_summary_tells_users_every_key_name():
    assert _names("src/ui/summary.js") == LADDER


def test_release_workflows_pass_every_key_to_the_ladder():
    for name in ("PROJECT-COMMON-RELEASE-CHANGELOG.yaml", "PROJECT-COMMON-AI-PR-SUMMARY.yaml"):
        path = next((ROOT / ".github" / "workflows").rglob(name))
        text = path.read_text(encoding="utf-8")
        missing = sorted(k for k in LADDER if f"{k}: ${{{{ secrets.{k} }}}}" not in text)
        assert not missing, f"{name} 이 사다리에 넘기지 않는 키: {missing}"
