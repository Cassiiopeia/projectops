#!/usr/bin/env python3
"""Regenerate the extras plugin's shared copies from their originals. Never edit the copies directly."""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRAS = ROOT / "plugins" / "projectops-extras"
# (original, path inside extras) — what extras skills point to via ../references + the hook runner (#987)
COPIES = [
    ("skills/references/config-rules.md", "skills/references/config-rules.md"),
    ("skills/references/preferences.md", "skills/references/preferences.md"),
    ("skills/references/sensitive-info.md", "skills/references/sensitive-info.md"),   # pro-brain self-review before saving a note
    ("hooks/run_python.sh", "hooks/run_python.sh"),
    ("scripts/common/redact.py", "skills/pro-skill-bug/scripts/bug/redact.py"),   # redaction rules original (extras cannot use common)
    ("scripts/common/proc.py", "skills/pro-remote-link/scripts/tunnel/proc.py"),  # original of the per-OS process liveness check
    ("scripts/common/credentials.py", "skills/pro-brain/scripts/brain/credentials.py"),  # credential store accessor (team brain token, #1265)
]

if __name__ == "__main__":
    for src, dst in COPIES:
        target = EXTRAS / dst
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / src, target)
        shutil.copymode(ROOT / src, target)
        print(f"synced {dst}")
