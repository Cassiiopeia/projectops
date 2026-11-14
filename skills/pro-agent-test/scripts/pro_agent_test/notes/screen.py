"""Screen target records: parse 'label=kind:value' (pixels rejected), record scores, press guidance"""
from __future__ import annotations

import re

from common import memory as _memory

from pro_agent_test.notes.recall import _target_verify
from pro_agent_test.notes.store import (_LOCATORS, _SIZE, _fmt_ratio, _locator, _promote_screen, _px_to_at,
                                        _variant_key)


# ── Screen targets (#838) ────────────────────────────────────────────────────

class _TargetError(ValueError):
    def __init__(self, code: str, message: str, hint: str | None = None):
        super().__init__(message)
        self.code, self.hint = code, hint


def _parse_target(spec: str, size: str | None) -> tuple[str, dict]:
    """'label=text:phrase' · 'label=id:x|index=1' · 'label=at:0.5,0.8' → (label, target).

    Pixels are not accepted — app tap rejects pixels, so storing them is useless (#826).
    If the resolution is known, the converted ratio is suggested.
    """
    label, sep, rest = spec.partition("=")
    label = label.strip()
    if not (sep and label and rest.strip()):
        raise _TargetError("bad_target", f"--target '{spec}' must look like 'label=kind:value'",
                           "e.g. login=text:Log in / menu=id:menu_btn / map_pin=at:0.5,0.8")
    rest = rest.strip()
    px = re.fullmatch(r"(?:at:)?\s*(\d+(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*", rest)
    if px and (float(px.group(1)) > 1 or float(px.group(2)) > 1):
        conv = _px_to_at(f"{int(float(px.group(1)))},{int(float(px.group(2)))}", size)
        raise _TargetError(
            "pixels_rejected", f"--target '{spec}' is a pixel coordinate — not saved",
            (f"write it as a ratio: --target \"{label}=at:{conv}\" (for {size}). " if conv else
             "write it as a 0~1 ratio of the screen size (pass --screen-size to have it converted). ")
            + "If the element is visible, prefer text:/id:/desc:")
    kind, colon, val = rest.partition(":")
    kind = kind.strip().lower()
    if not colon or kind not in (*_LOCATORS, "at"):
        raise _TargetError("bad_target", f"--target '{spec}' has an unknown kind",
                           "one of text: · id: · desc: · at: (e.g. start=text:Start)")
    if kind == "at":
        m = re.fullmatch(r"\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\s*", val)
        if not m or not all(0 <= float(g) <= 1 for g in m.groups()):
            raise _TargetError("bad_target", f"--target '{spec}' at must be two 0~1 ratios",
                               "e.g. start=at:0.5,0.815")
        return label, {"at": f"{_fmt_ratio(float(m.group(1)))},{_fmt_ratio(float(m.group(2)))}"}
    idx = None
    m = re.search(r"\|index=(\d+)\s*$", val)
    if m:
        idx, val = int(m.group(1)), val[:m.start()]
    if not val.strip():
        raise _TargetError("bad_target", f"--target '{spec}' has an empty value")
    t = {kind: val.strip()}
    if idx is not None:
        t["index"] = idx
    return label, t



def _tap_hint(t: dict) -> str:
    """launch_cli arguments to press this target."""
    if "at" in t:
        return f"app tap --at {t['at']}"
    k = next(k for k in _LOCATORS if k in t)
    s = f"app tap --{k} \"{t[k]}\""
    return s + (f" --index {t['index']}" if t.get("index") else "")


def _note_screen(args, notes: dict, today: str) -> dict:
    """Write a screen record (--target label=…) or record a score (--result + --target label). Returns ok=False on failure."""
    if not args.name:
        return {"ok": False, "code": "args_required", "error": "--name is required"}
    # Junk left in learned.json is read on every later run — filter before writing (#706)
    if args.screen_size and not _SIZE.fullmatch(args.screen_size):
        return {"ok": False, "code": "bad_screen_size",
                "error": f"--screen-size '{args.screen_size}' must be widthxheight in numbers",
                "hint": "e.g. 1080x2400"}
    screens = notes.setdefault("screens", {})
    existing = screens.get(args.name)

    if args.result:
        # Score — ok if pressing with app tap changed the screen, fail if not found or unchanged
        labels = [t.split("=", 1)[0].strip() for t in (args.target or []) if t.strip()]
        if not labels:
            return {"ok": False, "code": "args_required",
                    "error": "--result needs a --target label (the name of what was pressed)"}
        if not existing:
            return {"ok": False, "code": "screen_not_found",
                    "error": f"No record of screen '{args.name}'", "next": "note show --all"}
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
                        "error": (f"'{args.name}' has no '{label}' target" if not cands else
                                  f"'{label}' is in several device records: {', '.join(k for k, _ in cands)}"),
                        "hint": "pick the record with --role · --screen-size"}
            k, v = cands[0]
            t = v["targets"][label]
            counted = _memory.bump(t, args.result, today)
            graded.append({"variant": k, "label": label, "ok": t["ok"], "fail": t["fail"],
                           "counted": counted, "verify": _target_verify(t, today)})
        return {"ok": True, "graded": graded}

    if args.taps:
        # Old input. Pixels are not stored — report the converted ratio (#838)
        conv = [f"{t.split('=', 1)[0]}=at:{_px_to_at(t.split('=', 1)[1], args.screen_size)}"
                for t in args.taps if "=" in t and _px_to_at(t.split("=", 1)[1], args.screen_size)]
        return {"ok": False, "code": "pixels_rejected",
                "error": "--taps takes pixel coordinates and is no longer accepted — app tap rejects pixels",
                "hint": ("use --target" + (f": {' '.join(repr(c) for c in conv)}" if conv else
                         " ('label=text:copy' for an element, 'label=at:0.5,0.8' for a canvas)"))}
    if not existing and not args.anchor:
        return {"ok": False, "code": "args_required",
                "error": "a new screen needs --anchor (a clue that identifies this screen)"}

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
        entry["anchor"] = args.anchor          # clue that identifies this screen
    variant = entry["variants"].setdefault(key, {})
    targets = variant.setdefault("targets", {})
    for label, t in parsed.items():
        cur = targets.get(label)
        if isinstance(cur, dict) and _locator(cur) == t:
            continue                           # same target keeps its score
        targets[label] = t                     # a changed target does not inherit the old score
    if args.screen_size:
        variant["measured_on"] = args.screen_size
    if args.build:
        # A new build may change the screen. Do not block; report it when read.
        variant["build"] = args.build
    variant["updated"] = today
    entry["updated"] = today
    return {"ok": True, "variant": key, "targets": {k: _tap_hint(v) for k, v in targets.items()}}
