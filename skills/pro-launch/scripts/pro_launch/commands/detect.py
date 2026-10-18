"""`detect` — 무엇을 띄울 수 있는지. 마커 파일만 보고 구조를 알아맞히지 않는다."""
from __future__ import annotations

import re
from pathlib import Path

from common.access import load_access
from common.proc import run

from pro_launch.registry import Command
from pro_launch.runtime.app_identity import android_package as _android_package
from pro_launch.runtime.app_identity import find_flutter_root as _find_flutter_root
from pro_launch.runtime.app_identity import ios_bundle_id as _ios_bundle_id
from pro_launch.runtime.browser import playwright_state
from pro_launch.runtime.context import state_home
from pro_launch.runtime.devices import list_devices
from pro_launch.runtime.output import out


KINDS = ("app", "web", "server")


# projectops 프로젝트 타입 → 띄울 수 있는 것. 한 타입이 여럿을 줄 수 있다.
_TYPE_TO_KIND = {
    "flutter": ["app"],
    "react-native": ["app"],
    "react-native-expo": ["app"],
    "react": ["web"],
    "next": ["web"],
    "node": ["web", "server"],
    "spring": ["server"],
    "python": ["server"],
    "basic": [],
}


def _version_yml_types(root: Path) -> list[str]:
    """version.yml의 project_types. yaml 파서를 쓰지 않는다 — 표준 라이브러리만으로 돈다."""
    f = root / "version.yml"
    if not f.is_file():
        return []
    try:
        body = f.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []
    m = re.search(r"project_types:\s*\n((?:\s*-\s*\S+\n?)+)", body)
    if m:
        return re.findall(r"-\s*([A-Za-z0-9_-]+)", m.group(1))
    m = re.search(r"project_types:\s*\[([^\]]*)\]", body)
    if m:
        return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()]
    return []


def _marker_kinds(root: Path) -> dict:
    """파일로 추론한다. version.yml이 없는 레포(대부분의 남의 프로젝트)를 위한 길이다."""
    found: dict[str, list[str]] = {}

    def add(kind: str, why: str):
        found.setdefault(kind, []).append(why)

    for pub in list(root.rglob("pubspec.yaml"))[:20]:
        if "build" in pub.parts or ".dart_tool" in pub.parts:
            continue
        add("app", str(pub.relative_to(root)))
        break

    for pkg in list(root.rglob("package.json"))[:20]:
        if "node_modules" in pkg.parts:
            continue
        try:
            body = pkg.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(pkg.relative_to(root))
        if re.search(r'"(react|next|vue|svelte|@angular/core)"\s*:', body):
            add("web", rel)
        if re.search(r'"react-native"\s*:', body):
            add("app", rel)
        if re.search(r'"(express|fastify|@nestjs/core|koa)"\s*:', body):
            add("server", rel)

    for marker, why in (("build.gradle", "spring"), ("build.gradle.kts", "spring"),
                        ("pom.xml", "maven"), ("pyproject.toml", "python"),
                        ("requirements.txt", "python"), ("manage.py", "django")):
        for f in list(root.rglob(marker))[:10]:
            if "build" in f.parts or "node_modules" in f.parts or ".venv" in f.parts:
                continue
            # Flutter 앱의 android/build.gradle을 서버로 오해하면 안 된다
            if marker.startswith("build.gradle") and "android" in f.parts:
                continue
            add("server", f"{f.relative_to(root)} ({why})")
            break
    return found


def detect_kinds(root: Path) -> dict:
    """version.yml 선언 → 마커 파일 순. 선언은 '무엇인가'일 뿐이라 agent 가 확인한다."""
    types = _version_yml_types(root)
    if types:
        kinds: list[str] = []
        for ty in types:
            for k in _TYPE_TO_KIND.get(ty, []):
                if k not in kinds:
                    kinds.append(k)
        if kinds:
            return {"kinds": kinds, "source": "version.yml", "project_types": types}
    found = _marker_kinds(root)
    kinds = [k for k in KINDS if k in found]
    return {"kinds": kinds, "source": "marker" if kinds else "none", "evidence": found}


def _app_base_urls(root: Path) -> list[str]:
    """**Flutter 앱 전용.** .env와 dart 설정에서 앱이 바라보는 주소를 모은다."""
    found: list[str] = []
    candidates = [root / ".env"]
    candidates += list((root / "lib" / "core").rglob("*config*.dart"))
    for f in candidates[:12]:
        if not f.exists() or not f.is_file():
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r'https?://[\w.\-]+(?::\d+)?[\w./\-]*', text):
            url = m.group(0).rstrip('/')
            if url not in found:
                found.append(url)
    return found[:8]


