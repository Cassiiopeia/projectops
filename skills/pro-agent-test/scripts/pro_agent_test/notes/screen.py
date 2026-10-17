"""화면 대상 기록: '라벨=종류:값' 해석(픽셀 거절), 성적 기록, 누르기 안내"""
from __future__ import annotations

import re

from common import memory as _memory

from pro_agent_test.notes.recall import _target_verify
from pro_agent_test.notes.store import (_LOCATORS, _SIZE, _fmt_ratio, _locator, _promote_screen, _px_to_at,
                                        _variant_key)


# ── 화면 대상 (#838) ────────────────────────────────────────────────────

class _TargetError(ValueError):
    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code, self.hint = code, hint


def _parse_target(spec: str, size: str | None) -> tuple[str, dict]:
    """'라벨=text:문구' · '라벨=id:x|index=1' · '라벨=at:0.5,0.8' → (라벨, 대상).

    픽셀은 받지 않는다 — app tap 이 픽셀을 거절하므로 저장해 봐야 쓸 수 없다(#826).
    해상도를 알면 비율로 바꾼 값을 안내한다.
    """
    label, sep, rest = spec.partition("=")
    label = label.strip()
    if not (sep and label and rest.strip()):
        raise _TargetError("bad_target", f"--target '{spec}' 는 '라벨=종류:값' 형식이어야 합니다",
                           "예: 로그인=text:로그인하기 / 메뉴=id:menu_btn / 지도핀=at:0.5,0.8")
    rest = rest.strip()
    px = re.fullmatch(r"(?:at:)?\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*", rest)
    if px and (float(px.group(1)) > 1 or float(px.group(2)) > 1):
        conv = _px_to_at(f"{int(float(px.group(1)))},{int(float(px.group(2)))}", size)
        raise _TargetError(
            "pixels_rejected", f"--target '{spec}' 는 픽셀 좌표입니다 — 저장하지 않습니다",
            (f"비율로 적으세요: --target \"{label}=at:{conv}\" ({size} 기준). " if conv else
             "화면 크기로 나눈 0~1 비율로 적으세요(--screen-size 를 주면 바꿔 드립니다). ")
            + "요소가 보이면 text:/id:/desc: 가 먼저입니다")
    kind, colon, val = rest.partition(":")
    kind = kind.strip().lower()
    if not colon or kind not in (*_LOCATORS, "at"):
        raise _TargetError("bad_target", f"--target '{spec}' 의 종류를 모릅니다",
                           "text: · id: · desc: · at: 중 하나 (예: 시작=text:시작하기)")
    if kind == "at":
        m = re.fullmatch(r"\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\s*", val)
        if not m or not all(0 <= float(g) <= 1 for g in m.groups()):
            raise _TargetError("bad_target", f"--target '{spec}' 의 at 은 0~1 비율 두 개여야 합니다",
                               "예: 시작=at:0.5,0.815")
        return label, {"at": f"{_fmt_ratio(float(m.group(1)))},{_fmt_ratio(float(m.group(2)))}"}
    idx = None
    m = re.search(r"\|index=(\d+)\s*$", val)
    if m:
        idx, val = int(m.group(1)), val[:m.start()]
    if not val.strip():
        raise _TargetError("bad_target", f"--target '{spec}' 의 값이 비었습니다")
    t = {kind: val.strip()}
    if idx is not None:
        t["index"] = idx
    return label, t



def _tap_hint(t: dict) -> str:
    """이 대상을 누르는 launch_cli 인자."""
    if "at" in t:
        return f"app tap --at {t['at']}"
    k = next(k for k in _LOCATORS if k in t)
    s = f"app tap --{k} \"{t[k]}\""
    return s + (f" --index {t['index']}" if t.get("index") else "")


