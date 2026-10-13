#!/usr/bin/env python3
"""extras 플러그인용 공유 문서 사본을 정본에서 다시 만든다. 사본을 직접 고치지 말 것."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRAS = ROOT / "plugins" / "projectops-extras"
# (정본, extras 안의 경로) — extras 스킬이 ../references 로 가리키는 것만
COPIES = [
    ("skills/references/config-rules.md", "skills/references/config-rules.md"),
    ("skills/references/preferences.md", "skills/references/preferences.md"),
]

if __name__ == "__main__":
    for src, dst in COPIES:
        target = EXTRAS / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / src, target)
        print(f"synced {dst}")
