"""`web upload` — 파일 입력(숨은 것 포함)에 파일을 넣거나, 눌러서 뜬 파일 선택 창에 답한다 (#876).

드롭존 뒤에 숨은 <input type=file> 은 find·click 으로 못 채운다. 바꾸는 조작이라 읽기 전용 세션에서는 막는다.
순서: 파일 검사(있나 · 허용 폴더 안인가) > 읽기 전용 막기 > 대상 고르기 > accept · multiple 검사 > 넣기 > 들어간 것 읽기
"""
from __future__ import annotations

import argparse
import mimetypes
from pathlib import Path

from pro_launch.commands.web.element import is_timeout_error, locate_target, outcome_wait_seconds, target_wait_seconds
from pro_launch.registry import Action
from pro_launch.runtime.context import project_root
from pro_launch.runtime.shots import shot_folder

# --selector · --ref 가 없을 때 고르는 파일 입력
DEFAULT_FILE_INPUT_SELECTOR = "input[type=file]"
FILE_LIST_DELIMITER = ","

# 파일 입력의 accept · multiple · 지금 들어간 파일 이름
FILE_INPUT_JS = """(e) => ({ is_file_input: e.tagName === 'INPUT' && (e.type || '').toLowerCase() === 'file',
  accept: e.getAttribute('accept'), multiple: !!e.multiple,
  files: e.files ? [...e.files].map(f => f.name) : [] })"""


def allowed_folders(root: Path) -> list[Path]:
    """올릴 파일을 둘 수 있는 곳: 작업 폴더 · 프로젝트 루트 · 이번 실행 폴더($SHOT_DIR)"""
    folders = [Path.cwd().resolve(), root.resolve(), shot_folder(root).resolve()]
    return list(dict.fromkeys(folders))


def resolve_upload_files(raw: str, root: Path) -> tuple[list[Path], dict | None]:
    """--files 쉼표 목록 > 실제 경로. 없거나 허용 폴더 밖이면 (빈 목록, 실패 결과)"""
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
    """accept 속성(.png · image/* · image/png 쉼표 목록)이 이 파일을 받나. accept 가 없으면 전부 받는다"""
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
    """입력이 받을 수 있는 파일인가 (개수 · 종류). 맞으면 None"""
    if len(paths) > 1 and not is_multiple:
        return {"ok": False, "code": "multiple_not_allowed", "files": [p.name for p in paths],
                "error": "This input takes only one file (not multiple)", "next": "Upload the files one at a time"}
    rejected = [p.name for p in paths if not is_type_accepted(p, accept)]
    if rejected:
        return {"ok": False, "code": "type_not_accepted", "rejected": rejected, "accepted": accept,
                "error": f"Files not allowed by accept='{accept}': {', '.join(rejected)}"}
    return None


def _upload_via_chooser(page, args, state: dict, paths: list[Path]) -> dict:
    """--click-ref 를 눌러 뜬 파일 선택 창에 답한다"""
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
    chooser.set_files([str(p) for p in paths])
    after = chooser.element.evaluate(FILE_INPUT_JS)
    return _uploaded_payload(page, paths, after, info, via="file_chooser")


def _upload_into_input(page, args, state: dict, paths: list[Path]) -> dict:
    """파일 입력에 바로 넣는다. 숨은 입력도 된다"""
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
    element.set_input_files([str(p) for p in paths], timeout=target_wait_seconds(args) * 1000)
    after = element.evaluate(FILE_INPUT_JS)
    return _uploaded_payload(page, paths, after, info, via="input")


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
    # 파일을 올리는 것 자체가 바꾸는 조작이다 — 버튼 문구와 상관없이 막는다
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
