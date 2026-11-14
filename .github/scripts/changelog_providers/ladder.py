#!/usr/bin/env python3
"""Changelog provider fallback ladder orchestrator (#455).

Tries providers in order based on version.yml options.changelog.provider and
keeps the pr_body.md of the first one that succeeds. commit is the AI-free last resort.

  provider=commit                    → commit
  provider=copilot                   -> copilot -> (external AI if a key exists) -> commit
                                       * Copilot is billed per request. Used only when set explicitly.
  provider=openai|gemini|claude|ollama -> that provider -> commit
  provider=commit / unset (default)    -> (external AI if a key exists) -> commit
                                       * The default path has no billed step.
    (The coderabbit step itself is the request/polling in workflow Job 1 — reaching this ladder
     means CodeRabbit already did not respond, so it is not retried)
  * The openai step is added only when MODEL_API_KEY exists (pointless otherwise)

Input: CHANGELOG_PROVIDER + each provider's env vars passed through
Output: pr_body.md + provider_result.json({provider, attempted, failed, notice})
      + stdout `PROVIDER=<winner>` + exit 0. exit 1 if every step fails.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OPENAI_FAMILY = ("openai", "gemini", "claude", "groq", "mistral", "ollama")


# Dedicated Secret name per service (#569).
# With a single MODEL_API_KEY neither people nor code could tell "which service the key is for".
# The name alone should tell what to put in it.
KEY_ENVS = [
    ("GEMINI_API_KEY", "gemini"),
    ("OPENAI_API_KEY", "openai"),
    ("ANTHROPIC_API_KEY", "claude"),
    ("GROQ_API_KEY", "groq"),
    ("MISTRAL_API_KEY", "mistral"),
]

# MODEL_API_KEY (old name) backward compatibility — guess the service from the key prefix.
KEY_PREFIXES = [
    ("sk-ant-", "claude"),
    ("gsk_", "groq"),
    ("sk-", "openai"),
    ("AIza", "gemini"),
]


def detect_key():
    """Find (provider name, env name holding the key) among registered keys. None -> (None, None).

    Dedicated names first. If several exist, pick one in the order of the list above.
    """
    for env, name in KEY_ENVS:
        if os.environ.get(env):
            return name, env

    legacy = os.environ.get("MODEL_API_KEY")
    if not legacy:
        return None, None
    for prefix, name in KEY_PREFIXES:
        if legacy.startswith(prefix):
            return name, "MODEL_API_KEY"
    # Unknown prefix: try gemini — it is the most common because of its free tier.
    print("ℹ️ Cannot tell which service MODEL_API_KEY is for, trying Gemini. "
          "A dedicated name such as GEMINI_API_KEY is exact.", file=sys.stderr)
    return "gemini", "MODEL_API_KEY"


def build_rungs(provider):
    """List of (label, script, extra env) — the order to try.

    Every path ends with commit. It depends on no AI or network and always finishes,
    so "empty release notes" never happens.

    github-ai was removed from the list — GitHub Models shut down on 2026-07-30 and calls
    return 410 (#566). A stored value is absorbed by the GONE handling below.
    """
    commit = ("commit", "commit.py", {})
    copilot = ("copilot", "copilot.py", {})
    key_provider, key_env = detect_key()
    has_key = key_provider is not None
    # Whatever name holds it, openai_compatible.py reads MODEL_API_KEY, so pass it there.
    key_rung = (f"openai:{key_provider}", "openai_compatible.py",
                {"PROVIDER_NAME": key_provider or "gemini",
                 "MODEL_API_KEY": os.environ.get(key_env or "", "")}) if has_key else None

    if provider == "commit":
        # Registering a key is itself a statement of "I want AI" (#569).
        # commit is the default for "not configured", not "never use AI",
        # so with a key AI is tried first. To run without AI, do not register a key.
        #
        # ⚠️ Never put Copilot here. Copilot consumes Premium Requests, so
        # on the default path it would drain credits without the installer knowing. This template is
        # installed into other people's repos, so the default must be "costs nothing".
        # To use Copilot, set provider to copilot explicitly.
        rungs = []
        if has_key:
            rungs.append(key_rung)
        rungs.append(commit)
        return rungs
    if provider in OPENAI_FAMILY:
        # If a provider is set explicitly, follow it. Find the key under the dedicated or old name and pass it on.
        return [(f"openai:{provider}", "openai_compatible.py",
                 {"PROVIDER_NAME": provider,
                  "MODEL_API_KEY": os.environ.get(key_env or "", "") or os.environ.get("MODEL_API_KEY", "")}), commit]
    if provider == "copilot":
        rungs = [copilot]
        # Copilot is billed per request and its quota is tight. With a key, external AI is the next step.
        if has_key:
            rungs.append(key_rung)
        rungs.append(commit)
        return rungs
    # Retired provider (github-ai), coderabbit or unknown value -> external AI with a key, else commit analysis
    rungs = []
    if has_key:
        rungs.append(key_rung)
    rungs.append(commit)
    return rungs


def run_rung(script, extra_env):
    env = dict(os.environ)
    env.update(extra_env)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    proc = subprocess.run(
        [sys.executable, os.path.join(HERE, script)],
        env=env, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    # Pass the rung's logs through so the reason shows in the workflow log
    if proc.stdout.strip():
        print(proc.stdout.strip())
    if proc.stderr.strip():
        print(proc.stderr.strip(), file=sys.stderr)
    return proc.returncode == 0 and os.path.isfile("pr_body.md")


def main():
    provider = os.environ.get("CHANGELOG_PROVIDER") or "commit"
    if provider == "github-ai":
        # Retired service — absorbed silently for existing repos that still store it (#566).
        print("ℹ️ Skipping github-ai because the service was shut down (GitHub Models, 2026-07-30)", file=sys.stderr)
        provider = "commit"
    rungs = build_rungs(provider)
    attempted, failed, winner = [], [], None

    for label, script, extra_env in rungs:
        attempted.append(label)
        print(f"🪜 Trying provider: {label}")
        if run_rung(script, extra_env):
            winner = label
            break
        failed.append(label)
        print(f"↩️ {label} failed — falling back to the next step", file=sys.stderr)

    notice = None
    if winner and failed:
        notice = f"{' → '.join(failed)} failed → {winner} used"

    with open("provider_result.json", "w", encoding="utf-8") as f:
        json.dump(
            {"provider": winner, "attempted": attempted, "failed": failed, "notice": notice},
            f, ensure_ascii=False,
        )

    if not winner:
        print("❌ Every ladder step failed — cannot create pr_body.md", file=sys.stderr)
        sys.exit(1)
    print(f"PROVIDER={winner}")


if __name__ == "__main__":
    main()
