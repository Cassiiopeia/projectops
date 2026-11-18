#!/usr/bin/env python3
"""ios_release_rules: pure rules behind ios_release.py (#643, #1232)
Version closing and next version, Apple upload error classification, IPA bundle check, ASC status table. No network, no processes
"""
from __future__ import annotations

import os
import plistlib
import re
import sys
import zipfile
from pathlib import Path
from xml.parsers.expat import ExpatError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from i18n.messages import t as message  # noqa: E402

# States after approval. DEVELOPER_REJECTED cannot tell pre-approval withdrawal from post-approval rejection, so it counts as open.
CLOSED_VERSION_STATES = {
    "ACCEPTED", "PENDING_DEVELOPER_RELEASE", "PENDING_APPLE_RELEASE",
    "PROCESSING_FOR_DISTRIBUTION", "READY_FOR_DISTRIBUTION", "REPLACED_WITH_NEW_VERSION",
}
# Old appStoreState values. Same meaning as the new ones plus sales-related states.
CLOSED_STORE_STATES = CLOSED_VERSION_STATES | {
    "READY_FOR_SALE", "PROCESSING_FOR_APP_STORE", "PREORDER_READY_FOR_SALE",
    "DEVELOPER_REMOVED_FROM_SALE", "REMOVED_FROM_SALE",
}
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
def parse_version(s: str | None) -> tuple[int, int, int] | None:
    """Accept only 1-3 integers joined by dots. Missing parts become 0; anything else is None."""
    if not s:
        return None
    parts = str(s).strip().split(".")
    if not 1 <= len(parts) <= 3 or not all(p.isdigit() for p in parts):
        return None
    nums = [int(p) for p in parts] + [0] * (3 - len(parts))
    return nums[0], nums[1], nums[2]
def format_version(t: tuple[int, int, int]) -> str:
    return f"{t[0]}.{t[1]}.{t[2]}"
def next_patch(s: str) -> str:
    """Next patch version. ValueError for an unparsable string."""
    t = parse_version(s)
    if t is None:
        raise ValueError(message("ios_release.version_unparsable", value=repr(s)))
    return format_version((t[0], t[1], t[2] + 1))
def closed_max(versions: list[dict]) -> str | None:
    """Highest closed version. Checks both new and old state fields and skips unparsable versions."""
    best: tuple[int, int, int] | None = None
    for v in versions:
        closed = (v.get("appVersionState") in CLOSED_VERSION_STATES
                  or v.get("appStoreState") in CLOSED_STORE_STATES)
        t = parse_version(v.get("version")) if closed else None
        if t is not None and (best is None or t > best):
            best = t
    return format_version(best) if best else None
def decide_version(current: str, closed: str | None, mode: str) -> dict:
    """Decide the version to use. For a release, a closed version is not changed but reported as a failure (ok False)."""
    cur_t, closed_t = parse_version(current), parse_version(closed)
    base = {"ok": True, "version": current, "changed": False, "closed_max": closed}
    if closed_t is None:
        return {**base, "reason": message("ios_release.reason.no_closed")}
    if cur_t is None:
        # Leave version strings we cannot judge untouched (post-failure recovery covers it)
        return {**base, "reason": message("ios_release.reason.unparsable", current=repr(current))}
    if cur_t > closed_t:
        return {**base, "reason": message("ios_release.reason.open", current=current, closed=closed)}
    if mode == "release":
        return {**base, "ok": False,
                "reason": message("ios_release.reason.release_closed", current=current)}
    nxt = next_patch(closed)
    # Korean particles after a number (는/은, 로/으로) depend on the final consonant, so the text avoids particles
    why = (message("ios_release.reason.closed_same", current=current) if cur_t == closed_t
           else message("ios_release.reason.closed_lower", current=current, closed=closed))
    return {"ok": True, "version": nxt, "changed": True, "closed_max": closed,
            "reason": message("ios_release.reason.changed", why=why, next=nxt)}
