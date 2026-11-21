#!/usr/bin/env python3
"""SUH-ISSUE-HELPER — posts the branch name / commit message comment when an issue is created or retitled (in-house version).

Replaces the old external action (Cassiiopeia/github-issue-helper@deploy). stdlib only.

⚠️ Fixed contract — consumers machine-parse the formats below, never break them:
  1. Branch name `{prefix}YYYYMMDD_#issueNumber_normalizedTitle`
     - PROJECT-FLUTTER-ANDROID-TEST-APK.yaml      : sed 's/.*#\\([0-9]*\\).*/\\1/p'
     - PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml   : same
     - PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml : /#(\\d+)/
     - PROJECT-REACT-NATIVE-EXPO-PROJECTOPS-APP-BUILD-TRIGGER.yaml : same (same body as the Flutter trigger)
     - scripts/common/issue_number.py             : \\d{8}_(\\d+)_ (worktree)
  2. The `### 브랜치` heading + code block in the comment body, and the signature line
     - PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml, PROJECT-REACT-NATIVE-EXPO-PROJECTOPS-APP-BUILD-TRIGGER.yaml
       : /### 브랜치\\s*```\\s*([\\s\\S]*?)\\s*```/ (old versions keep running in user repos)
     - The signature comes from config (guide_signature, default `Guide by ProjectOps`).
       Old consumers look for the old text `Guide by SUH-LAB` with includes, so
       the old marker always stays as one invisible HTML comment line (LEGACY_SIGNATURE).

Config: version.yml metadata.template.options.issue_helper (all defaults when missing).
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

import github_api
from i18n.contracts import BRANCH_HEADING, LEGACY_COMMENT, LEGACY_SIGNATURE  # contract strings that are never translated (#787)
from i18n.messages import resolve_language, t

# ── Default config (when version.yml has no issue_helper section) ─────────────────
DEFAULT_CONFIG = {
    "branch_prefix": "",
    "max_branch_length": 100,
    "timezone": "Asia/Seoul",
    "commit_template": "${issueTitle} : ${commitType} : {변경 사항에 대한 설명} ${issueUrl}",
    "commit_type_map": {},
    "comment_marker": "<!-- SUH-ISSUE-HELPER -->",
    "guide_signature": "Guide by ProjectOps",
    "show_guide": True,
}

# The old signature (LEGACY_SIGNATURE) has its source in i18n/contracts.py. Old consumer workflows (app build trigger,
# PR preview) look for this text in comments, so it stays only as an invisible HTML comment.

# Title tag -> commit type (based on the title tags of the 4 issue templates). Config commit_type_map is merged in.
# Always knows both Korean and English tags: must work regardless of the template language (options.language),
# and it only adds entries, so existing repos are unaffected (#769).
DEFAULT_COMMIT_TYPE_MAP = {
    "버그": "fix",
    "기능요청": "feat",
    "기능추가": "feat",
    "기능개선": "feat",
    "문서": "docs",
    "디자인": "design",
    "시험요청": "test",
    "Bug": "fix",
    "Feature Request": "feat",
    "Feature": "feat",
    "Improvement": "feat",
    "Docs": "docs",
    "Design": "design",
    "QA": "test",
}

_TAG = re.compile(r"\[([^\]]*)\]")
# Keep Unicode letters/digits (kana, CJK, accented Latin included) and turn everything else (spaces, symbols) into _.
# \w also includes `_`, which is harmless since it equals the separator.
_KEEP = re.compile(r"[^\w]")
_MULTI_UNDERSCORE = re.compile(r"_+")


def _strip_emoji(text: str) -> str:
    """Remove emoji (So), control chars (C*) and variation selectors — parity with old TS \\p{So}|\\p{C}|\\uFE0F|\\u200D."""
    out = []
    for ch in text:
        if ch in ("️", "‍"):
            continue
        cat = unicodedata.category(ch)
        if cat == "So" or cat.startswith("C"):
            continue
        out.append(ch)
    return "".join(out)


def extract_issue_title(raw_title: str) -> str:
    """Remove [tags] and emoji. If the result is empty, return the trimmed original (old behavior kept)."""
    title = _TAG.sub("", raw_title).strip()
    title = _strip_emoji(title).strip()
    return title if title else raw_title.strip()


def normalize_title(title: str) -> str:
    normalized = _KEEP.sub("_", title)
    normalized = _MULTI_UNDERSCORE.sub("_", normalized)
    return normalized.strip("_")


def infer_commit_type(raw_title: str, type_map: dict | None = None) -> str:
    """Look up the original title's [tags] in order. No match -> feat."""
    merged = dict(DEFAULT_COMMIT_TYPE_MAP)
    if type_map:
        merged.update(type_map)
    lowered = {k.lower(): v for k, v in merged.items()}  # English tags ignore case
    for tag in _TAG.findall(raw_title):
        key = tag.strip()
        commit_type = merged.get(key) or lowered.get(key.lower())
        if commit_type:
            return commit_type
    return "feat"


