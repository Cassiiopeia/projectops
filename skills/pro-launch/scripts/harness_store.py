"""Keeps the guide (harness) for a recurring site or task in one folder — a new site is just a new folder (projectops#1023).

  ~/.projectops/launch/_machine/harness/<name>/        this whole computer (default)
  ~/.projectops/launch/<owner__repo>/harness/<name>/   this repo only — wins on a name clash

Inside the folder:
  README.md      guide the agent reads, judges and follows (purpose · loop · decision points · when stuck …)
  harness.json   optional. {"description", "match": {"hosts": [...], "urls": [...], "apps": [...], "windows": [...]}, "areas": [...]}
                 when present, attached as `harness` to responses of commands aimed at those URLs·hosts·apps·windows. Without it, list and show only
                 (apps·windows: projectops#1024)
  anything else  optional helper scripts that cut repeated clicks. Scripts support the guide, they do not replace it

The journal is the context of one task, memory (learn) is a one-line conclusion, a harness is a guide + helpers.
No secrets in any file — accounts go in cred.
"""
from __future__ import annotations

import datetime as dt
import json
import locale
import re
from fnmatch import fnmatchcase
from pathlib import Path
from urllib.parse import urlsplit

from common import memory
from common.access import find_secrets
from common.repo_language import read_team_language
from common.state import MACHINE_BUCKET, base_dir, is_scratch_root, repo_unknown, state_dir

DIR_NAME = "harness"
META_FILE = "harness.json"
README_FILE = "README.md"
SEEN_FILE = "harness_seen.json"
SCOPES = ("machine", "repo")
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
MAX_DESCRIPTION = 200
SURFACE_LIMIT = 2         # harnesses attached per response
EXCERPT_LINES = 8         # README excerpt lines attached to a response
EXCERPT_CHARS = 600
FILES_LIMIT = 12          # helper file names attached to a response
# A section with one of these headings is used as the excerpt (otherwise the intro paragraph right under the title)
SUMMARY_HEADINGS = ("요약", "summary", "tl;dr", "tldr")   # 요약 = Korean for "summary"
TEMPLATE_DIR = Path(__file__).resolve().parent / "harness_templates"
LANGUAGES = ("ko", "en")
MATCH_KEYS = ("hosts", "urls", "apps", "windows")
# Areas of app commands. Memory areas (knowledge.AREAS) are per platform (ios·android), so areas treat them as interchangeable
APP_AREA = "app"
APP_PLATFORMS = ("ios", "android")


def machine_dir() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / DIR_NAME


# root > repo harness folder. Called on every response, so git is checked only once
_REPO_DIRS: dict = {}


def repo_dir(root: Path | None) -> Path | None:
    """This repo's harness location. None when the repo is unknown or a temp folder — tidy may remove such buckets."""
    if root is None:
        return None
    key = (str(root), str(base_dir()))
    if key not in _REPO_DIRS:
        if repo_unknown(root) or is_scratch_root(root):
            _REPO_DIRS[key] = None
        else:
            _REPO_DIRS[key] = state_dir("launch", root) / DIR_NAME
    return _REPO_DIRS[key]


def scope_dirs(root: Path | None) -> list[tuple[str, Path]]:
    """Lookup order: repo > this computer. On a name clash the earlier one wins."""
    dirs = []
    repo = repo_dir(root)
    if repo is not None and repo != machine_dir():
        dirs.append(("repo", repo))
    dirs.append(("machine", machine_dir()))
    return dirs