def stale_branch_reason(current: str, base: str | None) -> str | None:
    """Merge-recommendation reason if the branch version is lower than the default branch's, else None (None quietly if not comparable)."""
    cur_t, base_t = parse_version(current), parse_version(base)
    if cur_t is None or base_t is None or cur_t >= base_t:
        return None
    return message("ios_release.stale_branch", current=current, base=base)
def _code(n: str) -> str:
    """Match Apple error codes only with context (#694).

    Forms the code takes in real logs: `ITMS-90189`, altool's `(90186)`,
    `.digits` after an uppercase code as in `STATE_ERROR.VALIDATION_ERROR.90061`.
    Matching bare digits misclassifies when a build number, byte count or ms duration has the same value,
    and the result decides retries and version switching.
    """
    return rf"(?:ITMS-{n}(?!\d)|(?<=[A-Z]\.){n}(?!\d)|\({n}\))"
_TRAIN_VERSION = re.compile(r"train version '(?P<v>[\d.]+)' is closed", re.I)
_APPROVED_VERSION = re.compile(r"previously approved version \[(?P<v>[\d.]+)\]", re.I)
_TOO_LOW_NUMBERS = [
    re.compile(r"must (?:contain a )?higher version than that of the previously uploaded version \[(?P<n>\d+)", re.I),
    re.compile(r"bundle version must be higher than the previously uploaded version: '(?P<n>\d+)'", re.I),
]
# Patterns per kind. Earlier kinds win (train_closed > too_low > duplicate)
_KIND_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    ("train_closed", [re.compile(_code("90186")), _TRAIN_VERSION,
                      re.compile(_code("90062")), _APPROVED_VERSION,
                      re.compile(_code("90478")), re.compile(r"later version has been closed", re.I)]),
    ("too_low", [re.compile(_code("90061")), *_TOO_LOW_NUMBERS]),
    ("duplicate", [re.compile(_code("90189")), re.compile(r"Redundant Binary Upload", re.I),
                   re.compile(r"INVALID\.DUPLICATE"), re.compile(r"(?<!\d)-19232(?!\d)")]),
]
_FALLBACK_LINE = re.compile(r"ITMS-\d+|ERROR|error|실패|\[!\]")
# altool's own success line. fastlane < 2.240 still fails on a stray ERROR line printed after it (Xcode 27.2, fastlane#30586)
_ALTOOL_UPLOAD_SUCCEEDED = "UPLOAD SUCCEEDED with no errors"
# DEPLOY_MODE values whose deploy lane ends at the TestFlight upload (Fastfile default: testflight_only)
_UPLOAD_ONLY_DEPLOY_MODES = ("store_only", "testflight_only")
def _first_group(patterns: list[re.Pattern], text: str, group: str) -> str | None:
    for p in patterns:
        m = p.search(text)
        if m and m.groupdict().get(group):
            return m.group(group)
    return None
def _clean_line(line: str) -> str:
    return line.strip()[:300]
def classify_upload_error(log: str) -> dict:
    """Classify the fastlane upload log. Color codes are stripped first."""
    text = _ANSI.sub("", log or "")
    kind, hit_patterns = "other", []
    for k, pats in _KIND_PATTERNS:
        matched = [p for p in pats if p.search(text)]
        if matched:
            kind, hit_patterns = k, matched
            break

    required = closed_version = None
    if kind == "train_closed":
        closed_version = _first_group([_TRAIN_VERSION, _APPROVED_VERSION], text, "v")
    elif kind == "too_low":
        n = _first_group(_TOO_LOW_NUMBERS, text, "n")
        required = int(n) if n else None

    reason = ""
    lines = text.splitlines()
    if hit_patterns:
        reason = next((_clean_line(l) for l in lines if any(p.search(l) for p in hit_patterns)), "")
    else:
        hits = [l for l in lines if _FALLBACK_LINE.search(l)]
        reason = _clean_line(hits[-1]) if hits else ""
    return {"kind": kind, "required_build": required, "closed_version": closed_version,
            "is_upload_reported_ok": _ALTOOL_UPLOAD_SUCCEEDED in text,
            "reason_line": reason or message("ios_release.no_reason")}
