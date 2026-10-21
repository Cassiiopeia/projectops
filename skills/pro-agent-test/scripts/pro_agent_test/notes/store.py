"""learned.json 읽기·쓰기: 구조 판 올리기(픽셀 > 비율), 깨진 파일 보관, 원자적 저장"""
from __future__ import annotations

import re
from pathlib import Path

from common.state import base_dir as _base_dir

from pro_agent_test.storage import _MACHINE, _NOTE_FILE, _scenario_dir


# =========================================================================
# 학습 노트 — 이 프로젝트에서만 통하는 것을 쌓아 간다
# =========================================================================
#
# 기억 원칙: skills/references/memory-principles.md (#833 · #837)
#  - 읽기는 agent 호출에 맡기지 않는다 → detect · scenario show 응답에 몇 건만 싣는다 (_surface)
#  - 쓰기 전에 비슷한 항목을 찾는다 → 확실하면 합치고, 애매하면 related 로 보여 준다
#  - 성적(ok·fail·last_seen)과 낡음 → 지우지 않고 verify 로 표시해 뒤로 민다
#  - 레포와 무관한 것(flutter·platform)은 이 컴퓨터 범위 한 곳에 둔다


def _note_path(root: Path, create: bool = False) -> Path:
    return _scenario_dir(root, create) / _NOTE_FILE


def _machine_note_path() -> Path:
    return _base_dir() / "agent-test" / _MACHINE / _NOTE_FILE


# 이 파일이 담는 구조의 판. 필드를 없애는 변경을 할 때만 올린다.
# 2: screens 에 variants 축 추가 (#583)
# 3: variants 의 taps(픽셀) → targets(요소·비율), 원본은 legacy_taps 로 보존 (#838)
_NOTE_SCHEMA = 3


def _variant_key(role: str | None, screen_size: str | None) -> str:
    """좌표 한 벌을 구분하는 키.

    해상도가 같아도 **빌드가 다르면 화면이 다르다.** 역할마다 다른 빌드가 깔리는 일이
    흔해서(한쪽만 재설치되기도 한다) 역할을 키에 넣는다. 역할 이름은 JSON 키로만
    쓰이므로 한글·공백이 들어와도 안전하다 — 셸 변수명으로는 쓰지 않는다.
    """
    return "%s@%s" % (role or "default", screen_size or "?")


def _promote_screen(entry: dict) -> dict:
    """구 포맷(화면당 좌표 한 벌)을 변형 하나로 올린다.

    읽는 순간 올리고 파일은 다음 쓰기에 갱신된다. 기존 프로젝트가 쌓아 둔 기록을
    깨뜨리지 않는 것이 조건이다 — 지우고 다시 재라고 하면 아무도 안 쓴다.
    """
    if "variants" in entry:
        return entry
    legacy = {k: entry.pop(k) for k in ("taps", "measured_on") if k in entry}
    entry["variants"] = ({_variant_key(None, legacy.get("measured_on")): legacy}
                         if legacy else {})
    return entry


_SIZE = re.compile(r"(\d{2,5})x(\d{2,5})")
_LOCATORS = ("text", "id", "desc")


def _fmt_ratio(v: float) -> str:
    """0.815 처럼 짧게. 소수 넷째 자리면 1080 폭에서도 1px 안쪽이다."""
    return f"{round(v, 4):.4f}".rstrip("0").rstrip(".") or "0"


def _px_to_at(xy: str, size: str | None) -> str | None:
    """'540,1956' @ '1080x2400' → '0.5,0.815'. 바꿀 수 없으면 None."""
    m = _SIZE.fullmatch(size or "")
    p = re.fullmatch(r"\s*(\d+)\s*,\s*(\d+)\s*", xy or "")
    if not (m and p):
        return None
    w, h = int(m.group(1)), int(m.group(2))
    x, y = int(p.group(1)), int(p.group(2))
    if not (0 <= x <= w and 0 <= y <= h):
        return None
    return f"{_fmt_ratio(x / w)},{_fmt_ratio(y / h)}"


