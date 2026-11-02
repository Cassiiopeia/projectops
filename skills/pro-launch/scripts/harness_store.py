"""반복하는 사이트·작업의 안내서(하네스)를 폴더 하나로 둔다 — 새 사이트는 폴더를 만드는 것으로 끝난다 (projectops#1023).

  ~/.projectops/launch/_machine/harness/<name>/        이 컴퓨터 전체 (기본)
  ~/.projectops/launch/<owner__repo>/harness/<name>/   이 레포만 — 이름이 같으면 이쪽이 이긴다

폴더 안:
  README.md      agent 가 읽고 판단하며 따라가는 안내서 (목적 · 루프 · 판단 지점 · 막혔을 때 …)
  harness.json   선택. {"description", "match": {"hosts": [...], "urls": [...], "apps": [...], "windows": [...]}, "areas": [...]}
                 있으면 그 주소·호스트·앱·창으로 향하는 명령의 응답에 `harness` 로 실린다. 없으면 목록·보기만 된다
                 (apps·windows: projectops#1024)
  그 밖          반복 클릭을 줄이는 도우미 스크립트 (선택). 스크립트는 안내서를 돕는 것이지 대신하지 않는다

일지(journal)는 작업 한 건의 맥락, 기억(learn)은 한 줄 결론, 하네스는 안내서 + 도우미다.
비밀값은 어느 파일에도 쓰지 않는다 — 계정은 cred 에 둔다.
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
SURFACE_LIMIT = 2         # 한 응답에 싣는 하네스 수
EXCERPT_LINES = 8         # 응답에 싣는 README 발췌 줄 수
EXCERPT_CHARS = 600
FILES_LIMIT = 12          # 응답에 싣는 도우미 파일 이름 수
# 이 제목의 절이 있으면 발췌로 쓴다 (없으면 제목 바로 아래 소개 문단)
SUMMARY_HEADINGS = ("요약", "summary", "tl;dr", "tldr")   # 요약 = 한국어 "요약"
TEMPLATE_DIR = Path(__file__).resolve().parent / "harness_templates"
LANGUAGES = ("ko", "en")
MATCH_KEYS = ("hosts", "urls", "apps", "windows")
# app 명령의 영역. 기억 영역(knowledge.AREAS)은 플랫폼별(ios·android)이라 areas 에서 서로 통하게 한다
APP_AREA = "app"
APP_PLATFORMS = ("ios", "android")


def machine_dir() -> Path:
    return base_dir() / "launch" / MACHINE_BUCKET / DIR_NAME


# 루트 > 레포 하네스 폴더. 응답마다 불리므로 git 을 한 번만 본다
_REPO_DIRS: dict = {}


def repo_dir(root: Path | None) -> Path | None:
    """이 레포의 하네스 자리. 레포를 모르거나 임시 폴더면 None — 그런 버킷은 tidy 가 지울 수 있다."""
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
    """찾는 순서: 레포 > 이 컴퓨터. 같은 이름이면 앞의 것이 이긴다."""
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
    """harness.json > (내용, 오류). 없으면 ({}, None) · 깨졌으면 ({}, 이유) — 목록에서 빠지지 않고 이유가 보인다."""
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
    """README 의 첫 제목(없으면 첫 글줄) — harness.json 이 없을 때의 설명."""
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
    """하네스 폴더 하나 > 목록 항목."""
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
    """모든 하네스 (레포 것이 같은 이름의 컴퓨터 것을 가린다). 이름순."""
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


# ── 맞추기 ────────────────────────────────────────────────────────────────
#
# hosts: 호스트 이름(대소문자 무시, * 와일드카드). `호스트:포트` 로 적으면 주소의 포트까지 본다
# urls : 주소 패턴(* 와일드카드). 경로 없이 적으면 그 사이트 전체(`/*`)로 본다
# 호스트만 아는 명령(ssh)은 urls 패턴의 호스트 부분과도 맞춘다 — 같은 서버의 웹 하네스가 보이게
# apps   : Android 패키지명 · iOS 번들 ID (대소문자 무시, * 와일드카드) — app 명령 (projectops#1024)
# windows: desktop 창 제목 · 프로그램 이름 (대소문자 무시, * 와일드카드). 프로그램 이름은 .exe 를 떼고도 맞춘다


def _normalize_url(url: str) -> str:
    """scheme · 호스트는 소문자, 빈 경로는 / — 'https://h:1/' 와 'HTTPS://H:1' 을 같게 본다."""
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
    """app · window 값(문자열 하나 또는 여럿) > 비교할 이름들. 빈 값은 뺀다."""
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
    """areas 를 적은 하네스는 그 영역에만. app 과 ios·android 는 서로 통한다 (area 를 모르면 거르지 않는다)."""
    if not area or not entry_areas or area in entry_areas:
        return True
    if area in APP_PLATFORMS and APP_AREA in entry_areas:
        return True
    return area == APP_AREA and any(a in APP_PLATFORMS for a in entry_areas)


def match_reason(entry: dict, url: str | None = None, host: str | None = None,
                 app=None, window=None) -> str | None:
    """이 하네스가 url · host · app · window 에 맞으면 맞은 규칙("url:<패턴>" · "host:<호스트>" ·
    "app:<패턴>" · "window:<패턴>"), 아니면 None. app · window 는 문자열 하나 또는 여럿."""
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
        except ValueError:   # 잘못된 포트·IPv6 괄호 — 맞추지 못한 것으로 친다
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
    """url · host · app · window 에 맞는 하네스. areas 를 적은 하네스는 그 영역의 명령에만 맞는다 (area_applies)."""
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


# ── 응답에 싣기 ───────────────────────────────────────────────────────────


def excerpt(readme: str | Path | None, max_lines: int = EXCERPT_LINES, max_chars: int = EXCERPT_CHARS) -> str:
    """README 발췌: `## 요약`(Summary) 절 > 첫 제목 아래 소개 문단 > 첫 절 본문. 줄·글자 상한."""
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
            continue   # 문서 제목(H1)은 건너뛴다
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
    """명령 응답에 실을 하네스. 하네스마다 하루 한 번 — 실패한 명령(mark=False)은 '보여 줌'으로 치지 않는다."""
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


# ── 만들기 ────────────────────────────────────────────────────────────────


def resolve_language(lang: str | None, root: Path | None) -> str:
    """README 뼈대 언어: 지정값 > 레포 팀 언어(version.yml) > 이 컴퓨터 로캘 > en."""
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
    """하네스 폴더 + harness.json + README 뼈대. 실패하면 {"error": 코드, "message": ...}."""
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
    # 앱·창 칸은 준 것만 적는다 — 웹 하네스의 harness.json 모양은 그대로 (projectops#1024)
    match.update({k: v for k, v in (("apps", apps), ("windows", windows)) if v})
    meta = {"description": description, "match": match, "areas": areas}
    folder.mkdir(parents=True, exist_ok=False)
    (folder / META_FILE).write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (folder / README_FILE).write_text(_readme_skeleton(name, description, [*urls, *hosts, *apps, *windows], language),
                                      encoding="utf-8")
    return {"entry": describe(folder, scope), "language": language}