def _string_list(value) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _load_meta(folder: Path) -> tuple[dict, str | None]:
    """harness.json > (content, error). Missing: ({}, None) · broken: ({}, reason) — it stays in the list with the reason shown."""
    f = folder / META_FILE
    if not f.is_file():
        return {}, None
    try:
        data = json.loads(f.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as e:
        return {}, f"{META_FILE} unreadable: {e}"
    if not isinstance(data, dict):
        return {}, f"{META_FILE} must be a JSON object"
    return data, None


def _readme_title(readme: Path) -> str:
    """First README heading (or first text line) — the description when harness.json is missing."""
    try:
        lines = readme.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return ""
    for line in lines:
        text = line.strip()
        if text:
            return text.lstrip("#").strip()[:MAX_DESCRIPTION]
    return ""


def _helper_files(folder: Path) -> list[str]:
    try:
        names = sorted(p.name + ("/" if p.is_dir() else "") for p in folder.iterdir()
                       if p.name not in (README_FILE, META_FILE) and not p.name.startswith("."))
    except OSError:
        return []
    return names[:FILES_LIMIT]


def describe(folder: Path, scope: str) -> dict:
    """One harness folder > list entry."""
    meta, meta_error = _load_meta(folder)
    readme = folder / README_FILE
    match = meta.get("match") if isinstance(meta.get("match"), dict) else {}
    entry = {"name": folder.name, "scope": scope, "path": str(folder),
             "readme": str(readme) if readme.is_file() else None,
             "description": str(meta.get("description") or "").strip()[:MAX_DESCRIPTION]
             or (_readme_title(readme) if readme.is_file() else ""),
             "match": {key: _string_list(match.get(key)) for key in MATCH_KEYS},
             "areas": _string_list(meta.get("areas")),
             "has_meta": (folder / META_FILE).is_file(),
             "files": _helper_files(folder)}
    if meta_error:
        entry["meta_error"] = meta_error
    return entry


def list_all(root: Path | None) -> list[dict]:
    """All harnesses (repo ones hide same-named computer ones). Sorted by name."""
    found: dict[str, dict] = {}
    for scope, d in scope_dirs(root):
        try:
            folders = sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
        except OSError:
            continue
        for folder in folders:
            if folder.name in found:
                found[folder.name].setdefault("shadows", []).append(str(folder))
                continue
            found[folder.name] = describe(folder, scope)
    return [found[name] for name in sorted(found)]


def find(root: Path | None, name: str) -> dict | None:
    return next((e for e in list_all(root) if e["name"] == name), None)


# ── Matching ────────────────────────────────────────────────────────────────
#
# hosts: host names (case-insensitive, * wildcard). Written as `host:port`, the URL port is checked too
# urls : URL patterns (* wildcard). Without a path, the whole site (`/*`) is meant
# Host-only commands (ssh) also match the host part of urls patterns — so the web harness of the same server shows
# apps   : Android package name · iOS bundle ID (case-insensitive, * wildcard) — app commands (projectops#1024)
# windows: desktop window title · program name (case-insensitive, * wildcard). Program names also match without .exe


def _normalize_url(url: str) -> str:
    """Lowercase scheme and host, empty path is / — treats 'https://h:1/' and 'HTTPS://H:1' as equal."""
    parts = urlsplit(url.strip())
    path = parts.path or "/"
    tail = (f"?{parts.query}" if parts.query else "") + (f"#{parts.fragment}" if parts.fragment else "")
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}{tail}"


def _url_pattern(pattern: str) -> str:
    try:
        parts = urlsplit(pattern.strip())
        normalized = _normalize_url(pattern)
    except ValueError:
        return pattern.strip()
    if not parts.scheme or not parts.netloc:
        return pattern.strip()
    return normalized + "*" if not parts.path else normalized


def _pattern_host(pattern: str) -> str | None:
    try:
        return urlsplit(pattern.strip()).hostname
    except ValueError:
        return None


def _host_matches(entry_host: str, host: str | None, port: int | None) -> bool:
    if not host:
        return False
    wanted = entry_host.lower()
    want_port = None
    if wanted.count(":") == 1:
        wanted, _, port_text = wanted.partition(":")
        want_port = int(port_text) if port_text.isdigit() else None
    if not fnmatchcase(host.lower(), wanted):
        return False
    return want_port is None or port is None or want_port == port


def _names(value) -> list[str]:
    """app · window value (one string or several) > names to compare. Empty values are dropped."""
    if isinstance(value, str):
        value = [value]
    return [str(v).strip() for v in (value or []) if v and str(v).strip()]


def _window_names(window) -> list[str]:
    names = _names(window)
    stems = [n[:-4] for n in names if n.lower().endswith(".exe") and len(n) > 4]
    return list(dict.fromkeys([*names, *stems]))


