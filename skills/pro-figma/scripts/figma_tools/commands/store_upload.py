"""store-upload-plan · store-upload-mark · store-upload-status: 스토어 콘솔 업로드 체크리스트 (#1021)

업로드 자체는 하지 않는다 — 에이전트가 pro-launch web 으로 콘솔에 올리고, 단계마다 여기에 기록한다.
체크리스트: store-check 가 ready 인 폴더 > 스토어 x 언어 x 슬롯 항목 (파일 순서 · 상태 · 시각)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from common.emit import emit
from figma_tools.commands.store import check_store_folder
from figma_tools.store_check import GLOBAL_LOCALE

CHECKLIST_FILE_NAME = "upload_checklist.json"
# 항목 상태 4개: pending 미착수 > uploaded 콘솔에 파일 올림 > saved 임시저장 완료 > verified 저장 후 다시 열어 장수 확인
UPLOAD_STATUSES = ("pending", "uploaded", "saved", "verified")
UPLOAD_TAB_NAME = "store-upload"
# 누르면 심사 제출·출시로 이어지는 버튼 (사용자 명시 승인 없이는 누르지 않음)
NEVER_CLICK_LABELS = (
    "Add for Review", "Submit for Review", "Submit to App Review", "Resubmit to App Review",
    "Send for review", "Send changes for review", "Start rollout", "Publish", "Release",
)
STORE_CONSOLES = {
    "ios": {"name": "App Store Connect", "url": "https://appstoreconnect.apple.com/apps",
            "where": "the app's version page > the locale > Previews and Screenshots"},
    "play": {"name": "Google Play Console", "url": "https://play.google.com/console",
             "where": "the app > Store presence > Store listings > the locale > Graphics"},
}


def _output_root_error(folder: Path, project_root: Path) -> dict | None:
    """쓰기 위치가 산출물 루트 안인지 확인. 밖이면 에러 응답"""
    try:
        from common.paths import resolve_output_root
    except ImportError:
        return {"ok": False, "code": "common_not_found", "error": "scripts/common/paths.py not found",
                "hint": "Check that the projectops installation is intact"}
    output_root = resolve_output_root(project_root).resolve()
    try:
        folder.relative_to(output_root)
        return None
    except ValueError:
        return {"ok": False, "code": "dir_outside_output_root",
                "error": f"The checklist is written next to --dir, which must be inside {output_root}",
                "hint": "Keep store images in the run_dir from get-output-path (store-compose writes <run_dir>/store/images)"}


def _item_key(store: str, locale: str, slot: str) -> str:
    return f"{store}/{locale}/{slot}"


def _upload_command(files: list[str]) -> str:
    return (f"LAUNCH_TAB={UPLOAD_TAB_NAME} launch_cli.py web upload --files {','.join(files)} "
            "--click-ref <ref of the slot's drop zone from web find>")


def _build_items(report: dict, images_dir: Path) -> list:
    """matrix(ok 칸) > 업로드 항목. 파일은 이름 순 = 콘솔 표시 순서"""
    items = []
    for store, locales in report["matrix"].items():
        for locale, slots in locales.items():
            for slot, cell in slots.items():
                if cell.get("status") != "ok":
                    continue
                files = sorted(str(images_dir / entry["file"]) for entry in cell.get("files", []))
                items.append({"key": _item_key(store, locale, slot), "store": store, "locale": locale,
                              "slot": slot, "global": locale == GLOBAL_LOCALE, "count": len(files),
                              "files": files, "status": "pending", "updated_at": None, "note": None,
                              "upload_command": _upload_command(files)})
    return items


def _carry_progress(new_items: list, checklist_path: Path) -> int:
    """이전 체크리스트에서 같은 항목·같은 파일이면 진행 상태 유지 > 유지한 항목 수"""
    try:
        previous = json.loads(checklist_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    previous_by_key = {item.get("key"): item for item in previous.get("items", []) if isinstance(item, dict)}
    carried = 0
    for item in new_items:
        old = previous_by_key.get(item["key"])
        if old and old.get("files") == item["files"] and old.get("status") in UPLOAD_STATUSES:
            item.update(status=old["status"], updated_at=old.get("updated_at"), note=old.get("note"))
            carried += old["status"] != "pending"
    return carried


def _progress(items: list) -> dict:
    counts = {status: 0 for status in UPLOAD_STATUSES}
    for item in items:
        counts[item.get("status", "pending")] = counts.get(item.get("status", "pending"), 0) + 1
    return counts


def _next_item(items: list) -> dict | None:
    """다음 작업: verified 가 아닌 첫 항목"""
    return next((item for item in items if item["status"] != "verified"), None)


def _next_hint(item: dict | None, checklist_path: Path) -> str:
    if item is None:
        return ("Every item is verified. Post final_report to the issue with pro-github. "
                "Submitting for review is the user's call; do not press any never_click button")
    step = {"pending": f"upload the files: {item['upload_command']}",
            "uploaded": "press the console's Save (draft) button, wait for the saved message",
            "saved": "reload the page and confirm the slot shows exactly the planned count"}[item["status"]]
    following = UPLOAD_STATUSES[UPLOAD_STATUSES.index(item["status"]) + 1]
    return (f"{item['key']}: {step}, then store-upload-mark --checklist {checklist_path} "
            f"--key {item['key']} --status {following}")


def _final_report(items: list) -> list:
    return [{"key": item["key"], "count": item["count"], "status": item["status"],
             "updated_at": item["updated_at"]} for item in items]


def _write_checklist(path: Path, checklist: dict) -> None:
    path.write_text(json.dumps(checklist, ensure_ascii=False, indent=2), encoding="utf-8")


def cmd_store_upload_plan(args) -> int:
    """store-check ready 확인 > 항목 생성 (이전 진행 유지) > upload_checklist.json"""
    images_dir = Path(args.dir).resolve()
    project_root = Path(args.root).resolve()
    error = _output_root_error(images_dir, project_root)
    if error:
        return emit(error)
    report = check_store_folder(args.dir, args.locales, args.root)
    if report.get("ok") is False:
        return emit(report)
    if report["verdict"] != "ready":
        return emit({"ok": False, "code": "not_ready",
                     "error": f"store-check verdict is {report['verdict']}; upload only images that pass",
                     "issues": report["issues"], "next": f"store-check --dir {images_dir}, fix issues, then plan again"})

    checklist_path = Path(args.out).resolve() if args.out else images_dir.parent / CHECKLIST_FILE_NAME
    error = _output_root_error(checklist_path.parent, project_root)
    if error:
        return emit(error)
    items = _build_items(report, images_dir)
    carried = _carry_progress(items, checklist_path)
    stores = sorted({item["store"] for item in items})
    checklist = {"images_dir": str(images_dir), "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                 "locales": report["locales"], "items": items}
    try:
        _write_checklist(checklist_path, checklist)
    except OSError as os_error:
        return emit({"ok": False, "code": "write_failed", "error": str(os_error)})
    return emit({
        "verdict": "planned",
        "summary": f"{len(items)} upload item(s) in {', '.join(stores)} · {carried} kept from the earlier checklist",
        "next": _next_hint(_next_item(items), checklist_path),
        "checklist": str(checklist_path),
        "consoles": {store: STORE_CONSOLES[store] for store in stores if store in STORE_CONSOLES},
        "browser": (f"Use your own tab (LAUNCH_TAB={UPLOAD_TAB_NAME}) in a normal, not --readonly, web open; "
                    "sign in with web login and hand two-factor prompts to the user"),
        "never_click": list(NEVER_CLICK_LABELS),
        "progress": _progress(items),
        "items": [{key: item[key] for key in ("key", "count", "status")} for item in items],
        "warnings": report["warnings"],
    })


def _load_checklist(path_arg: str) -> tuple[Path, dict | None, dict | None]:
    path = Path(path_arg).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as read_error:
        return path, None, {"ok": False, "code": "checklist_unreadable", "error": str(read_error),
                            "hint": "Create it with store-upload-plan --dir <images dir>"}
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return path, None, {"ok": False, "code": "checklist_invalid", "error": "items list missing"}
    return path, data, None


def cmd_store_upload_mark(args) -> int:
    """항목 1개 상태 기록 (단계마다 바로 저장 — 중간에 끊겨도 어디까지 했는지 남는다)"""
    path, data, error = _load_checklist(args.checklist)
    if error:
        return emit(error)
    item = next((entry for entry in data["items"] if entry.get("key") == args.key), None)
    if item is None:
        return emit({"ok": False, "code": "item_not_found", "error": f"No item {args.key}",
                     "keys": [entry.get("key") for entry in data["items"]]})
    before = item.get("status")
    item.update(status=args.status, updated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
                note=args.note if args.note is not None else item.get("note"))
    try:
        _write_checklist(path, data)
    except OSError as os_error:
        return emit({"ok": False, "code": "write_failed", "error": str(os_error)})
    return emit({"summary": f"{args.key}: {before} -> {args.status}",
                 "next": _next_hint(_next_item(data["items"]), path),
                 "progress": _progress(data["items"])})


def cmd_store_upload_status(args) -> int:
    """진행 현황 + 최종 보고 표 (스토어 x 언어 x 슬롯, 장수, 상태)"""
    path, data, error = _load_checklist(args.checklist)
    if error:
        return emit(error)
    items = data["items"]
    progress = _progress(items)
    is_done = bool(items) and progress["verified"] == len(items)
    return emit({"verdict": "done" if is_done else "in_progress",
                 "summary": f"{progress['verified']}/{len(items)} verified",
                 "next": _next_hint(_next_item(items), path),
                 "progress": progress, "final_report": _final_report(items),
                 "never_click": list(NEVER_CLICK_LABELS)})
