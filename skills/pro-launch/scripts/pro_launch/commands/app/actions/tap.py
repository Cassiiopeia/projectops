"""`app tap` — 화면 요소를 누른다."""
from __future__ import annotations


import app_input
import node_match

from pro_launch.commands.app.gestures import (backend_for, before_shot, gesture_result, not_found_response,
                                              device_failure_response)
from pro_launch.registry import Action
from pro_launch.runtime.output import out


def _app_tap(args) -> int:
    """화면 요소를 누른다. --text / --id / --desc 로 찾고, 요소가 없는 화면(캔버스·지도)만 --at 비율."""
    sel = next(((f, getattr(args, f"sel_{f}")) for f in app_input.SELECTOR_FIELDS
                if getattr(args, f"sel_{f}", None)), None)
    at = app_input.parse_ratio(getattr(args, "at", None))
    if getattr(args, "at", None) and not at:
        return out({"ok": False, "code": "bad_ratio",
                    "error": "--at 은 0~1 비율이다 (예: 0.5,0.8). 픽셀은 받지 않는다 — 캡처가 축소돼 있어 빗나간다"})
    if not sel and not at:
        return out({"ok": False, "code": "target_required",
                    "error": "--text · --id · --desc 중 하나, 또는 --at 비율 좌표가 필요하다",
                    "next": "app tree  # 누를 수 있는 요소와 화면 언어를 본다"})
    be, dev_id, err = backend_for(args)
    if err is not None:
        return err
    before = before_shot(args, be, dev_id)
    label = f"{sel[0]}={sel[1]!r}" if sel else f"at {args.at}"

    if not sel:
        ok, detail = be.tap_ratio(dev_id, *at)
        return gesture_result(args, be, dev_id, before, ok, detail, "tap_failed", f"탭 ({label})")

    field, value = sel
    nodes = be.nodes(dev_id) or []
    if not nodes and be.selects_itself:
        # iOS 트리를 못 읽음: 예전처럼 Maestro 선택자에 값을 그대로 (빠른 길)
        ok, detail = be.tap_selector(dev_id, field, value)
        if not ok and "not found" in (detail or "").lower():
            return not_found_response(be, dev_id, field, value, None, args)
        return gesture_result(args, be, dev_id, before, ok, detail, "tap_failed", f"탭 ({label})")
    if not nodes:
        return device_failure_response(be, dev_id, args)
    # 플랫폼 공통 matcher: 정확 > 정규화(겹친 라벨·줄 단위) > 포함, text <-> desc 대체
    found, matched_by, match_kind = node_match.find_nodes(nodes, field, value)
    if not found:
        return not_found_response(be, dev_id, field, value, nodes, args)
    idx = getattr(args, "index", 0) or 0
    if idx >= len(found):
        return out({"ok": False, "code": "index_out_of_range", "matches": len(found)})
    target = found[idx]
    if be.selects_itself:
        # iOS: 저장된 값 그대로 누르고, 선택자가 못 찾으면 중심 좌표
        ok, detail = be.tap_selector(dev_id, "id" if matched_by == "id" else "text", target[matched_by])
        if not ok and "not found" in (detail or "").lower():
            ok, detail = be.tap_xy(dev_id, *target["center"])
    else:
        ok, detail = be.tap_xy(dev_id, *target["center"])
    return gesture_result(args, be, dev_id, before, ok, detail, "tap_failed",
                           f"탭 {target['center']} ({label})",
                           element={k: v for k, v in target.items() if v not in ("", None)},
                           matches=len(found), matched_by=matched_by, match_kind=match_kind)


def configure(p) -> None:
    p.add_argument("--text", dest="sel_text", default=None, help="tap: 보이는 문구로 찾는다")
    p.add_argument("--id", dest="sel_id", default=None, help="tap: resource-id(Android) · accessibilityIdentifier(iOS)")
    p.add_argument("--desc", dest="sel_desc", default=None, help="tap: 접근성 설명(content-desc)으로 찾는다")
    p.add_argument("--index", type=int, default=0, help="tap: 여러 개 맞으면 몇 번째 (0부터)")
    p.add_argument("--at", default=None, help="tap: 요소로 못 찾을 때만 — 0~1 비율 좌표 (예: 0.5,0.8)")


ACTION = Action(name="tap", device_use="mutate", run=_app_tap, configure=configure)
