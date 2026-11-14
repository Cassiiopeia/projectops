#!/usr/bin/env python3
"""Message catalog lookup (#787) — stdlib only.

Switches text posted to user repos by `options.language`. English is the source (en.json), and each other language
is one JSON file. Translators add only a file, without touching code.

  - Missing keys fall back to English, and to the key string if English lacks it too (one text must never kill a workflow)
  - Substitution uses only {name} (same syntax in Python and JS). Missing values leave the placeholder as is
  - Contract strings (read by old consumers) live in contracts.py, not in the catalogs

CLI (bash and JS steps call Python once)
  messages.py lang                         current language
  messages.py get KEY [--var k=v ...]      one text
  messages.py bundle PREFIX                keys starting with PREFIX as JSON (for JS steps, placeholders kept)
  messages.py js PREFIX... [--version-yml P] module for github-script to require (comment_runtime.cjs + texts)
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
    """Language catalog. Empty dict if the file is missing or broken (falls back to English)."""
    try:
        data = json.loads((CATALOG_DIR / f"{lang}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def supported() -> list[str]:
    return sorted(p.stem for p in CATALOG_DIR.glob("*.json"))


def normalize(value) -> str:
    """Normalize values like ko-KR, ko_KR.UTF-8, zh-cn to a supported code. Unknown means English."""
    v = str(value or "").strip().split(".")[0].replace("_", "-")
    if not v:
        return FALLBACK
    have = {s.lower(): s for s in supported()}
    if v.lower() in have:
        return have[v.lower()]
    base = v.split("-")[0].lower()
    return have.get(base, FALLBACK)


def resolve_language(version_yml="version.yml", env=None) -> str:
    """REPO_LANG > version.yml options.language > (ko if version.yml exists without the key, en if there is no file).

    Why existing repos without the key stay ko: an update alone must not change the text in user repos
    (same principle as the template language, #769).
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
    """Whether any catalog (English included) has the key. The CLI uses it to tell missing keys apart."""
    return key in load_catalog(FALLBACK)


def bundle(prefix: str, lang: str | None = None) -> dict:
    lang = lang or resolve_language()
    base = {k: v for k, v in load_catalog(FALLBACK).items() if k.startswith(prefix)}
    base.update({k: v for k, v in load_catalog(lang).items() if k.startswith(prefix)})
    return base


RUNTIME_JS = CATALOG_DIR / "comment_runtime.cjs"


def render_js(prefixes, lang: str) -> str:
    """Texts for several prefixes + runtime > CommonJS module string (for type workflow comments, #769)."""
    merged = {}
    for prefix in prefixes:
        merged.update(bundle(prefix, lang))
    data = json.dumps({"lang": lang, "messages": merged}, ensure_ascii=False)
    return f"const DATA = {data};\n" + RUNTIME_JS.read_text(encoding="utf-8")


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
    j = sub.add_parser("js")
    j.add_argument("prefix", nargs="+")
    j.add_argument("--version-yml", default="version.yml")
    j.add_argument("--lang", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "lang":
        print(resolve_language())
    elif a.cmd == "get":
        # A missing key writes nothing and exits abnormally. Returning the key string like t() would make the bash step
        # use it as a commit message — the caller must be able to continue with `|| fallback text`.
        if not has(a.key):
            print(f"unknown message key: {a.key}", file=sys.stderr)
            return 3
        values = dict(v.split("=", 1) for v in a.var if "=" in v)
        sys.stdout.write(t(a.key, a.lang, **values))
    elif a.cmd == "js":
        sys.stdout.write(render_js(a.prefix, a.lang or resolve_language(a.version_yml)))
    else:
        print(json.dumps(bundle(a.prefix, a.lang), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
