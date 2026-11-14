#!/usr/bin/env python3
# ===================================================================
# store_notes.py — prepares store release notes per language (#829)
# ===================================================================
#
# Why it exists
#   Copying one text to every store language shows Korean to en-US/ja/zh-Hans users.
#   But languages without a translation must not be dropped either — App Store Connect rejects review submission
#   if any language has an empty What's New (ENTITY_ERROR.ATTRIBUTE.REQUIRED, measured 2026-10-10).
#   So it uses the per-language text when there is one, else the default-language text.
#
# How to turn it on
#   version.yml  metadata.template.options.store_locales: ["ko-KR", "en-US", "ja-JP", "zh-CN"]
#   If languages differ per store, list them per store with store_locales_ios / store_locales_play (else shared).
#   The first item is the default language. **Without the key this script does nothing** — existing users
#   behave exactly as now (the caller sees "enabled": false and takes the old path).
#
# Where the text comes from
#   default language : --default-file (Korean notes built from CHANGELOG) or --override
#   other languages  : store_notes[language] of that version in CHANGELOG.json. Missing or empty -> default-language text.
#                      But if that language file already exists and is not empty (notes the repo wrote itself), it is not overwritten.
#
# Usage
#   store_notes.py write --platform play --workspace . [--app-root app] --version 1.2.3 --version-code 136 \
#                        --default-file final_release_notes.txt
#   store_notes.py write --platform ios  --workspace . --version 1.2.3 --out-dir DIR \
#                        --default-file final_release_notes.txt [--override "fixed text"]
#   store_notes.py locales --platform ios        # show only the configured languages and their conversion
#
# Output is always one JSON object. Never exits abnormally (never blocks a deploy) — except
# invalid arguments exit 2.
# ===================================================================
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Language codes the stores accept — same as the fastlane 2.240.1 source.
#   App Store : fastlane_core/lib/fastlane_core/languages.rb  ALL_LANGUAGES
#   Google Play: supply/lib/supply/languages.rb              ALL_LANGUAGES (underscore -> hyphen)
# Passing a code not in the list makes deliver try to enable that language on the app, and supply rejects it.
# So invented codes are never passed through — outside the list, skip it for that store and report.
IOS_LANGUAGES = frozenset("""
ar-SA bn-BD ca cs da de-DE el en-AU en-CA en-GB en-US es-ES es-MX fi fr-CA fr-FR gu-IN he hi hr hu id it ja
kn-IN ko ml-IN mr-IN ms nl-NL no or-IN pa-IN pl pt-BR pt-PT ro ru sk sl-SI sv ta-IN te-IN th tr uk ur-PK vi
zh-Hans zh-Hant
""".split())
PLAY_LANGUAGES = frozenset("""
af am ar az-AZ be bg bn-BD ca cs-CZ da-DK de-DE el-GR en-AU en-CA en-GB en-IN en-SG en-US en-ZA es-419 es-ES
es-US et eu-ES fa fi-FI fil fr-CA fr-FR gl-ES hi-IN hr hu-HU hy-AM id is-IS it-IT iw-IL ja-JP ka-GE km-KH
kn-IN ko-KR ky-KG lo-LA lt lv mk-MK ml-IN mn-MN mr-IN ms ms-MY my-MM ne-NP nl-NL no-NO pl-PL pt-BR pt-PT rm
ro ru-RU si-LK sk sl sr sv-SE sw ta-IN te-IN th tr-TR uk vi zh-CN zh-HK zh-TW zu
""".split())

# Pairs that naming rules alone cannot match (Play -> App Store). _ios_for below finds the rest by rule.
_PLAY_TO_IOS_EXCEPTIONS = {
    "zh-CN": "zh-Hans", "zh-TW": "zh-Hant", "zh-HK": "zh-Hant",
    "iw-IL": "he", "es-419": "es-MX", "ar": "ar-SA", "sl": "sl-SI",
}


def _ios_for(play_code: str) -> str | None:
    """App Store code matching a Play code. None if there is none (that language is not on the App Store)."""
    if play_code in _PLAY_TO_IOS_EXCEPTIONS:
        return _PLAY_TO_IOS_EXCEPTIONS[play_code]
    if play_code in IOS_LANGUAGES:
        return play_code
    base = play_code.split("-")[0]
    if base in IOS_LANGUAGES:                      # fi-FI → fi, ko-KR → ko, hi-IN → hi, ms-MY → ms
        return base
    regional = [c for c in IOS_LANGUAGES if c.split("-")[0] == base]
    return regional[0] if len(regional) == 1 else None


