"""One note file for write: frontmatter id > stable brain slug, issue number, content (read once, never modified)
Slug: pro-brain/<project>/<note id>, so writing the same note again updates the same page in every brain.
"""
from __future__ import annotations

import re
from pathlib import Path

from .notes import read_frontmatter

SLUG_PREFIX = "pro-brain"
SLUG_PART = re.compile(r"[^a-z0-9._-]+")
ISSUE_ID = re.compile(r"^issue-(\d+)$", re.IGNORECASE)
MAX_NOTE_BYTES = 256_000   # one put_page request; bigger notes break the note format anyway


class NoteError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def slug_part(value: str) -> str:
    return SLUG_PART.sub("-", str(value).strip().lower()).strip("-.") or "note"


def project_prefix(project: str) -> str:
    return f"{SLUG_PREFIX}/{slug_part(project)}/"


def note_slug(project: str, note_id: str) -> str:
    return project_prefix(project) + slug_part(note_id)


def issue_from_slug(slug: str) -> int | None:
    match = ISSUE_ID.match(slug.rsplit("/", 1)[-1])
    return int(match.group(1)) if match else None


def load_note(path_text: str, project: str, id_override: str | None = None) -> dict:
    """Note file > {path, content, id, title, slug, issue, file_name}; NoteError when unusable"""
    path = Path(path_text).expanduser()
    if not path.is_file():
        raise NoteError("note_missing", f"note file not found: {path}")
    raw = path.read_bytes()
    if len(raw) > MAX_NOTE_BYTES:
        raise NoteError("note_too_large", f"note is {len(raw)} bytes (limit {MAX_NOTE_BYTES}): keep it compact")
    # utf-8-sig: Windows editors and PowerShell 5.1 prefix a BOM that would hide the frontmatter
    content = raw.decode("utf-8-sig", errors="replace")
    frontmatter = read_frontmatter(content)
    note_id = id_override or frontmatter.get("id")
    if not note_id:
        raise NoteError("note_without_id", "the note has no frontmatter id: add id (for example issue-123) or pass --id")
    issue = frontmatter.get("issue")
    issue = int(issue) if isinstance(issue, int) or (isinstance(issue, str) and issue.isdigit()) else None
    title = frontmatter.get("title") or next((line[2:].strip() for line in content.splitlines() if line.startswith("# ")), None)
    return {"path": str(path.resolve()), "content": content, "id": str(note_id), "title": title,
            "slug": note_slug(project, str(note_id)), "issue": issue or issue_from_slug(str(note_id)),
            "file_name": path.name, "bytes": len(raw)}
