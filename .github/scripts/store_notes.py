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
#   스토어마다 언어가 다르면 store_locales_ios / store_locales_play 로 그 스토어만 따로 적는다(없으면 공통).
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

# 스토어가 인정하는 언어 코드 — fastlane 2.240.1 소스에서 그대로 옮겼다.
#   App Store : fastlane_core/lib/fastlane_core/languages.rb  ALL_LANGUAGES
#   Google Play: supply/lib/supply/languages.rb              ALL_LANGUAGES (밑줄 → 하이픈)
# 목록에 없는 코드를 넘기면 deliver 는 그 언어를 앱에 새로 활성화하려 하고, supply 는 거부한다.
# 그래서 지어낸 코드를 그대로 넘기지 않는다 — 목록 밖이면 그 스토어에서는 건너뛰고 보고한다.
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

# 이름 규칙만으로는 맞출 수 없는 짝 (Play → App Store). 나머지는 아래 _ios_for 가 규칙으로 찾는다.
_PLAY_TO_IOS_EXCEPTIONS = {
    "zh-CN": "zh-Hans", "zh-TW": "zh-Hant", "zh-HK": "zh-Hant",
    "iw-IL": "he", "es-419": "es-MX", "ar": "ar-SA", "sl": "sl-SI",
}


def _ios_for(play_code: str) -> str | None:
    """Play 코드에 대응하는 App Store 코드. 없으면 None (그 언어는 App Store 에 없다)."""
    if play_code in _PLAY_TO_IOS_EXCEPTIONS:
        return _PLAY_TO_IOS_EXCEPTIONS[play_code]
    if play_code in IOS_LANGUAGES:
        return play_code
    base = play_code.split("-")[0]
    if base in IOS_LANGUAGES:                      # fi-FI → fi, ko-KR → ko, hi-IN → hi, ms-MY → ms
        return base
    regional = [c for c in IOS_LANGUAGES if c.split("-")[0] == base]
    return regional[0] if len(regional) == 1 else None


# 정본 표기는 Play 방식(ko-KR). 사용자가 App Store 표기(ko, zh-Hans)로 적어도 같은 정본으로 모은다.
CANONICAL_TO_IOS = {pc: ic for pc in sorted(PLAY_LANGUAGES) if (ic := _ios_for(pc))}
ALIASES: dict[str, str] = {}
for _pc, _ic in sorted(CANONICAL_TO_IOS.items()):
    # App Store 코드 하나에 Play 코드가 여럿이면(zh-Hant ← zh-TW, zh-HK) 지역 표기가 대표인 쪽을 고정한다
    ALIASES.setdefault(_ic.lower(), _pc)
ALIASES.update({"zh-hant": "zh-TW", "ms": "ms", "ko": "ko-KR", "ja": "ja-JP"})
for _ic in IOS_LANGUAGES:                          # Play 에는 없는 App Store 전용 언어(or-IN, pa-IN, ur-PK 등)
    ALIASES.setdefault(_ic.lower(), _ic)

# 스토어별 한도 (여유를 둔 값). 넘기면 업로드가 통째로 거부된다.
LIMITS = {"play": (480, "char"), "ios": (3800, "byte")}
FALLBACK_TEXT = "버그를 수정하고 안정성을 개선했습니다."


def canonical(locale: str) -> str:
    """언어 표기를 정본(Play 방식)으로 모은다. ko_KR·KO-kr 처럼 적어도 같다. 모르는 표기는 그대로 둔다."""
    loc = (locale or "").strip().replace("_", "-")
    if loc in PLAY_LANGUAGES:
        return loc
    lower = loc.lower()
    for code in PLAY_LANGUAGES:                    # 대소문자만 다른 Play 코드
        if code.lower() == lower:
            return code
    return ALIASES.get(lower, loc)


def store_code(platform: str, locale: str) -> str | None:
    """그 스토어가 인정하는 언어 코드. 그 스토어에 없는 언어면 None — 호출부는 건너뛰고 보고한다."""
    c = canonical(locale)
    if platform == "ios":
        if c in IOS_LANGUAGES:                     # App Store 전용 언어를 정본으로 받은 경우
            return c
        return CANONICAL_TO_IOS.get(c)
    return c if c in PLAY_LANGUAGES else None


def _read_list(version_yml_text: str, key: str) -> list[str] | None:
    """options.<key> 인라인 배열. 키가 없으면 None, 있으면 정본 표기로 모은 중복 없는 목록."""
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
    """이 스토어가 쓸 언어 목록. 없으면 빈 목록 — 호출부는 옛 동작을 유지한다.

    스토어마다 언어 구성이 다를 수 있다. store_locales_ios / store_locales_play 가 있으면 그 스토어는
    그것을 쓰고, 없으면 공통 store_locales. App Store 에 없는 언어를 목록에 두면 deliver 가 그 언어를
    앱에 새로 활성화해 버리므로(fastlane 소스 확인) 스토어별로 좁힐 수 있어야 한다.
    """
    if platform in ("ios", "play"):
        own = _read_list(version_yml_text, f"store_locales_{platform}")
        if own:
            return own
    return _read_list(version_yml_text, "store_locales") or []


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
    locales = read_store_locales(_read(str(ws / "version.yml")), args.platform)
    return {"enabled": bool(locales), "default": locales[0] if locales else None,
            "locales": [{"locale": l, "code": store_code(args.platform, l)} for l in locales],
            "unsupported": [l for l in locales if store_code(args.platform, l) is None]}


def cmd_write(args) -> dict:
    ws = Path(args.workspace)
    locales = read_store_locales(_read(str(ws / "version.yml")), args.platform)
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

    written, unsupported = [], []
    for i, loc in enumerate(locales):
        code = store_code(args.platform, loc)
        if code is None:
            # 이 스토어에 없는 언어 코드. 넘기면 deliver 는 앱에 언어를 새로 활성화하려 하고 supply 는 거부한다.
            unsupported.append(loc)
            print(f"⚠️ store_notes: '{loc}' 는 {args.platform} 스토어 언어 코드가 아니라 건너뜁니다", file=sys.stderr)
            continue
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
