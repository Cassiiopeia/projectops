"""워크플로우가 만드는 커밋 메시지(#787): 언어별 문구, 카탈로그가 없는 설치에서의 대체, [skip ci] 계약."""
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"

SITES = {
    "PROJECT-COMMON-README-VERSION-UPDATE.yaml": ("release.commit.readme", True),
    "PROJECT-COMMON-VERSION-CONTROL.yaml": ("release.commit.version_control", True),
    # 릴리스 확정 커밋은 [skip ci] 를 일부러 넣지 않는다: main HEAD 가 되어 배포 워크플로우를 깨워야 한다
    "PROJECT-COMMON-RELEASE-CHANGELOG.yaml": ("release.commit.finalize", False),
}


def _snippet(name):
    """워크플로우에서 COMMIT_TITLE=... 두 줄(조회와 대체)을 그대로 뽑는다."""
    text = (WF / name).read_text(encoding="utf-8")
    m = re.search(r"^ *COMMIT_TITLE=\$\(.*?\) \\\n *\|\| COMMIT_TITLE=.*$", text, re.M)
    assert m, f"{name}: COMMIT_TITLE 조회/대체 구문이 없다"
    return textwrap.dedent(m.group(0))


def _run(name, cwd, lang, extra_env=""):
    script = (f'REPO_NAME=proj; VERSION=1.2.3; NEW_VERSION=1.2.3; PR_NUMBER=7\nexport REPO_LANG={lang}\n'
              f'{extra_env}\n{_snippet(name)}\nprintf "%s" "$COMMIT_TITLE"')
    r = subprocess.run(["bash", "-c", script], cwd=cwd, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.mark.parametrize("name", SITES)
def test_한국어는_이관_전_문구와_같다(name):
    out = _run(name, ROOT, "ko")
    expected = {
        "PROJECT-COMMON-README-VERSION-UPDATE.yaml": "proj 버전 관리 : docs : v1.2.3 README 버전 정보 업데이트",
        "PROJECT-COMMON-VERSION-CONTROL.yaml": "proj 버전 정보 관리: chore: 버전 1.2.3",
        "PROJECT-COMMON-RELEASE-CHANGELOG.yaml": "proj 버전 관리 : chore : v1.2.3 릴리즈 버전 확정 및 릴리즈 문서 업데이트 (PR #7)",
    }[name]
    assert out == expected


@pytest.mark.parametrize("name", SITES)
def test_영문은_한글이_없다(name):
    assert not re.search(r"[가-힣]", _run(name, ROOT, "en"))


@pytest.mark.parametrize("name", SITES)
def test_카탈로그가_없는_오래된_설치에서도_기존_한국어_문구로_이어간다(name, tmp_path):
    # i18n 폴더가 없는 레포 루트에서 돌린다 — 조회가 실패해도 릴리스가 막히면 안 된다
    assert re.search(r"[가-힣]", _run(name, tmp_path, "en"))


@pytest.mark.parametrize("name", SITES)
def test_skip_ci_는_워크플로우가_붙이고_카탈로그에는_없다(name):
    key, skip = SITES[name]
    text = (WF / name).read_text(encoding="utf-8")
    assert key in text
    if skip:
        assert re.search(r'"\$COMMIT_(TITLE|MSG)[^"]*\[skip ci\]"|COMMIT_MSG="\$COMMIT_TITLE \[skip ci\]"', text) or "[skip ci]\"" in text
    else:
        assert 'git commit -m "$COMMIT_TITLE"' in text


def test_카탈로그_문구에는_skip_ci_가_없다():
    import json
    for p in (ROOT / ".github/scripts/i18n").glob("*.json"):
        for k, v in json.loads(p.read_text(encoding="utf-8")).items():
            assert "[skip ci]" not in v, f"{p.name}:{k}"
