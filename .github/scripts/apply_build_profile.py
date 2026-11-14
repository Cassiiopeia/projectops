#!/usr/bin/env python3
# ===================================================================
# apply_build_profile.py — applies a build profile to both layers together (#603)
# ===================================================================
#
# Cross-platform (Windows/macOS/Linux), standard library only — no PyYAML/jq.
#
# ## Why it exists
#
# An app's development switches live in **two layers**.
#
#   runtime       `.env`           read as an asset by dotenv. Injected from a Secret.
#   compile time  `--dart-define`  baked into the binary. Cannot be forged with a Secret.
#
# Turning one feature on needs **both layers to agree.** When the workflow handles the two
# separately, **applying only one still passes.** Real incident: `.env` got the dev flag and
# the log said "applied", but the installed app had no debugging tools — it was a release build,
# so the compile-time gate was closed. The log alone could not show it.
#
# This script **decides both layers in one place.** The workflow uses the result as is:
#
#   - name: Apply build profile
#     id: build_profile
#     run: python3 .github/scripts/apply_build_profile.py test .env
#
#   - name: Build
#     # 🔴 Never write dart-defines here directly. The moment you do, there are two places again.
#     run: flutter build apk --release ${{ steps.build_profile.outputs.build_flags }}
#
# ## No config means it does nothing ⚠️
#
# This template is installed into other people's repos. Touching `.env` or inventing build flags
# in a repo without profile definitions **breaks builds that were working.**
# Without a config file it emits an empty `build_flags` and ends successfully.
#
# ## Config (.github/config/build-profile.json)
#
#   {
#     "dev_keys":    ["APP_SHOW_DEV_TOOLS", "APP_ENABLE_NETWORK_LOG"],
#     "secret_keys": ["APP_DEV_ACCESS_TOKEN"],
#     "profiles": {
#       "test":    {"env": {"APP_SHOW_DEV_TOOLS": "true"},
#                   "dart_define": {"APP_FLAVOR": "dev"}},
#       "release": {"env": {"APP_SHOW_DEV_TOOLS": "false"},
#                   "dart_define": {}}
#     }
#   }
#
#   dev_keys     dev-only runtime keys. Removed from .env before applying the profile
#                (so values left in the Secret cannot survive).
#   secret_keys  keys that stop a release build if they have any value (QA tokens, etc.).
#   profiles     profile name -> env / dart_define to apply. Names are free.
#
# A profile named `release` **is verified** — a build never goes out with dev keys on
# or with a QA token left behind.
# ===================================================================

import argparse
import json
import os
import shlex
import sys
from pathlib import Path

DEFAULT_CONFIG = Path(".github/config/build-profile.json")

# A profile with this name is verified to have everything "off".
GUARDED_PROFILE = "release"


def log(msg):
    # Keep log output alive even when non-UTF-8 bytes (surrogateescape) are in values
    print(msg.encode("utf-8", "backslashreplace").decode("utf-8"), file=sys.stderr)


def fail(msg):
    # GitHub Actions annotation format — stands out in the log and shows in the summary
    print(f"::error::{msg}", file=sys.stderr)
    sys.exit(1)


