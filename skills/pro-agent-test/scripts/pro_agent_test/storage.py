"""기록 자리: 프로젝트 키, 홈 아래 시나리오·노트 폴더, 시나리오 파일 찾기·전제 펼치기"""
from __future__ import annotations

from pathlib import Path

from common.state import repo_key, state_dir

# 기록 파일 이름 · 노트 요약 크기
_NOTE_FILE = "learned.json"
_SEEN_FILE = "memory_seen.json"     # 응답에 기억을 실은 날 (하루·영역 1회)
_MACHINE = "_machine"               # ~/.projectops/agent-test/_machine/ — 이 컴퓨터 범위

_SHOW_MAX = 5                       # note show 요약: 제약·함정 각각 이만큼
_SHOW_CHARS = 120                   # 요약에서 항목당 글자 수
_SURFACE_CHARS = 200                # 응답에 싣는 항목당 글자 수 (원칙: 200자)
_NOTE_MIN_WORDS = 3                 # 고유어가 이보다 적은 짧은 문장은 자동으로 합치지 않는다
_MACHINE_SCOPES = ("flutter", "platform")


def _repo_key(root: Path) -> str:
    """프로젝트를 가리키는 키 (common/state.py 가 단독으로 정한다)."""
    return repo_key(root)


def _home_dir(root: Path) -> Path:
    """쌓은 것(learned.json · 시나리오 · flows)을 두는 곳. 프로젝트 밖(홈)이라 워크트리를 만들어도 살아남는다.

    기기·브라우저·접속 정보는 pro-launch 의 자리(~/.projectops/launch/)로 옮겼다 (#629).
    """
    return state_dir("agent-test", root)


def _scenario_dir(root: Path, create: bool = False) -> Path:
    """시나리오·지식을 둘 곳.

    홈에 두고 git remote로 프로젝트를 구분한다. 프로젝트 안 폴더는 .gitignore로 빠지면
    **새 워크트리에 복사되지 않아**, 이슈마다 워크트리를 만드는 흐름에서 지식이 사라진다 (#586).
    """
    home = _home_dir(root)
    if create and not home.is_dir():
        home.mkdir(parents=True, exist_ok=True)
    return home

def _scenario_files(d: Path) -> list[Path]:
    """시나리오 파일 목록. flows/ 하위와 _shared/ 를 함께 본다.

    app-map·learned 는 시나리오가 아니므로 제외한다.
    """
    if not d.is_dir():
        return []
    # app-map 은 bootstrap 시절 산출물, memory_seen 은 기억을 실은 날 기록 (#837)
    skip = {"app-map.json", _NOTE_FILE, _SEEN_FILE}
    out = [f for f in d.rglob("*.json")
           if f.name not in skip and not f.name.startswith("learned.broken-")]
    return sorted(out)


def _resolve_scenario(d: Path, name: str) -> Path | None:
    """이름으로 파일을 찾는다. `flows/auth/x` 처럼 경로를 줘도, `x` 만 줘도 된다."""
    direct = d / f"{name}.json"
    # 폴더 밖 파일(../x)은 시나리오가 아니다 (#707)
    if direct.exists() and d.resolve() in direct.resolve().parents:
        return direct
    matches = [f for f in _scenario_files(d) if f.stem == name]
    return matches[0] if len(matches) == 1 else None


def _expand(d: Path, path: Path, seen: list[str] | None = None) -> tuple[dict, list[str]]:
    """전제를 펼쳐 전체 단계를 만든다.

    로그인처럼 거의 모든 시나리오의 앞에 붙는 흐름을 매번 적지 않게 한다.
    순환 참조는 여기서 끊는다 — 무한 재귀로 죽는 대신 문제로 보고한다.
    """
    import json
    seen = seen or []
    key = str(path)
    if key in seen:
        return {}, [f"Precondition cycle: {' → '.join(seen + [key])}"]
    data = json.loads(path.read_text(encoding="utf-8"))
    pre = data.get("precondition")
    if not pre:
        return data, []

    target = _resolve_scenario(d, pre)
    if target is None:
        return data, [f"Precondition '{pre}' not found"]
    base, problems = _expand(d, target, seen + [key])
    merged = dict(data)
    merged["steps"] = list(base.get("steps", [])) + list(data.get("steps", []))
    merged["_precondition_steps"] = len(base.get("steps", []))
    if base.get("reset") and not data.get("reset"):
        merged["reset"] = base["reset"]
    return merged, problems
