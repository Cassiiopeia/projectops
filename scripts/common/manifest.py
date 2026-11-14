"""Read and write .cursor/skills/MANIFEST.json."""

import json
from pathlib import Path
from typing import Any, Optional

MANIFEST_PATH = Path(".cursor") / "skills" / "MANIFEST.json"


def read(project_root: Any) -> Optional[dict]:
    """Read MANIFEST.json and return a dict. None if missing."""
    path = Path(project_root) / MANIFEST_PATH
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write(project_root: Any, data: dict) -> None:
    """Save data to MANIFEST.json. Creates the parent directory if missing."""
    path = Path(project_root) / MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
