#!/usr/bin/env python3
# ===================================================================
# version_manager.py — project version management (Python port of version_manager.sh)
# ===================================================================
#
# Cross-platform (Windows/macOS/Linux), standard library only — no yq/jq.
# The old version_manager.sh is a shim that delegates here; the call contract is the same:
#   - result on the last stdout line, logs on stderr (works with the workflows' `| tail -n 1`)
#   - commands: get | get-code | increment | increment-code | set | sync | validate
#
# version.yml schema (v4.1.0 SSOT):
#   - the project_types array is the only source (first item is primary)
#   - the singular project_type key is removed: ignored with a warning if present, singular-only legacy fails explicitly
#   - project_paths map supports monorepo subfolders
# ===================================================================

# Lets the macOS default python3 (3.9) start without evaluating `str | None` annotations (#695)
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# \Z: `$` allows a trailing newline ("1.2.3\n"), so it is not used. Leading zeros (01.02.03) are rejected too (#685)
VERSION_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)\Z")
VERSION_YML = Path("version.yml")


class VersionError(Exception):
    """Update/read failure. Used to end with an error message and exit 1 instead of a success log (#678)."""


# ── Logs (stderr — same emoji as .sh) ─────────────────────────────────
def log_info(msg): print(f"ℹ️  {msg}", file=sys.stderr)
def log_success(msg): print(f"✅ {msg}", file=sys.stderr)
def log_error(msg): print(f"❌ {msg}", file=sys.stderr)
def log_warning(msg): print(f"⚠️  {msg}", file=sys.stderr)
def log_debug(msg):
    if os.environ.get("DEBUG") == "true":
        print(f"🔍 DEBUG: {msg}", file=sys.stderr)


# ── File read/write (byte-preserving — newlines and encoding untouched, #675 #682) ──
def read_text(path: Path) -> str:
    """Read without newline conversion (CRLF kept). A BOM character is kept too."""
    try:
        return path.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise VersionError(f"Could not read {path.as_posix()}: {e}")


def write_text(path: Path, content: str) -> bool:
    """Write without newline conversion. If content is already the same, skip and return False (idempotent — no mtime/diff noise)."""
    data = content.encode("utf-8")
    try:
        if path.is_file() and path.read_bytes() == data:
            return False
        path.write_bytes(data)
    except OSError as e:
        raise VersionError(f"Could not write {path.as_posix()}: {e} (check file permissions)")
    return True


