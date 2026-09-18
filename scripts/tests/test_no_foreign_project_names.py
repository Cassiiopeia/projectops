# scripts/tests/test_no_foreign_project_names.py
"""사용자에게 나가는 자산에 남의 프로젝트 이름이 들어갔는지 본다 (#614).

이 저장소는 남의 프로젝트에 설치되는 템플릿이다. 만든 사람이 지금 작업 중인
자기 프로젝트에서 예시를 복사해 붙이면, 설치한 사람 화면에 모르는 조직 이름이 뜬다.
기능이 깨지지 않으므로 리뷰에서 걸리지 않고 오래 남는다 — 실제로 마법사 화면·CLI
`--help`·시나리오 템플릿 기본값까지 11개 파일에 퍼져 있었다.

새로 생길 이름까지 알아맞히는 검사는 만들 수 없다. 현실적인 실수 하나만 겨냥한다:
**자기 프로젝트 이름을 그대로 붙여넣는 것.** 새 프로젝트를 시작하면 아래 목록에
한 줄 추가한다.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# 만든 사람이 실제로 쓰는 조직·앱 이름. 새 프로젝트를 시작하면 여기에 추가한다.
# 이 저장소 자신의 이름(Cassiiopeia/projectops)은 넣지 않는다 — 이슈 링크 등에
# 정당하게 쓰인다.
FOREIGN_NAMES = [
    "elum",
    "twinfang", "twin-fang",
    "romrom",
    "passql",
    "mapsee",
]

# 사용자에게 도달하는 경로.
#   skills/  — Cursor 설치로 통째 복사되고 플러그인으로도 배포된다
#   scripts/ — 스킬 CLI 가 common/ 을 import 하므로 함께 나간다
#   .github/workflows/ · .github/util/ — 통합 시 사용자 레포로 복사된다
SHIPPED_DIRS = ["skills", "scripts", ".github/workflows", ".github/util"]

# 테스트·픽스처는 사용자에게 복사되지 않는다(cursor 어댑터의 SKIP_IN_COPY).
# 실제 이름을 픽스처로 쓰는 것이 오히려 자연스러우므로 제외한다.
SKIP_PARTS = {"test", "tests", "fixtures"}
TEXT_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".toml", ".sh",
                 ".ps1", ".html", ".js", ".ts", ".css", ".txt"}


def _shipped_files():
    """git 이 추적하는 파일만 본다.

    추적되지 않는 것(로컬 venv·빌드 산출물·캐시)은 어차피 사용자에게 가지 않는다.
    디렉터리를 직접 훑으면 `scripts/venv/` 같은 것까지 읽어 엉뚱한 곳에서 걸린다.
    """
    import subprocess
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", *SHIPPED_DIRS],
        capture_output=True, text=True, check=True).stdout
    for rel in filter(None, out.split("\0")):
        p = ROOT / rel
        if p.suffix not in TEXT_SUFFIXES or not p.is_file():
            continue
        if SKIP_PARTS & {part.lower() for part in Path(rel).parts}:
            continue
        yield p


def test_shipped_assets_do_not_name_the_authors_own_projects():
    # 단어 경계를 둔다 — 없으면 `qf1pElump` 안의 `Elum` 까지 걸린다
    pattern = re.compile(
        r"\b(?:" + "|".join(re.escape(n) for n in FOREIGN_NAMES) + r")\b",
        re.IGNORECASE)

    files = list(_shipped_files())
    assert files, "검사할 파일을 찾지 못했다 — 경로 목록이 낡았다"

    hits = []
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), 1):
            m = pattern.search(line)
            if m:
                hits.append(f"{f.relative_to(ROOT).as_posix()}:{i} `{m.group(0)}`"
                            f"\n    {line.strip()[:110]}")

    assert hits == [], (
        "남의 프로젝트 이름이 사용자에게 나가는 자산에 들어 있다. "
        "acme-org · myapp · appdb 같은 중립적인 예시로 바꾸세요:\n" + "\n".join(hits))