def _name_reason(kind: str, patterns: list[str], names: list[str]) -> str | None:
    for pattern in patterns:
        if any(fnmatchcase(name.lower(), pattern.lower()) for name in names):
            return f"{kind}:{pattern}"
    return None


def area_applies(entry_areas: list[str], area: str | None) -> bool:
    """Harnesses listing areas apply only there. app and ios·android are interchangeable (no filtering when area is unknown)."""
    if not area or not entry_areas or area in entry_areas:
        return True
    if area in APP_PLATFORMS and APP_AREA in entry_areas:
        return True
    return area == APP_AREA and any(a in APP_PLATFORMS for a in entry_areas)


def match_reason(entry: dict, url: str | None = None, host: str | None = None,
                 app=None, window=None) -> str | None:
    """If this harness matches url · host · app · window, the matched rule ("url:<pattern>" · "host:<host>" ·
    "app:<pattern>" · "window:<pattern>"), otherwise None. app · window are one string or several."""
    match = entry["match"]
    reason = _name_reason("app", match.get("apps") or [], _names(app))
    if reason:
        return reason
    reason = _name_reason("window", match.get("windows") or [], _window_names(window))
    if reason:
        return reason
    parsed_host, port, normalized = None, None, None
    if url:
        try:
            parts = urlsplit(url.strip())
            parsed_host, port, normalized = parts.hostname, parts.port, _normalize_url(url)
        except ValueError:   # bad port or IPv6 brackets — counted as no match
            parsed_host, port, normalized = None, None, None
    if normalized:
        for pattern in entry["match"]["urls"]:
            if fnmatchcase(normalized, _url_pattern(pattern)):
                return f"url:{pattern}"
    for target_host in dict.fromkeys(h for h in (parsed_host, host) if h):
        target_port = port if target_host == parsed_host else None
        for entry_host in entry["match"]["hosts"]:
            if _host_matches(entry_host, target_host, target_port):
                return f"host:{entry_host}"
    if host and not url:
        for pattern in entry["match"]["urls"]:
            pattern_host = _pattern_host(pattern)
            if pattern_host and fnmatchcase(host.lower(), pattern_host.lower()):
                return f"url-host:{pattern}"
    return None


def matching(root: Path | None, url: str | None = None, host: str | None = None,
             area: str | None = None, app=None, window=None) -> list[dict]:
    """Harnesses matching url · host · app · window. Harnesses listing areas match only commands in those areas (area_applies)."""
    if not url and not host and not _names(app) and not _names(window):
        return []
    rows = []
    for entry in list_all(root):
        if not area_applies(entry["areas"], area):
            continue
        reason = match_reason(entry, url=url, host=host, app=app, window=window)
        if reason:
            rows.append({**entry, "matched_by": reason})
    return rows


# ── Attaching to responses ───────────────────────────────────────────────────────────


def excerpt(readme: str | Path | None, max_lines: int = EXCERPT_LINES, max_chars: int = EXCERPT_CHARS) -> str:
    """README excerpt: `## Summary` (or `## 요약`) section > intro paragraph under the first title > first section body. Line and character caps."""
    if not readme:
        return ""
    try:
        lines = Path(readme).read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError:
        return ""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in lines:
        heading = re.match(r"^(#{1,6})\s+(.*)$", line.strip())
        if heading and len(heading.group(1)) == 1 and len(sections) == 1 and not any(x.strip() for x in sections[0][1]):
            continue   # skip the document title (H1)
        if heading and len(heading.group(1)) == 2:
            sections.append((heading.group(2).strip().lower(), []))
            continue
        sections[-1][1].append(line.rstrip())
    body = next((b for title, b in sections if title.split(" (")[0] in SUMMARY_HEADINGS), None)
    if body is None:
        body = next((b for _, b in sections if any(x.strip() for x in b)), [])
    kept = [x for x in body if x.strip()][:max_lines]
    text = "\n".join(kept)
    return text if len(text) <= max_chars else text[:max_chars].rstrip() + " …"


