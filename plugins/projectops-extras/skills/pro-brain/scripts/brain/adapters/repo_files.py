"""repo-files adapter: notes as markdown in the repo's knowledge folder, committed with the work by pro-commit (never here)"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from ..repo_facts import GitError, path_tracking_state, run_git
from .base import Adapter, check, write_result


class RepoFilesAdapter(Adapter):
    kind = "repo-files"

    def _folder(self) -> Path:
        return self.context["root"] / self.destination.get("path", "knowledge/")

    def detect(self) -> dict:
        return {"available": True, "folder": str(self._folder())}

    def doctor(self, quick: bool = False) -> dict:
        folder, root = self._folder(), self.context["root"]
        relative = self.destination.get("path", "knowledge/")
        checks = [check("repo_switch", "ok" if self.context["switch"].get("enabled") else "fail",
                        "knowledge capture is on" if self.context["switch"].get("enabled") else "knowledge capture is off",
                        None if self.context["switch"].get("enabled") else "brain_cli.py setup, then setup --apply --yes --enable",
                        code=None if self.context["switch"].get("enabled") else "switch_off")]
        if folder.is_dir():
            state = path_tracking_state(root, relative)
            checks.append(check("knowledge_folder", "ok" if state != "ignored" else "fail",
                                f"{relative} exists ({state})", "remove the folder from .gitignore so notes are committed"
                                if state == "ignored" else None, code="folder_ignored" if state == "ignored" else None))
        else:
            checks.append(check("knowledge_folder", "warn", f"{relative} does not exist yet", "the first write creates it"))
        return {"checks": checks, "command": f"copy the note to {relative}<note_dir>/<file>, then commit with pro-commit",
                "capabilities": {"write": True, "search": "files"}}

    def target_path(self, note: dict) -> Path:
        switch = self.context["switch"]
        note_dir = switch.get("note_dir") or ("issues/" if note.get("issue") else "changes/")
        return self._folder() / note_dir / note["file_name"]

    def write(self, note: dict) -> dict:
        """Copy into the folder unless the note already lives there; identical content = unchanged"""
        source, target = Path(note["path"]), self.target_path(note)
        relative = target.relative_to(self.context["root"]).as_posix()
        if self._folder().resolve() in source.resolve().parents:
            return write_result(self.destination, "unchanged", f"note already in the folder: {source.name}",
                                path=str(source.relative_to(self.context["root"])) if self.context["root"] in source.parents else str(source),
                                commit="stage this path and commit with pro-commit")
        if target.is_file() and target.read_bytes() == source.read_bytes():
            return write_result(self.destination, "unchanged", f"{relative} already holds this note", path=relative)
        if target.is_file() and not self._is_safe_to_replace(target, relative):
            return write_result(self.destination, "failed", f"{relative} was edited after the last write",
                                path=relative, code="note_edited",
                                fix="merge those edits into the new note, then write that file")
        outcome = "updated" if target.is_file() else "written"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        self._remember_written(relative, target.read_bytes())
        return write_result(self.destination, outcome, f"{outcome} {relative}", path=relative,
                            commit="stage this path and commit with pro-commit")

    def _receipt_path(self, relative: str) -> Path:
        """{state}/pro-brain/written/<hash of repo + path>.json: digest of the last content this adapter wrote"""
        from ..doctor import state_folder
        key = hashlib.sha256(f"{self.context['root']}::{relative}".encode()).hexdigest()[:24]
        return state_folder() / "written" / f"{key}.json"

    def _remember_written(self, relative: str, content: bytes) -> None:
        receipt = self._receipt_path(relative)
        receipt.parent.mkdir(parents=True, exist_ok=True)
        receipt.write_text(json.dumps({"path": relative, "sha256": hashlib.sha256(content).hexdigest()}), encoding="utf-8")

    def _is_safe_to_replace(self, target: Path, relative: str) -> bool:
        """Replace only content nobody edited by hand: equal to HEAD, or equal to what this adapter wrote last"""
        current = target.read_bytes()
        try:
            # Line endings ignored: a Windows checkout may hold CRLF for the same committed text
            committed = run_git(self.context["root"], "show", f"HEAD:{relative}").encode("utf-8")
            if committed.replace(b"\r", b"") == current.replace(b"\r", b""):
                return True
        except (GitError, FileNotFoundError):
            pass
        receipt = self._receipt_path(relative)
        if receipt.is_file():
            recorded = json.loads(receipt.read_text(encoding="utf-8")).get("sha256")
            return recorded == hashlib.sha256(current).hexdigest()
        return False

    def search_hint(self) -> str:
        return f"read {self.destination.get('path', 'knowledge/')} (search by topic, file or issue number)"

    def note_ids(self) -> tuple[set[str] | None, str]:
        return None, "note files (gaps reads the folder itself)"
