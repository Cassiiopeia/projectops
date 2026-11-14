#!/usr/bin/env python3
"""Reads store deploy settings from code (.github/config/store-deploy.json) (#767) — stdlib only.

The deploy mode used to be decided as `manual run input || repo variable || default`. Repo variables
can only be changed in the GitHub settings page, leave no history in git, and do not follow
a moved or forked repo, so it **silently** reverts to the default.

Priority (highest first):
  1. Manual run input   — that run only
  2. Config file        — read by this script (kept in git and reviewed)
  3. Repo variable      — the old way, kept for compatibility
  4. Default (store_only)

Without a config file it does nothing — this template is installed into other repos, so the old behavior is the default.
**A mistyped value fails.** Silently ignoring a typo would deploy in a different mode while the user believes the setting
applied, and this setting even decides automatic production review submission.

Config (.github/config/store-deploy.json — a file the wizard does not overwrite):
  {
    "android": { "deploy_mode": "store_only", "production_rollout": "1.0" },
    "ios":     { "deploy_mode": "store_only" }
  }

Usage (workflow step):
  python3 .github/scripts/store_deploy_config.py resolve --platform android
  -> writes the applied values to $GITHUB_ENV. Env: INPUT_DEPLOY_MODE (manual run input, wins over the file when set)

push deploys skip the review stage (#816):
  Google Play merges new changes arriving during review into that review and reviews again (measured 2026-10-10 on EarLocAlert).
  Submitting production on every deploy means review never ends. So on push (automatic deploy)
  store_prepare / store_submit drop to store_only — even if a repo variable or the config file says otherwise.
  Production promotion and App Store review are chosen in a manual run (workflow_dispatch).
  Only repos that want automation set "auto_submit_on_push": true in the config file.

Conflict between automatic closed-testing promotion and production review (#816):
  Closed-testing promotion is also a review submission, so a push promoting closed testing while a manually submitted production review runs
  restarts the production review. The Play API has no review status, so after a manual store_submit run
  push skips intermediate-track promotion for review_cooldown_hours (default 48) -> review-guard subcommand.
  Manual runs too (#1005) — manual runs promoted by default and review was cancelled 9 times in a row (measured on passQL).
  Forcing it only via the manual run input force_promote_during_review (env FORCE_PROMOTE_DURING_REVIEW=true).
"""
import argparse
import json
import os
import sys

DEFAULT_PATH = ".github/config/store-deploy.json"
# Production stages that lead to review. Not used on push without auto_submit_on_push (#816).
REVIEW_MODES = {"store_prepare", "store_submit", "appstore_prepare", "appstore_submit"}
DEFAULT_REVIEW_COOLDOWN_HOURS = 48
DEPLOY_MODES = {"store_only", "store_prepare", "store_submit",
                # Old aliases (the Fastfile accepts them)
                "testflight_only", "appstore_prepare", "appstore_submit"}
PLATFORMS = ("android", "ios")


class ConfigError(Exception):
    pass


