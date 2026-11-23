"""Existing notes in the knowledge folder: flat frontmatter, issue/PR/commit references, last capture point, related notes
Works on any vault layout (pro-brain default notes or a repo's own schema such as ISS-/DEC- ids); reads files only.
"""
from __future__ import annotations

import re
from pathlib import Path

from .repo_facts import GitError, _to_scalar, parse_flow_list, run_git

# Files that index or log the vault rather than hold one piece of knowledge
NON_NOTE_NAMES = {"readme.md", "index.md", "log.md"}
RELATED_LIMIT = 5              # related note suggestions kept
EXISTING_TOPIC_LIMIT = 30      # most used topics echoed so new notes reuse the same tags
RANGE_NOTE_LIMIT = 200         # newest notes whose commit range is expanded for gap coverage
# Hex token 7-40 chars with at least one digit and one letter: a commit sha mentioned in prose
SHA_TOKEN = re.compile(r"\b(?=[0-9a-f]*\d)(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}\b")


def iter_note_files(knowledge_folder: Path):
    """*.md under the folder, skipping templates and tool folders (_templates, .obsidian) and index/log files"""
    if not knowledge_folder.is_dir():
        return
    for path in sorted(knowledge_folder.rglob("*.md")):
        relative_parts = path.relative_to(knowledge_folder).parts
        if any(part.startswith(("_", ".")) for part in relative_parts[:-1]) or path.name.lower() in NON_NOTE_NAMES:
            continue
        yield path


def read_frontmatter(text: str) -> dict:
    """Leading '---' block > flat {key: scalar | list}; nested or multi-line values are ignored"""
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    result = {}
    for line in text[3:end].splitlines():
        match = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if not match:
            continue
        raw = match.group(2).strip()
        result[match.group(1)] = parse_flow_list(raw) if raw.startswith("[") else _to_scalar(raw)
    return result


def _first_heading(text: str) -> str | None:
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def _int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def read_note(path: Path, knowledge_folder: Path, remote_slug: str | None) -> dict:
    """One note > id, title, topics, modules, files and the issues, PRs and commits it refers to"""
    text = path.read_text(encoding="utf-8", errors="replace")
    frontmatter = read_frontmatter(text)
    slug_pattern = re.escape(remote_slug) if remote_slug else r"[^/\s]+/[^/\s]+"
    issues = {int(number) for number in re.findall(rf"github\.com/{slug_pattern}/issues/(\d+)", text, re.IGNORECASE)}
    issues |= {int(number) for number in re.findall(r"^#\s.*?\(#(\d+)\)", text, re.MULTILINE)}
    issues |= {int(number) for number in re.findall(r"^#\s+#(\d+)\b", text, re.MULTILINE)}
    pulls = {int(number) for number in re.findall(rf"github\.com/{slug_pattern}/pull/(\d+)", text, re.IGNORECASE)}
    for key, bucket in (("issue", issues), ("pr", pulls)):
        number = _int_or_none(frontmatter.get(key))
        if number:
            bucket.add(number)
    shas = set(SHA_TOKEN.findall(text.lower()))
    return {
        "path": path.relative_to(knowledge_folder).as_posix(),
        "id": frontmatter.get("id") or path.stem,
        "title": frontmatter.get("title") or _first_heading(text) or path.stem,
        "captured_by": frontmatter.get("captured_by"),
        "captured_at": str(frontmatter.get("captured_at") or frontmatter.get("created") or ""),
        "topics": parse_flow_list(frontmatter.get("topics") or frontmatter.get("tags") or []),
        "changed_modules": parse_flow_list(frontmatter.get("changed_modules") or []),
        "main_files": parse_flow_list(frontmatter.get("main_files") or []),
        "commit_base": frontmatter.get("commit_base"),
        "commit_head": frontmatter.get("commit_head"),
        "issues": issues,
        "pulls": pulls,
        "shas": shas,
    }


def scan_notes(knowledge_folder: Path, remote_slug: str | None) -> list[dict]:
    return [read_note(path, knowledge_folder, remote_slug) for path in iter_note_files(knowledge_folder)]


def existing_topics(notes: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    for note in notes:
        for topic in note["topics"]:
            counts[topic] = counts.get(topic, 0) + 1
    return sorted(counts, key=lambda topic: (-counts[topic], topic))[:EXISTING_TOPIC_LIMIT]


def last_captured_head(repo_root: Path, notes: list[dict], head: str) -> str | None:
    """Newest pro-brain note whose commit_head is an ancestor of head: where the next change set starts"""
    ranged = [note for note in notes if note["commit_head"]]
    for note in sorted(ranged, key=lambda item: item["captured_at"], reverse=True):
        try:
            run_git(repo_root, "merge-base", "--is-ancestor", str(note["commit_head"]), head)
            return str(note["commit_head"])
        except GitError:
            continue
    return None


def covered_commits(repo_root: Path, notes: list[dict]) -> set[str]:
    """Full shas inside the commit ranges of the newest notes that record one"""
    ranged = sorted((note for note in notes if note["commit_base"] and note["commit_head"]),
                    key=lambda item: item["captured_at"], reverse=True)[:RANGE_NOTE_LIMIT]
    covered: set[str] = set()
    for note in ranged:
        try:
            covered.update(run_git(repo_root, "rev-list", f"{note['commit_base']}..{note['commit_head']}").split())
        except GitError:
            continue
    return covered


def related_notes(notes: list[dict], modules: list[str], files: list[str], topic_hints: list[str]) -> list[dict]:
    """Notes sharing modules, files or topics with this change, best first (no LLM: plain overlap counts)"""
    module_set, file_set, topic_set = set(modules), set(files), set(topic_hints)
    scored = []
    for note in notes:
        score = (2 * len(file_set & set(note["main_files"])) + len(module_set & set(note["changed_modules"]))
                 + len(topic_set & set(note["topics"])))
        if score:
            scored.append((score, note["captured_at"], note))
    # Higher score first, newer note first on ties
    scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [{"id": note["id"], "title": note["title"], "path": note["path"], "score": score}
            for score, _, note in scored[:RELATED_LIMIT]]
