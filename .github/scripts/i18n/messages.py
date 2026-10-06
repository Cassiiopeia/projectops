#!/usr/bin/env python3
"""메시지 카탈로그 조회 (#787) — stdlib 전용.

사용자 레포에 게시되는 문구를 `options.language` 에 따라 바꾼다. 영문이 정본(en.json)이고 다른 언어는
JSON 한 파일씩이다. 번역가는 코드를 건드리지 않고 파일만 추가한다.

  - 없는 키는 영문으로, 영문에도 없으면 키 문자열을 돌려준다 (문구 하나 때문에 워크플로우가 죽으면 안 된다)
  - 치환은 {name} 만 쓴다 (파이썬과 JS 가 같은 문법). 값이 없으면 자리표시자를 그대로 둔다
  - 계약 문자열(구버전 소비자가 읽는 것)은 contracts.py 에 있고 카탈로그에 넣지 않는다

CLI (bash 와 JS 단계가 파이썬을 한 번 부르면 된다)
  messages.py lang                         현재 언어
  messages.py get KEY [--var k=v ...]      한 문구
  messages.py bundle PREFIX                PREFIX 로 시작하는 키를 JSON 으로 (JS 단계용, 자리표시자는 그대로)
"""
from __future__ import annotations

import argparse
import functools
import json
import os
import re
import sys
from pathlib import Path

FALLBACK = "en"
CATALOG_DIR = Path(__file__).resolve().parent
_PLACEHOLDER = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_LANG_KEY = re.compile(r"^\s+language:\s*[\"']?([A-Za-z]{2,3}(?:[-_][A-Za-z0-9]{2,8})*)[\"']?", re.M)


@functools.lru_cache(maxsize=None)
def load_catalog(lang: str) -> dict:
    """언어 카탈로그. 파일이 없거나 깨져 있으면 빈 사전 (영문으로 대체된다)."""
    try:
        data = json.loads((CATALOG_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def supported() -> list[str]:
    return sorted(p.stem for p in CATALOG_DIR.glob("*.json"))


def normalize(value) -> str:
    """ko-KR, ko_KR.UTF-8, zh-cn 같은 값을 지원하는 코드로 맞춘다. 모르면 영문."""
    v = str(value or "").strip().split(".")[0].replace("_", "-")
    if not v:
        return FALLBACK
    have = {s.lower(): s for s in supported()}
    if v.lower() in have:
        return have[v.lower()]
    base = v.split("-")[0].lower()
    return have.get(base, FALLBACK)


def resolve_language(version_yml="version.yml", env=None) -> str:
    """REPO_LANG > version.yml options.language > (version.yml 이 있는데 키가 없으면 ko, 파일이 없으면 en).

    키가 없는 기존 레포를 ko 로 두는 이유: 업데이트만으로 사용자 레포의 문구가 바뀌면 안 된다
    (템플릿 언어와 같은 원칙, #769).
    """
    env = os.environ if env is None else env
    if env.get("REPO_LANG"):
        return normalize(env["REPO_LANG"])
    try:
        text = Path(version_yml).read_text(encoding="utf-8")
    except OSError:
        return FALLBACK
    m = _LANG_KEY.search(text)
    return normalize(m.group(1)) if m else "ko"


def _format(text: str, values: dict) -> str:
    return _PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


def t(key: str, lang: str | None = None, **values) -> str:
    lang = lang or resolve_language()
    text = load_catalog(lang).get(key)
    if text is None:
        text = load_catalog(FALLBACK).get(key)
    if text is None:
        return key
    return _format(text, values)


def has(key: str) -> bool:
    """어느 카탈로그(영문 포함)에도 키가 있는가. CLI 가 없는 키를 구분하는 데 쓴다."""
    return key in load_catalog(FALLBACK)


def bundle(prefix: str, lang: str | None = None) -> dict:
    lang = lang or resolve_language()
    base = {k: v for k, v in load_catalog(FALLBACK).items() if k.startswith(prefix)}
    base.update({k: v for k, v in load_catalog(lang).items() if k.startswith(prefix)})
    return base


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lang")
    g = sub.add_parser("get")
    g.add_argument("key")
    g.add_argument("--var", action="append", default=[], help="k=v")
    g.add_argument("--lang", default=None)
    b = sub.add_parser("bundle")
    b.add_argument("prefix")
    b.add_argument("--lang", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "lang":
        print(resolve_language())
    elif a.cmd == "get":
        # 없는 키는 아무것도 쓰지 않고 비정상 종료한다. t() 처럼 키 문자열을 돌려주면 bash 단계가
        # 그것을 커밋 메시지로 쓰게 된다 — 호출자가 `|| 대체 문구`로 이어 갈 수 있어야 한다.
        if not has(a.key):
            print(f"unknown message key: {a.key}", file=sys.stderr)
            return 3
        values = dict(v.split("=", 1) for v in a.var if "=" in v)
        sys.stdout.write(t(a.key, a.lang, **values))
    else:
        print(json.dumps(bundle(a.prefix, a.lang), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
