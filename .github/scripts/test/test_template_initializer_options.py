"""'Use this template' 으로 만든 레포의 version.yml 이 템플릿 언어와 라벨 표기를 영문으로 못 박는다 (#769).

못 박지 않으면 키가 없는 "기존 레포" 로 해석돼, 첫 `npx projectops` 업데이트가 영문 템플릿을 받은
레포를 한국어(오버레이)로 뒤집고 영문 라벨을 한글로 바꾼다. 대화형이면 "지금은 한국어입니다" 라는
틀린 질문까지 나온다.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
import template_initializer as ti  # noqa: E402


def _options(tmp_path, monkeypatch) -> str:
    monkeypatch.chdir(tmp_path)
    ti.create_version_yml("1.0.0", "node", "main", "tester", "4.33.0")
    return (tmp_path / "version.yml").read_text(encoding="utf-8")


def test_템플릿으로_만든_레포는_language_en을_기록한다(tmp_path, monkeypatch):
    assert re.search(r"^\s+language:\s*en\b", _options(tmp_path, monkeypatch), re.M)


def test_템플릿으로_만든_레포는_label_style_en을_기록한다(tmp_path, monkeypatch):
    assert re.search(r"^\s+label_style:\s*en\b", _options(tmp_path, monkeypatch), re.M)