def load_config(path: Path):
    """Read the config. None if missing — the caller treats it as 'do nothing'."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        # Silently ignoring a broken config costs hours of "why doesn't it work"
        fail(f"Cannot read the build profile config: {path} ({e})")
    if not isinstance(data, dict):
        fail(f"The build profile config is not an object: {path}")
    return data


def read_env_lines(env_file: Path):
    if not env_file.is_file():
        fail(f"No .env file: {env_file}")
    # Do not crash on non-ASCII values — do not rely on the runner locale.
    # Reading with replace and writing back permanently turns the original bytes into U+FFFD,
    # so read with surrogateescape and restore the same bytes on write (#693).
    return env_file.read_text(encoding="utf-8", errors="surrogateescape").splitlines()


def parse_env_line(line):
    """Read one `.env` line as (key, value). None if it is not a key line.

    Treats `export KEY=v`, `KEY = v`, `KEY="v"` (all accepted by dotenv variants) as the same key.
    strip and verify must share this one function so neither side misses a bypass (#692).
    """
    s = line.strip()
    if not s or s.startswith("#") or "=" not in s:
        return None
    key, value = s.split("=", 1)
    key = key.strip()
    if key.startswith("export") and key[6:7].isspace():
        key = key[6:].strip()
    if not key:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        value = value[1:-1]
    return key, value


def strip_keys(lines, keys):
    """Remove the lines that declare the given keys.

    Why not sed -i: GNU (-i) and BSD (-i '') syntax differ, so Linux and
    macOS runners behave differently. A silent pass that changed nothing
    really happened (#523).
    """
    keys = set(keys)
    kept = []
    for ln in lines:
        parsed = parse_env_line(ln)
        if parsed is None or parsed[0] not in keys:
            kept.append(ln)
    return kept


def env_value(lines, key):
    """The last declared value wins — the usual dotenv behavior."""
    found = None
    for ln in lines:
        parsed = parse_env_line(ln)
        if parsed is not None and parsed[0] == key:
            found = parsed[1]
    return found


def mask(key, value):
    """Never print values of tokens/passwords — anyone can read build logs."""
    if value is None or value == "":
        return "(none)"
    upper = key.upper()
    if any(w in upper for w in ("TOKEN", "SECRET", "PASSWORD", "KEY_JSON", "CREDENTIAL")):
        return "(set)"
    return value


def to_text(where, key, value):
    """Turn a config value into a string. JSON booleans become lowercase — bool.fromEnvironment
    only reads lowercase `true` as true, so a `True` would silently become false in the app (#693)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if "\n" in value or "\r" in value:
            fail(f"Build profile value contains a newline: {where}.{key}")
        return value
    fail(f"Build profile values must be a string, number or boolean: {where}.{key} ({type(value).__name__})")


def as_map(where, value):
    """Validate a config piece that must be an object and return a copy (structure errors as guidance instead of a traceback)."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        fail(f"Build profile config structure error: {where} must be an object")
    return {str(k): to_text(where, k, v) for k, v in value.items()}


def as_key_list(where, value):
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(k, str) for k in value):
        fail(f"Build profile config structure error: {where} must be a list of strings")
    return list(value)


def define_tokens(dart_define: dict):
    # Keep dict order — the order in the config file should show in the log as is for readability
    return [f"--dart-define={k}={v}" for k, v in dart_define.items()]


def build_flags(dart_define: dict) -> str:
    # The workflow drops this into a shell command line as is, so quote spaces and metacharacters (#693)
    return " ".join(shlex.quote(t) for t in define_tokens(dart_define))


def emit_output(flags: str):
    """Export so the workflow can append it to the build command. Local runs print to screen only."""
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"build_flags={flags}\n")


def verify_release(lines, dev_keys, secret_keys, flags, test_defines):
    """Check both layers so a release build does not ship in a dev state."""
    for k in dev_keys:
        v = env_value(lines, k)
        if v is not None and v.strip().lower() == "true":
            fail(f"A development key is on in a release build: {k}")
    for k in secret_keys:
        v = env_value(lines, k)
        if v is not None and v.strip() != "":
            fail(f"A development secret is left in a release build: {k}")
    # Check the compile-time side too. If this leaks, a dev build ships no matter how clean .env is.
    for k, v in test_defines.items():
        if f"--dart-define={k}={v}" in shlex.split(flags):
            fail(f"A test-only flag got into a release build: {k}={v}")
    log("✅ Confirmed both runtime and compile-time layers are off")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Apply a build profile to both .env and dart-define")
    ap.add_argument("profile", help="Profile name (e.g. test, release)")
    ap.add_argument("env_file", help=".env path")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG),
                    help=f"Config file (default: {DEFAULT_CONFIG})")
    args = ap.parse_args(argv)

    cfg = load_config(Path(args.config))

    # ── No config -> do nothing (existing repos unaffected) ──
    if cfg is None:
        log(f"ℹ️  No build profile config ({args.config}) — skipping")
        emit_output("")
        return 0

    profiles = cfg.get("profiles") or {}
    if not isinstance(profiles, dict):
        fail("Build profile config structure error: profiles must be an object")
    if args.profile not in profiles:
        available = ", ".join(sorted(profiles)) or "(none)"
        fail(f"Unknown profile: {args.profile} — available in config: {available}")

    profile = profiles[args.profile]
    if profile is None:
        profile = {}
    if not isinstance(profile, dict):
        fail(f"Build profile config structure error: profiles.{args.profile} must be an object")
    dev_keys = as_key_list("dev_keys", cfg.get("dev_keys"))
    secret_keys = as_key_list("secret_keys", cfg.get("secret_keys"))
    want_env = as_map(f"{args.profile}.env", profile.get("env"))
    dart_define = as_map(f"{args.profile}.dart_define", profile.get("dart_define"))

    env_file = Path(args.env_file)
    lines = read_env_lines(env_file)

    # Remove dev keys and the keys we are about to write, then write them again.
    # Why remove dev_keys: if values left in the Secret survive, the profile
    # loses its meaning. Why remove want_env: prevents the same key appearing twice.
    lines = strip_keys(lines, set(dev_keys) | set(want_env))
    for k, v in want_env.items():
        lines.append(f"{k}={v}")

    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8",
                        errors="surrogateescape")

    flags = build_flags(dart_define)
    emit_output(flags)

    # ── Result — show both layers together ──
    # Printing only one layer makes "applied" a lie. That is why this script exists.
    log(f"✅ Build profile applied: {args.profile}")
    log("── Runtime switches (.env) ──")
    shown = list(dict.fromkeys(list(want_env) + dev_keys + secret_keys))
    if shown:
        for k in shown:
            log(f"  {k:<28} {mask(k, env_value(lines, k))}")
    else:
        log("  (no keys defined)")
    log("── Compile-time flags (dart-define) ──")
    log(f"  {flags}" if flags else "  (none)")

    if args.profile == GUARDED_PROFILE:
        test_defines = {}
        for name, p in profiles.items():
            if name != GUARDED_PROFILE:
                p = {} if p is None else p
                if not isinstance(p, dict):
                    fail(f"Build profile config structure error: profiles.{name} must be an object")
                test_defines.update(as_map(f"{name}.dart_define", p.get("dart_define")))
        # If the release profile overwrote the same key **with a different value**, it is not a violation
        # (e.g. test has APP_FLAVOR=dev, release has APP_FLAVOR=prod).
        # If the value is the same, it was not overwritten — the test value is shipping as is, so block it.
        for k, v in dart_define.items():
            if test_defines.get(k) != v:
                test_defines.pop(k, None)
        verify_release(lines, dev_keys, secret_keys, flags, test_defines)

    return 0


if __name__ == "__main__":
    sys.exit(main())
