#!/usr/bin/env python3
"""Consistency check for the 4 projectops Flutter wizards (testflight, playstore, firebase, oauth).

Why it exists
-----------
Only the iOS (testflight) wizard used to get improvements, which never spread to the other two,
so the same class name ended up meaning opposite things, or features existed on one side only.
This script catches that drift immediately in CI and locally.

Checks
---------
1. Shared asset loading   — does the wizard HTML reference _shared/wizard.css and wizard-common.js
2. Shared function override — does wizard JS redefine and override shared utils
3. Required feature parity — do all wizards provide the core features under the same names
4. Undefined CSS classes  — is every project class used in HTML defined somewhere
5. Version sync           — do version.json and the HTML inline versionJson match
6. Stale links            — does anything point to the old repo name or nonexistent paths
7. First-time user guide  — does every wizard have prerequisites/duration/docs link/resume notice
8. Python shared blocks   — are the .py write gate (testflight, playstore, oauth) and argument contract (testflight, playstore) blocks identical character for character
9. Language switch (i18n) — engine load order, missing en/ko dictionary keys, leftover Korean in HTML (check_i18n.py, common wizards included)

Usage
------
    python3 .github/util/flutter/_shared/check-consistency.py
    python3 .github/util/flutter/_shared/check-consistency.py --json

Exit code: 0 = pass, 1 = violations
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_i18n  # noqa: E402  module in the same folder (this file cannot be imported because its name has a hyphen)

# Keep emoji output from crashing a cp949 console
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

WIZARDS = ("testflight", "playstore", "firebase", "oauth")
SHARED_DIR = Path(__file__).resolve().parent
FLUTTER_DIR = SHARED_DIR.parent
REPO_SLUG = "Cassiiopeia/projectops"

# Functions defined in the shared utils — redefining them in wizard JS disables the source of truth
SHARED_FUNCS_RE = re.compile(r"^(?:async )?function ([A-Za-z0-9_]+)", re.M)

# Functions that intentionally override shared JS (explicit list per wizard)
# firebase: step navigation has no order constraint and the Secret input UI differs, so flow functions are its own implementation
INTENTIONAL_OVERRIDES = {
    "firebase": {"showStep", "prevStep", "addCustomSecret", "updateCustomSecretKey", "renderCustomSecrets"},
}

# Blocks that must be identical character for character in .py (# >>> 공통 블록: name ... # <<< 공통 블록: name) > wizards that have the block
# Why not a shared module: each .py runs and ships as a single file (the firebase ZIP contains only the .py)
# oauth has no history of positional calls (argparse), so it shares only the write gate, not the argument contract block
PY_BLOCK_WIZARDS_BY_BLOCK = {
    "쓰기 게이트": ("testflight", "playstore", "oauth"),
    "인자 계약": ("testflight", "playstore"),
}

# Features every wizard must provide (names unified)
REQUIRED_FUNCS = (
    "showStep",
    "goToStep",
    "nextStep",
    "prevStep",
    "saveState",
    "loadState",
    "resetWizard",
    "updateProgress",
    "downloadAsJson",
    "downloadAsTxt",
    "downloadAsZip",
    "addCustomSecret",
    "removeCustomSecret",
    "renderCustomSecrets",
)

# First-time user guide elements every wizard HTML must have (id or class)
REQUIRED_MARKERS = (
    ("securityWarning", 'id="securityWarning"'),
    ("changelogModal", 'id="changelogModal"'),
    ("duration/prerequisites banner", 'class="wizard-meta"'),
    ("resume notice", 'class="resume-hint"'),
    # Docs link: Korean docs/FLUTTER-*.md or English docs/en/flutter-*.md (#976 site rule)
    ("docs link", ("docs/FLUTTER-", "docs/en/flutter-")),
    ("language toggle button", "data-lang-toggle"),
)


def wizard_paths(name: str) -> dict[str, Path]:
    base = FLUTTER_DIR / f"{name}-wizard"
    return {
        "html": base / f"{name}-wizard.html",
        "js": base / f"{name}-wizard.js",
        "py": base / f"{name}-wizard.py",
        "version": base / "version.json",
        "sync": base / "version-sync.sh",
    }


def wizard_js_files(name: str) -> list[Path]:
    """All wizard JS (main file + per-step split files {name}-wizard-*.js)"""
    base = FLUTTER_DIR / f"{name}-wizard"
    return sorted(base.glob(f"{name}-wizard*.js"))


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def check() -> list[str]:
    problems: list[str] = []

    shared_css = SHARED_DIR / "wizard.css"
    shared_js = SHARED_DIR / "wizard-common.js"
    shared_i18n_js = SHARED_DIR / "wizard-i18n.js"
    for p in (shared_css, shared_js, shared_i18n_js):
        if not p.exists():
            problems.append(f"[shared assets] {p.name} is missing")
    if problems:
        return problems

    shared_funcs = set(SHARED_FUNCS_RE.findall(read(shared_js) + "\n" + read(shared_i18n_js)))
    # Classes defined in the shared CSS
    shared_classes = set(re.findall(r"^\.([a-zA-Z][\w-]*)", read(shared_css), re.M))

    for name in WIZARDS:
        paths = wizard_paths(name)
        tag = f"[{name}]"

        for key, p in paths.items():
            if not p.exists():
                problems.append(f"{tag} {p.name} is missing")
        js_files = wizard_js_files(name)
        html, js = read(paths["html"]), "\n".join(read(p) for p in js_files)
        if not html or not js:
            continue

        # 1. Shared asset loading
        # Judge by the actual tag so a path string in a comment does not pass
        if not re.search(r'<link[^>]+href="\.\./_shared/wizard\.css"', html):
            problems.append(f"{tag} HTML does not load ../_shared/wizard.css")
        if not re.search(r'<script[^>]+src="\.\./_shared/wizard-common\.js"', html):
            problems.append(f"{tag} HTML does not load ../_shared/wizard-common.js")
        else:
            # Shared JS must load before wizard JS, or overrides go wrong
            i_common = html.find("../_shared/wizard-common.js")
            for js_file in js_files:
                i_own = html.find(f'src="{js_file.name}"')
                if i_own == -1:
                    problems.append(f"{tag} HTML does not load {js_file.name}")
                elif i_common > i_own:
                    problems.append(f"{tag} shared JS loads after {js_file.name} (fix the order)")

        # 2. Shared function override
        own_funcs = set(SHARED_FUNCS_RE.findall(js))
        allowed = INTENTIONAL_OVERRIDES.get(name, set())
        redefined = sorted((own_funcs & shared_funcs) - allowed)
        if redefined:
            problems.append(f"{tag} redefines shared utils: {', '.join(redefined)}")

        # 3. Required feature parity
        available = own_funcs | shared_funcs
        missing = [f for f in REQUIRED_FUNCS if f not in available]
        if missing:
            problems.append(f"{tag} missing required features: {', '.join(missing)}")

        # 4. Undefined CSS classes (project classes only — Tailwind utilities excluded)
        own_css = set(re.findall(r"^\s*\.([a-zA-Z][\w-]*)", html, re.M))
        used = set(re.findall(r'class="([^"]+)"', html))
        used_classes = {c for chunk in used for c in chunk.split()}
        known = shared_classes | own_css
        project_prefixes = ("tooltip-", "code-", "file-", "custom-", "secret-", "type-",
                            "usage-", "dependency-", "result-", "copy-btn", "add-secret",
                            "remove-secret", "step-", "modal-", "wizard-", "resume-",
                            "skip-", "input-", "error-", "success-", "toast", "fade-in", "lang-")
        undefined = sorted(
            c for c in used_classes
            if c.startswith(project_prefixes) and c not in known
        )
        if undefined:
            problems.append(f"{tag} uses undefined classes: {', '.join(undefined)}")

        # 5. Version sync
        try:
            vjson = json.loads(read(paths["version"]))
            inline = re.search(
                r'<script type="application/json" id="versionJson">(.*?)</script>', html, re.S
            )
            if not inline:
                problems.append(f"{tag} HTML has no versionJson block")
            elif json.loads(inline.group(1)) != vjson:
                problems.append(f"{tag} version.json and HTML differ — run ./version-sync.sh")
        except (json.JSONDecodeError, ValueError) as e:
            problems.append(f"{tag} failed to parse version.json: {e}")

        # 6. Stale links
        # ⚠️ Looks only at "real URLs", not string containment.
        #    version.json changelogs include text like "fixed the old repo name",
        #    and that text is injected into the HTML, so a plain containment check gives false positives.
        for blob, label in ((html, "HTML"), (js, "JS")):
            seen = set()
            for m in re.finditer(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", blob):
                slug = m.group(1)
                if slug != REPO_SLUG and slug not in seen:
                    seen.add(slug)
                    hint = " (old repo name — projectops after the rebrand)" if "SUH-DEVOPS-TEMPLATE" in slug else ""
                    problems.append(f"{tag} {label} points to another repo: {slug}{hint}")

        # 7. First-time user guide
        for label, marker in REQUIRED_MARKERS:
            # With several marker candidates, any one passes
            marker_candidates = marker if isinstance(marker, tuple) else (marker,)
            if not any(candidate in html for candidate in marker_candidates):
                problems.append(f"{tag} first-time user guide missing: {label}")

    # Is version-sync.sh identical across wizards except the file name
    norm = []
    for name in WIZARDS:
        s = read(wizard_paths(name)["sync"]).replace(f"{name}-wizard.html", "<HTML>")
        norm.append((name, s))
    if len({s for _, s in norm}) > 1:
        problems.append("[shared] version-sync.sh differs between wizards (only the file name may differ)")

    # ── Python CLI contract ────────────────────────────────────────────
    # Wizards must be called the same way: named flags canonical + shared boolean flags.
    # testflight used to take only positional arguments and firebase only flags, so usage diverged.
    for name in WIZARDS:
        py = read(wizard_paths(name)["py"])
        if not py:
            continue
        tag = f"[{name}]"
        for flag in ("--dry-run", "--non-interactive", "--no-backup"):
            if flag not in py:
                problems.append(f"{tag} missing shared CLI option: {flag}")
        # Prevent --dry-run being "declared but still writing files"
        if "--dry-run" in py and not re.search(r"\bDRY_RUN\b|\bdry_run\b", py):
            problems.append(f"{tag} accepts --dry-run but it is not wired to the actual behavior")

    problems.extend(check_python_shared_blocks())
    problems.extend(check_i18n.check())
    return problems


def extract_python_block(source: str, block_name: str) -> str | None:
    """Body between `# >>> 공통 블록: name` and `# <<< 공통 블록: name` (start line description excluded)"""
    pattern = re.compile(
        rf"^# >>> 공통 블록: {re.escape(block_name)}\b[^\n]*\n(.*?)^# <<< 공통 블록: {re.escape(block_name)}$",
        re.S | re.M,
    )
    match = pattern.search(source)
    return match.group(1) if match else None


def check_python_shared_blocks() -> list[str]:
    """Shared block exists > compare across wizards"""
    problems: list[str] = []
    for block_name, block_wizards in PY_BLOCK_WIZARDS_BY_BLOCK.items():
        bodies = {}
        for name in block_wizards:
            body = extract_python_block(read(wizard_paths(name)["py"]), block_name)
            if body is None:
                problems.append(f"[{name}] .py has no '{block_name}' shared block marker")
            else:
                bodies[name] = body
        if len(bodies) == len(block_wizards) and len(set(bodies.values())) > 1:
            names = " ↔ ".join(block_wizards)
            problems.append(f"[shared] .py '{block_name}' blocks differ ({names}) — if you edited one, make the other match")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Flutter wizard consistency check")
    ap.add_argument("--json", action="store_true", help="print as JSON")
    args = ap.parse_args()

    problems = check()

    if args.json:
        print(json.dumps({"ok": not problems, "count": len(problems), "problems": problems},
                         ensure_ascii=False, indent=2))
    elif problems:
        print(f"❌ {len(problems)} consistency violations\n")
        for p in problems:
            print(f"  - {p}")
        print("\nFix them and run again.")
    else:
        print(f"✅ All {len(WIZARDS)} wizards are consistent")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
