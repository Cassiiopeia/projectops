"""`app type` — 포커스된 입력창에 글자를 넣는다."""
from __future__ import annotations

import os
import subprocess

from common.proc import sdk_tool

import credentials

from pro_launch.registry import Action
from pro_launch.runtime.creds import cred_field
from pro_launch.runtime.devices import no_device_response, pick_device
from pro_launch.runtime.output import out


def _app_type(args) -> int:
    """기기 화면의 포커스된 입력창에 글자를 넣는다. 로그인 정보는 저장된 자격증명에서 꺼내 쓴다.

    값은 명령줄이 아니라 표준입력으로만 기기에 보낸다 (호스트 `ps` 에 남지 않는다).
    Android 만 된다 — iOS 는 시뮬레이터에 텍스트를 넣는 공식 명령이 없다.
    """
    if getattr(args, "cred", None):
        value, err = cred_field(args.cred, getattr(args, "cred_field", None))
        if err:
            return out(err)
    elif getattr(args, "text_env", None):
        if args.text_env not in os.environ:
            return out({"ok": False, "code": "env_not_set", "error": f"환경변수 {args.text_env} 가 비어 있습니다"})
        value = os.environ[args.text_env]
    else:
        return out({"ok": False, "code": "text_required",
                    "error": "--cred 또는 --text-env 가 필요합니다 (값을 --text 로 적지 않는다 — 기록에 평문으로 남는다)",
                    "next": "cred list  # 저장된 로그인 정보"})
    platform, dev_id, dev = pick_device(args.device)
    if not platform:
        return no_device_response(dev, args.device)
    if platform != "android":
        return out({"ok": False, "code": "ios_text_unsupported",
                    "error": "iOS 시뮬레이터에는 텍스트를 넣는 공식 명령이 없다",
                    "next": "프로젝트의 E2E 도구(Maestro 등)를 쓰거나 사용자에게 직접 입력을 부탁한다"})
    if not value.isascii():
        return out({"ok": False, "code": "non_ascii_unsupported",
                    "error": "adb input text 는 ASCII 만 받는다 (한글 불가)",
                    "next": "영문·숫자 값으로 대체하거나 ADBKeyboard 같은 IME 를 설치한다"})
    adb = sdk_tool("adb")
    if not adb:
        return out({"ok": False, "code": "adb_missing", "error": "adb 를 찾지 못했습니다"})
    # 공백은 `%s`. 값은 표준입력으로 읽어 따옴표 안에서만 쓴다 (셸 메타문자가 해석되지 않는다)
    payload = value.replace(" ", "%s") + "\n"
    try:
        r = subprocess.run([adb, "-s", dev_id, "shell", 'IFS= read -r T; input text "$T"'],
                           input=payload, capture_output=True, text=True, timeout=30)
        if r.returncode == 0 and getattr(args, "submit", False):
            subprocess.run([adb, "-s", dev_id, "shell", "input", "keyevent", "66"],
                           capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return out({"ok": False, "code": "app_type_timeout", "error": "기기 응답 없음 (30초)"})
    entry = {"password": value, "token": value}
    ok = r.returncode == 0
    return out({"ok": ok, "code": "ok" if ok else "app_type_failed", "device": dev_id,
                "chars": len(value), "submitted": bool(getattr(args, "submit", False)) and ok,
                "error": credentials.mask((r.stderr or "").strip(), entry)[:300] or None,
                "summary": f"{len(value)}자 입력" + (" + Enter" if getattr(args, "submit", False) and ok else ""),
                "next": "app shot  # 입력됐는지 화면으로 확인한다 (비밀번호 칸은 가려져 보인다)"})


def configure(p) -> None:
    p.add_argument("--cred", default=None, help="type: 저장된 로그인 정보 이름 (cred list)")
    p.add_argument("--cred-field", dest="cred_field", default=None, help="type: 넣을 필드 (기본 password, 예: account)")
    p.add_argument("--text-env", dest="text_env", default=None, help="type: 값을 읽을 환경변수 (일회용)")
    p.add_argument("--submit", action="store_true", help="type: 입력 뒤 Enter")


ACTION = Action(name="type", run=_app_type, configure=configure)
