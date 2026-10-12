"""`http` — 단건 HTTP 요청."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from common.access import load_access
from common.http import request as http_request

from pro_launch.registry import Command
from pro_launch.runtime.context import project_root
from pro_launch.runtime.creds import load_cred
from pro_launch.runtime.output import out, set_area, use_access


def cmd_http(args) -> int:
    """HTTP 한 건. 경로만 주면 access 의 base_url 에 붙인다 — 판정은 부르는 쪽이 한다."""
    set_area("server", project_root(args))
    root = project_root(args)
    url = args.url
    if not re.match(r"https?://", url):
        # 경로만 주면 적어 둔 base_url 에 붙인다. 코드에서 짐작하지 않는다.
        bu = load_access(root).get("base_url")
        base = bu.get("url") if isinstance(bu, dict) else bu
        if not base:
            return out({"ok": False, "code": "base_url_required",
                        "error": f"'{url}' 는 전체 주소가 아니고, 적어 둔 base_url 도 없습니다",
                        "next": "access set --key base_url --json '{\"url\":\"http://...\"}'"})
        url = base.rstrip("/") + "/" + url.lstrip("/")
        use_access(root, "base_url")

    headers = {"Accept": "application/json"}
    cred, err = load_cred(getattr(args, "cred", None))
    if err:
        return out(err)
    if cred:
        # 저장된 토큰·계정으로 Authorization 을 만든다 (직접 준 --header 가 있으면 그것이 이긴다)
        if cred.get("token"):
            headers["Authorization"] = f"Bearer {cred['token']}"
        elif cred.get("username") and cred.get("password"):
            import base64
            headers["Authorization"] = "Basic " + base64.b64encode(
                f"{cred['username']}:{cred['password']}".encode()).decode()
    for h in args.header or []:
        if ":" not in h:
            return out({"ok": False, "code": "bad_header",
                        "error": f"헤더 '{h}' 는 '이름: 값' 형식이어야 합니다"})
        k, v = h.split(":", 1)
        headers[k.strip()] = v.strip()
    data = None
    if args.data is not None:
        if args.data.startswith("@"):
            data_f = Path(args.data[1:])
            if not data_f.is_file():
                return out({"ok": False, "code": "data_file_not_found",
                            "error": f"--data 파일이 없습니다: {data_f}",
                            "next": "@ 뒤 경로를 확인한다 (본문 자체가 @ 로 시작하면 파일에 담아 @파일 로 넘긴다)"})
            text = data_f.read_text(encoding="utf-8")
        else:
            text = args.data
        data = text.encode("utf-8")
        try:
            json.loads(text)
            headers.setdefault("Content-Type", "application/json")
        except json.JSONDecodeError:
            pass

    r = http_request(args.method.upper(), url, headers, data, timeout=args.timeout)
    raw = r.pop("raw", None)
    if not r["ok"]:
        return out(r)
    saved = None
    if args.save:
        run_dir = os.environ.get("RUN_DIR")
        target = Path(args.save) if (os.sep in args.save or "/" in args.save or not run_dir) \
            else Path(run_dir) / "http" / args.save
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw or b"")
        saved = str(target)
    ok = args.expect_status is None or r["status"] == args.expect_status
    return out({
        "ok": ok, "code": "ok" if ok else "unexpected_status",
        "method": args.method.upper(), "url": url, "status": r["status"],
        # 요청 헤더 값은 되돌려 주지 않는다 — Authorization 이 기록에 남는다
        "request_headers": sorted(headers),
        "headers": r["headers"], "json": r["json"], "text": r["text"],
        "elapsed_ms": r["elapsed_ms"], "saved": saved,
        "summary": f"{args.method.upper()} {url} → {r['status']} ({r['elapsed_ms']}ms)",
    })


def configure_http(p) -> None:
    p.add_argument("--method", default="GET")
    p.add_argument("--url", required=True, help="전체 주소 또는 경로(→ access 의 base_url 에 붙인다)")
    p.add_argument("--header", action="append", default=None, help="'이름: 값' — 여러 번")
    p.add_argument("--cred", default=None, help="저장된 토큰·계정으로 Authorization 을 만든다 (cred list)")
    p.add_argument("--data", default=None, help="본문. @파일 로 파일을 읽는다")
    p.add_argument("--save", default=None, help="응답 본문을 저장 (이름이면 $RUN_DIR/http/ 아래)")
    p.add_argument("--expect-status", type=int, default=None, help="다르면 ok:false")
    p.add_argument("--timeout", type=int, default=30)
    p.add_argument("--root", default=".")


COMMANDS = [
    Command(name="http", help="단건 HTTP 요청", run=cmd_http,
            configure=configure_http),
]
