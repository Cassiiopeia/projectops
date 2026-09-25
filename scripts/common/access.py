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