def _migrate_variant(v: dict) -> dict:
    """픽셀 taps 를 비율 targets 로 바꾼다 (#838).

    `launch_cli app tap` 은 픽셀을 거절한다(#826). 옛 기록을 그대로 두면 쓸 수 없다.
    바꾼 값은 계산일 뿐 확인된 것이 아니라 verify 를 붙이고, 원본은 legacy_taps 로 남긴다.
    읽을 때마다 메모리에서 바꾸고, 파일은 다음 쓰기에서 갱신된다.
    """
    taps = v.get("taps")
    if not isinstance(taps, dict):
        return v
    v.pop("taps")
    targets = v.setdefault("targets", {})
    unconverted = []
    for label, xy in taps.items():
        if label in targets:
            continue
        at = _px_to_at(str(xy), v.get("measured_on"))
        if at:
            targets[label] = {"at": at, "verify": True}
        else:
            unconverted.append(label)
    v["legacy_taps"] = {**(v.get("legacy_taps") or {}), **taps}
    if unconverted:
        # 해상도를 모르면 비율로 바꿀 수 없다 — 지우지 않고 다시 재라고 알린다
        v["unconverted"] = sorted(set((v.get("unconverted") or []) + unconverted))
    return v


def _migrate_screens(notes: dict) -> None:
    screens = notes.get("screens")
    if not isinstance(screens, dict):
        return
    for entry in screens.values():
        if not isinstance(entry, dict):
            continue
        _promote_screen(entry)
        for v in (entry.get("variants") or {}).values():
            if isinstance(v, dict):
                _migrate_variant(v)


def _read_notes(f: Path) -> tuple[dict, str | None]:
    """쌓인 기록을 읽는다. 읽지 못해도 **지우지 않는다.**

    반환: (내용, 경고). 경고가 있으면 호출부가 사용자에게 알려야 한다.

    깨진 파일을 빈 값으로 덮으면 그동안 쌓은 것이 조용히 사라진다. 편집 중 충돌이나
    부분 쓰기로 깨질 수 있으므로, 이때는 원본을 따로 보관하고 새로 시작한다.
    """
    import json
    from datetime import datetime

    empty = {"schema": _NOTE_SCHEMA, "constraints": [], "screens": {},
             "pitfalls": [], "runs": []}
    if not f.exists():
        return empty, None
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("top level is not an object")
    except (json.JSONDecodeError, ValueError, OSError) as e:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = f.with_suffix(f".broken-{stamp}.json")
        try:
            backup.write_bytes(f.read_bytes())
            where = str(backup.name)
        except OSError:
            where = "(backup failed)"
        return empty, f"Could not read {f.name} ({e}). Moved the original to {where}"

    # 모르는 필드는 건드리지 않는다 — 다른 하네스나 다음 버전이 쓴 것일 수 있다
    for k, v in empty.items():
        data.setdefault(k, v)
    for k in ("constraints", "pitfalls", "runs"):
        if not isinstance(data.get(k), list):
            data[k] = []
    _migrate_screens(data)
    return data, None


def _load_notes(root: Path) -> tuple[dict, str | None]:
    return _read_notes(_note_path(root))


def _save_notes(f: Path, notes: dict) -> None:
    """원자적으로 쓴다 — 쓰는 도중 멈춰도 기존 파일이 깨지지 않는다.

    쓸 때 판 번호를 지금 판으로 올린다 — 읽을 때 바꾼 구조(targets 등)가 이때 파일에 들어간다.
    """
    import json
    import os
    notes["schema"] = _NOTE_SCHEMA
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_name(f"{f.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(notes, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, f)      # 같은 파일시스템 안에서는 원자적이다


def _locator(t: dict) -> dict:
    return {k: t[k] for k in (*_LOCATORS, "index", "at") if k in t}