def create_branch_name(
    title: str,
    issue_number: int | str,
    date_yyyymmdd: str,
    branch_prefix: str = "",
    max_branch_length: int = 100,
) -> str:
    """Fixed contract 1: core `YYYYMMDD_#number_title`. Length limit applies only to the core part (old TS parity)."""
    # A title of only emoji/symbols normalizes to empty, so fill the title slot with a number-based fallback
    slug = normalize_title(title) or f"issue-{issue_number}"
    base = f"{date_yyyymmdd}_#{issue_number}_{slug}"
    if max_branch_length > 0:
        # A cut at a separator leaves a trailing `_`, so trim it
        base = base[:max_branch_length].rstrip("_")
    return f"{branch_prefix}{base}"


def render_commit_message(template: str, ctx: dict) -> str:
    """${var} substitution — the original 5 + commitType/labels/assignees. Unknown variables stay as is."""
    out = template
    for key in ("issueTitle", "issueUrl", "issueNumber", "branchName",
                "date", "commitType", "labels", "assignees"):
        out = out.replace("${" + key + "}", str(ctx.get(key, "")))
    return out.strip()


# ── Config load (version.yml — parses only this section, no pyyaml) ────────────────────
def _strip_comment(raw: str) -> str:
    """Strip the end-of-line comment after a value. A value starting with a quote is read up to the closing quote, keeping ` #` inside."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        if end != -1:
            return raw[: end + 1]
    return re.sub(r"\s+#.*$", "", raw)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_config(repo_root: str = ".") -> dict:
    """Parse the issue_helper block of version.yml and merge it into DEFAULT_CONFIG.

    No file/section -> defaults, preserving the no-config behavior of existing repos.
    A future wizard 'central settings' menu reads and writes this section (keep flat scalars + one shallow map).
    """
    cfg = dict(DEFAULT_CONFIG)
    cfg["commit_type_map"] = dict(DEFAULT_CONFIG["commit_type_map"])
    path = Path(repo_root) / "version.yml"
    if not path.exists():
        return cfg

    lines = path.read_text(encoding="utf-8").splitlines()
    section_indent = None
    in_type_map = False
    type_map_indent = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        if section_indent is None:
            if re.match(r"^issue_helper:\s*(#.*)?$", stripped):
                section_indent = indent
            continue

        if indent <= section_indent:  # end of section
            break

        m = re.match(r"""^["']?([^"':]+)["']?\s*:\s*(.*?)\s*$""", stripped)
        if not m:
            continue
        key, raw = m.group(1).strip(), _strip_comment(m.group(2))

        if in_type_map and indent > type_map_indent:
            cfg["commit_type_map"][key] = _unquote(raw)
            continue
        in_type_map = False

        if key == "commit_type_map":
            in_type_map = True
            type_map_indent = indent
        elif key == "max_branch_length":
            try:
                cfg[key] = int(_unquote(raw))
            except ValueError:
                pass  # invalid value keeps the default
        elif key == "show_guide":
            cfg[key] = _unquote(raw).lower() != "false"
        elif key in ("branch_prefix", "timezone", "commit_template", "comment_marker", "guide_signature"):
            cfg[key] = _unquote(raw)
    return cfg


# ── Dynamic guide — mention only workflows that exist in the repo (no false guidance) ────
# ⚠️ Extension rule: when a new workflow depends on the branch rule (YYYYMMDD_#number_), add one line here.
#    Based on file existence, so it follows type changes made in the wizard setting automatically.
# Values are message catalog keys, not text (i18n/en.json, #787). version.yml decides the language.
GUIDE_LINES = [
    ("PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml", "issue_helper.guide.app_build"),
    ("PROJECT-FLUTTER-ANDROID-TEST-APK.yaml", "issue_helper.guide.test_apk"),
    ("PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml", "issue_helper.guide.test_testflight"),
    ("PROJECT-REACT-NATIVE-EXPO-PROJECTOPS-APP-BUILD-TRIGGER.yaml", "issue_helper.guide.app_build"),
]

_GUIDE_ALWAYS = ["issue_helper.guide.skills"]


def effective_commit_template(cfg: dict, lang: str) -> str:
    """Commit template. Uses a language-specific placeholder only when it is the untouched default (#790).

    The default string had the Korean placeholder `{변경 사항에 대한 설명}` baked in, so it showed up in English comments too.
    Repos that set commit_template in version.yml get that value as is regardless of language.
    """
    template = cfg["commit_template"]
    if template == DEFAULT_CONFIG["commit_template"]:
        return t("issue_helper.commit_template", lang)
    return template


def build_guide(workflows_dir: Path, lang: str | None = None) -> str:
    """Collapsible (details) guide body. Lists dependent features if the repo has them, else one recommended line."""
    lang = lang or resolve_language()
    # One line per key even when several workflows share it (Flutter and Expo triggers)
    active = list(dict.fromkeys(key for fname, key in GUIDE_LINES if (workflows_dir / fname).exists()))
    items = "\n".join(f"- {t(key, lang)}" for key in active + _GUIDE_ALWAYS)
    return (
        "<details>\n"
        f"<summary>{t('issue_helper.guide.summary', lang)}</summary>\n\n"
        f"{t('issue_helper.guide.intro', lang)}\n"
        f"{items}\n\n"
        f"{t('issue_helper.guide.outro', lang)}\n"
        "</details>"
    )


def build_comment_body(cfg: dict, branch_name: str, commit_message: str, guide: str, lang: str | None = None) -> str:
    """Fixed contract 2: keep the ### 브랜치 code block structure + signature (configurable; old signature kept as a hidden comment)."""
    marker = cfg["comment_marker"]
    signature = cfg.get("guide_signature") or DEFAULT_CONFIG["guide_signature"]
    guide_block = f"\n{guide}\n" if (cfg.get("show_guide", True) and guide) else ""
    # Even with a changed signature, keep one invisible line with the old text old consumers look for
    # ⚠️ A comment right below the signature breaks `signature\n---` (heading rendering), so it goes above
    legacy = "" if LEGACY_SIGNATURE in signature else f"{LEGACY_COMMENT}\n\n"
    lang = lang or resolve_language()
    return (
        f"{marker}\n\n"
        f"{legacy}"
        f"{signature}\n"
        "---\n\n"
        f"{BRANCH_HEADING}\n"
        f"```\n{branch_name}\n```\n\n"
        f"### {t('issue_helper.heading.commit', lang)}\n"
        f"```\n{commit_message}\n```\n"
        f"{guide_block}\n"
        f"{marker}"
    )


# ── Event handling ──────────────────────────────────────────────────────────
def should_process(payload: dict) -> bool:
    """Handle only opened or edited (title change) — same as the old workflow if condition."""
    action = payload.get("action")
    if action == "opened":
        return True
    return action == "edited" and bool(payload.get("changes", {}).get("title"))


def today_yyyymmdd(tz_name: str) -> str:
    """Today's date in the configured time zone. Fixes the old action's UTC runner offset (-9h at dawn in Korea)."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name)).strftime("%Y%m%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y%m%d")


def prepare_comment(payload: dict, cfg: dict, workflows_dir: Path, date_yyyymmdd: str):
    """Payload -> (branch name, commit message, comment body). No network — a testable unit."""
    issue = payload["issue"]
    raw_title = issue["title"]
    title = extract_issue_title(raw_title)
    issue_number = str(issue["number"])

    branch = create_branch_name(
        title, issue_number, date_yyyymmdd,
        branch_prefix=cfg["branch_prefix"], max_branch_length=cfg["max_branch_length"])

    ctx = {
        "issueTitle": title,
        "issueUrl": issue["html_url"],
        "issueNumber": issue_number,
        "branchName": branch,
        "date": date_yyyymmdd,
        "commitType": infer_commit_type(raw_title, cfg["commit_type_map"]),
        "labels": ", ".join(l["name"] for l in issue.get("labels", [])),
        "assignees": ", ".join(a["login"] for a in issue.get("assignees", [])),
    }
    lang = resolve_language()  # decide once and use the same language for the whole comment
    commit_message = render_commit_message(effective_commit_template(cfg, lang), ctx)
    body = build_comment_body(cfg, branch, commit_message, build_guide(workflows_dir, lang), lang)
    return branch, commit_message, body


# ── GitHub API (shared github_api — unified timeout and auth header) ──────────────────
# Comments left by the old action are upsert targets too (avoids duplicate comments — backward compatible)
LEGACY_MARKER_HINTS = ("github-issue-helper", "SUH-ISSUE-HELPER 에 의해 자동으로")
# Comment listing cap (100 x 50 pages) — generous so an existing guide is not missed on busy issues
MAX_COMMENT_PAGES = 50


def find_existing_comment(comments: list, marker: str):
    """New marker first, else match by the old action's marker hints."""
    found = github_api.find_marker_comment(comments, marker)
    if found:
        return found
    for c in comments:
        body = c.get("body") or ""
        if any(hint in body for hint in LEGACY_MARKER_HINTS):
            return c
    return None


def upsert_comment(owner: str, repo: str, issue_number: int, marker: str, body: str, token: str):
    action, _ = github_api.upsert_marker_comment(
        f"{owner}/{repo}", issue_number, token, body, marker,
        find_function=lambda comments: find_existing_comment(comments, marker),
        max_pages=MAX_COMMENT_PAGES)
    return action


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not event_path or not Path(event_path).exists():
        print("❌ GITHUB_EVENT_PATH is not set (Actions environment only)", file=sys.stderr)
        return 1
    if not token:
        print("❌ GITHUB_TOKEN is not set", file=sys.stderr)
        return 1

    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if not should_process(payload):
        print("ℹ️ Not a handled event (only opened / title edited) -> exit", file=sys.stderr)
        return 0

    cfg = load_config(".")
    branch, commit_message, body = prepare_comment(
        payload, cfg, Path(".github") / "workflows", today_yyyymmdd(cfg["timezone"]))

    owner = payload["repository"]["owner"]["login"]
    repo = payload["repository"]["name"]
    result = upsert_comment(
        owner, repo, payload["issue"]["number"], cfg["comment_marker"], body, token)
    print(f"✅ Comment {result}: {branch}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
