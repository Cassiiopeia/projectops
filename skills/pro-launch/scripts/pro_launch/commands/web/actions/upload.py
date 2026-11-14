"""`web upload` — put files into a file input (hidden ones too), or answer the file chooser opened by a press (#876).

An <input type=file> hidden behind a dropzone cannot be filled via find or click. It is a changing action, so read-only sessions block it.
Order: check files (exist · inside allowed folders) > block in read-only > pick target > check accept · multiple > set > read what went in
"""
from __future__ import annotations

import argparse
import mimetypes
import uuid
from pathlib import Path

from pro_launch.commands.web.element import is_timeout_error, locate_target, outcome_wait_seconds, target_wait_seconds
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.shots import shot_folder

# File input picked when there is no --selector · --ref
DEFAULT_FILE_INPUT_SELECTOR = "input[type=file]"
FILE_LIST_DELIMITER = ","
# Total size Playwright can pass to a CDP-attached browser (50MB; beyond that, the CDP path)
PLAYWRIGHT_REMOTE_TRANSFER_LIMIT_BYTES = 50 * 1024 * 1024
PLAYWRIGHT_TRANSFER_LIMIT_ERROR = "Cannot transfer files larger than"
# Marker attribute briefly added to find the target node over CDP
CDP_UPLOAD_MARK_ATTRIBUTE = "data-pro-launch-upload"

# A file input's accept · multiple · names of files currently set
FILE_INPUT_JS = """(e) => ({ is_file_input: e.tagName === 'INPUT' && (e.type || '').toLowerCase() === 'file',
  accept: e.getAttribute('accept'), multiple: !!e.multiple,
  files: e.files ? [...e.files].map(f => f.name) : [] })"""


def allowed_folders(root: Path) -> list[Path]:
    """Where files to upload may live: working folder · project root · this run's folder ($SHOT_DIR)"""
    folders = [Path.cwd().resolve(), root.resolve(), shot_folder(root).resolve()]
    return list(dict.fromkeys(folders))


def resolve_upload_files(raw: str, root: Path) -> tuple[list[Path], dict | None]:
    """--files comma list > real paths. If missing or outside allowed folders, (empty list, failure result)"""
    names = [name.strip() for name in (raw or "").split(FILE_LIST_DELIMITER) if name.strip()]
    if not names:
        return [], {"ok": False, "code": "files_required", "error": "Give the files to upload in --files"}
    folders = allowed_folders(root)
    paths = []
    for name in names:
        path = Path(name).expanduser().resolve()
        if not path.is_file():
            return [], {"ok": False, "code": "file_not_found", "file": name, "error": f"File not found: {name}"}
        if not any(path.is_relative_to(folder) for folder in folders):
            return [], {"ok": False, "code": "file_outside_allowed", "file": name,
                        "allowed": [str(folder) for folder in folders],
                        "error": f"{name} is outside the working folder, project and run folder",
                        "next": "Move the file into the working folder or $SHOT_DIR, then call again"}
        paths.append(path)
    return paths, None


def is_type_accepted(path: Path, accept: str | None) -> bool:
    """Does the accept attribute (comma list of .png · image/* · image/png) take this file? No accept takes everything"""
    tokens = [token.strip().lower() for token in (accept or "").split(",") if token.strip()]
    if not tokens:
        return True
    suffix = path.suffix.lower()
    mime = (mimetypes.guess_type(path.name)[0] or "").lower()
    for token in tokens:
        if token.startswith(".") and token == suffix:
            return True
        if token.endswith("/*") and mime.startswith(token[:-1]):
            return True
        if token == mime:
            return True
    return False


def check_files_fit(paths: list[Path], accept: str | None, is_multiple: bool) -> dict | None:
    """Can the input take these files (count · type)? None if they fit"""
    if len(paths) > 1 and not is_multiple:
        return {"ok": False, "code": "multiple_not_allowed", "files": [p.name for p in paths],
                "error": "This input takes only one file (not multiple)", "next": "Upload the files one at a time"}
    rejected = [p.name for p in paths if not is_type_accepted(p, accept)]
    if rejected:
        return {"ok": False, "code": "type_not_accepted", "rejected": rejected, "accepted": accept,
                "error": f"Files not allowed by accept='{accept}': {', '.join(rejected)}"}
    return None


def _upload_via_chooser(page, args, state: dict, paths: list[Path]) -> dict:
    """Press --click-ref and answer the file chooser that opens"""
    click_args = argparse.Namespace(**{**vars(args), "ref": args.click_ref, "selector": None})
    element, info, failure = locate_target(page, click_args, state, "upload", should_guard_mutating=False)
    if failure:
        return failure
    try:
        with page.expect_file_chooser(timeout=outcome_wait_seconds(args) * 1000) as chooser_info:
            element.click(timeout=target_wait_seconds(args) * 1000)
        chooser = chooser_info.value
    except Exception as error:
        if not is_timeout_error(error):
            raise
        return {"ok": False, "code": "file_chooser_not_opened", "action": "upload", "clicked": info,
                "error": "Clicked, but no file chooser opened",
                "next": "web upload --files <file>  # put it straight into the hidden input[type=file]"}
    input_state = chooser.element.evaluate(FILE_INPUT_JS)
    failure = check_files_fit(paths, input_state["accept"], chooser.is_multiple())
    if failure:
        return failure | {"action": "upload"}
    via = _set_files(page, chooser.element, paths, chooser.set_files, "file_chooser")
    if isinstance(via, dict):
        return via | {"clicked": info}
    after = chooser.element.evaluate(FILE_INPUT_JS)
    return _uploaded_payload(page, paths, after, info, via=via)


