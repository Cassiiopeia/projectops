"""`app record start|stop` — 화면을 영상으로 녹화한다 (#928).

iOS: `simctl io recordVideo` 를 백그라운드로 띄우고 stop 에서 SIGINT 로 끝내 파일을 닫는다.
Android: 기기 안 `screenrecord` 를 띄우고 stop 에서 SIGINT 로 끝낸 뒤 pull. 진행 중 녹화는 상태 폴더에 기록한다.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from common.proc import pid_alive, sdk_tool

from pro_launch.commands.app.gestures import elapsed_seconds
from pro_launch.registry import Action
from pro_launch.runtime import procs
from pro_launch.runtime.context import project_root, state_home
from pro_launch.runtime.devices import no_device_response, pick_device
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import shot_target

RECORD_VERBS = ("start", "stop")
# screenrecord 한 번의 상한은 180초다 — 더 길게 필요하면 stop 후 다시 start
ANDROID_RECORD_LIMIT_SECONDS = 180
# 기기 안 임시 파일 (pull 뒤 지운다)
ANDROID_REMOTE_FILE = "/sdcard/pro_launch_record.mp4"
# start 뒤 프로세스가 바로 죽었는지 보는 대기 (초)
START_CHECK_SECONDS = 1.0
# 영상 > gif 변환: 초당 프레임 · 가로 픽셀
GIF_FRAMES_PER_SECOND = 12
GIF_WIDTH_PIXELS = 480
# ffmpeg 변환 시간 상한 (초)
FFMPEG_TIMEOUT_SECONDS = 120


def _state_file(root: Path, dev_id: str) -> Path:
    folder = state_home(root) / "recordings"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (re.sub(r"[^A-Za-z0-9._-]", "_", dev_id) + ".json")


def _app_record(args) -> int:
    """동사 고르기 > 기기 > start · stop."""
    verb = getattr(args, "session_verb", None)
    if verb not in RECORD_VERBS:
        return out({"ok": False, "code": "record_verb_required", "error": "start 또는 stop 이 필요하다",
                    "next": "app record start --device <기기>  # 끝낼 때 app record stop"})
    root = project_root(args)
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return no_device_response(dev, args.device)
    if platform not in ("ios", "android"):
        return out({"ok": False, "code": "platform_unsupported", "error": f"{platform} 은 녹화를 지원하지 않는다"})
    state_file = _state_file(root, dev_id)
    if verb == "start":
        return _start(args, root, platform, dev_id, state_file)
    return _stop(args, root, platform, dev_id, state_file)


def _start(args, root: Path, platform: str, dev_id: str, state_file: Path) -> int:
    """이미 녹화 중이면 거절 > 대상 파일 정하기 > 백그라운드 녹화 시작 > 상태 기록."""
    previous = _read_state(state_file)
    if previous and pid_alive(previous["pid"]):
        return out({"ok": False, "code": "already_recording", "device": dev_id, "started_at": previous["started_at"],
                    "error": "이 기기는 이미 녹화 중이다", "next": "app record stop --device <기기>"})
    target, _ = shot_target(root, args.out, ".mp4")
    log_path = state_file.with_suffix(".log")
    if platform == "ios":
        command = ["xcrun", "simctl", "io", dev_id, "recordVideo", "--codec=h264", "--force", str(target)]
    else:
        adb = sdk_tool("adb")
        if not adb:
            return out({"ok": False, "code": "adb_missing", "error": "adb 를 찾지 못했습니다"})
        command = [adb, "-s", dev_id, "shell", "screenrecord", "--time-limit", str(ANDROID_RECORD_LIMIT_SECONDS),
                   ANDROID_REMOTE_FILE]
    pid = procs.spawn_detached(command, str(root), log_path)
    time.sleep(START_CHECK_SECONDS)
    if not pid_alive(pid):
        error = log_path.read_text(encoding="utf-8", errors="replace").strip()[-300:] if log_path.exists() else ""
        return out({"ok": False, "code": "record_start_failed", "device": dev_id, "error": error or "녹화 프로세스가 바로 끝났다"})
    state_file.write_text(json.dumps({"pid": pid, "platform": platform, "file": str(target), "started_at": time.time(),
                                      "is_gif_requested": bool(getattr(args, "gif", False))}), encoding="utf-8")
    return out({"ok": True, "code": "ok", "action": "record", "device": dev_id, "platform": platform, "recording": True,
                "file": str(target), "elapsed_seconds": elapsed_seconds(args),
                "summary": "녹화 시작", "next": "화면을 조작한 뒤 app record stop --device <기기> [--gif]"})


def _stop(args, root: Path, platform: str, dev_id: str, state_file: Path) -> int:
    """녹화 끝내기 > (Android) 파일 가져오기 > 포스터 · gif (ffmpeg 가 있으면) > 상태 지우기."""
    state = _read_state(state_file)
    if not state:
        return out({"ok": False, "code": "not_recording", "device": dev_id,
                    "error": "이 기기에 진행 중인 녹화 기록이 없다", "next": "app record start --device <기기>"})
    target = Path(state["file"])
    if platform == "android":
        error = _finish_android(dev_id, state, target)
    else:
        procs.interrupt_process(state["pid"])
        error = None if target.exists() and target.stat().st_size > 0 else "녹화 파일이 만들어지지 않았다"
    state_file.unlink(missing_ok=True)
    if error:
        return out({"ok": False, "code": "record_stop_failed", "device": dev_id, "error": error})
    extras = _make_extras(target, bool(getattr(args, "gif", False)) or state.get("is_gif_requested", False))
    seconds = round(time.time() - state["started_at"], 1)
    return out({"ok": True, "code": "ok", "action": "record", "device": dev_id, "platform": platform, "recording": False,
                "file": str(target), "size_bytes": target.stat().st_size, "recorded_seconds": seconds, **extras,
                "elapsed_seconds": elapsed_seconds(args), "summary": f"녹화 {seconds}초: {target.name}",
                "next": "영상은 열어 보기 어렵다 — poster 이미지를 읽어 확인한다" if extras.get("poster") else
                        "ffmpeg 가 있으면 poster·gif 도 만든다 (doctor 로 확인)"})


def _finish_android(dev_id: str, state: dict, target: Path) -> str | None:
    """screenrecord 에 SIGINT > 기기 파일 마무리 대기 > pull > 기기 파일 삭제. 실패 사유 또는 None."""
    adb = sdk_tool("adb")
    try:
        subprocess.run([adb, "-s", dev_id, "shell", "pkill", "-INT", "screenrecord"], capture_output=True, timeout=15)
        procs.interrupt_process(state["pid"], wait_seconds=8.0)
        time.sleep(1.0)   # 기기가 mp4 를 닫는 시간
        target.parent.mkdir(parents=True, exist_ok=True)
        pulled = subprocess.run([adb, "-s", dev_id, "pull", ANDROID_REMOTE_FILE, str(target)],
                                capture_output=True, text=True, timeout=120)
        subprocess.run([adb, "-s", dev_id, "shell", "rm", "-f", ANDROID_REMOTE_FILE], capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError) as e:
        return str(e)
    return None if pulled.returncode == 0 and target.exists() else (pulled.stderr or "pull 실패").strip()[-300:]


def _make_extras(video: Path, should_make_gif: bool) -> dict:
    """ffmpeg 가 있으면 첫 장 poster(jpg) · gif. 없으면 이유만."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return {"poster": None, "gif": None, "extras_skipped": "ffmpeg_missing"}
    extras: dict = {}
    poster = video.with_suffix(".poster.jpg")
    gif = video.with_suffix(".gif")
    jobs = [("poster", poster, ["-i", str(video), "-frames:v", "1",
                                                "-pix_fmt", "yuvj420p", str(poster)])]   # jpg 인코더가 full-range 만 받는다(실측)
    if should_make_gif:
        filters = f"fps={GIF_FRAMES_PER_SECOND},scale={GIF_WIDTH_PIXELS}:-1:flags=lanczos"
        jobs.append(("gif", gif, ["-i", str(video), "-vf", filters, str(gif)]))
    for key, path, arguments in jobs:
        try:
            result = subprocess.run([ffmpeg, "-y", "-loglevel", "error", *arguments], capture_output=True,
                                    timeout=FFMPEG_TIMEOUT_SECONDS)
        except (OSError, subprocess.SubprocessError):
            result = None
        extras[key] = str(path) if result and result.returncode == 0 and path.exists() else None
    return extras


def _read_state(state_file: Path) -> dict | None:
    try:
        return json.loads(state_file.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def configure(p) -> None:
    # start · stop 동사는 session 과 같은 위치 인자(session_verb)를 쓴다. --out 은 shot 과 공유
    p.add_argument("--gif", action="store_true", help="record stop: gif 도 만든다 (ffmpeg 필요)")


ACTION = Action(name="record", device_use="mutate", run=_app_record, configure=configure,
                help="화면 녹화 start·stop (iOS simctl · Android screenrecord) — stop 에서 poster(·--gif) 도 만든다",
                example="app record start --device $DEV --out demo  →  app record stop --device $DEV --gif")