# Canonical form is Play style (ko-KR). App Store forms (ko, zh-Hans) written by the user map to the same canonical form.
CANONICAL_TO_IOS = {pc: ic for pc in sorted(PLAY_LANGUAGES) if (ic := _ios_for(pc))}
ALIASES: dict[str, str] = {}
for _pc, _ic in sorted(CANONICAL_TO_IOS.items()):
    # When one App Store code has several Play codes (zh-Hant <- zh-TW, zh-HK), pin the one whose region form is representative
    ALIASES.setdefault(_ic.lower(), _pc)
ALIASES.update({"zh-hant": "zh-TW", "ms": "ms", "ko": "ko-KR", "ja": "ja-JP"})
for _ic in IOS_LANGUAGES:                          # App Store-only languages not on Play (or-IN, pa-IN, ur-PK, etc.)
    ALIASES.setdefault(_ic.lower(), _ic)

# Per-store limits (with margin). Exceeding them rejects the whole upload.
LIMITS = {"play": (480, "char"), "ios": (3800, "byte")}
FALLBACK_TEXT = "버그를 수정하고 안정성을 개선했습니다."


def canonical(locale: str) -> str:
    """Normalize a language form to canonical (Play style). ko_KR and KO-kr are the same. Unknown forms stay as is."""
    loc = (locale or "").strip().replace("_", "-")
    if loc in PLAY_LANGUAGES:
        return loc
    lower = loc.lower()
    for code in PLAY_LANGUAGES:                    # Play codes differing only in case
        if code.lower() == lower:
            return code
    return ALIASES.get(lower, loc)


def store_code(platform: str, locale: str) -> str | None:
    """Language code the store accepts. None if the store lacks the language — the caller skips it and reports."""
    c = canonical(locale)
    if platform == "ios":
        if c in IOS_LANGUAGES:                     # an App Store-only language received as canonical
            return c
        return CANONICAL_TO_IOS.get(c)
    return c if c in PLAY_LANGUAGES else None


def _read_list(version_yml_text: str, key: str) -> list[str] | None:
    """options.<key> inline array. None without the key; otherwise a de-duplicated list in canonical form."""
    for line in version_yml_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(rf"^\s+{key}:\s*\[([^\]]*)\]", line)
        if m:
            raw = [s.strip().strip("\"'") for s in m.group(1).split(",")]
            seen: list[str] = []
            for loc in raw:
                c = canonical(loc)
                if c and c not in seen:
                    seen.append(c)
            return seen
    return None


def read_store_locales(version_yml_text: str, platform: str | None = None) -> list[str]:
    """Languages this store uses. Empty list if none — the caller keeps the old behavior.

    Language sets can differ per store. With store_locales_ios / store_locales_play that store
    uses it, else the shared store_locales. A language the App Store lacks would make deliver enable it
    on the app (checked in the fastlane source), so it must be narrowable per store.
    """
    if platform in ("ios", "play"):
        own = _read_list(version_yml_text, f"store_locales_{platform}")
        if own:
            return own
    return _read_list(version_yml_text, "store_locales") or []


def locale_text(release: dict | None, locale: str, default_text: str) -> tuple[str, str]:
    """(text, source). An empty per-language text falls back to the default-language text — an empty What's New fails review submission."""
    notes = (release or {}).get("store_notes") or {}
    for key, value in notes.items():
        if canonical(key) == locale and str(value or "").strip():
            return str(value).strip(), "store_notes"
    return default_text, "default"


def find_release(changelog: dict | None, version: str) -> dict | None:
    for rel in (changelog or {}).get("releases") or []:
        if str(rel.get("version")) == str(version):
            return rel
    return None


