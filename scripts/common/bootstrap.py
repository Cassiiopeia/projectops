"""sys.path bootstrap helper.

Each _cli.py adjusts sys.path itself on its first line, so
this module is only an aid for tests and debugging.
"""
from pathlib import Path
from typing import Optional


def find_scripts_root(start: Path) -> Optional[Path]:
    """Walk up from start looking for 'scripts/common/__init__.py'.

    Returns the 'scripts/' path if found, else None.
    """
    cur = start.resolve()
    for _ in range(10):
        candidate = cur / "scripts" / "common" / "__init__.py"
        if candidate.exists():
            return cur / "scripts"
        if cur.parent == cur:
            return None
        cur = cur.parent
    return None
