#!/usr/bin/env python3
# ===================================================================
# store_notes.py — 스토어 릴리스 노트를 언어별로 준비한다 (#829)
# ===================================================================
#
# 왜 있나
#   한 문구를 모든 스토어 언어에 복사하면 en-US/ja/zh-Hans 사용자에게 한국어가 보인다.
#   그렇다고 번역이 없는 언어를 빼면 안 된다 — App Store Connect 는 What's New 가 빈 언어가
#   하나라도 있으면 심사 제출을 거부한다(ENTITY_ERROR.ATTRIBUTE.REQUIRED, 2026-10-10 실측).
#   그래서 언어별 문구가 있으면 그것을, 없으면 기본 언어 문구를 쓴다.
#
# 켜는 법
#   version.yml  metadata.template.options.store_locales: ["ko-KR", "en-US", "ja-JP", "zh-CN"]
#   첫 항목이 기본 언어. **키가 없으면 이 스크립트는 아무것도 하지 않는다** — 기존 사용자는
#   지금과 똑같이 동작한다(호출부가 "enabled": false 를 보고 옛 경로를 그대로 탄다).
#
# 문구의 출처
#   기본 언어  : --default-file (CHANGELOG 에서 만든 한국어 노트) 또는 --override
#   그 외 언어 : CHANGELOG.json 해당 버전의 store_notes[언어]. 없거나 비면 기본 언어 문구.
#                단, 그 언어 파일이 이미 있고 비어 있지 않으면(레포가 직접 쓴 노트) 덮어쓰지 않는다.
#
# 사용법
#   store_notes.py write --platform play --workspace . [--app-root app] --version 1.2.3 --version-code 136 \
#                        --default-file final_release_notes.txt
#   store_notes.py write --platform ios  --workspace . --version 1.2.3 --out-dir DIR \
#                        --default-file final_release_notes.txt [--override "고정 문구"]
#   store_notes.py locales --platform ios        # 설정된 언어와 변환 결과만 본다
#
# 출력은 항상 JSON 한 개. 어떤 경우에도 비정상 종료하지 않는다(배포를 막지 않는다) — 단,
# 잘못된 인자는 exit 2.
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

# 정본 표기는 Play 방식(ko-KR). iOS(App Store Connect) 코드는 표로 바꾼다.
# 2026-10-10 EarLocAlert 실측: ASC 실제 코드는 ko / en-US / ja / zh-Hans (ja-JP, zh-CN 은 ASC 코드가 아니다).
CANONICAL_TO_IOS = {
    "ko-KR": "ko", "en-US": "en-US", "en-GB": "en-GB", "ja-JP": "ja",
    "zh-CN": "zh-Hans", "zh-TW": "zh-Hant", "de-DE": "de-DE", "fr-FR": "fr-FR",
    "es-ES": "es-ES", "pt-BR": "pt-BR", "ru-RU": "ru", "it-IT": "it",
    "nl-NL": "nl-NL", "pl-PL": "pl", "tr-TR": "tr", "vi": "vi", "th": "th", "id": "id",
}
# 사용자가 iOS/짧은 표기로 적어도 같은 정본으로 모은다
ALIASES = {
    "ko": "ko-KR", "ja": "ja-JP", "zh-hans": "zh-CN", "zh-hant": "zh-TW",
    "ru": "ru-RU", "it": "it-IT", "pl": "pl-PL", "tr": "tr-TR",
}

# 스토어별 한도 (여유를 둔 값). 넘기면 업로드가 통째로 거부된다.
LIMITS = {"play": (480, "char"), "ios": (3800, "byte")}
FALLBACK_TEXT = "버그를 수정하고 안정성을 개선했습니다."


def canonical(locale: str) -> str:
    """언어 표기를 정본(Play 방식)으로 모은다. 모르는 표기는 그대로 둔다."""
    loc = (locale or "").strip()
    if loc in CANONICAL_TO_IOS:
        return loc
    return ALIASES.get(loc.lower(), loc)


def store_code(platform: str, locale: str) -> str:
    """플랫폼이 인정하는 언어 코드. 모르는 표기는 그대로 넘긴다(스토어가 판단)."""
    c = canonical(locale)
    return CANONICAL_TO_IOS.get(c, c) if platform == "ios" else c


def read_store_locales(version_yml_text: str) -> list[str]:
    """version.yml 의 options.store_locales. 없으면 빈 목록 — 호출부는 옛 동작을 유지한다."""
    for line in version_yml_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s+store_locales:\s*\[([^\]]*)\]", line)
        if m:
            raw = [s.strip().strip("\"'") for s in m.group(1).split(",")]
            seen: list[str] = []
            for loc in raw:
                c = canonical(loc)
                if c and c not in seen:
                    seen.append(c)
            return seen
    return []