def _web_base_urls(root: Path) -> list[str]:
    """웹이 뜨는 주소 후보. 없으면 사용자에게 묻는 수밖에 없다."""
    urls: list[str] = []
    for f in list(root.rglob("package.json"))[:20]:
        if "node_modules" in f.parts:
            continue
        try:
            body = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for m in re.finditer(r"-p\s*(\d{4,5})|--port[= ](\d{4,5})", body):
            u = f"http://localhost:{m.group(1) or m.group(2)}"
            if u not in urls:
                urls.append(u)
    for env in (".env", ".env.local", ".env.development"):
        f = root / env
        if f.is_file():
            try:
                for m in re.finditer(r"^[A-Z_]*URL[A-Z_]*=(https?://\S+)",
                                     f.read_text(encoding="utf-8", errors="ignore"), re.M):
                    if m.group(1) not in urls:
                        urls.append(m.group(1))
            except OSError:
                pass
    # 흔한 기본값을 마지막에 둔다 — 못 찾았을 때의 출발점
    for u in ("http://localhost:3000", "http://localhost:5173"):
        if u not in urls:
            urls.append(u)
    return urls[:6]


def cmd_detect(args) -> int:
    """무엇을 띄울 수 있는지. 마커 파일·기기·브라우저 준비 상태만 본다."""
    start = Path(args.path).resolve()
    git_root = run(["git", "-C", str(start), "rev-parse", "--show-toplevel"]).strip()
    root = Path(git_root) if git_root else start

    det = detect_kinds(root)
    # 부르는 쪽이 이미 안다면(확인해 적어 둔 타겟 등) 그 종류의 정보를 모은다 — 감지를 덮는다
    if getattr(args, "kinds", None):
        want = [k.strip() for k in args.kinds.split(",") if k.strip()]
        bad = [k for k in want if k not in KINDS]
        if bad:
            return out({"ok": False, "code": "unknown_kind",
                        "error": f"모르는 종류: {', '.join(bad)}", "hint": " · ".join(KINDS)})
        det = {**det, "kinds": want, "source": "given"}
    kinds = det["kinds"]
    payload: dict = {"root": str(root), "kinds": kinds, "source": det["source"],
                     "state_dir": str(state_home(root))}
    for k in ("project_types", "evidence"):
        if det.get(k):
            payload[k] = det[k]

    if "app" in kinds:
        app_root = _find_flutter_root(root)
        payload["app"] = {
            "flutter_root": str(app_root) if app_root else None,
            "android_package": _android_package(app_root) if app_root else None,
            "ios_bundle_id": _ios_bundle_id(app_root) if app_root else None,
            "base_urls": _app_base_urls(app_root) if app_root else [],
            "devices": list_devices(),
        }
    if "web" in kinds:
        payload["web"] = {"base_urls": _web_base_urls(root), "playwright": playwright_state()}
    if "server" in kinds:
        # 설정이 어디 있고 어떻게 붙는지는 **여기서 맞히지 않는다** (#589).
        saved = load_access(root)
        bu = saved.get("base_url")
        payload["server"] = {
            "base_url": bu.get("url") if isinstance(bu, dict) else bu,
            "access_recorded": sorted(saved) or None,
        }

    if det["source"] == "version.yml":
        payload["confirm"] = ("이 kinds 는 version.yml 선언에서 나왔습니다 — 서버가 화면을 직접 "
                              "뿌리면 web 도 띄울 수 있습니다. 코드를 보고 판단하세요")

    nxt = None
    if not kinds:
        nxt = "무엇을 띄울지 알 수 없습니다 — 코드를 보고 app·web·server 중 무엇인지 판단하세요"
    elif "app" in kinds and not (payload["app"]["devices"]["android"]
                                 or payload["app"]["devices"]["ios_booted"]):
        nxt = "devices  # 기기가 없습니다. AVD 나 시뮬레이터를 부팅하세요"
    elif "web" in kinds and not payload["web"]["playwright"]["ready"]:
        nxt = "web setup  # 브라우저(약 100MB)를 받습니다. 먼저 사용자에게 물어보세요"
    payload["summary"] = f"{root.name}: {'·'.join(kinds) if kinds else '없음'} ({det['source']})"
    payload["next"] = nxt
    return out(payload)


def configure_detect(p) -> None:
    p.add_argument("--path", default=".", help="탐색 시작 경로")
    p.add_argument("--kinds", default=None,
                   help="app,web,server 중 정보를 모을 것 (감지 대신 — 부르는 쪽이 이미 알 때)")


COMMANDS = [
    Command(name="detect", help="무엇을 띄울 수 있는지 (마커 파일 · 기기 · 브라우저)", run=cmd_detect,
            configure=configure_detect),
]
