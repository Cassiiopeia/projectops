#!/usr/bin/env python3
"""
changelog_manager.py

Unified changelog manager script.

Subcommands:
  - update-from-summary: parse CodeRabbit Summary Markdown and update CHANGELOG.json
  - generate-md        : regenerate CHANGELOG.md from CHANGELOG.json
  - export             : build release notes for one version and write to stdout or a file
  - classify-bump      : decide the semver bump (major/minor/patch) from a list of commit subjects

Usage:
  python3 changelog_manager.py update-from-summary
  python3 changelog_manager.py generate-md
  python3 changelog_manager.py export --version 0.0.2 --output release_notes.txt

Input files:
  - pr_body.md: GitHub PR body (Markdown)
"""

from __future__ import annotations

import argparse
import html
import io
import json
import os
import re
import sys
import traceback

# Keep emoji output from crashing a cp949 console
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Used in the release step, so it must not crash on old installs without the i18n folder (#787).
# In that case it keeps the old Korean headers.
try:
    from i18n.messages import resolve_language, t
except ImportError:  # pragma: no cover
    def resolve_language():
        return "ko"

    def t(key, lang=None, **values):
        return {"changelog.current_version": "현재 버전", "changelog.last_updated": "마지막 업데이트"}.get(key, key)


# ----------------------------- Common utilities -----------------------------

def _normalize_text(text: str) -> str:
    """Normalize text: decode HTML entities and tidy whitespace."""
    return html.unescape(text).strip()


def _clean_summary_noise(text: str) -> str:
    """
    Remove noise from the Summary text.

    Removed:
    1. HTML comments (<!-- ... -->)
    2. CodeRabbit Tip messages
    3. Leftover HTML tags
    4. Runs of blank lines
    """
    if not text:
        return text

    # 1. Remove HTML comments
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # 2. Remove CodeRabbit Tip lines
    text = re.sub(r'^.*?✏️\s*Tip:.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<sub>.*?Tip:.*?</sub>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'^\s*Tip:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

    # 3. Remove leftover HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # 4. Collapse blank lines (3 or more -> 2)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


# ----------------------- Per-language store notes (#829) -----------------------
#
# Translation drafts are appended to the end of the PR body in this block. The Korean parser (_parse_summary_markdown)
# and _clean_summary_noise strip HTML comments/tags and read items into categories,
# so **this block must be cut off before parsing** or the translated lines leak into Korean categories.
#
#   <!-- projectops:store-notes -->
#   <details><summary>Store release notes (translations)</summary>
#
#   **en-US**
#   - Improved alerts
#
#   **ja-JP**
#   - 通知を改善
#
#   </details>
#   <!-- /projectops:store-notes -->
STORE_NOTES_BLOCK_RE = re.compile(r'<!--\s*projectops:store-notes\s*-->(.*?)<!--\s*/projectops:store-notes\s*-->', re.DOTALL)
STORE_NOTES_LOCALE_RE = re.compile(r'^\*\*([a-z]{2,3}(?:-[A-Za-z0-9]+)*)\*\*\s*$')


def extract_store_notes(content: str) -> tuple[str, dict]:
    """Cut the per-language notes block from the body: (body without block, {language: text}). No block -> body unchanged."""
    if not content or 'projectops:store-notes' not in content:
        return content, {}
    notes: dict[str, str] = {}
    for m in STORE_NOTES_BLOCK_RE.finditer(content):
        inner = re.sub(r'</?details>|<summary>.*?</summary>', '', m.group(1), flags=re.DOTALL | re.IGNORECASE)
        current, buf = None, []

        def flush():
            text = "\n".join(buf).strip()
            if current and text:
                notes[current] = text

        for line in inner.splitlines():
            head = STORE_NOTES_LOCALE_RE.match(line.strip())
            if head:
                flush()
                current, buf = head.group(1), []
            elif current is not None:
                buf.append(line.rstrip())
        flush()
    return STORE_NOTES_BLOCK_RE.sub('', content).strip() + "\n", notes


def _make_safe_key(title: str, idx: int) -> str:
    """Category title -> safe key."""
    safe_key = re.sub(r'[^a-zA-Z0-9가-힣]', '_', title.lower()).strip('_')
    return safe_key if safe_key else f"category_{idx}"


# ----------------------- Markdown parser (unified) -----------------------

def _parse_summary_markdown(md_content: str) -> dict:
    """
    Parse a CodeRabbit Summary in Markdown.

    3-step fallback:
    1. Strict parse (current CodeRabbit format)
    2. Lenient parse (format variations)
    3. Heuristic parse (last resort)

    Expected format:
    ## Summary by CodeRabbit

    * **버그 수정**
      * OCR 입력 처리 개선
      * 빈 콘텐츠 응답 오류 감지 강화

    * **Chores**
      * 버전 0.1.39로 업그레이드
    """
    # Step 1: strict parse
    detected = _parse_markdown_precise(md_content)
    if detected:
        print("  → Strict parser succeeded")
        return detected

    # Step 2: lenient parse
    detected = _parse_markdown_lenient(md_content)
    if detected:
        print("  → Lenient parser succeeded")
        return detected

    # Step 3: heuristic parse
    detected = _parse_markdown_heuristic(md_content)
    if detected:
        print("  → Heuristic parser succeeded")
    return detected


def _parse_markdown_precise(md_content: str) -> dict:
    """
    Strict parser: tuned for the current CodeRabbit format.

    Format: * **Category**\n  * item
    """
    detected: dict[str, dict] = {}

    # Pattern: * **Category** (bold, 2-space indent)
    pattern = r'\*\s*\*\*(.+?)\*\*\s*\n((?:\s{2}\*\s+.+(?:\n|$))*)'
    matches = re.findall(pattern, md_content, re.MULTILINE)

    for idx, (category_title, items_text) in enumerate(matches):
        category_title = category_title.strip()

        # Item extraction: "  * item text"
        items = re.findall(r'\s{2}\*\s+(.+)', items_text)
        items = [item.strip() for item in items if item.strip()]

        if not category_title and not items:
            continue

        safe_key = _make_safe_key(category_title, idx)
        detected[safe_key] = {
            'title': category_title,
            'items': items,
        }

    return detected


def _parse_markdown_lenient(md_content: str) -> dict:
    """
    Lenient parser: handles format variations.

    Supports:
    - 1-8 spaces of indent (tabs included)
    - optional bold (**title** or title)
    - various list markers (*, -, +)
    """
    content = md_content.replace('\t', '    ')
    detected: dict[str, dict] = {}

    # Pattern: category + nested items
    pattern = r'(?:^|\n)([\*\-\+])\s*(\*\*)?([^\*\n]+?)(\*\*)?\s*\n((?:(?:^|\n)\s{1,8}[\*\-\+]\s+.+)*)'
    matches = re.findall(pattern, content, re.MULTILINE)

    for idx, (marker, bold_start, category_title, bold_end, items_text) in enumerate(matches):
        category_title = category_title.strip()

        # Item extraction
        items = re.findall(r'(?:^|\n)\s{1,8}[\*\-\+]\s+(.+)', items_text, re.MULTILINE)
        items = [item.strip() for item in items if item.strip()]

        if not category_title and not items:
            continue

        # A very long title is not a category
        if len(category_title) > 100:
            continue

        safe_key = _make_safe_key(category_title, idx)
        detected[safe_key] = {
            'title': category_title,
            'items': items,
        }

    return detected


def _parse_markdown_heuristic(md_content: str) -> dict:
    """
    Heuristic parser: infer category/item line by line.

    Rules:
    1. Bold text (**...**) -> category
    2. Indented line -> item
    """
    lines = md_content.split('\n')
    detected: dict[str, dict] = {}
    current_key = None

    for line in lines:
        stripped = line.strip()

        if not stripped or stripped.startswith('<!--') or stripped.startswith('##'):
            continue

        # Bold text -> category
        bold_match = re.search(r'\*\*([^\*]+)\*\*', stripped)
        if bold_match:
            title = bold_match.group(1).strip()
            title = re.sub(r'^[\*\-\+\d\.]+\s*', '', title).strip()

            if title and len(title) < 100:
                current_key = _make_safe_key(title, len(detected))
                detected[current_key] = {'title': title, 'items': []}
            continue

        # Indented line -> item
        if line.startswith((' ', '\t')) and stripped:
            item = re.sub(r'^[\*\-\+\d\.]+\s*', '', stripped).strip()
            item = re.sub(r'<[^>]+>', '', item).strip()

            if current_key and item and len(item) > 3:
                detected[current_key]['items'].append(item)

    # Drop empty categories
    return {k: v for k, v in detected.items() if v.get('items')}


# ------------------------ Subcommand implementations ------------------------

def cmd_update_from_summary() -> int:
    """Parse Markdown from pr_body.md and update CHANGELOG.json."""
    version = os.environ.get('VERSION')
    project_type = os.environ.get('PROJECT_TYPE')
    # Multi-type: PROJECT_TYPES (csv) env -> array, else fall back to the singular key
    project_types_csv = os.environ.get('PROJECT_TYPES', '')
    project_types = [t.strip() for t in project_types_csv.split(',') if t.strip()]
    if not project_types and project_type:
        project_types = [project_type]
    # Recording without VERSION leaves a version: null release that taints every later decision
    if not version:
        print("❌ The VERSION environment variable is required", file=sys.stderr)
        return 1
    today = os.environ.get('TODAY')
    pr_number_raw = os.environ.get('PR_NUMBER')
    timestamp = os.environ.get('TIMESTAMP')

    try:
        pr_number = int(pr_number_raw) if pr_number_raw else None
    except ValueError:
        pr_number = None

    # Find the input file.
    # Check PR_BODY_PATH first (#564): the workflow puts the temp file outside the working tree
    # ($RUNNER_TEMP). At the repo root it would ride along with the release commit's git add -A
    # and pollute the repo. Without the env, look in cwd as before (backward compatible).
    candidates = []
    env_path = os.environ.get('PR_BODY_PATH')
    if env_path:
        candidates.append(env_path)
    candidates += ['pr_body.md', 'summary_section.html']

    input_file = next((f for f in candidates if os.path.isfile(f)), None)

    if not input_file:
        print(f"❌ Input file not found (paths checked: {', '.join(candidates)})")
        return 1

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        print(f"📄 Input file: {input_file}")
        print(f"📝 File size: {len(content)} bytes")

        # Cut the per-language notes block before the Korean parser sees it (#829)
        content, store_notes = extract_store_notes(content)
        if store_notes:
            print(f"🌐 Store notes by language: {', '.join(store_notes)}")

        # Parse Markdown (unified)
        print("\n🔍 Parsing Markdown...")
        categories = _parse_summary_markdown(content)

        parse_method = 'markdown' if categories else 'markdown_failed'
        if categories:
            print(f"✅ Parsed: {len(categories)} categories")
        else:
            print("⚠️ Parsing failed, saving raw_summary only")

        # Build raw_summary (noise removed)
        raw_summary = _clean_summary_noise(content)

        # Build release data
        new_release = {
            "version": version,
            "project_type": project_type,      # old singular key, kept (backward compatible)
            "project_types": project_types,    # new multi-type array
            "date": today,
            "pr_number": pr_number,
            "raw_summary": raw_summary,
            "parsed_changes": categories or {},
            "parse_method": parse_method,
        }
        # Add the key only when translations exist; otherwise CHANGELOG.json keeps its current shape
        if store_notes:
            new_release["store_notes"] = store_notes

        # Print parse result
        print("\n📊 Parse result:")
        print(f"  - Parse method: {parse_method}")
        print(f"  - raw_summary length: {len(raw_summary)} characters")
        print(f"  - Parsed categories: {len(categories)}")
        for key, value in categories.items():
            title = value.get('title', key)
            items_count = len(value.get('items', []))
            print(f"    • {title}: {items_count} items")

        # Update CHANGELOG.json
        try:
            with open('CHANGELOG.json', 'r', encoding='utf-8') as f:
                changelog_data = json.load(f)
        except json.JSONDecodeError as e:
            # Overwriting a broken file with an empty structure would erase history; stop so a person fixes it
            print(f"❌ CHANGELOG.json is corrupted, not updating it (repair it manually): {e}", file=sys.stderr)
            return 1
        except FileNotFoundError:
            changelog_data = {
                "metadata": {
                    "lastUpdated": timestamp,
                    "currentVersion": version,
                    "projectType": project_type,
                    "projectTypes": project_types,
                    "totalReleases": 0,
                },
                "releases": [],
            }

        if not isinstance(changelog_data.get("metadata"), dict) or not isinstance(changelog_data.get("releases", []), list):
            print("❌ CHANGELOG.json has an invalid structure, not updating it", file=sys.stderr)
            return 1

        changelog_data["metadata"]["lastUpdated"] = timestamp
        changelog_data["metadata"]["currentVersion"] = version
        changelog_data["metadata"]["projectType"] = project_type
        changelog_data["metadata"]["projectTypes"] = project_types
        # Replace the same version so reruns and PR updates give the same result (idempotent)
        releases = [r for r in changelog_data.get("releases", [])
                    if not (isinstance(r, dict) and str(r.get("version")) == str(version))]
        releases.insert(0, new_release)
        changelog_data["releases"] = releases
        changelog_data["metadata"]["totalReleases"] = len(releases)

        with open('CHANGELOG.json', 'w', encoding='utf-8') as f:
            json.dump(changelog_data, f, indent=2, ensure_ascii=False)

        print("\n✅ CHANGELOG.json updated!")
        return 0

    except Exception as e:
        print(f"❌ update-from-summary failed: {e}")
        traceback.print_exc()
        return 1


def cmd_generate_md() -> int:
    """Regenerate CHANGELOG.md from CHANGELOG.json."""
    try:
        with open('CHANGELOG.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Build everything in memory and write once so a mid-way exception does not truncate CHANGELOG.md
        with io.StringIO() as f:
            f.write("# Changelog\n\n")

            metadata = data.get('metadata', {})
            current_version = metadata.get('currentVersion', 'Unknown')
            last_updated = metadata.get('lastUpdated', 'Unknown')

            lang = resolve_language()
            f.write(f"**{t('changelog.current_version', lang)}:** {current_version}  \n")
            f.write(f"**{t('changelog.last_updated', lang)}:** {last_updated}  \n\n")
            f.write("---\n\n")

            for release in data.get('releases', []):
                version = release.get('version', 'Unknown')
                date = release.get('date', 'Unknown')
                pr_number = release.get('pr_number')

                f.write(f"## [{version}] - {date}\n\n")

                if pr_number is not None:
                    f.write(f"**PR:** #{pr_number}  \n\n")

                parsed = release.get('parsed_changes') or {}

                if parsed:
                    # Structured data output
                    for _, items in parsed.items():
                        if not items:
                            continue
                        if isinstance(items, dict) and 'items' in items:
                            actual_items = items.get('items') or []
                            title = items.get('title') or ''
                        else:
                            actual_items = items
                            title = _normalize_text(_)

                        f.write(f"**{title}**\n")
                        for item in actual_items:
                            f.write(f"- {item}\n")
                        f.write("\n")
                else:
                    # Parse failed: print raw_summary
                    raw_summary = release.get('raw_summary', '').strip()
                    if raw_summary:
                        raw_summary = _clean_summary_noise(raw_summary)
                        if raw_summary:
                            f.write(raw_summary + "\n\n")
                        else:
                            f.write("*변경사항 정보 없음*\n\n")
                    else:
                        f.write("*변경사항 정보 없음*\n\n")

                f.write("---\n\n")

            with open('CHANGELOG.md', 'w', encoding='utf-8') as out:
                out.write(f.getvalue())

        print("✅ CHANGELOG.md regenerated!")
        return 0

    except Exception as e:
        print(f"❌ Failed to generate CHANGELOG.md: {e}")
        traceback.print_exc()
        return 1


def cmd_export_release_notes(version: str, output_path: str | None) -> int:
    """Build the release notes for a version from CHANGELOG."""
    notes_text = ""

    # 1) Try CHANGELOG.json
    try:
        if os.path.isfile('CHANGELOG.json'):
            with open('CHANGELOG.json', 'r', encoding='utf-8') as f:
                changelog = json.load(f)
            releases = changelog.get('releases') or []
            matched = next((r for r in releases if str(r.get('version')) == str(version)), None)
            if matched:
                header = f"버전 {matched.get('version')} 업데이트\n\n"
                parsed_changes = matched.get('parsed_changes') or {}
                if parsed_changes:
                    category_blocks: list[str] = []
                    for _, value in parsed_changes.items():
                        title = (value.get('title') or '').strip()
                        items = [it for it in (value.get('items') or []) if it]
                        if title and items:
                            block = "**" + title + "**\n" + "\n".join("- " + it for it in items)
                            category_blocks.append(block)
                    body = "\n\n".join(category_blocks) if category_blocks else (matched.get('raw_summary') or '').strip()
                else:
                    body = (matched.get('raw_summary') or '').strip()
                notes_text = (header + (body or "")).strip()
    except Exception as e:
        # Swallowing it hides the fallback reason; log only the reason to stderr and try the next path
        print(f"[warn] Could not build notes from CHANGELOG.json, falling back: {e}", file=sys.stderr)

    # 2) Fall back to CHANGELOG.md
    if not notes_text and os.path.isfile('CHANGELOG.md'):
        try:
            with open('CHANGELOG.md', 'r', encoding='utf-8') as f:
                md = f.read()
            pattern = re.compile(rf"^## \[{re.escape(str(version))}\].*$", re.MULTILINE)
            m = pattern.search(md)
            if m:
                start = m.end()
                next_m = re.search(r"^## \[", md[start:], re.MULTILINE)
                section = md[start: start + next_m.start()] if next_m else md[start:]
                body = section.strip()
                # Section separators (---) are not needed in store release notes
                body = re.sub(r'\n*-{3,}\s*$', '', body).strip()
                notes_text = (f"버전 {version} 업데이트\n\n" + body).strip()
        except Exception as e:
            print(f"[warn] Could not build notes from CHANGELOG.md, falling back: {e}", file=sys.stderr)

    # 3) Final fallback
    if not notes_text:
        notes_text = f"버전 {version} 업데이트\n앱 안정성 및 사용자 경험이 개선되었습니다."

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(notes_text)
    else:
        sys.stdout.write(notes_text + "\n")
    return 0


# --------------------- semver bump decision (issue #546) ---------------------
#
# Separate from release-notes rendering (the changelog_providers ladder). This only decides
# "major, minor or patch" without building buckets or polishing text. Merging the two paths
# would split release-note generation in two and cause drift.
#
# Looks only at the commit subject line (collection uses %s, so the body is unavailable). Conventional Commits item
# 13 accepts the `!` marker alone as a breaking marker, so not supporting a BREAKING CHANGE footer is
# a subset the standard allows.

# tier-1: projectops convention "title : type[!] : text [URL]".
# The colon before the type must be preceded by a space, so bare colons in the title ("v1:2") do not split it.
_BUMP_TIER1_RE = re.compile(
    r'^.+?\s:\s*(feat|fix|chore|docs|refactor|test)(!)?\s*:\s*.+$', re.IGNORECASE
)
# tier-2: Conventional Commits "type(scope)[!]: text".
_BUMP_TIER2_RE = re.compile(
    r'^(feat|fix|chore|docs|refactor|test|perf|style|build|ci)(?:\([^)]*\))?(!)?:\s*.+$', re.IGNORECASE
)


def classify_bump_level(lines: list[str]) -> str:
    """Decide the semver bump from commit subjects by rule (deterministic, no AI).

    - `!` marker after the type (both conventions) -> major (decided at once)
    - feat type -> minor
    - anything else (no match, free-form) -> patch
    """
    level = 'patch'

    for raw_line in lines:
        line = raw_line.strip()
        if not line or '[skip ci]' in line or line.startswith('Merge '):
            continue

        # Try tier-1 first: our convention with the title in front wins.
        matched = _BUMP_TIER1_RE.match(line)
        if matched:
            commit_type, breaking = matched.group(1), matched.group(2)
        else:
            matched = _BUMP_TIER2_RE.match(line)
            if not matched:
                continue
            commit_type, breaking = matched.group(1), matched.group(2)

        if breaking:
            return 'major'  # highest level, no need to look further
        if commit_type.lower() == 'feat':  # case-insensitive (#686)
            level = 'minor'

    return level


def cmd_classify_bump(commits_file: str) -> int:
    """Read the commit list file and print the bump on the last stdout line.

    If the file cannot be read it falls back to patch, so a failed decision never blocks a release.
    """
    try:
        with open(commits_file, 'r', encoding='utf-8') as f:
            commit_lines = [line.rstrip('\n').rstrip('\r') for line in f]
    except Exception as e:
        print(f"[warn] Could not read the commit list ({e}) — treating it as patch", file=sys.stderr)
        commit_lines = []

    print(classify_bump_level(commit_lines))
    return 0


# ------------------------------- CLI -------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='changelog_manager',
        description='Unified changelog manager',
        add_help=True
    )
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('update-from-summary', help='Update CHANGELOG.json from the PR body')
    sub.add_parser('generate-md', help='Generate CHANGELOG.md from CHANGELOG.json')

    p_export = sub.add_parser('export', help='Export release notes for a specific version')
    p_export.add_argument('--version', required=True, help='Version number')
    p_export.add_argument('--output', help='Output file path (stdout if omitted)')

    p_classify_bump = sub.add_parser(
        'classify-bump', help='Decide the semver bump (major/minor/patch) from a commit list')
    p_classify_bump.add_argument(
        '--commits-file', required=True, help='File of commit subjects (one per line)')

    args = parser.parse_args(argv)

    if args.command == 'update-from-summary':
        return cmd_update_from_summary()
    if args.command == 'generate-md':
        return cmd_generate_md()
    if args.command == 'export':
        return cmd_export_release_notes(args.version, args.output)
    if args.command == 'classify-bump':
        return cmd_classify_bump(args.commits_file)
    return 2


if __name__ == '__main__':
    sys.exit(main())