def locale_text(release: dict | None, locale: str, default_text: str) -> tuple[str, str]:
    """(문구, 출처). 언어별 문구가 비면 기본 언어 문구를 쓴다 — 빈 What's New 는 심사 제출이 거부된다."""
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
    # 절단 로직은 한 곳(truncate_release_notes.py)에 둔다 — 이모지 조합과 바이트 경계 처리가 거기 있다
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
    locales = read_store_locales(_read(str(ws / "version.yml")))
    return {"enabled": bool(locales), "default": locales[0] if locales else None,
            "locales": [{"locale": l, "code": store_code(args.platform, l)} for l in locales]}


def cmd_write(args) -> dict:
    ws = Path(args.workspace)
    locales = read_store_locales(_read(str(ws / "version.yml")))
    if not locales:
        # 키가 없으면 아무것도 하지 않는다 — 기존 사용자의 동작을 바꾸지 않는 약속
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
            return {"enabled": True, "ok": False, "error": "play 는 --version-code 가 필요합니다"}
        # 앱이 하위 폴더에 있는 모노레포는 version.yml(레포 루트)과 android/(앱 루트)가 다르다
        base = Path(args.app_root or args.workspace) / "android" / "fastlane" / "metadata" / "android"
    else:
        if not args.out_dir:
            return {"enabled": True, "ok": False, "error": "ios 는 --out-dir 가 필요합니다"}
        base = Path(args.out_dir)

    written = []
    for i, loc in enumerate(locales):
        code = store_code(args.platform, loc)
        # 기본 언어는 항상 기본 문구. 그 외는 번역이 있으면 번역
        text, source = (default_text, "default") if i == 0 else locale_text(release, loc, default_text)
        if args.platform == "play":
            target = base / code / "changelogs" / f"{args.version_code}.txt"
        else:
            target = base / f"{code}.txt"
        target.parent.mkdir(parents=True, exist_ok=True)
        # 번역이 없을 때 이미 준비된 파일(레포가 직접 쓴 언어별 노트 등)이 있으면 기본 문구로 덮어쓰지 않는다.
        # 덮으면 직접 쓴 영어 노트가 한국어로 바뀌는 회귀가 된다. 비어 있거나 없을 때만 기본 문구로 채운다.
        if i > 0 and source == "default" and target.is_file() and target.read_text(encoding="utf-8", errors="replace").strip():
            written.append({"locale": loc, "code": code, "source": "existing", "file": str(target)})
            continue
        target.write_text(text + "\n", encoding="utf-8")
        _truncate(target, args.platform)
        written.append({"locale": loc, "code": code, "source": source, "file": str(target)})

    pruned = []
    if args.platform == "play":
        # 목록에 없는 언어 폴더에 이번 버전 노트가 있으면(옛 경로가 만든 ko-KR 등) 치운다.
        # 안 치우면 목록에서 뺀 언어에도 문구가 올라간다.
        listed = {store_code("play", l) for l in locales}
        if base.is_dir():
            for d in sorted(p for p in base.iterdir() if p.is_dir() and p.name not in listed):
                stale = d / "changelogs" / f"{args.version_code}.txt"
                if stale.is_file():
                    stale.unlink()
                    pruned.append(d.name)
    return {"enabled": True, "ok": True, "default": locales[0], "written": written, "pruned": pruned,
            "translated": [w["locale"] for w in written if w["source"] == "store_notes"],
            "fell_back": [w["locale"] for w in written[1:] if w["source"] == "default"],
            "kept": [w["locale"] for w in written[1:] if w["source"] == "existing"]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="스토어 릴리스 노트를 언어별로 준비한다 (#829)")
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("write", "locales"):
        s = sub.add_parser(name)
        s.add_argument("--platform", choices=["play", "ios"], required=True)
        s.add_argument("--workspace", default=".")
    w = sub.choices["write"]
    w.add_argument("--version", required=True)
    w.add_argument("--version-code", default="")
    w.add_argument("--default-file", default="")
    w.add_argument("--override", default="", help="기본 언어 문구를 이 값으로 고정 (STORE_WHATS_NEW_OVERRIDE)")
    w.add_argument("--out-dir", default="")
    w.add_argument("--app-root", default="", help="android/ 가 있는 앱 폴더 (기본: --workspace)")
    args = p.parse_args(argv)
    result = cmd_write(args) if args.cmd == "write" else cmd_locales(args)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
