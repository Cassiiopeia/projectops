"""detect: pro-launch detect result + confirmed targets (note target)"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit

from pro_agent_test.launch_bridge import _launch
from pro_agent_test.notes.recall import _TARGET_WORDS, _surface
from pro_agent_test.notes.store import _load_notes
from pro_agent_test.scenario_rules import TARGETS
from pro_agent_test.storage import _home_dir


# =========================================================================
# detect — what can be launched (pro-launch) + what was confirmed and recorded (note target)
# =========================================================================

def _recorded_targets(root: Path) -> dict | None:
    """What the agent confirmed from the code and recorded. Trusted over declarations."""
    notes, _ = _load_notes(root)
    rec = notes.get("targets")
    if not isinstance(rec, dict):
        return None
    vals = [t for t in rec.get("value", []) if t in TARGETS]
    return {"targets": vals, "why": rec.get("why")} if vals else None


def cmd_detect(args) -> int:
    """What can be driven. Decision order: ① --target ② note target ③ version.yml ④ marker files.

    ③④ and device/browser info come from pro-launch. Here only what QA confirmed and recorded is added.
    """
    start = Path(args.path).resolve()
    data, raw, _ = _launch(["detect", "--path", str(start)])
    if data is None:
        return emit({"ok": False, "code": "launch_unavailable",
                     "error": "Could not call pro-launch detect", "output": raw[-400:],
                     "next": "Read output for the cause, then run launch detect directly to see the full error"})
    root = Path(data.get("root") or start)

    targets = list(data.get("kinds") or [])
    source = data.get("source")
    rec = _recorded_targets(root)
    if rec:
        targets, source = rec["targets"], "recorded"
    if getattr(args, "target", None):
        if args.target not in TARGETS:
            return emit({"ok": False, "code": "unknown_target",
                         "error": f"Unknown target '{args.target}'",
                         "hint": f"one of {'·'.join(TARGETS)}"})
        targets = [args.target]

    # If a target different from detection was chosen, collect that target's info (device, browser, access) again.
    # Otherwise it records "drive web" yet never sees whether the browser is ready.
    launchable = [t for t in targets if t in ("app", "web", "server")]
    if launchable and set(launchable) != set(data.get("kinds") or []):
        again, _, _ = _launch(["detect", "--path", str(start), "--kinds", ",".join(launchable)])
        if again is not None:
            data = again

    payload: dict = {k: v for k, v in data.items()
                     if k not in ("kinds", "source", "confirm", "summary", "next", "ok", "code")}
    payload.update({"targets": targets, "target_source": source,
                    "knowledge_dir": str(_home_dir(root))})
    if rec:
        # Show why it was decided too — the record must be re-checkable later
        payload["recorded_why"] = rec.get("why")

    # version.yml only declares **what it is**, not what can be driven (#591).
    # If the server renders the screen itself, web must be driven too — that call is the agent's.
    if source == "version.yml" and not getattr(args, "target", None):
        payload["confirm"] = {
            "why": ("These targets come from the version.yml declaration — they are not confirmed. "
                    "If the server renders pages itself, web must be walked too"),
            "check": ("Decide from the code: do template folders (templates·views·resources/templates), "
                      "static files or routes return HTML? The same applies when an app or "
                      "web client lives in the same repo"),
            "record": (f"note target --root {root} --targets {','.join(targets) or 'server'}"
                       ",web --why \"{reason}\"   # leave it as is if it is right"),
        }

    nxt = None
    if not targets:
        nxt = "Cannot tell what to walk — set it with --target app|web|server|other"
    elif "app" in targets:
        dev = (payload.get("app") or {}).get("devices") or {}
        if not (dev.get("android") or dev.get("ios_booted")):
            nxt = "pro-launch devices  # no device. Boot an AVD or a simulator"
    if not nxt and "web" in targets and not ((payload.get("web") or {}).get("playwright") or {}).get("ready"):
        nxt = "pro-launch web setup  # walking web needs a browser (ask the user first)"
    # Include a few rules and pitfalls learned about this app — visible without calling note show (#837)
    mem = _surface(root, "detect:" + ",".join(targets),
                   " ".join([*targets, *(_TARGET_WORDS.get(t, "") for t in targets)]))
    if mem:
        payload["memory"] = mem
    payload["summary"] = f"{root.name}: targets={'·'.join(targets) if targets else 'none'} ({source})"
    payload["next"] = nxt
    return emit(payload)