def detect_eol(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def split_lines(text: str) -> list:
    """Split lines keeping the newline at the end of each. ''.join(result) == text always holds."""
    return [p for p in re.split(r"(?<=\n)", text) if p != ""]


def split_eol(piece: str):
    """Split one line piece into (body, newline)."""
    if piece.endswith("\r\n"):
        return piece[:-2], "\r\n"
    if piece.endswith("\n"):
        return piece[:-1], "\n"
    return piece, ""


def yml_lines():
    # Newlines and the first-line BOM are stripped only for reading (each write function preserves them)
    text = read_text(VERSION_YML)
    if text.startswith("\ufeff"):
        text = text[1:]
    return [split_eol(p)[0] for p in split_lines(text)]


def _unquote(value: str) -> str:
    """Strip surrounding whitespace and one layer of quotes (" or ')."""
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def parse_project_types() -> list:
    """Read project_types. Supported forms: inline ["a","b"] and block list (- a). Missing -> [].

    Unsupported notation is reported as an error instead of silently becoming basic (#684).
    """
    if not VERSION_YML.is_file():
        return []
    lines = yml_lines()
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^project_types:[ \t]*(.*?)[ \t]*$", line)
        if not m:
            continue
        rest = m.group(1)
        if rest.startswith("["):
            inline = re.match(r"^\[([^\]]*)\][ \t]*(#.*)?$", rest)
            if not inline:
                raise VersionError("version.yml project_types supports only a one-line array ([\"a\", \"b\"]) or a block list (- a).")
            return [_unquote(t) for t in inline.group(1).split(",") if t.strip()]
        if rest and not rest.startswith("#"):
            raise VersionError(f"Unsupported version.yml project_types notation: '{rest}' (use an array or a block list)")
        # Empty value: read the block list on the following lines
        types = []
        for nxt in lines[idx + 1:]:
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                continue
            item = re.match(r"^\s*-[ \t]+(.*?)[ \t]*$", nxt)
            if not item:
                break
            raw = item.group(1)
            # Strip end-of-line comments after quoted values ("node"  # note) and after unquoted values
            qm = re.match(r"^(\"[^\"]*\"|'[^']*')[ \t]*(#.*)?$", raw)
            types.append(_unquote(qm.group(1)) if qm else re.sub(r"[ \t]+#.*$", "", raw).strip())
        return [t for t in types if t]
    return []


def parse_legacy_single_type() -> str:
    """Pre-v4.1.0 singular project_type key (for detection only — the value is not used)."""
    for line in yml_lines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^project_type:\s*[\"']?([A-Za-z0-9_-]+)", line)
        if m:
            return m.group(1)
    return ""


def _ensure_inside_repo(path_str: str, t: str) -> str:
    """Reject project_paths values pointing outside the repo — version file writes must not touch files outside it (#673)."""
    p = Path(path_str)
    if p.is_absolute() or ".." in p.parts:
        raise VersionError(f"version.yml project_paths.{t} must be a relative path inside the repository: '{path_str}'")
    root = Path.cwd().resolve()
    try:
        # Compare after resolve to also catch symlinks pointing outside the repo
        (root / p).resolve().relative_to(root)
    except ValueError:
        raise VersionError(f"version.yml project_paths.{t} points outside the repository: '{path_str}'")
    return path_str


def get_type_path(t: str) -> str:
    """project_paths.<type> — '.' when the key is missing (legacy: repo root). Double-quoted, single-quoted or unquoted values all work."""
    in_paths = False
    for line in yml_lines():
        if line.lstrip().startswith("#") or not line.strip():
            continue
        pm = re.match(r"^project_paths:[ \t]*(.*?)[ \t]*$", line)
        if pm:
            rest = pm.group(1)
            if rest and not rest.startswith("#"):
                raise VersionError(f"Unsupported version.yml project_paths notation: '{rest}' (use a block map 'type: path')")
            in_paths = True
            continue
        if in_paths:
            if re.match(r"^\S", line):
                break
            m = re.match(r"^\s+([A-Za-z0-9_-]+):[ \t]*(\"[^\"]*\"|'[^']*'|[^#\s]*)[ \t]*(#.*)?$", line)
            if not m:
                raise VersionError(f"Could not read version.yml project_paths entry: '{line.strip()}' (use the type: path form)")
            if m.group(1) == t:
                return _ensure_inside_repo(_unquote(m.group(2)) or ".", t)
    return "."


def get_yml_version():
    """Read the version: value. A v prefix is allowed (normalized); unreadable -> None (never replaced with 0.0.0 — #678)."""
    for line in yml_lines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^version:\s*[\"']?[vV]?([0-9][0-9.]*)", line)
        if m:
            return m.group(1)
    return None


def set_yml_field(pattern: str, new_line_fn):
    """Replace the first line matching pattern with new_line_fn(match). Returns whether it matched. Newlines and BOM are preserved."""
    text = read_text(VERSION_YML)
    # The first-line BOM is excluded only for matching and written back as is
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    pieces = split_lines(text[len(bom):])
    for i, piece in enumerate(pieces):
        body, eol = split_eol(piece)
        if body.lstrip().startswith("#"):
            continue
        m = re.match(pattern, body)
        if m:
            pieces[i] = new_line_fn(m) + eol
            write_text(VERSION_YML, bom + "".join(pieces))
            return True
    return False


# ── Config read (.sh read_version_config equivalent, v4.1.0 SSOT) ───────────
class Config:
    def __init__(self, require_version=True):
        if not VERSION_YML.is_file():
            log_error("version.yml not found!")
            sys.exit(1)

        log_debug("Parsing version.yml (stdlib)")

        self.types = parse_project_types()
        legacy = parse_legacy_single_type()

        if self.types:
            if legacy:
                log_warning("The singular project_type key is ignored since v4.1.0 — remove that line from version.yml (the project_types array is the only source)")
            self.primary = self.types[0]
        elif legacy:
            log_error("version.yml uses the pre-v4.1.0 format (only the singular project_type key exists).")
            log_error("To migrate: delete the project_type line and replace it with a project_types array.")
            log_error(f'  e.g. project_type: "{legacy}"  →  project_types: ["{legacy}"]')
            sys.exit(1)
        else:
            self.primary = "basic"

        current = get_yml_version()
        if current is None:
            if require_version:
                log_error('Could not read the version value from version.yml. A `version: "x.y.z"` line is required.')
                sys.exit(1)
            current = "0.0.0"  # placeholder unused by version_code-only commands
        self.current_version = current
        self.version_file = self._resolve_version_file()

        log_info("Project settings:")
        if self.types:
            log_info(f"  Types (array): {','.join(self.types)}")
        log_info(f"  Type (primary): {self.primary}")
        log_info(f"  Version file (primary): {self.version_file}")
        log_info(f"  Current version: {self.current_version}")

    def _resolve_version_file(self) -> str:
        p = get_type_path(self.primary)
        t = self.primary
        if t == "spring":
            # Also read projects that only have Kotlin DSL (build.gradle.kts) (#680)
            if not Path(f"{p}/build.gradle").is_file() and Path(f"{p}/build.gradle.kts").is_file():
                return f"{p}/build.gradle.kts"
            return f"{p}/build.gradle"
        if t == "flutter":
            return f"{p}/pubspec.yaml"
        if t in ("react", "node"):
            return f"{p}/package.json"
        if t == "react-native":
            ios_dir = Path(p) / "ios"
            if ios_dir.is_dir():
                plists = find_info_plists(ios_dir)
                if plists:
                    return str(plists[0])
            return f"{p}/android/app/build.gradle"
        if t == "react-native-expo":
            return f"{p}/app.json"
        if t == "python":
            return f"{p}/pyproject.toml"
        return "version.yml"  # basic and anything else


# ── Version utilities ────────────────────────────────────────────────────────
def validate_version(version: str) -> bool:
    if VERSION_RE.match(version or ""):
        return True
    log_error(f"Invalid version format: '{version}' (must be x.y.z)")
    return False


def increment_patch(version: str) -> str:
    major, minor, patch = version.split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


def increment_version(version: str, bump: str = "patch") -> str:
    """bump: 'major'|'minor'|'patch'. Omitted -> patch increment as before (backward compatible)."""
    major, minor, patch = version.split(".")
    if bump == "major":
        return f"{int(major) + 1}.0.0"
    if bump == "minor":
        return f"{major}.{int(minor) + 1}.0"
    return f"{major}.{minor}.{int(patch) + 1}"


def higher_version(v1: str, v2: str) -> str:
    a = [int(x) for x in v1.split(".")[:3]]
    b = [int(x) for x in v2.split(".")[:3]]
    return v1 if a >= b else v2


# ── version_code ─────────────────────────────────────────────────────
def get_version_code() -> int:
    if not VERSION_YML.is_file():
        log_warning("version.yml not found. Returning default 1")
        return 1
    for line in yml_lines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^version_code:\s*([0-9]+)", line)
        if m:
            log_debug(f"Current version_code: {m.group(1)}")
            return int(m.group(1))
    # Field missing -> add after the version line (initial value 1)
    log_warning("No version_code field. Adding it automatically (initial value: 1)")
    text = read_text(VERSION_YML)
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    body_text = text[len(bom):]
    eol = detect_eol(body_text)
    new_line = "version_code: 1 # app build number" + eol
    pieces = split_lines(body_text)
    for i, piece in enumerate(pieces):
        if not piece.lstrip().startswith("#") and re.match(r"^version:", piece):
            if not piece.endswith("\n"):  # last line has no newline: add one first so it does not join the previous line
                pieces[i] = piece + eol
            pieces.insert(i + 1, new_line)
            break
    else:
        if pieces and not pieces[-1].endswith("\n"):
            pieces[-1] += eol
        pieces.append(new_line)
    write_text(VERSION_YML, bom + "".join(pieces))
    log_success("Added version_code field: 1")
    return 1


def set_version_code(new_code: int):
    replaced = set_yml_field(
        r"^version_code:\s*[0-9]+",
        lambda m: f"version_code: {new_code} # app build number",
    )
    if not replaced:
        get_version_code()  # creates the field
        set_yml_field(r"^version_code:\s*[0-9]+", lambda m: f"version_code: {new_code} # app build number")


def increment_version_code() -> int:
    current = get_version_code()
    new_code = current + 1
    log_info(f"VERSION_CODE increment: {current} → {new_code}")
    set_version_code(new_code)
    log_success(f"VERSION_CODE updated: {new_code}")
    return new_code


# ── Per-file version read/write helpers ────────────────────────────────────────
def read_json(path: Path):
    """Read a JSON object. BOM allowed; broken JSON or a non-object top level raises VersionError (#683)."""
    text = read_text(path)
    try:
        obj = json.loads(text.lstrip("\ufeff"))
    except ValueError as e:
        raise VersionError(f"Could not read {path.as_posix()}: {e} (check the JSON syntax and merge conflict markers)")
    if not isinstance(obj, dict):
        raise VersionError(f"Could not read {path.as_posix()}: the top level is not a JSON object")
    return obj


# JSON is not rewritten with json.dumps; only the string span of the version value is replaced.
# Rewriting would change tabs/4-space indent, one-line arrays, trailing newline and CRLF (#682).
def _json_ws(t: str, i: int) -> int:
    while i < len(t) and t[i] in " \t\r\n":
        i += 1
    return i


def _json_string_end(t: str, i: int) -> int:
    i += 1
    while t[i] != '"':
        i += 2 if t[i] == "\\" else 1
    return i + 1


def _json_value_end(t: str, i: int) -> int:
    """End position of the value starting at i. Only for text already validated by json.loads."""
    i = _json_ws(t, i)
    c = t[i]
    if c == '"':
        return _json_string_end(t, i)
    if c in "{[":
        close = "}" if c == "{" else "]"
        i += 1
        while True:
            i = _json_ws(t, i)
            if t[i] == close:
                return i + 1
            if t[i] == ",":
                i += 1
                continue
            if c == "{":
                i = _json_ws(t, _json_string_end(t, i)) + 1  # skip the key and colon
            i = _json_value_end(t, i)
    j = i
    while j < len(t) and t[j] not in ",}] \t\r\n":
        j += 1
    return j


def _json_member_span(t: str, obj_start: int, key: str):
    """(start, end) of key's value in the object at obj_start. Duplicate keys use the last one, like json.loads."""
    i = _json_ws(t, obj_start) + 1
    found = None
    while True:
        i = _json_ws(t, i)
        if t[i] == "}":
            return found
        if t[i] == ",":
            i += 1
            continue
        key_end = _json_string_end(t, i)
        name = json.loads(t[i:key_end])
        i = _json_ws(t, key_end) + 1
        vs = _json_ws(t, i)
        ve = _json_value_end(t, vs)
        if name == key:
            found = (vs, ve)
        i = ve


def json_set_string(text: str, keys: list, new_value: str):
    """New text with the string value at the keys path replaced. None if the path is missing or not a string."""
    vs = _json_ws(text, 1 if text.startswith("\ufeff") else 0)
    ve = vs
    for key in keys:
        if text[vs] != "{":
            return None
        span = _json_member_span(text, vs, key)
        if span is None:
            return None
        vs, ve = span
    if text[vs] != '"':
        return None
    return text[:vs] + json.dumps(new_value, ensure_ascii=False) + text[ve:]


def json_rebuild(text: str, obj) -> str:
    """Fallback used only when a key must be inserted. Follows the original indent, newlines, trailing newline and BOM as far as possible."""
    bom = "\ufeff" if text.startswith("\ufeff") else ""
    body = text[len(bom):]
    indents = re.findall(r"^([ \t]+)\S", body, re.MULTILINE)
    indent = min(indents, key=len) if indents else "  "
    eol = detect_eol(body)
    out = json.dumps(obj, indent=indent, ensure_ascii=False)
    if eol != "\n":
        out = out.replace("\n", eol)
    if body.endswith("\n"):
        out += eol
    return bom + out


def set_json_version(path: Path, keys: list, new_version: str) -> bool:
    """Set the keys path (e.g. ["version"], ["expo", "version"]) of a JSON file to new_version. Returns whether it changed."""
    obj = read_json(path)  # broken JSON ends here with an error (later scans assume valid JSON)
    text = read_text(path)
    new_text = json_set_string(text, keys, new_version)
    if new_text is None:
        node = obj
        for key in keys[:-1]:
            node = node.setdefault(key, {})
            if not isinstance(node, dict):
                raise VersionError(f"Cannot write version: '{key}' in {path.as_posix()} is not an object")
        node[keys[-1]] = new_version
        new_text = json_rebuild(text, obj)
    return write_text(path, new_text)


SAME, CHANGED, NO_MATCH = "same", "changed", "nomatch"


def sub_file(path: Path, pattern: str, repl, count=0, flags=re.MULTILINE) -> str:
    """Regex replace. Returns CHANGED / SAME (matched but already equal, not written) / NO_MATCH."""
    text = read_text(path)
    new_text, n = re.subn(pattern, repl, text, count=count, flags=flags)
    if not n:
        return NO_MATCH
    return CHANGED if write_text(path, new_text) else SAME


PLIST_EXCLUDED_DIRS = {"Pods", "build", "node_modules", "DerivedData", "Carthage", ".build"}
_PLIST_VERSION_RE = re.compile(r"(<key>CFBundleShortVersionString</key>\s*<string>)([^<]*)(</string>)")
VARIABLE = "variable"


def find_info_plists(ios_dir: Path) -> list:
    """App Info.plist candidates under ios/. Excludes third-party/build output such as Pods and build,
    keeps only files with CFBundleShortVersionString, sorted by shallow path then non-Tests target (#679).
    (Sorting by folder name picks ios/Pods/... or ios/AppTests/... as the project plist)
    """
    found = []
    for plist in ios_dir.rglob("Info.plist"):
        folders = plist.relative_to(ios_dir).parts[:-1]
        if any(part in PLIST_EXCLUDED_DIRS for part in folders):
            continue
        try:
            has_key = "CFBundleShortVersionString" in read_text(plist)
        except VersionError:
            continue
        if has_key:
            found.append(plist)
    return sorted(found, key=lambda f: (len(f.relative_to(ios_dir).parts), "Tests" in f.parent.name, f.as_posix()))


def plist_set_version(path: Path, new_version: str) -> str:
    """Replace the <string> value after the CFBundleShortVersionString key (same line or next line).

    If the value is an Xcode variable such as $(MARKETING_VERSION), leave it and return VARIABLE —
    overwriting it with a literal drifts from MARKETING_VERSION in pbxproj.
    """
    text = read_text(path)
    if not _PLIST_VERSION_RE.search(text):
        return NO_MATCH
    new_text = _PLIST_VERSION_RE.sub(
        lambda m: m.group(0) if m.group(2).startswith("$(") else f"{m.group(1)}{new_version}{m.group(3)}", text)
    if new_text == text:
        return VARIABLE if _PLIST_VERSION_RE.search(text).group(2).startswith("$(") else SAME
    return CHANGED if write_text(path, new_text) else SAME


_PLIST_BUILD_RE = re.compile(r"(<key>CFBundleVersion</key>\s*<string>)([^<]*)(</string>)")


def plist_set_build(path: Path, build: int) -> str:
    """Replace the CFBundleVersion (build number) value. Variables such as $(CURRENT_PROJECT_VERSION) -> VARIABLE (#721)."""
    text = read_text(path)
    m = _PLIST_BUILD_RE.search(text)
    if not m:
        return NO_MATCH
    new_text = _PLIST_BUILD_RE.sub(
        lambda mm: mm.group(0) if mm.group(2).startswith("$(") else f"{mm.group(1)}{build}{mm.group(3)}", text)
    if new_text == text:
        return VARIABLE if m.group(2).startswith("$(") else SAME
    return CHANGED if write_text(path, new_text) else SAME


# Match only when versionCode is followed by a numeric literal (variables like `versionCode rootProject.ext.x` are left alone)
_GRADLE_BUILD_RE = re.compile(r"^([ \t]*versionCode[ \t]*=?[ \t]*)\d+(?=[ \t]*(?://.*)?\r?$)", re.MULTILINE)


def sync_build_number(cfg: Config, code: int):
    """Apply version.yml version_code to the react-native build numbers (versionCode, CFBundleVersion) (#721).

    Stores need the build number to grow every time; if it drifts from version.yml it must be managed by hand.
    Applies to the react-native type only (expo is out of scope); warns only when the target pattern is missing.
    """
    if "react-native" not in cfg.types and cfg.primary != "react-native":
        return
    p = get_type_path("react-native")
    base = Path(p)
    ios_dir = base / "ios"
    if ios_dir.is_dir():
        plists = find_info_plists(ios_dir)
        if not plists:
            log_warning(f"react-native: no Info.plist found under {p}/ios — iOS build number not synced")
        for plist in plists:
            status = plist_set_build(plist, code)
            if status == CHANGED:
                log_success(f"Build number updated: {plist.as_posix()} (CFBundleVersion {code})")
            elif status == VARIABLE:
                log_warning(f"CFBundleVersion in {plist.as_posix()} is an Xcode variable, so it was not synced — manage it in the Xcode project")
            elif status == NO_MATCH:
                log_warning(f"No CFBundleVersion in {plist.as_posix()}, so the build number could not be synced")
    else:
        log_warning(f"react-native: no {p}/ios directory — skipping build number")
    gradle = base / "android" / "app" / "build.gradle"
    if gradle.is_file():
        status = sub_file(gradle, _GRADLE_BUILD_RE.pattern, lambda m: f"{m.group(1)}{code}")
        if status == CHANGED:
            log_success(f"Build number updated: {gradle.as_posix()} (versionCode {code})")
        elif status == NO_MATCH:
            log_warning(f"No numeric literal versionCode found in {gradle.as_posix()} — build number not synced")
    else:
        log_warning(f"react-native: no {p}/android/app/build.gradle — skipping build number")


# pyproject.toml: only the version key inside the [project] (PEP 621) or [tool.poetry] table is the project version.
# Replacing without regard to tables overwrites version in other tables such as [tool.foo] (#681).
TOML_VERSION_TABLES = ("project", "tool.poetry")
_TOML_HEADER_RE = re.compile(r"^[ \t]*\[([^\[\]]+)\][ \t]*(#.*)?$")
_TOML_VERSION_RE = re.compile(r"""^([ \t]*version[ \t]*=[ \t]*)("[^"\r\n]*"|'[^'\r\n]*')(.*)$""", re.DOTALL)


def _toml_version_lines(pieces: list) -> list:
    """Indexes of version lines inside the target tables (in table order)."""
    table = None
    found = []
    for i, piece in enumerate(pieces):
        body, _ = split_eol(piece)
        h = _TOML_HEADER_RE.match(body)
        if h:
            table = re.sub(r"\s+", "", h.group(1))
            continue
        if body.lstrip().startswith("[["):  # array tables ([[x]]) are not targets
            table = None
            continue
        if table in TOML_VERSION_TABLES and _TOML_VERSION_RE.match(body):
            found.append(i)
    return found


def toml_get_version(text: str) -> str:
    pieces = split_lines(text)
    for i in _toml_version_lines(pieces):
        m = re.match(r"^[ \t]*version[ \t]*=[ \t]*[\"'](\d+\.\d+\.\d+)[\"']", split_eol(pieces[i])[0])
        if m:
            return m.group(1)
    return ""


def toml_set_version(path: Path, new_version: str) -> str:
    """Replace the version value in the target table. Quote style and end-of-line comment are kept. Returns CHANGED/SAME/NO_MATCH."""
    pieces = split_lines(read_text(path))
    targets = _toml_version_lines(pieces)
    if not targets:
        return NO_MATCH
    for i in targets:
        body, eol = split_eol(pieces[i])
        m = _TOML_VERSION_RE.match(body)
        quote = m.group(2)[0]
        pieces[i] = f"{m.group(1)}{quote}{new_version}{quote}{m.group(3)}{eol}"
    return CHANGED if write_text(path, "".join(pieces)) else SAME


def get_project_file_version(cfg: Config) -> str:
    vf = Path(cfg.version_file)
    if cfg.primary == "basic" or not vf.is_file():
        return cfg.current_version

    v = ""
    t = cfg.primary
    try:
        if t == "spring":
            m = re.search(r"^\s*version\s*=\s*['\"](\d+\.\d+\.\d+)['\"]", read_text(vf), re.MULTILINE)
            v = m.group(1) if m else ""
        elif t == "flutter":
            m = re.search(r"^version:\s*(\S+)", read_text(vf), re.MULTILINE)
            v = (m.group(1) if m else "").split("+")[0].strip('"').strip("'")
        elif t in ("react", "node"):
            v = str(read_json(vf).get("version", "") or "")
        elif t == "react-native":
            if cfg.version_file.endswith("Info.plist"):
                m = re.search(r"CFBundleShortVersionString</key>\s*<string>([^<]*)</string>", read_text(vf))
                v = m.group(1) if m else ""
                if v.startswith("$("):  # an Xcode variable (MARKETING_VERSION) is not a readable version
                    log_warning(f"The version in {vf.as_posix()} is an Xcode variable ({v}) and cannot be read — using the version.yml value")
                    v = ""
            else:
                m = re.search(r'versionName\s*"([^"]+)"', read_text(vf))
                v = m.group(1) if m else ""
        elif t == "react-native-expo":
            v = str((read_json(vf).get("expo") or {}).get("version", "") or "")
        elif t == "python":
            v = toml_get_version(read_text(vf))
        else:
            v = cfg.current_version
    except (OSError, ValueError, VersionError) as e:
        log_warning(f"Failed to read project file ({vf}): {e}")
        v = ""

    if not v:
        v = cfg.current_version
    log_debug(f"Project file version: '{v}'")
    return v


# ── Per-type sync (.sh sync_for_type equivalent) ─────────────────────────────
def _sync_spring(type_name: str, base_dir: Path, type_path: str, new_version: str):
    if not base_dir.is_dir():
        log_warning(f"spring: no {type_path} directory — skipping")
        return
    # equivalent of find -maxdepth 2 -name build.gradle
    candidates = sorted(
        set(base_dir.glob("build.gradle")) | set(base_dir.glob("*/build.gradle"))
        | set(base_dir.glob("build.gradle.kts")) | set(base_dir.glob("*/build.gradle.kts"))
    )
    if not candidates:
        log_warning(f"spring: no build.gradle(.kts) in {type_path} — skipping")
    for gradle in candidates:
        # Only fix `version = '...'` at line start (project version assignment). Without the anchor it would
        # overwrite other assignments such as ext.kotlin_version = '1.9.0' or comments and break the build (#680).
        results = {
            sub_file(gradle, r"^([ \t]*version[ \t]*=[ \t]*)'[^']*'", lambda m: f"{m.group(1)}'{new_version}'"),
            sub_file(gradle, r'^([ \t]*version[ \t]*=[ \t]*)"[^"]*"', lambda m: f'{m.group(1)}"{new_version}"'),
        }
        if CHANGED in results:
            log_success(f"Updated: {gradle.as_posix()}")
        elif results == {NO_MATCH}:
            log_warning(f"spring: no version assignment found in {gradle.as_posix()} — not synced")


def _sync_flutter(type_name: str, base_dir: Path, type_path: str, new_version: str):
    pubspec = base_dir / "pubspec.yaml"
    if not pubspec.is_file():
        log_warning(f"flutter: no {type_path}/pubspec.yaml — skipping")
        return
    code = get_version_code()
    # Replace only the value and keep the end-of-line comment (version: 1.2.3+7 # rel)
    status = sub_file(
        pubspec, r"^(version:[ \t]*)[^\s#]*([ \t]*#[^\r\n]*)?",
        lambda m: f"{m.group(1)}{new_version}+{code}{m.group(2) or ''}", count=1)
    if status == CHANGED:
        log_success(f"Updated: {pubspec.as_posix()}")


def _sync_package_json(type_name: str, base_dir: Path, type_path: str, new_version: str):
    package_json = base_dir / "package.json"
    if not package_json.is_file():
        log_warning(f"{type_name}: no {type_path}/package.json — skipping")
        return
    if set_json_version(package_json, ["version"], new_version):
        log_success(f"Updated: {package_json.as_posix()}")


def _sync_python(type_name: str, base_dir: Path, type_path: str, new_version: str):
    toml = base_dir / "pyproject.toml"
    if not toml.is_file():
        log_warning(f"python: no {type_path}/pyproject.toml — skipping")
        return
    status = toml_set_version(toml, new_version)
    if status == CHANGED:
        log_success(f"Updated: {toml.as_posix()}")
    elif status == NO_MATCH:
        log_warning(f"python: no version found in [project]/[tool.poetry] of {toml.as_posix()} — not synced")


def _sync_react_native(type_name: str, base_dir: Path, type_path: str, new_version: str):
    # iOS Info.plist (Xcode variables left alone) > Android build.gradle versionName
    ios_dir = base_dir / "ios"
    if ios_dir.is_dir():
        plists = find_info_plists(ios_dir)
        if not plists:
            log_warning(f"react-native: no Info.plist with CFBundleShortVersionString found under {type_path}/ios — iOS version not synced")
        for plist in plists:
            status = plist_set_version(plist, new_version)
            if status == CHANGED:
                log_success(f"Updated: {plist.as_posix()}")
            elif status == VARIABLE:
                log_warning(f"The version in {plist.as_posix()} is an Xcode variable (MARKETING_VERSION), so it was not synced — manage it in the Xcode project")
    else:
        log_warning(f"react-native: no {type_path}/ios directory — skipping")
    gradle = base_dir / "android" / "app" / "build.gradle"
    if gradle.is_file():
        if sub_file(gradle, r'versionName "[^"]*"', f'versionName "{new_version}"') == CHANGED:
            log_success(f"Updated: {gradle.as_posix()}")
    else:
        log_warning(f"react-native: no {type_path}/android/app/build.gradle — skipping")


def _sync_expo(type_name: str, base_dir: Path, type_path: str, new_version: str):
    app_json = base_dir / "app.json"
    if not app_json.is_file():
        log_warning(f"react-native-expo: no {type_path}/app.json — skipping")
        return
    if set_json_version(app_json, ["expo", "version"], new_version):
        log_success(f"Updated: {app_json.as_posix()}")


# type > function that updates that type's version file (basic has only version.yml, so none). Adding a type = one function + one row here
TYPE_SYNCERS = {
    "spring": _sync_spring, "flutter": _sync_flutter, "react": _sync_package_json, "node": _sync_package_json,
    "python": _sync_python, "react-native": _sync_react_native, "react-native-expo": _sync_expo,
}


def sync_for_type(t: str, new_version: str):
    p = get_type_path(t)
    log_info(f"Sync by type: {t} → {new_version} (path: {p})")
    if t == "basic":
        return
    syncer = TYPE_SYNCERS.get(t)
    if syncer is None:
        log_warning(f"Unknown type: {t} — skipping")
        return
    syncer(t, Path(p), p, new_version)

def sync_all_project_files(cfg: Config, new_version: str):
    if cfg.types:
        log_info(f"Starting multi-type sync: {','.join(cfg.types)}")
        for t in cfg.types:
            sync_for_type(t, new_version)
    else:
        # No array -> treated as basic (Config already has primary=basic) — no target files
        sync_for_type(cfg.primary, new_version)


# ── version.yml update (.sh update_version_yml equivalent) ───────────────────
def update_version_yml(cfg: Config, new_version: str):
    from datetime import datetime, timezone

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    user = os.environ.get("GITHUB_ACTOR") or os.environ.get("USER") or os.environ.get("USERNAME") or "unknown"

    if get_yml_version() == new_version:
        # Same version already: leave the file untouched, timestamp included (idempotent)
        log_info(f"version.yml is already {new_version} — no change")
        cfg.current_version = new_version
        return
    log_debug(f"Updating version.yml: {new_version}")
    # Replace the whole value whatever its quotes, v prefix or prerelease suffix; keep only the end-of-line comment.
    replaced = set_yml_field(
        r"^version:[ \t]*(?:\"[^\"]*\"|'[^']*'|[^#\s]*)([ \t]*#.*)?[ \t]*$",
        lambda m: f'version: "{new_version}"' + (m.group(1) or ""),
    )
    if not replaced:
        # Emitting a success log and the new version would release the new number while version.yml stays unchanged
        raise VersionError("Could not update the version line in version.yml. Fix it to the `version: \"x.y.z\"` form and run again.")
    # metadata fields are updated only when present (.sh yq -e guard equivalent)
    set_yml_field(r"^(\s+last_updated:\s*).*$", lambda m: f'{m.group(1)}"{timestamp}"')
    set_yml_field(r"^(\s+last_updated_by:\s*).*$", lambda m: f'{m.group(1)}"{user}"')

    cfg.current_version = new_version
    log_success(f"version.yml updated: {new_version}")


# ── sync (.sh sync_versions equivalent) ────────────────────────────────────
def sync_versions(cfg: Config) -> str:
    yml_version = cfg.current_version
    project_version = get_project_file_version(cfg)

    log_info("Checking version sync")
    log_info(f"  version.yml: {yml_version}")
    log_info(f"  Project file: {project_version}")

    if yml_version != project_version:
        if VERSION_RE.match(yml_version) and VERSION_RE.match(project_version):
            higher = higher_version(yml_version, project_version)
            log_info(f"Version mismatch detected, syncing to the higher version: {higher}")
            if higher != yml_version:
                update_version_yml(cfg, higher)
            if higher != project_version:
                sync_all_project_files(cfg, higher)
            return higher
        log_warning("Cannot sync because of a version format error")
        return yml_version

    # primary matches — for multi-type, align the non-primary files
    if cfg.types:
        log_info(f"Multi-type — aligning every type's files to the version.yml version: {yml_version}")
        sync_all_project_files(cfg, yml_version)
    log_success(f"Versions already in sync: {yml_version}")
    return yml_version


def preflight_json_files(cfg: Config):
    """Read JSON version files before writing. Prevents stopping with only some files updated (#683)."""
    for t in (cfg.types or [cfg.primary]):
        name = {"react": "package.json", "node": "package.json", "react-native-expo": "app.json"}.get(t)
        if not name:
            continue
        f = Path(get_type_path(t)) / name
        if f.is_file():
            read_json(f)


def update_all_versions(cfg: Config, new_version: str):
    log_info(f"Updating all version files: {new_version}")
    preflight_json_files(cfg)
    update_version_yml(cfg, new_version)
    sync_all_project_files(cfg, new_version)
    log_success(f"All version files updated: {new_version}")


USAGE = """Usage: version_manager.py {get|get-code|get-option|get-types|increment|increment-code|set|sync|validate} [version]

Commands:
  get            - Get the current version (with sync)
  get-code       - Get the current VERSION_CODE
  increment      - Bump the version + bump VERSION_CODE
                   [--bump major|minor|patch] (default patch — previous behavior when omitted)
  increment-code - Bump VERSION_CODE only
  set            - Set a specific version
  sync           - Sync version files
  validate       - Validate the version format
"""


def _strip_yaml_comment(line: str) -> str:
    """Treat text after ` #` outside quotes as a comment and remove it. A # inside quotes (URL fragments, etc.) stays."""
    quote = None
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            return line[:i]
    return line


def get_option(key: str):
    """Return the scalar value of metadata.template.options.<key>. None if missing.

    key accepts a dotted path (e.g. changelog.provider -> provider of the changelog block under options).
    Workflows that read version.yml directly with grep/regex silently get wrong values depending on indent,
    quotes, comments and nested keys with the same name. Follows open blocks on a stack and reads only
    the direct keys of exactly that path (#832, #851).
    """
    parts = key.split(".")
    prefix, leaf = ["metadata", "template", "options"] + parts[:-1], parts[-1]
    stack = []  # [(block name, indent)] — the blocks enclosing the current line
    for raw in yml_lines():
        line = _strip_yaml_comment(raw).rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        # Same or shallower indent means we left that block
        while stack and indent <= stack[-1][1]:
            stack.pop()
        m = re.match(r"^([A-Za-z0-9_]+):\s*(.*)$", line.strip())
        if not m:
            continue
        name, rest = m.group(1), m.group(2)
        if rest == "" or rest[:1] in "|>":
            # Child block or multi-line string — block the name so "a: b" inside a multi-line string is not read as a key
            stack.append((name if rest == "" else "\0scalar", indent))
            continue
        if name == leaf and [n for n, _ in stack] == prefix:
            return _unquote(rest)
    return None


def parse_bump_flag(argv) -> str | None:
    """Parse `increment --bump <level>`. No flag -> 'patch' (old behavior); invalid value -> None.

    Why not argparse: this CLI must keep its positional contract (`set 1.2.3`, etc.),
    and the .sh shim passes arguments through, so parsing stays simple.
    """
    if "--bump" not in argv:
        return "patch"
    idx = argv.index("--bump")
    if idx + 1 >= len(argv):
        return None
    value = argv[idx + 1]
    return value if value in ("major", "minor", "patch") else None


def main(argv):
    try:
        return _main(argv)
    except VersionError as e:
        log_error(str(e))
        return 1


def _main(argv):
    command = argv[1] if len(argv) > 1 else "get"

    if command not in ("get", "get-code", "get-option", "get-types", "increment", "increment-code", "set", "sync", "validate"):
        print(USAGE, file=sys.stderr)
        return 1

    # version_code-only commands must work without a version key (existing contract)
    # validate can check a version given as an argument without a version value in version.yml
    needs_yml_version = command not in ("get-code", "increment-code", "get-option", "get-types") and not (command == "validate" and len(argv) > 2)
    cfg = Config(require_version=needs_yml_version)

    if command == "get-option":
        # get-option KEY [DEFAULT] — print DEFAULT (or an empty string) when the key is missing
        if len(argv) < 3:
            log_error("Specify a key: version_manager.py get-option semver_auto [default]")
            return 1
        value = get_option(argv[2])
        print(value if value is not None else (argv[3] if len(argv) > 3 else ""))
        return 0
    if command == "get-types":
        # Print project_types as csv — replaces workflows grepping only one-line arrays and missing block lists (#851)
        print(",".join(parse_project_types()))
        return 0
    if command == "get":
        version = sync_versions(cfg)
        log_success(f"Current version: {version}")
        print(version)
    elif command == "get-code":
        code = get_version_code()
        log_success(f"Current VERSION_CODE: {code}")
        print(code)
    elif command == "increment-code":
        new_code = increment_version_code()
        sync_build_number(cfg, new_code)
        print(new_code)
    elif command == "increment":
        bump = parse_bump_flag(argv)
        if bump is None:
            log_error("--bump must be one of major|minor|patch")
            return 1
        log_info("Checking version sync")
        current = sync_versions(cfg)
        if not validate_version(current):
            return 1
        new_version = increment_version(current, bump)
        log_info(f"Version update ({bump}): {current} → {new_version}")
        update_all_versions(cfg, new_version)
        sync_build_number(cfg, increment_version_code())
        log_success(f"Version updated: {new_version}")
        print(new_version)
    elif command == "set":
        new_version = argv[2] if len(argv) > 2 else ""
        if not new_version:
            log_error("Specify the new version: version_manager.py set 1.2.3")
            return 1
        if not validate_version(new_version):
            return 1
        log_info(f"Setting version: {new_version}")
        update_all_versions(cfg, new_version)
        sync_build_number(cfg, get_version_code())  # set does not bump the code but aligns files with the current value
        log_success(f"Version set: {new_version}")
        print(new_version)
    elif command == "sync":
        synced = sync_versions(cfg)
        log_success(f"Versions synced: {synced}")
        print(synced)
    elif command == "validate":
        version = argv[2] if len(argv) > 2 else cfg.current_version
        if not version:
            version = get_project_file_version(cfg)
        if validate_version(version):
            log_success(f"Valid version format: {version}")
            print(version)
            return 0
        return 1
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main(sys.argv))
