"""`detect` — what can be launched. Looks only at marker files; does not guess the structure."""
from __future__ import annotations

import re
from pathlib import Path

from common.access import load_access
from common.proc import run
from common.project_types import launch_kinds_by_type

from pro_launch.registry import Command
from pro_launch.runtime.app_identity import android_package as _android_package
from pro_launch.runtime.app_identity import find_flutter_root as _find_flutter_root
from pro_launch.runtime.app_identity import ios_bundle_id as _ios_bundle_id
from pro_launch.runtime.browser import playwright_state
from pro_launch.runtime.context import state_home
from pro_launch.runtime.devices import list_devices
from pro_launch.runtime.output import out


KINDS = ("app", "web", "server")


# projectops project type → what can be launched (registry launch_kinds, #1244). One type can yield several.
# "next" was merged into react in v4.1.0; old version.yml files may still name it.
_TYPE_TO_KIND = {**launch_kinds_by_type(), "next": ["web"]}


def _version_yml_types(root: Path) -> list[str]:
    """project_types from version.yml. No yaml parser — runs on the standard library only."""
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
    """Infer from files. The path for repos without version.yml (most other people's projects)."""
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
            # A Flutter app's android/build.gradle must not be mistaken for a server
            if marker.startswith("build.gradle") and "android" in f.parts:
                continue
            add("server", f"{f.relative_to(root)} ({why})")
            break
    return found


def detect_kinds(root: Path) -> dict:
    """version.yml declaration → marker files. A declaration only says 'what it is', so the agent confirms."""
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
    """**Flutter apps only.** Collect the addresses the app points at from .env and dart config."""
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
    """Candidate addresses where the web app runs. If none, the only option is to ask the user."""
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
    # Common defaults go last — a starting point when nothing was found
    for u in ("http://localhost:3000", "http://localhost:5173"):
        if u not in urls:
            urls.append(u)
    return urls[:6]


def cmd_detect(args) -> int:
    """What can be launched. Looks only at marker files and device/browser readiness."""
    start = Path(args.path).resolve()
    git_root = run(["git", "-C", str(start), "rev-parse", "--show-toplevel"]).strip()
    root = Path(git_root) if git_root else start

    det = detect_kinds(root)
    # If the caller already knows (a confirmed, recorded target etc.), collect info for that kind — overrides detection
    if getattr(args, "kinds", None):
        want = [k.strip() for k in args.kinds.split(",") if k.strip()]
        bad = [k for k in want if k not in KINDS]
        if bad:
            return out({"ok": False, "code": "unknown_kind",
                        "error": f"Unknown kind: {', '.join(bad)}", "hint": " · ".join(KINDS)})
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
        # Where config lives and how to connect is **not guessed here** (#589).
        saved = load_access(root)
        bu = saved.get("base_url")
        payload["server"] = {
            "base_url": bu.get("url") if isinstance(bu, dict) else bu,
            "access_recorded": sorted(saved) or None,
        }

    if det["source"] == "version.yml":
        payload["confirm"] = ("These kinds come from the version.yml declaration — if the server renders "
                              "pages itself, web can be launched too. Check the code to decide")

    nxt = None
    if not kinds:
        nxt = "Cannot tell what to launch — read the code to decide between app, web and server"
    elif "app" in kinds and not (payload["app"]["devices"]["android"]
                                 or payload["app"]["devices"]["ios_booted"]):
        nxt = "devices  # no device. Boot an AVD or a simulator"
    elif "web" in kinds and not payload["web"]["playwright"]["ready"]:
        nxt = "web setup  # downloads a browser (about 100MB). Ask the user first"
    payload["summary"] = f"{root.name}: {'·'.join(kinds) if kinds else 'none'} ({det['source']})"
    payload["next"] = nxt
    return out(payload)


def configure_detect(p) -> None:
    p.add_argument("--path", default=".", help="Path to start searching from")
    p.add_argument("--kinds", default=None,
                   help="Which of app,web,server to gather info for (instead of detecting — when the caller already knows)")


COMMANDS = [
    Command(name="detect", help="What can be launched (marker files · devices · browser)", run=cmd_detect,
            configure=configure_detect),
]
