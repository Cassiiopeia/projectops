"""detect: pro-launch detect 결과 + 확인해 적어 둔 타겟(note target)"""
from __future__ import annotations

from pathlib import Path

from common.emit import emit

from pro_agent_test.launch_bridge import _launch
from pro_agent_test.notes.recall import _TARGET_WORDS, _surface
from pro_agent_test.notes.store import _load_notes
from pro_agent_test.scenario_rules import TARGETS
from pro_agent_test.storage import _home_dir


# =========================================================================
# detect — 띄울 수 있는 것(pro-launch) + 확인해 적어 둔 것(note target)
# =========================================================================

def _recorded_targets(root: Path) -> dict | None:
    """agent가 코드를 보고 확인해 적어 둔 것. 선언보다 이쪽을 믿는다."""
    notes, _ = _load_notes(root)
    rec = notes.get("targets")
    if not isinstance(rec, dict):
        return None
    vals = [t for t in rec.get("value", []) if t in TARGETS]
    return {"targets": vals, "why": rec.get("why")} if vals else None


def cmd_detect(args) -> int:
    """무엇을 밟을 수 있는지. 판정 순서: ① --target ② note target ③ version.yml ④ 마커 파일.

    ③④ 와 기기·브라우저 정보는 pro-launch 가 준다. 여기서는 QA 가 확인해 적어 둔 것만 얹는다.
    """
    start = Path(args.path).resolve()
    data, raw, _ = _launch(["detect", "--path", str(start)])
    if data is None:
        return emit({"ok": False, "code": "launch_unavailable",
                     "error": "pro-launch detect 를 부르지 못했습니다", "output": raw[-400:]})
    root = Path(data.get("root") or start)

    targets = list(data.get("kinds") or [])
    source = data.get("source")
    rec = _recorded_targets(root)
    if rec:
        targets, source = rec["targets"], "recorded"
    if getattr(args, "target", None):
        if args.target not in TARGETS:
            return emit({"ok": False, "code": "unknown_target",
                         "error": f"target '{args.target}' 을 모릅니다",
                         "hint": f"{'·'.join(TARGETS)} 중 하나"})
        targets = [args.target]

    # 감지와 다른 타겟으로 정해졌으면 그 타겟의 정보(기기·브라우저·접속)를 다시 모은다.
    # 안 그러면 "web 을 밟는다"고 적어 두고도 브라우저 준비 상태를 못 본다.
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
        # 왜 그렇게 판단했는지를 함께 보여준다 — 다음에 이 기록이 맞는지 다시 볼 수 있어야 한다
        payload["recorded_why"] = rec.get("why")

    # version.yml 은 **무엇인가**를 선언할 뿐, 무엇을 밟을 수 있는지가 아니다 (#591).
    # 서버가 화면을 직접 뿌리는 구조면 web 도 밟아야 한다 — 판단은 agent 의 일이다.
    if source == "version.yml" and not getattr(args, "target", None):
        payload["confirm"] = {
            "why": ("이 targets 는 version.yml 선언에서 나왔습니다 — 확인된 것이 아닙니다. "
                    "서버가 화면을 직접 뿌리면 web 도 밟아야 합니다"),
            "check": ("코드를 보고 판단하세요: 템플릿 폴더(templates·views·resources/templates)·"
                      "정적 파일·라우트가 HTML을 돌려주는지. 앱·웹 클라이언트가 한 레포에 "
                      "같이 있는 경우도 마찬가지입니다"),
            "record": (f"note target --root {root} --targets {','.join(targets) or 'server'}"
                       ",web --why \"{판단 근거}\"   # 맞으면 그대로 두면 됩니다"),
        }

    nxt = None
    if not targets:
        nxt = "무엇을 밟을지 알 수 없습니다 — --target app|web|server|other 로 직접 알려주세요"
    elif "app" in targets:
        dev = (payload.get("app") or {}).get("devices") or {}
        if not (dev.get("android") or dev.get("ios_booted")):
            nxt = "pro-launch devices  # 기기가 없습니다. AVD 나 시뮬레이터를 부팅하세요"
    if not nxt and "web" in targets and not ((payload.get("web") or {}).get("playwright") or {}).get("ready"):
        nxt = "pro-launch web setup  # 웹을 밟으려면 브라우저가 필요합니다 (먼저 사용자에게 묻는다)"
    # 이 앱에서 알아낸 규칙·함정을 몇 건 싣는다 — note show 를 부르지 않아도 보이게 (#837)
    mem = _surface(root, "detect:" + ",".join(targets),
                   " ".join([*targets, *(_TARGET_WORDS.get(t, "") for t in targets)]))
    if mem:
        payload["memory"] = mem
    payload["summary"] = f"{root.name}: 타겟={'·'.join(targets) if targets else '없음'} ({source})"
    payload["next"] = nxt
    return emit(payload)