# Info.plist of the main app and the extension/watch/App Clip bundles nested in it
_BUNDLE_PLIST = re.compile(
    r"^Payload/[^/]+\.app(?:/(?:PlugIns|Watch|AppClips)/[^/]+\.(?:appex|app))*/Info\.plist$")
def write_runtime_export_options(src: Path, dst: Path) -> Path:
    """Turn off automatic numbering only in a copy, leaving the original (so Xcode cannot change numbers during export)."""
    with open(src, "rb") as f:
        data = plistlib.load(f)
    data["manageAppVersionAndBuildNumber"] = False
    dst.parent.mkdir(parents=True, exist_ok=True)
    with open(dst, "wb") as f:
        plistlib.dump(data, f)
    return dst
def verify_ipa(ipa: Path, version: str, build: int) -> list[str]:
    """Check that every app/extension bundle in the IPA has the expected version and build number. Empty passes."""
    problems: list[str] = []
    try:
        zf = zipfile.ZipFile(ipa)
    except (OSError, zipfile.BadZipFile) as e:
        return [message("ios_release.ipa.cannot_open", name=ipa.name, error=e)]
    with zf:
        names = [n for n in zf.namelist() if _BUNDLE_PLIST.match(n)]
        if not any(n.count("/") == 2 for n in names):  # Payload/X.app/Info.plist
            return [message("ios_release.ipa.no_info_plist")]
        for n in sorted(names):
            rel = n[len("Payload/"):-len("/Info.plist")]
            try:
                info = plistlib.loads(zf.read(n))
            except (ExpatError, plistlib.InvalidFileException, ValueError, KeyError) as e:
                problems.append(message("ios_release.ipa.unreadable_plist", bundle=rel, error=e))
                continue
            got_b, got_v = info.get("CFBundleVersion"), info.get("CFBundleShortVersionString")
            if str(got_b) != str(build) or str(got_v) != str(version):
                problems.append(message("ios_release.ipa.mismatch", bundle=rel, got_build=got_b, build=build,
                                        got_version=got_v, version=version))
    return problems
def _last_error_line(out: str) -> str:
    """One line to show as the failure reason. The real cause is the `error: ...` line; the trailing `** ARCHIVE FAILED **`
    banner is a result, not a cause, so the banner is used only when there is no error line (E2E showed only the banner)."""
    lines = [l for l in _ANSI.sub("", out or "").splitlines() if l.strip()]
    errors = [l for l in lines if "error:" in l]
    if errors:
        # Drop the leading file path and keep only the cause sentence
        return _clean_line(errors[-1].split("error:", 1)[1])
    # run_cmd failure text depends on language (ko 실행 실패 / en failed to run)
    hits = [l for l in lines if re.search(r"\*\* .* FAILED|실행 실패|failed to run", l)]
    return _clean_line((hits or lines or [message("ios_release.no_output")])[-1])
def _status_markdown(bundle_id: str, versions: list[dict], closed: str | None, recent: int | None) -> str:
    """Table for the run summary. Values are only version strings and state names, so no secrets can mix in."""
    lines = [f"## App Store Connect status ({bundle_id})", "",
             f"- Highest closed version: `{closed or 'none'}`",
             f"- Latest uploaded build number: `{recent if recent is not None else 'unavailable'}`", "",
             "| Version | State | Closed |", "|---|---|---|"]
    for v in versions:
        state = v.get("appVersionState") or v.get("appStoreState") or "-"
        lines.append(f"| {v['version']} | {state} | {'yes' if v['closed'] else 'no'} |")
    return "\n".join(lines) + "\n"


# Failure reasons go into PR comments: one line, secrets from the environment masked, 300 chars
_SECRET_ENV = re.compile(r"KEY|TOKEN|SECRET|PASSWORD", re.I)


def _one_line(v) -> str:
    """Strip newlines and color codes into one line."""
    return " ".join(_ANSI.sub("", str(v)).split())


def _scrub(text: str) -> str:
    """Mask secrets held in environment variables so they never leak into logs or reasons."""
    for k, v in os.environ.items():
        if _SECRET_ENV.search(k) and len(v) >= 8:
            text = text.replace(v, "***")
    return text


def _reason(text: str) -> str:
    return _scrub(_one_line(text))[:300]
