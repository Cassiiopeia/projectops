"""Repo harness: STYLE.md, characters, image kinds, reference images > status, scaffold, kind guide lookup
Kind guides: repo kinds/ overrides the skill defaults (references/kinds) by same name
"""
from __future__ import annotations

from pathlib import Path

STYLE_FILE = "STYLE.md"
CHARACTERS_DIR = "characters"
KINDS_DIR = "kinds"
REFERENCES_DIR = "refs"
HISTORY_FILE = "history.jsonl"
# Skill default kind guides: scripts/pro_image/ > ../../references/kinds
BUILTIN_KINDS_DIR = Path(__file__).resolve().parents[2] / "references" / "kinds"
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")

STYLE_SKELETON = """# {project} art guide

> Read by the agent before every image request. Keep it short and concrete. The agent updates it when the user
> approves or rejects a result for a reason that applies to future images.

## Look
- Medium and style: (e.g. anime watercolor with thin ink lines / flat vector / pixel art 32px / 3D clay)
- Line and shading:
- Palette: (main colors with hex if known; saturation level; what to avoid)
- Lighting:

## Reference images
- refs/<file>: what it is the reference for (style, a character's face, a palette)

## Layout rules for this app
- (e.g. bottom third stays empty for the dialogue box; icons keep 10% padding)

## Never
- Text, logos, watermarks, signatures, frames
- Mixing styles; photo-real or 3D unless the look says so
- Drawing with code (SVG, PIL, canvas). Images come from the image model only
"""

CHARACTER_SKELETON = """# {name}

- Role:
- Fixed look (same in every image): age, hair, eyes, face, body
- Default outfit:
- Reference: refs/<sheet or face image>
- Expressions already made:
"""


def _names(folder: Path, suffixes: tuple[str, ...]) -> list[str]:
    if not folder.is_dir():
        return []
    return sorted(path.name for path in folder.iterdir() if path.suffix.lower() in suffixes)


def kinds(harness: Path) -> list[dict]:
    """Kind guide list: defaults + repo (repo wins on same name)"""
    by_name = {path.stem: {"kind": path.stem, "source": "builtin", "path": str(path)}
               for path in sorted(BUILTIN_KINDS_DIR.glob("*.md"))}
    for path in sorted((harness / KINDS_DIR).glob("*.md")):
        by_name[path.stem] = {"kind": path.stem, "source": "repo", "path": str(path)}
    return list(by_name.values())


def find_kind(harness: Path, kind: str) -> dict | None:
    return next((entry for entry in kinds(harness) if entry["kind"] == kind), None)


def describe(harness: Path) -> dict:
    style = harness / STYLE_FILE
    return {
        "harness_dir": str(harness),
        "exists": harness.is_dir(),
        "style": str(style) if style.is_file() else None,
        "characters": [str(harness / CHARACTERS_DIR / name) for name in _names(harness / CHARACTERS_DIR, (".md",))],
        "references": [str(harness / REFERENCES_DIR / name) for name in _names(harness / REFERENCES_DIR, IMAGE_SUFFIXES)],
        "kinds": kinds(harness),
        "history": str(harness / HISTORY_FILE) if (harness / HISTORY_FILE).is_file() else None,
    }


def initialize(harness: Path, project_name: str, character_names: list[str]) -> list[str]:
    """Create scaffold (never overwrites existing files) > list of newly created paths"""
    created = []
    for folder in (harness, harness / CHARACTERS_DIR, harness / KINDS_DIR, harness / REFERENCES_DIR):
        if not folder.is_dir():
            folder.mkdir(parents=True)
            created.append(str(folder))
    targets = [(harness / STYLE_FILE, STYLE_SKELETON.format(project=project_name))]
    targets += [(harness / CHARACTERS_DIR / f"{name}.md", CHARACTER_SKELETON.format(name=name))
                for name in character_names]
    for path, content in targets:
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            created.append(str(path))
    return created