def _note_screen(args, notes: dict, today: str) -> dict:
    """화면 기록을 쓰거나(--target 라벨=…) 성적을 남긴다(--result + --target 라벨). 실패면 ok=False 결과."""
    if not args.name:
        return {"ok": False, "code": "args_required", "error": "--name 이 필요합니다"}
    # 쓰레기 값이 learned.json 에 남으면 다음 실행마다 그대로 읽힌다 — 쓰기 전에 거른다 (#706)
    if args.screen_size and not _SIZE.fullmatch(args.screen_size):
        return {"ok": False, "code": "bad_screen_size",
                "error": f"--screen-size '{args.screen_size}' 는 가로x세로 숫자여야 합니다",
                "hint": "예: 1080x2400"}
    screens = notes.setdefault("screens", {})
    existing = screens.get(args.name)

    if args.result:
        # 성적 기록 — app tap 으로 눌러서 화면이 바뀌었으면 ok, 못 찾았거나 그대로면 fail
        labels = [t.split("=", 1)[0].strip() for t in (args.target or []) if t.strip()]
        if not labels:
            return {"ok": False, "code": "args_required",
                    "error": "--result 에는 --target 라벨(누른 대상 이름)이 필요합니다"}
        if not existing:
            return {"ok": False, "code": "screen_not_found",
                    "error": f"화면 '{args.name}' 기록이 없습니다", "next": "note show --all"}
        variants = existing.get("variants") or {}
        want = (_variant_key(args.role, args.screen_size)
                if (args.role or args.screen_size) else None)
        graded = []
        for label in labels:
            cands = [(k, v) for k, v in variants.items()
                     if isinstance(v, dict) and label in (v.get("targets") or {})
                     and (want is None or k == want)]
            if len(cands) != 1:
                return {"ok": False,
                        "code": "target_not_found" if not cands else "ambiguous_variant",
                        "error": (f"'{args.name}' 에 '{label}' 대상이 없습니다" if not cands else
                                  f"'{label}' 이 여러 기기 기록에 있습니다: {', '.join(k for k, _ in cands)}"),
                        "hint": "--role · --screen-size 로 어느 기록인지 고릅니다"}
            k, v = cands[0]
            t = v["targets"][label]
            counted = _memory.bump(t, args.result, today)
            graded.append({"variant": k, "label": label, "ok": t["ok"], "fail": t["fail"],
                           "counted": counted, "verify": _target_verify(t, today)})
        return {"ok": True, "graded": graded}

    if args.taps:
        # 옛 입력. 픽셀은 저장하지 않는다 — 바꾼 비율을 알려 준다 (#838)
        conv = [f"{t.split('=', 1)[0]}=at:{_px_to_at(t.split('=', 1)[1], args.screen_size)}"
                for t in args.taps if "=" in t and _px_to_at(t.split("=", 1)[1], args.screen_size)]
        return {"ok": False, "code": "pixels_rejected",
                "error": "--taps 는 픽셀 좌표라 더는 받지 않습니다 — app tap 이 픽셀을 거절합니다",
                "hint": ("--target 으로 적으세요" + (f": {' '.join(repr(c) for c in conv)}" if conv else
                         " (요소면 '라벨=text:문구', 캔버스면 '라벨=at:0.5,0.8')"))}
    if not existing and not args.anchor:
        return {"ok": False, "code": "args_required",
                "error": "새 화면에는 --anchor(이 화면임을 알아보는 단서)가 필요합니다"}

    key = _variant_key(args.role, args.screen_size)
    size = args.screen_size or ((existing or {}).get("variants", {}).get(key) or {}).get("measured_on")
    parsed = {}
    for spec in args.target or []:
        try:
            label, t = _parse_target(spec, size)
        except _TargetError as e:
            return {"ok": False, "code": e.code, "error": str(e), **({"hint": e.hint} if e.hint else {})}
        parsed[label] = t

    entry = _promote_screen(screens.setdefault(args.name, {}))
    if args.anchor:
        entry["anchor"] = args.anchor          # 이 화면임을 알아보는 단서
    variant = entry["variants"].setdefault(key, {})
    targets = variant.setdefault("targets", {})
    for label, t in parsed.items():
        cur = targets.get(label)
        if isinstance(cur, dict) and _locator(cur) == t:
            continue                           # 같은 대상이면 성적을 지킨다
        targets[label] = t                     # 대상이 바뀌면 옛 성적을 물려받지 않는다
    if args.screen_size:
        variant["measured_on"] = args.screen_size
    if args.build:
        # 빌드가 바뀌면 화면도 바뀔 수 있다. 막지 않고 꺼낼 때 알려 준다.
        variant["build"] = args.build
    variant["updated"] = today
    entry["updated"] = today
    return {"ok": True, "variant": key, "targets": {k: _tap_hint(v) for k, v in targets.items()}}
