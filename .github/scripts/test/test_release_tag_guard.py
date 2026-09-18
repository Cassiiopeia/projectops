"""릴리스 태그가 조용히 잘못 만들어지지 않는지 (#545).

실사고 보고: **워크플로우가 전부 초록불인데 태그도 릴리스도 만들어지지 않았다.**
버전은 올라갔는데 릴리스는 이전 버전에서 멈춰 있었고, 어떤 단계도 실패로 표시되지
않아 배포가 끝난 줄 알았다.

그 보고가 지목한 워크플로우(`PROJECT-COMMON-RELEASE-PUBLISH.yaml`)는 설계 문서에만
있던 것이라 이 저장소에는 없고, 원인이던 커밋 메시지 게이트도 지금 구조에는 없다.
다만 **요구사항 하나는 그대로 남아 있었다** — "누락되면 실패로 표시된다".

남아 있던 구멍:

    NEW_VERSION=""            # 앞 잡의 출력이 비면
    TAG_NAME="v$NEW_VERSION"  # → "v"
    git tag "v" && git push   # 이름이 v 뿐인 태그가 올라가고
    echo "✅ 릴리스 태그 생성: v"   # **성공으로 보고된다**

버전이 비었을 때 세우고, 밀어 넣은 태그가 원격에 실제로 있는지 확인해야 한다.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WF = ROOT / ".github" / "workflows"

_TAGS = re.compile(r"git tag\s+[\"']?\$")


def _steps_creating_tags():
    """`git tag "$..."` 를 실행하는 run 블록을 (파일, 블록) 으로 돌려준다."""
    found = []
    for path in sorted(WF.rglob("*.y*ml")):
        text = path.read_text(encoding="utf-8")
        if not _TAGS.search(text):
            continue
        # run: | 블록 단위로 자른다. 들여쓰기가 얕아지면 블록이 끝난 것으로 본다.
        block, indent = [], None
        for line in text.splitlines():
            if indent is None:
                if re.match(r"\s*run:\s*\|", line):
                    indent = len(line) - len(line.lstrip())
                    block = []
                continue
            if line.strip() and (len(line) - len(line.lstrip())) <= indent:
                if _TAGS.search("\n".join(block)):
                    found.append((path, "\n".join(block)))
                indent, block = None, []
                if re.match(r"\s*run:\s*\|", line):
                    indent = len(line) - len(line.lstrip())
                continue
            block.append(line)
        if indent is not None and _TAGS.search("\n".join(block)):
            found.append((path, "\n".join(block)))
    return found


def test_tag_creation_refuses_an_empty_version():
    """버전이 비면 세워야 한다. 안 그러면 이름이 `v` 뿐인 태그가 성공으로 올라간다."""
    steps = _steps_creating_tags()
    assert steps, "태그를 만드는 단계를 못 찾았다 — 검사가 헛돌고 있다"

    missing = [
        path.relative_to(ROOT).as_posix()
        for path, body in steps
        if not (re.search(r'-z\s+"?\$\{?\w*VERSION', body) and "exit 1" in body)
    ]
    assert missing == [], (
        "버전이 비었을 때 막지 않는 태그 생성 단계가 있다. "
        '`[ -z "$NEW_VERSION" ] && exit 1` 를 앞에 두세요:\n' + "\n".join(missing))


def test_tag_push_is_verified_on_the_remote():
    """밀어 넣은 태그가 원격에 실제로 있는지 본다 — push 가 조용히 실패할 수 있다."""
    steps = _steps_creating_tags()
    missing = [
        path.relative_to(ROOT).as_posix()
        for path, body in steps
        if "ls-remote" not in body
    ]
    assert missing == [], (
        "태그를 밀어 넣고 확인하지 않는 단계가 있다. "
        "`git ls-remote --tags origin` 으로 실제로 올라갔는지 보세요:\n"
        + "\n".join(missing))
