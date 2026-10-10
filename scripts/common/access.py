"""붙는 법 기록과 비밀값 검사 (pro-launch · pro-agent-test 공용, #629).

**어떻게 DB에 붙고 로그를 보는지는 agent가 코드를 읽고 판단한다.** 서버는 프레임워크도
붙는 길도 제각각이라 정규식으로 맞힐 수 없다. 그래서 agent가 알아낸 것을 적어 두고
다음 실행이 그것을 쓴다. 저장 자리는 state.py 가 정한다 (프로젝트 밖 — 워크트리를 오가도 남는다).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.state import launch_file

ACCESS_FILE = "access.json"

# 기록에 들어가면 안 되는 것들. 파일은 평문으로 남고 다음 실행마다 다시 읽히므로,
# 한 번 들어가면 계속 노출된다 — 쓰기 전에 막는 편이 유일하게 확실하다.
SECRET_PATTERNS = [
    (r'[\w.+-]+@[\w-]+\.[\w.]{2,}', "이메일 주소"),
    (r'01[016-9][-\s]?\d{3,4}[-\s]?\d{4}', "전화번호"),
    (r'eyJ[\w-]{10,}\.[\w-]{10,}', "JWT 토큰"),
    # 따옴표를 허용해야 JSON도 잡힌다. 예전 패턴은 yaml(`password: x`)만 보고
    # `{"password": "x"}` 를 놓쳤다 — 기록에 원문이 그대로 들어갔다 (#589).
    (r'(?i)["\']?\b(password|passwd|비밀번호|비번)\b["\']?\s*[:=]?\s*["\']?\S{4,}', "비밀번호"),
    (r'(?i)["\']?\b(secret|api[_-]?key|access[_-]?token)\b["\']?\s*[:=]\s*["\']?\S{8,}', "비밀 값"),
]


def find_secrets(text: str) -> list[str]:
    """비밀값으로 보이는 것. 보고할 때도 원문을 다 드러내지 않는다."""
    found = []
    for pattern, label in SECRET_PATTERNS:
        m = re.search(pattern, text)
        if m:
            sample = m.group(0)
            masked = sample[:3] + "***" if len(sample) > 3 else "***"
            found.append(f"{label}({masked})")
    return found


def access_path(root: Path) -> Path:
    return launch_file(root, ACCESS_FILE)


def load_access(root: Path) -> dict:
    f = access_path(root)
    if not f.is_file():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_access(root: Path, data: dict) -> Path:
    f = access_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return f


# ── 붙는 법의 성적 (#836) ────────────────────────────────────────────────
#
# 적어 둔 접속 방법이 지금도 먹히는지 기록한다(기억 원칙 2·4). 도구가 직접 확인한 결과만 쓴다.
# access.json 은 사람이 적은 값 그대로 두고 옆 파일에 쌓는다 — 값이 문자열인 키(logs 명령 등)도
# 있어서 필드를 덧붙일 수 없고, access show·detect 가 키 목록을 그대로 보여 주기 때문이다.
# 날짜·결과 코드만 남긴다. 오류 원문은 비밀이 섞일 수 있어 적지 않는다.

STATUS_FILE = "access_status.json"


def status_path(root: Path) -> Path:
    return launch_file(root, STATUS_FILE)


def load_status(root: Path) -> dict:
    f = status_path(root)
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_status(root: Path, data: dict) -> None:
    f = status_path(root)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def needs_verify(entry: dict | None) -> bool:
    """마지막 결과가 실패인가 — 실패가 앞서면 다음 사용 때 확인하라고 알린다."""
    return bool(entry) and entry.get("last") == "fail"


def record_result(root: Path, key: str, ok: bool, code: str | None = None,
                  today: str | None = None) -> dict:
    """key 로 적힌 접속 방법의 결과를 남긴다. 기록 **전** 상태를 돌려준다(이번 호출이 의심스러운 기록을 썼는지).

    성공 → verified(날짜), 실패 → last_fail{date, code}. 같은 날 같은 결과는 한 번만 센다(부풀리지 않는다).
    """
    import datetime as _dt
    day = today or _dt.date.today().isoformat()
    data = load_status(root)
    prev = dict(data.get(key) or {})
    e = dict(prev)
    if ok:
        if e.get("verified") != day:
            e["ok"] = int(e.get("ok", 0)) + 1
        e["verified"] = day
        e["last"] = "ok"
    else:
        last_fail = e.get("last_fail") or {}
        if last_fail.get("date") != day:
            e["fail"] = int(e.get("fail", 0)) + 1
        e["last_fail"] = {"date": day, "code": code}
        e["last"] = "fail"
    data[key] = e
    try:
        _save_status(root, data)
    except OSError:
        pass   # 성적은 보조다 — 쓰지 못해도 본 명령 결과는 그대로 낸다
    return prev


def reset_status(root: Path, key: str) -> None:
    """방법을 바꿨으면 옛 성적은 의미가 없다 (access set/unset 때)."""
    data = load_status(root)
    if key in data:
        del data[key]
        try:
            _save_status(root, data)
        except OSError:
            pass