def surface(root: Path | None, seen_file: Path, url: str | None = None, host: str | None = None,
            area: str | None = None, mark: bool = True, today: str | None = None,
            app=None, window=None) -> list[dict]:
    """Harnesses to attach to a command response. Once a day per harness — a failed command (mark=False) does not count as shown."""
    now = today or dt.date.today().isoformat()
    rows = []
    for entry in matching(root, url=url, host=host, area=area, app=app, window=window):
        if len(rows) >= SURFACE_LIMIT:
            break
        if memory.seen_today(seen_file, entry["name"], now, mark=False):
            continue
        if mark:
            memory.seen_today(seen_file, entry["name"], now)
        rows.append({"name": entry["name"], "scope": entry["scope"], "description": entry["description"],
                     "readme": entry["readme"], "path": entry["path"], "matched_by": entry["matched_by"],
                     "excerpt": excerpt(entry["readme"]), "files": entry["files"]})
    return rows


# ── Creating ────────────────────────────────────────────────────────────────


def resolve_language(lang: str | None, root: Path | None) -> str:
    """README skeleton language: given value > repo team language (version.yml) > this computer's locale > en."""
    if lang in LANGUAGES:
        return lang
    team = (read_team_language(root) or "").lower() if root else ""
    if team[:2] in LANGUAGES:
        return team[:2]
    try:
        system = (locale.getlocale()[0] or "").lower()
    except (ValueError, TypeError):
        system = ""
    return "ko" if system.startswith("ko") or "korean" in system else "en"


def _readme_skeleton(name: str, description: str, targets_list: list[str], lang: str) -> str:
    template = (TEMPLATE_DIR / f"README.{lang}.md").read_text(encoding="utf-8")
    targets = ", ".join(f"`{t}`" for t in targets_list) or "-"
    return (template.replace("{{name}}", name).replace("{{description}}", description or name)
            .replace("{{targets}}", targets))


def create(root: Path | None, name: str, description: str = "", hosts: list[str] | None = None,
           urls: list[str] | None = None, areas: list[str] | None = None, scope: str = "machine",
           lang: str | None = None, apps: list[str] | None = None, windows: list[str] | None = None) -> dict:
    """Harness folder + harness.json + README skeleton. On failure {"error": code, "message": ...}."""
    hosts, urls, areas = _string_list(hosts or []), _string_list(urls or []), _string_list(areas or [])
    apps, windows = _string_list(apps or []), _string_list(windows or [])
    description = " ".join((description or "").split())
    if not NAME_PATTERN.match(name or ""):
        return {"error": "bad_name", "message": "Names must be letters, digits or ._- (max 40, starting with a letter or digit)"}
    if len(description) > MAX_DESCRIPTION:
        return {"error": "too_long", "message": f"description is {len(description)} characters (max {MAX_DESCRIPTION})"}
    secrets = find_secrets(" ".join([description, *hosts, *urls, *apps, *windows]))
    if secrets:
        return {"error": "secret_detected",
                "message": "Not saved: it contains what looks like a secret: " + ", ".join(secrets)}
    if scope == "repo":
        base = repo_dir(root)
        if base is None:
            return {"error": "repo_unknown", "message": "This folder is not a known repo — use --scope machine or pass --root <repo>"}
    else:
        base = machine_dir()
    existing = find(root, name)
    if existing is not None:
        return {"error": "exists", "message": f"A harness named {name} already exists: {existing['path']}",
                "entry": existing}
    folder = base / name
    language = resolve_language(lang, root)
    match = {"hosts": hosts, "urls": urls}
    # Write app and window fields only when given — web harness harness.json shape stays the same (projectops#1024)
    match.update({k: v for k, v in (("apps", apps), ("windows", windows)) if v})
    meta = {"description": description, "match": match, "areas": areas}
    folder.mkdir(parents=True, exist_ok=False)
    (folder / META_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (folder / README_FILE).write_text(_readme_skeleton(name, description, [*urls, *hosts, *apps, *windows], language),
                                      encoding="utf-8")
    return {"entry": describe(folder, scope), "language": language}