def load(path: str) -> dict | None:
    """Read the config. None if the file is missing."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise ConfigError(f"Cannot read {path}: {e}")
    if not isinstance(data, dict):
        raise ConfigError(f"The top level of {path} must be an object")
    return data


def resolve(data: dict | None, platform: str, input_deploy_mode: str = "",
            input_promote_closed: str = "") -> dict:
    """Decide values to apply from the file. Returns {env var name: value} (empty dict if nothing to apply)."""
    if not data or platform not in PLATFORMS:
        return {}
    section = data.get(platform) or {}
    if not isinstance(section, dict):
        raise ConfigError(f"'{platform}' must be an object")
    out: dict = {}

    mode = section.get("deploy_mode")
    if mode is not None:
        mode = str(mode).strip()
        if mode not in DEPLOY_MODES:
            raise ConfigError(
                f"Invalid {platform}.deploy_mode value '{mode}'. "
                f"Must be one of {' | '.join(sorted(DEPLOY_MODES - {'testflight_only', 'appstore_prepare', 'appstore_submit'}))}")
        # A manual run input wins for that run only
        if not (input_deploy_mode or "").strip():
            out["DEPLOY_MODE"] = mode

    rollout = section.get("production_rollout")
    if rollout is not None:
        if platform != "android":
            raise ConfigError("production_rollout is for android only")
        try:
            value = float(str(rollout).strip())
        except ValueError:
            value = None
        if value is None or not (0 < value <= 1):
            raise ConfigError(f"android.production_rollout value '{rollout}' must be a number greater than 0 and at most 1.0 (e.g. 1.0, 0.1)")
        out["PRODUCTION_ROLLOUT"] = str(rollout).strip()

    for key in ("auto_submit_on_push", "promote_closed_testing"):
        v = section.get(key)
        if v is not None and not isinstance(v, bool):
            raise ConfigError(f"{platform}.{key} must be true or false (got: {v!r})")
    if section.get("promote_closed_testing") is not None:
        if platform != "android":
            raise ConfigError("promote_closed_testing is for android only")
        # Choosing true/false in a manual run wins for that run only (default or empty lets the file win, #1005)
        if (input_promote_closed or "").strip() not in ("true", "false"):
            out["PROMOTE_TO_CLOSED_TESTING"] = "true" if section["promote_closed_testing"] else "false"
    hours = section.get("review_cooldown_hours")
    if hours is not None:
        if platform != "android":
            raise ConfigError("review_cooldown_hours is for android only")
        if not isinstance(hours, (int, float)) or isinstance(hours, bool) or hours < 0:
            raise ConfigError(f"android.review_cooldown_hours must be a number of 0 or more (got: {hours!r})")
    return out


def push_policy(data: dict | None, platform: str, event: str, effective_mode: str) -> tuple[dict, str | None]:
    """Block review stages on push (automatic deploy). Returns (values to override, notice text or None)."""
    if (event or "") == "workflow_dispatch":
        return {}, None
    mode = (effective_mode or "").strip()
    if mode not in REVIEW_MODES:
        return {}, None
    section = ((data or {}).get(platform) or {}) if isinstance((data or {}).get(platform), dict) else {}
    if section.get("auto_submit_on_push") is True:
        return {}, f"auto_submit_on_push: true — proceeding with {mode} on push too"
    what = "production promotion" if platform == "android" else "App Store review preparation and submission"
    return {"DEPLOY_MODE": "store_only"}, (
        f"This is a push deploy, so {what} ({mode}) is skipped and store_only is used. "
        f"Run this workflow manually in Actions (deploy_mode) for {what}. "
        "To do it automatically on every push, set "
        f'"{platform}": {{"auto_submit_on_push": true}} in .github/config/store-deploy.json — a deploy that arrives during review restarts that review.')


def recent_production_submit(runs: list[dict], now_ts: float, hours: float) -> dict | None:
    """Find a manual store_submit run that finished within the cooldown. runs is workflow_runs from the Actions API."""
    import datetime as _dt
    for r in runs:
        if r.get("event") != "workflow_dispatch" or r.get("conclusion") != "success":
            continue
        if "store_submit" not in (r.get("display_title") or ""):
            continue
        try:
            ts = _dt.datetime.strptime(r["updated_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc).timestamp()
        except (KeyError, ValueError):
            continue
        if now_ts - ts < hours * 3600:
            return r
    return None


def _write_env(values: dict) -> None:
    env_file = os.environ.get("GITHUB_ENV")
    for k, v in values.items():
        if env_file:
            with open(env_file, "a", encoding="utf-8") as f:
                f.write(f"{k}={v}\n")


def review_guard(a) -> int:
    """Keep intermediate-track promotion from restarting a production review in progress (push #816, manual run #1005).

    Never blocks the deploy on failure — if it cannot check, it only warns and proceeds as configured.
    """
    if os.environ.get("PROMOTE_TO_CLOSED_TESTING", "false") != "true" and os.environ.get("PROMOTE_TO_OPEN_TESTING", "false") != "true":
        return 0
    is_manual_run = os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if is_manual_run and os.environ.get("FORCE_PROMOTE_DURING_REVIEW", "").strip().lower() == "true":
        print("::warning title=Production review guard skipped::force_promote_during_review is on — "
              "closed/open testing promotion runs even if a production review is in progress, which restarts that review.")
        return 0
    try:
        data = load(a.file)
    except ConfigError as e:
        print(f"::error title=store-deploy.json config error::{e}")
        return 1
    hours = ((data or {}).get("android") or {}).get("review_cooldown_hours", DEFAULT_REVIEW_COOLDOWN_HOURS)
    if not hours:
        return 0
    import time as _time
    import github_api
    repo, token = os.environ.get("GITHUB_REPOSITORY", ""), os.environ.get("GITHUB_TOKEN", "")
    wf = (os.environ.get("GITHUB_WORKFLOW_REF", "").split("@")[0].rsplit("/", 1)[-1])
    url = f"{github_api.API_ROOT}/repos/{repo}/actions/workflows/{wf}/runs?event=workflow_dispatch&status=success&per_page=20"
    try:
        runs = (github_api.request("GET", url, token, user_agent="projectops-store-deploy",
                                   timeout_seconds=20) or {}).get("workflow_runs", [])
    except Exception as e:  # noqa: BLE001 — a failed check never blocks the deploy
        print(f"::warning title=Production review check failed::Could not check recent manual production submissions, proceeding as configured ({e})")
        return 0
    hit = recent_production_submit(runs, _time.time(), float(hours))
    if not hit:
        print(f"No manual production submission in the last {hours} hours — proceeding with closed/open testing promotion.")
        return 0
    _write_env({"PROMOTE_TO_CLOSED_TESTING": "false", "PROMOTE_TO_OPEN_TESTING": "false"})
    print(f"::warning title=Skipped closed/open testing promotion::A manual production submission ran at {hit.get('updated_at')}. "
          f"Promoting while that review runs restarts the production review, so for {hours} hours builds go to internal testing only "
          f"({hit.get('html_url')}). To promote now anyway, run this workflow manually with force_promote_during_review on.")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("resolve")
    r.add_argument("--platform", required=True, choices=PLATFORMS)
    r.add_argument("--file", default=DEFAULT_PATH)
    g = sub.add_parser("review-guard", help="Keep push-time intermediate track promotion from disturbing a production review in progress")
    g.add_argument("--file", default=DEFAULT_PATH)
    a = ap.parse_args(argv)
    if a.cmd == "review-guard":
        return review_guard(a)

    try:
        data = load(a.file)
        values = resolve(data, a.platform, os.environ.get("INPUT_DEPLOY_MODE", ""),
                         os.environ.get("INPUT_PROMOTE_TO_CLOSED_TESTING", ""))
    except ConfigError as e:
        print(f"::error title=store-deploy.json config error::{e}")
        print(f"❌ {e}", file=sys.stderr)
        return 1

    # On push block review stages — whether they came from a repo variable (already in env) or the config file (#816)
    effective = (os.environ.get("INPUT_DEPLOY_MODE") or values.get("DEPLOY_MODE")
                 or os.environ.get("DEPLOY_MODE", "store_only"))
    override, note = push_policy(data, a.platform, os.environ.get("GITHUB_EVENT_NAME", ""), effective)
    if note:
        print(f"::notice title=Review steps run from a manual run::{note}" if override else f"ℹ️ {note}")
    values.update(override)

    if not values:
        print("Nothing to apply from store-deploy.json (no file, or the manual input wins) — using repository variables and defaults.")
        return 0
    for k, v in values.items():
        print(f"📄 Applied → {k}={v}")
    _write_env(values)
    return 0


if __name__ == "__main__":
    sys.exit(main())
