"""`app record start|stop` — 화면을 영상으로 녹화한다 (#928).

iOS simctl recordVideo · Android 기기 screenrecord > stop 에서 SIGINT 로 마무리 > mp4 점검(moov · 실제 길이, #1130)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from common.proc import pid_alive, sdk_tool
from common.state import MACHINE_BUCKET, base_dir

from pro_launch.commands.app.gestures import elapsed_seconds
from pro_launch.registry import Action
from pro_launch.runtime import procs
from pro_launch.runtime.context import project_root
from pro_launch.runtime.devices import adb_shell, no_device_response, pick_device
from pro_launch.runtime.output import out
from pro_launch.runtime.shots import shot_target
from pro_launch.runtime.video_file import inspect_mp4

RECORD_VERBS = ("start", "stop")
# screenrecord 한 번의 상한은 180초다 — 더 길게 필요하면 stop 후 다시 start
ANDROID_RECORD_LIMIT_SECONDS = 180
# 상한 도달 판정 여유 (초): 실제 파일은 179.9초처럼 조금 짧게 끝남
ANDROID_LIMIT_MARGIN_SECONDS = 2.0
# 기기 안 임시 파일: {접두사}_{시작 시각}.mp4 (pull 뒤 지운다). 상태에 이름이 없던 옛 녹화는 접두사 이름
ANDROID_REMOTE_FILE_PREFIX = "/sdcard/pro_launch_record"
ANDROID_REMOTE_FILE = ANDROID_REMOTE_FILE_PREFIX + ".mp4"
# SIGINT 뒤 기기 screenrecord 종료 대기 · 파일 크기 안정 대기 · 확인 간격 (초)
ANDROID_EXIT_WAIT_SECONDS = 15.0
ANDROID_SIZE_SETTLE_SECONDS = 10.0
ANDROID_POLL_SECONDS = 0.5
# 기기 종료 뒤 로컬 adb shell 이 스스로 끝나길 기다리는 시간 (초)
LOCAL_ADB_EXIT_WAIT_SECONDS = 5.0
# iOS simctl 이 SIGINT 뒤 파일을 닫는 대기 (초)
IOS_STOP_WAIT_SECONDS = 15.0
# start 뒤 프로세스가 바로 죽었는지 보는 대기 (초)
START_CHECK_SECONDS = 1.0
# 영상 > gif 변환: 초당 프레임 · 가로 픽셀
GIF_FRAMES_PER_SECOND = 12
GIF_WIDTH_PIXELS = 480
# ffmpeg 변환 시간 상한 (초)
FFMPEG_TIMEOUT_SECONDS = 120


def _state_file(root: Path, dev_id: str) -> Path:
    """기기별 녹화 상태 (컴퓨터 공용 — start · stop 의 레포 폴더가 달라도 같은 기기면 이어짐)"""
    folder = base_dir() / "launch" / MACHINE_BUCKET / "recordings"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / (re.sub(r"[^A-Za-z0-9._-]", "_", dev_id) + ".json")


def _app_record(args) -> int:
    """동사 고르기 > 기기 > start · stop."""
    verb = getattr(args, "session_verb", None)
    if verb not in RECORD_VERBS:
        return out({"ok": False, "code": "record_verb_required", "error": "start or stop is required",
                    "next": "app record start --device <device>  # app record stop to finish"})
    root = project_root(args)
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return no_device_response(dev, args.device)
    if platform not in ("ios", "android"):
        return out({"ok": False, "code": "platform_unsupported", "error": f"{platform} does not support recording"})
    state_file = _state_file(root, dev_id)
    if verb == "start":
        return _start(args, root, platform, dev_id, state_file)
    return _stop(args, root, platform, dev_id, state_file)


def _start(args, root: Path, platform: str, dev_id: str, state_file: Path) -> int:
    """이미 녹화 중이면 거절 > 대상 파일 정하기 > 백그라운드 녹화 시작 > 상태 기록."""
    previous = _read_state(state_file)
    if previous and pid_alive(previous["pid"]):
        return out({"ok": False, "code": "already_recording", "device": dev_id, "started_at": previous["started_at"],
                    "error": "This device is already recording", "next": "app record stop --device <device>"})
    target, _ = shot_target(root, args.out, ".mp4")
    log_path = state_file.with_suffix(".log")
    remote_file = None
    if platform == "ios":
        command = ["xcrun", "simctl", "io", dev_id, "recordVideo", "--codec=h264", "--force", str(target)]
    else:
        adb = sdk_tool("adb")
        if not adb:
            return out({"ok": False, "code": "adb_missing", "error": "adb not found"})
        remote_file = f"{ANDROID_REMOTE_FILE_PREFIX}_{int(time.time())}.mp4"
        # exec: 기기 sh 가 screenrecord 로 바뀌어 stop 의 SIGINT 가 녹화 프로세스에 바로 닿음
        command = [adb, "-s", dev_id, "shell",
                   f"exec screenrecord --time-limit {ANDROID_RECORD_LIMIT_SECONDS} {remote_file}"]
    pid = procs.spawn_detached(command, str(root), log_path)
    time.sleep(START_CHECK_SECONDS)
    if not pid_alive(pid):
        error = log_path.read_text(encoding="utf-8", errors="replace").strip()[-300:] if log_path.exists() else ""
        return out({"ok": False, "code": "record_start_failed", "device": dev_id, "error": error or "The recording process exited right away"})
    state_file.write_text(json.dumps({"pid": pid, "platform": platform, "file": str(target), "started_at": time.time(),
                                      "remote_file": remote_file,
                                      "is_gif_requested": bool(getattr(args, "gif", False))}), encoding="utf-8")
    limit = {"time_limit_seconds": ANDROID_RECORD_LIMIT_SECONDS} if platform == "android" else {}
    summary = (f"recording started — Android screenrecord stops by itself after {ANDROID_RECORD_LIMIT_SECONDS}s"
               if platform == "android" else "recording started")
    next_step = "Drive the screen, then app record stop --device <device> [--gif]"
    if platform == "android":
        next_step += f" — stop within {ANDROID_RECORD_LIMIT_SECONDS}s; for longer flows stop and start a new recording"
    return out({"ok": True, "code": "ok", "action": "record", "device": dev_id, "platform": platform, "recording": True,
                "file": str(target), **limit, "elapsed_seconds": elapsed_seconds(args),
                "summary": summary, "next": next_step})


def _stop(args, root: Path, platform: str, dev_id: str, state_file: Path) -> int:
    """녹화 끝내기 > (Android) 파일 가져오기 > mp4 점검(moov · 실제 길이) > 포스터 · gif > 상태 지우기."""
    state = _read_state(state_file)
    if not state:
        return out({"ok": False, "code": "not_recording", "device": dev_id,
                    "error": "No recording in progress on this device", "next": "app record start --device <device>"})
    target = Path(state["file"])
    has_exited_before_stop = False
    if platform == "android":
        error, has_exited_before_stop = _finish_android(dev_id, state, target)
    else:
        procs.interrupt_process(state["pid"], wait_seconds=IOS_STOP_WAIT_SECONDS)
        error = None if target.exists() and target.stat().st_size > 0 else "The recording file was not created"
    state_file.unlink(missing_ok=True)
    if error:
        return out({"ok": False, "code": "record_stop_failed", "device": dev_id, "error": error})
    wall_clock_seconds = round(time.time() - state["started_at"], 1)
    video = inspect_mp4(target)
    if not video["is_playable"]:
        return out({"ok": False, "code": "record_unplayable", "device": dev_id, "platform": platform,
                    "file": str(target), "size_bytes": target.stat().st_size, "wall_clock_seconds": wall_clock_seconds,
                    "error": video["problem"],
                    "next": "Record again with app record start; if it repeats, run doctor and report it with pro-skill-bug"})
    extras = _make_extras(target, bool(getattr(args, "gif", False)) or state.get("is_gif_requested", False))
    seconds = video["duration_seconds"] if video["duration_seconds"] is not None else wall_clock_seconds
    is_time_limit_reached = platform == "android" and has_exited_before_stop and \
        max(seconds, wall_clock_seconds) >= ANDROID_RECORD_LIMIT_SECONDS - ANDROID_LIMIT_MARGIN_SECONDS
    summary = f"recorded {seconds}s: {target.name}"
    limit_fields = {}
    if is_time_limit_reached:
        summary += f" — screenrecord hit its {ANDROID_RECORD_LIMIT_SECONDS}s limit; the last {round(wall_clock_seconds - seconds, 1)}s were not recorded"
        limit_fields = {"is_time_limit_reached": True,
                        "warning": f"Android screenrecord stops at {ANDROID_RECORD_LIMIT_SECONDS}s. "
                                   "For longer flows, stop and start a new recording before the limit"}
    return out({"ok": True, "code": "ok", "action": "record", "device": dev_id, "platform": platform, "recording": False,
                "file": str(target), "size_bytes": target.stat().st_size, "recorded_seconds": seconds,
                "duration_source": video["duration_source"] or "wall_clock", "wall_clock_seconds": wall_clock_seconds,
                **limit_fields, **extras, "elapsed_seconds": elapsed_seconds(args), "summary": summary,
                "next": "Videos are hard to open — read the poster image to check" if extras.get("poster") else
                        "With ffmpeg it also makes a poster and gif (check with doctor)"})


def _finish_android(dev_id: str, state: dict, target: Path) -> tuple[str | None, bool]:
    """기기 screenrecord 에 SIGINT > 종료 대기 > 파일 크기 안정 대기 > pull > 기기 파일 삭제.

    > (실패 사유 또는 None, stop 전에 이미 끝나 있었는지). 로컬 adb 를 먼저 끊으면 기기 쪽이 moov 를 못 쓰고 죽는다.
    """
    adb = sdk_tool("adb")
    if not adb:
        return "adb not found", False
    remote_file = state.get("remote_file") or ANDROID_REMOTE_FILE
    try:
        recorder_pids = _remote_recorder_pids(dev_id, remote_file)
        has_exited_before_stop = not recorder_pids and not pid_alive(state["pid"])
        if recorder_pids:
            adb_shell(dev_id, "kill -2 " + " ".join(recorder_pids))
        elif not has_exited_before_stop:
            # 기기 프로세스를 못 찾음 (pidof 없는 옛 기기 등) — 이름으로 SIGINT
            adb_shell(dev_id, "pkill -INT screenrecord")
        if not _wait_until(lambda: not _remote_recorder_pids(dev_id, remote_file), ANDROID_EXIT_WAIT_SECONDS):
            return f"screenrecord did not exit within {ANDROID_EXIT_WAIT_SECONDS:g}s after SIGINT", has_exited_before_stop
        _wait_remote_size_settled(dev_id, remote_file)
        # 로컬 adb shell 은 기기 녹화 종료 뒤 스스로 끝남. 남았을 때만 정리 (파일 마무리 뒤라 안전)
        if not _wait_until(lambda: not pid_alive(state["pid"]), LOCAL_ADB_EXIT_WAIT_SECONDS):
            procs.interrupt_process(state["pid"], wait_seconds=LOCAL_ADB_EXIT_WAIT_SECONDS)
        target.parent.mkdir(parents=True, exist_ok=True)
        pulled = subprocess.run([adb, "-s", dev_id, "pull", remote_file, str(target)],
                                capture_output=True, text=True, errors="replace", timeout=120)
        adb_shell(dev_id, f"rm -f {remote_file}")
    except (OSError, subprocess.SubprocessError) as e:
        return str(e), False
    if pulled.returncode == 0 and target.exists():
        return None, has_exited_before_stop
    return (pulled.stderr or "pull failed").strip()[-300:], has_exited_before_stop


def _remote_recorder_pids(dev_id: str, remote_file: str) -> list[str]:
    """이 녹화 파일을 쓰는 기기 screenrecord pid 목록 (다른 녹화는 건드리지 않게 cmdline 으로 거름)."""
    script = (f"for p in $(pidof screenrecord); do grep -q '{Path(remote_file).name}' /proc/$p/cmdline 2>/dev/null "
              "&& echo $p; done")
    return [token for token in adb_shell(dev_id, script).split() if token.isdigit()]


def _wait_remote_size_settled(dev_id: str, remote_file: str) -> None:
    """기기 파일 크기가 두 번 연속 같을 때까지 대기 (moov 쓰기 마무리). 크기를 못 읽으면 한 번만 쉰다."""
    previous_size = None
    end = time.time() + ANDROID_SIZE_SETTLE_SECONDS
    while time.time() < end:
        size_text = adb_shell(dev_id, f"stat -c %s {remote_file}").strip()
        if not size_text.isdigit():
            time.sleep(1.0)
            return
        if size_text == previous_size and int(size_text) > 0:
            return
        previous_size = size_text
        time.sleep(ANDROID_POLL_SECONDS)


def _wait_until(is_done, timeout_seconds: float) -> bool:
    end = time.time() + timeout_seconds
    while time.time() < end:
        if is_done():
            return True
        time.sleep(ANDROID_POLL_SECONDS)
    return is_done()


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
    p.add_argument("--gif", action="store_true", help="record stop: also make a gif (needs ffmpeg)")


ACTION = Action(name="record", device_use="mutate", run=_app_record, configure=configure,
                help="Screen recording start·stop (iOS simctl · Android screenrecord) — stop also makes a poster (and --gif)",
                example="app record start --device $DEV --out demo  →  app record stop --device $DEV --gif")
