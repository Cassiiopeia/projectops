"""공통 워크플로우 댓글·로그 언어 (#769 3층 2단계).

- 댓글 문구: 메시지 카탈로그(en/ko)에서, 언어는 version.yml options.language
- 실행 로그(echo·console.log·스텝 이름): 언제나 영문
- 한국어 레포가 받는 댓글은 이관 전과 바이트 단위로 같아야 한다
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
ROOT = SCRIPTS.parents[1]
COMMON = ROOT / ".github" / "workflows" / "project-types" / "common"
sys.path.insert(0, str(SCRIPTS))
import dispatch_downstream as dd  # noqa: E402
from i18n import messages  # noqa: E402

HANGUL = re.compile(r"[가-힣]")
EN = json.loads((SCRIPTS / "i18n" / "en.json").read_text(encoding="utf-8"))
KO = json.loads((SCRIPTS / "i18n" / "ko.json").read_text(encoding="utf-8"))
COMMON_WORKFLOWS = sorted(COMMON.rglob("PROJECT-COMMON-*.y*ml"))


def _cli_get(key, lang, *variables):
    args = [sys.executable, str(SCRIPTS / "i18n" / "messages.py"), "get", key]
    for v in variables:
        args += ["--var", v]
    return subprocess.run(args, capture_output=True, text=True, check=True,
                          env={**os.environ, "REPO_LANG": lang}).stdout


# ── 카탈로그 ─────────────────────────────────────────────────────────────

def test_한국어_카탈로그는_영문의_모든_키를_가진다():
    # 한국어는 기존 사용자가 쓰는 언어라 부분 번역을 허용하지 않는다 (영문 대체로 섞이면 안 된다)
    assert sorted(set(EN) - set(KO)) == []
    assert sorted(set(KO) - set(EN)) == []


def test_워크플로우가_부르는_키는_en_ko_모두에_있다():
    pat = re.compile(r"messages\.py get ([a-z0-9_.]+)")
    used = set()
    for wf in COMMON_WORKFLOWS:
        used |= set(pat.findall(wf.read_text(encoding="utf-8")))
    assert used, "워크플로우에서 카탈로그 호출을 하나도 못 찾았다 — 검사가 헛돈다"
    assert sorted(k for k in used if k not in EN or k not in KO) == []


# ── 언어 결정 ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("yml,expected", [
    ("metadata:\n  template:\n    options:\n      language: en\n", "en"),
    ("metadata:\n  template:\n    options:\n      language: ko\n", "ko"),
    # 키 없는 기존 설치는 ko — src/core/repo-language.js resolveRepoLanguage(existing) 와 같은 규칙
    ("metadata:\n  template:\n    options:\n      deploy: none\n", "ko"),
], ids=["en", "ko", "missing-key"])
def test_언어는_version_yml_에서_정한다(tmp_path, yml, expected):
    vy = tmp_path / "version.yml"
    vy.write_text(yml, encoding="utf-8")
    assert messages.resolve_language(vy, env={}) == expected


def test_REPO_LANG_환경변수가_version_yml_보다_우선한다(tmp_path):
    vy = tmp_path / "version.yml"
    vy.write_text("metadata:\n  template:\n    options:\n      language: ko\n", encoding="utf-8")
    assert messages.resolve_language(vy, env={"REPO_LANG": "en"}) == "en"


# ── 댓글 렌더링 ───────────────────────────────────────────────────────────

FAILED = {"failed": [{"workflow": "PROJECT-COMMON-README-VERSION-UPDATE.yaml", "detail": "HTTP 403 Forbidden"}]}

# 이관 전 dispatch_downstream._notify_pr 가 만들던 본문 그대로
KO_DISPATCH_BEFORE = "\n".join([
    "⚠️ **릴리스 후속 워크플로우를 자동 실행하지 못했습니다**",
    "",
    "이 저장소에는 PAT(`_GITHUB_PAT_TOKEN`)가 등록되어 있지 않아, 릴리스 머지 후 후속",
    "워크플로우를 직접 깨우는 경로를 사용합니다. 그 호출이 전부 실패했습니다.",
    "",
    "| 워크플로우 | 사유 |",
    "|---|---|",
    "| `PROJECT-COMMON-README-VERSION-UPDATE.yaml` | HTTP 403 Forbidden |",
    "",
    "**확인할 것**",
    "- 저장소 Settings > Actions > General > Workflow permissions가 `Read and write permissions`인지",
    "- 위 워크플로우들을 Actions 탭에서 수동 실행(Run workflow)하면 이번 릴리스분이 반영됩니다",
])


def test_dispatch_실패_댓글_한국어는_이관_전과_같다():
    assert dd.render_failure_comment(FAILED, "ko") == KO_DISPATCH_BEFORE


def test_dispatch_실패_댓글_영문에는_한글이_없고_표가_유지된다():
    body = dd.render_failure_comment(FAILED, "en")
    assert not HANGUL.search(body)
    assert "| Workflow | Reason |" in body
    assert "| `PROJECT-COMMON-README-VERSION-UPDATE.yaml` | HTTP 403 Forbidden |" in body


def test_dispatch_실패_댓글은_레포_언어를_따른다(monkeypatch):
    monkeypatch.setenv("REPO_LANG", "en")
    assert dd.render_failure_comment(FAILED).startswith("⚠️ **Could not run")
    monkeypatch.setenv("REPO_LANG", "ko")
    assert dd.render_failure_comment(FAILED) == KO_DISPATCH_BEFORE


# 이관 전 RELEASE-CHANGELOG 의 bash 문구 (base 는 main)
KO_RELEASE_BEFORE = {
    "release.comment.applied_to_base": "✅ 변경사항이 자동으로 main 브랜치에 적용되었습니다. PR을 수동으로 닫아주세요.",
    "release.comment.merge_failed": "❌ 자동 병합 실패. 수동으로 병합해주세요.",
    "release.comment.merge_failed_no_pat": (
        "❌ 자동 병합 실패: PAT 토큰이 설정되어 있지 않습니다. Settings > Secrets에 `_GITHUB_PAT_TOKEN`을 "
        "등록하거나 Branch Protection Rules에서 GitHub Actions bot을 예외로 추가해주세요."),
}


@pytest.mark.parametrize("key", sorted(KO_RELEASE_BEFORE))
def test_릴리스_PR_댓글_한국어는_이관_전과_같고_영문에는_한글이_없다(key):
    assert _cli_get(key, "ko", "base=main") == KO_RELEASE_BEFORE[key]
    en = _cli_get(key, "en", "base=main")
    assert en and not HANGUL.search(en)
    if "{base}" in EN[key]:
        assert "main" in en


def test_README_새_버전_제목은_언어별이고_워크플로우_패턴이_다시_찾는다():
    assert _cli_get("readme.version_heading", "ko") == "최신 버전"
    assert _cli_get("readme.version_heading", "en") == "Latest version"
    # 다음 실행에서 같은 줄을 찾아 갱신해야 한다 — 워크플로우의 패턴 목록에 두 제목이 모두 걸려야 한다
    text = (COMMON / "PROJECT-COMMON-README-VERSION-UPDATE.yaml").read_text(encoding="utf-8")
    patterns = [p.replace("[[:space:]]", r"\s") for p in re.findall(r'^\s+"(\^##[^"]+)"$', text, re.M)]
    for heading in ("최신 버전", "Latest version"):
        line = f"## {heading} : v1.0.0"
        assert any(re.search(p, line, re.I) for p in patterns), heading


# ── 실행 로그는 영문 ──────────────────────────────────────────────────────

LOG_LINE = re.compile(r"^\s*(echo\b|console\.(log|error)\(|- name:|description:|print_error_message\b)")
# 데이터·예시라 번역 대상이 아닌 줄 (이유와 함께)
LOG_ALLOWED = (
    "• ## 최신",  # README 가 지원하는 한국어 제목 형식 예시 (패턴과 짝)
)


@pytest.mark.parametrize("wf", COMMON_WORKFLOWS, ids=lambda p: p.name)
def test_공통_워크플로우의_로그와_스텝_이름은_영문이다(wf):
    bad = []
    for no, line in enumerate(wf.read_text(encoding="utf-8").splitlines(), 1):
        if LOG_LINE.match(line) and HANGUL.search(line) and not any(a in line for a in LOG_ALLOWED):
            bad.append(f"{no}: {line.strip()}")
    assert not bad, "\n".join(bad)