def _truncate(path: Path, platform: str) -> None:
    limit, mode = LIMITS[platform]
    # Truncation logic lives in one place (truncate_release_notes.py) — emoji sequences and byte boundaries are handled there
    subprocess.run([sys.executable, str(HERE / "truncate_release_notes.py"), str(path), str(limit), mode],
                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _read(path: str | None) -> str:
    if not path:
        return ""
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").strip()
    except OSError:
        return ""


def cmd_locales(args) -> dict:
    ws = Path(args.workspace)
    locales = read_store_locales(_read(str(ws / "version.yml")), args.platform)
    return {"enabled": bool(locales), "default": locales[0] if locales else None,
            "locales": [{"locale": l, "code": store_code(args.platform, l)} for l in locales],
            "unsupported": [l for l in locales if store_code(args.platform, l) is None]}


def cmd_write(args) -> dict:
    ws = Path(args.workspace)
    locales = read_store_locales(_read(str(ws / "version.yml")), args.platform)
    if not locales:
        # Without the key do nothing — the promise not to change existing users' behavior
        return {"enabled": False}

    default_text = (args.override or "").strip()
    if not default_text:
        default_text = _read(args.default_file)
    if not default_text:
        default_text = FALLBACK_TEXT

    changelog = None
    try:
        changelog = json.loads(_read(str(ws / "CHANGELOG.json")) or "null")
    except ValueError:
        changelog = None
    release = find_release(changelog, args.version)

    if args.platform == "play":
        if not args.version_code:
            return {"enabled": True, "ok": False, "error": "play needs --version-code"}
        # In a monorepo with the app in a subfolder, version.yml (repo root) and android/ (app root) differ
        base = Path(args.app_root or args.workspace) / "android" / "fastlane" / "metadata" / "android"
    else:
        if not args.out_dir:
            return {"enabled": True, "ok": False, "error": "ios needs --out-dir"}
        base = Path(args.out_dir)

    written, unsupported = [], []
    for i, loc in enumerate(locales):
        code = store_code(args.platform, loc)
        if code is None:
            # A language code this store lacks. Passing it makes deliver try to enable the language and supply reject it.
            unsupported.append(loc)
            print(f"⚠️ store_notes: '{loc}' is not a {args.platform} store language code, skipping", file=sys.stderr)
            continue
        # Default language always gets the default text. Others get the translation if there is one
        text, source = (default_text, "default") if i == 0 else locale_text(release, loc, default_text)
        if args.platform == "play":
            target = base / code / "changelogs" / f"{args.version_code}.txt"
        else:
            target = base / f"{code}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        # Without a translation, an already prepared file (per-language notes the repo wrote, etc.) is not overwritten with the default text.
        # Overwriting would regress hand-written English notes into Korean. Fill with the default text only when empty or missing.
        if i > 0 and source == "default" and target.is_file() and target.read_text(encoding="utf-8", errors="replace").strip():
            written.append({"locale": loc, "code": code, "source": "existing", "file": str(target)})
            continue
        target.write_text(text + "\n", encoding="utf-8")
        _truncate(target, args.platform)
        written.append({"locale": loc, "code": code, "source": source, "file": str(target)})

    pruned = []
    if args.platform == "play":
        # If a language folder not in the list has notes for this version (ko-KR made by the old path, etc.), remove them.
        # Otherwise text still gets uploaded for languages removed from the list.
        listed = {c for l in locales if (c := store_code("play", l))}
        if base.is_dir():
            for d in sorted(p for p in base.iterdir() if p.is_dir() and p.name not in listed):
                stale = d / "changelogs" / f"{args.version_code}.txt"
                if stale.is_file():
                    stale.unlink()
                    pruned.append(d.name)
    return {"enabled": True, "ok": True, "default": locales[0], "written": written, "pruned": pruned,
            "unsupported": unsupported,
            "translated": [w["locale"] for w in written if w["source"] == "store_notes"],
            "fell_back": [w["locale"] for w in written[1:] if w["source"] == "default"],
            "kept": [w["locale"] for w in written[1:] if w["source"] == "existing"]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Prepare store release notes per language (#829)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("write", "locales"):
        s = sub.add_parser(name)
        s.add_argument("--platform", choices=["play", "ios"], required=True)
        s.add_argument("--workspace", default=".")
    w = sub.choices["write"]
    w.add_argument("--version", required=True)
    w.add_argument("--version-code", default="")
    w.add_argument("--default-file", default="")
    w.add_argument("--override", default="", help="Pin the default-language text to this value (STORE_WHATS_NEW_OVERRIDE)")
    w.add_argument("--out-dir", default="")
    w.add_argument("--app-root", default="", help="App folder that contains android/ (default: --workspace)")
    args = p.parse_args(argv)
    result = cmd_write(args) if args.cmd == "write" else cmd_locales(args)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