def _upload_into_input(page, args, state: dict, paths: list[Path]) -> dict:
    """Set files directly on the file input. Works on hidden inputs too"""
    if args.selector is None and args.ref is None:
        args.selector = DEFAULT_FILE_INPUT_SELECTOR
    element, info, failure = locate_target(page, args, state, "upload", should_guard_mutating=False)
    if failure:
        return failure
    input_state = element.evaluate(FILE_INPUT_JS)
    if not input_state["is_file_input"]:
        return {"ok": False, "code": "not_a_file_input", "action": "upload", "target": info,
                "error": "The target is not an <input type=file>",
                "next": "web upload --files <file> --click-ref <dropzone ref>  # answer the chooser that opens on click"}
    failure = check_files_fit(paths, input_state["accept"], input_state["multiple"])
    if failure:
        return failure | {"action": "upload"}
    timeout_milliseconds = target_wait_seconds(args) * 1000
    via = _set_files(page, element, paths,
                     lambda files: element.set_input_files(files, timeout=timeout_milliseconds), "input")
    if isinstance(via, dict):
        return via | {"target": info}
    after = element.evaluate(FILE_INPUT_JS)
    return _uploaded_payload(page, paths, after, info, via=via)


def _set_files(page, element, paths: list[Path], playwright_set_files, via: str) -> str | dict:
    """Set files: Playwright up to 50MB > CDP directly when larger or on a transfer limit error (#1008). Path names on success, result on failure"""
    files = [str(p) for p in paths]
    if sum(p.stat().st_size for p in paths) <= PLAYWRIGHT_REMOTE_TRANSFER_LIMIT_BYTES:
        try:
            playwright_set_files(files)
            return via
        except Exception as error:
            if PLAYWRIGHT_TRANSFER_LIMIT_ERROR not in str(error):
                raise
    try:
        _set_files_over_cdp(page, element, files)
        return "cdp"
    except Exception as error:  # noqa: BLE001 — failure of the fallback path is reported as a result
        return {"ok": False, "code": "file_too_large_for_transfer", "action": "upload",
                "bytes": sum(p.stat().st_size for p in paths),
                "error": f"Files over 50MB could not be set over CDP: {str(error)[:200]}",
                "next": "Upload a smaller file (50MB or less), or put the input in the top page (not a cross-origin frame) and call again"}


def _set_files_over_cdp(page, element, files: list[str]) -> None:
    """Set local paths as is via CDP DOM.setFileInputFiles (bypasses Playwright's 50MB transfer limit, #1008)
    Target node: temporary marker attribute > DOM.performSearch > nodeId (up to same-process frames)"""
    mark = uuid.uuid4().hex
    element.evaluate(f"(e, mark) => e.setAttribute('{CDP_UPLOAD_MARK_ATTRIBUTE}', mark)", mark)
    session = page.context.new_cdp_session(page)
    try:
        session.send("DOM.getDocument", {"depth": -1, "pierce": True})
        search = session.send("DOM.performSearch", {"query": f'[{CDP_UPLOAD_MARK_ATTRIBUTE}="{mark}"]'})
        try:
            if not search.get("resultCount"):
                raise RuntimeError("file input not reachable from the page's CDP session")
            node_ids = session.send("DOM.getSearchResults", {"searchId": search["searchId"],
                                                             "fromIndex": 0, "toIndex": 1})["nodeIds"]
        finally:
            session.send("DOM.discardSearchResults", {"searchId": search["searchId"]})
        session.send("DOM.setFileInputFiles", {"files": files, "nodeId": node_ids[0]})
    finally:
        # Remove the marker attribute (success or failure)
        try:
            element.evaluate(f"(e) => e.removeAttribute('{CDP_UPLOAD_MARK_ATTRIBUTE}')")
        except Exception:  # noqa: BLE001
            pass
        session.detach()


def _uploaded_payload(page, paths: list[Path], after: dict, target: dict | None, via: str) -> dict:
    return {"action": "upload", "via": via, "target": target,
            "uploaded": [{"name": p.name, "bytes": p.stat().st_size} for p in paths],
            "input_files": after["files"], "accepted": after["accept"], "multiple": after["multiple"],
            "url": page.url, "summary": f"Put {len(paths)} files ({via})",
            "next": "web wait --gone \"Uploading\"  # or check with web text that it went up"}


def execute(page, args, state: dict) -> dict:
    paths, failure = resolve_upload_files(args.files, project_root(args))
    if failure:
        return failure | {"action": "upload"}
    # Uploading a file is itself a changing action — block it regardless of button text
    if state.get("readonly") and not args.confirm_mutating:
        return {"ok": False, "code": "mutating_blocked", "action": "upload", "url": page.url,
                "error": "Read-only session, so the files were not uploaded",
                "next": "If it really must happen, tell the user what will be uploaded, get approval, then add --confirm-mutating"}
    if args.click_ref is not None:
        return _upload_via_chooser(page, args, state, paths)
    return _upload_into_input(page, args, state, paths)


def configure(p) -> None:
    p.add_argument("--files", required=True, help="Comma-separated files to upload (inside the working folder, project or $SHOT_DIR)")
    p.add_argument("--click-ref", dest="click_ref", type=int, default=None,
                   help="Click this ref and answer the file chooser that opens (dropzone)")


ACTION = Action(name="upload", run=execute, configure=configure,
                options=("selector", "ref", "target_timeout", "confirm_mutating", "frame"),
                help="Put files into a file input (hidden ones too) or into the chooser opened by a click",
                example="web upload --files shots/a.png,shots/b.png")
