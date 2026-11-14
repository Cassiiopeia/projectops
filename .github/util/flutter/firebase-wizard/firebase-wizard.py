#!/usr/bin/env python3
# ===================================================================
# Firebase App Distribution Wizard - CLI (Python)
# ===================================================================
# A single file merging the old setup scripts (bash/PowerShell pair) into argparse subcommands.
# The logic is preserved 100% identical to the old sh (canonical).
#
# Safely replaces the FIREBASE_APP_ID and FIREBASE_TESTER_GROUP keys in the workflow files
# line by line.
#
# Usage:
#   python3 firebase-wizard.py setup \
#     --project-path /path/to/project \
#     --app-id "1:905325245238:android:86db..." \
#     --tester-group "testers" \
#     [--dry-run] [--non-interactive] [--no-backup]
#
# sh/ps1 differences recorded (sh adopted):
# - Stripping quotes from values: sh strips one leading and one trailing quote independently, then
#   trims spaces. ps1 trims first and strips only "matching" quote pairs.
#   → sh approach adopted (independent strip, then trim).
# - abort input check: sh uses the case pattern `abort|A|a*` (anything starting with lowercase a is
#   abort; uppercase only a lone "A"). ps1 uses `^[aA]` (anything starting with a/A).
#   → sh approach adopted.
# - Header flag notation: sh uses 0/1, ps1 False/True. → sh approach (0/1) adopted.
# - File saving: sh appends LF (\n) after every line (files without a final newline
#   get one). ps1 joins with the OS newline. → sh approach (LF) adopted.
# - File processing order: sh uses `find | sort` (locale-dependent order); here Python's
#   default sort (byte order == LC_ALL=C sort). Each file is processed independently, so
#   the results are identical; only the Summary display order may vary by locale.
# ===================================================================
import argparse
import os
import re
import shutil
import sys
import time

# ---- stdout/stderr UTF-8 (cp949 console support) ----
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# ---- Color (same palette as sh) ----
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
BLUE = "\033[0;34m"
CYAN = "\033[0;36m"
NC = "\033[0m"


def _enable_windows_vt():
    """Try enabling Windows console ANSI (VT). Failures are ignored."""
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        for std_handle in (-11, -12):  # STD_OUTPUT_HANDLE, STD_ERROR_HANDLE
            handle = kernel32.GetStdHandle(std_handle)
            mode = ctypes.c_uint32()
            if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


_enable_windows_vt()

PROG = os.path.basename(sys.argv[0]) if sys.argv else "firebase-wizard.py"

SETUP_USAGE = """Usage: {prog} setup --project-path <path> --app-id <id> --tester-group <group> [options]

Options:
  --dry-run             Preview the changes without modifying any file
  --non-interactive     SKIP conflicts automatically (no prompt)
  --no-backup           Don't create backup files
  -h, --help            Show this help
"""

TOP_USAGE = """Usage: {prog} <command> [options]

commands:
  setup    Replace the FIREBASE_APP_ID/FIREBASE_TESTER_GROUP placeholders in workflow files

More options: {prog} setup --help
"""

# ---- key patterns for regex matching (word boundary guaranteed: space or colon right after the key) ----
# sh: ^([[:space:]]*)(FIREBASE_APP_ID|FIREBASE_TESTER_GROUP)([[:space:]]*:[[:space:]]*)(.*)$
_SP = r"[ \t\r\f\v]"
LINE_RE = re.compile(
    r"^(" + _SP + r"*)(FIREBASE_APP_ID|FIREBASE_TESTER_GROUP)"
    r"(" + _SP + r"*:" + _SP + r"*)(.*)$"
)
PRECHECK_RE = re.compile(
    r"^" + _SP + r"*(FIREBASE_APP_ID|FIREBASE_TESTER_GROUP)" + _SP + r"*:"
)


def print_setup_usage():
    print(SETUP_USAGE.format(prog=PROG), end="")


def strip_value(raw_value):
    """Normalize the value in the same order as sh:
    strip trailing \\r → leading " → trailing " → leading ' → trailing ' → trim spaces.
    (quotes are stripped independently, at most one each, without pair checks — sh canonical)"""
    stripped = raw_value
    if stripped.endswith("\r"):
        stripped = stripped[:-1]
    if stripped.startswith('"'):
        stripped = stripped[1:]
    if stripped.endswith('"'):
        stripped = stripped[:-1]
    if stripped.startswith("'"):
        stripped = stripped[1:]
    if stripped.endswith("'"):
        stripped = stripped[:-1]
    return stripped.strip(" \t\r\f\v\n")


class Ctx:
    """setup run state (equivalent of the sh global variables)"""

    def __init__(self):
        self.total_replaced = 0
        self.total_skipped = 0
        self.total_conflicts = 0
        self.summary = []


def process_file(file_path, project_path, app_id, tester_group,
                 dry_run, non_interactive, no_backup, timestamp, ctx):
    """Process one file. Returns 99 on abort (like sh return 99), else 0."""
    rel = os.path.relpath(file_path, project_path).replace(os.sep, "/")
    file_replaced = 0
    file_skipped = 0
    file_conflicts = 0

    with open(file_path, "rb") as f:
        content = f.read().decode("utf-8")

    # Check the key exists first (word boundary guaranteed: space or colon right after the key)
    lines = content.split("\n")
    if lines and lines[-1] == "":
        lines.pop()  # the empty piece after the final newline is not a line (same as the sh read loop)

    if not any(PRECHECK_RE.match(line) for line in lines):
        ctx.summary.append("⏭  %s — no target keys, SKIP" % rel)
        return 0

    # Backup
    backup_path = "%s.bak.%s" % (file_path, timestamp)
    if not no_backup and not dry_run:
        shutil.copyfile(file_path, backup_path)

    out_lines = []
    for line in lines:
        m = LINE_RE.match(line)
        if m:
            indent, key, sep, raw_value = m.group(1), m.group(2), m.group(3), m.group(4)
            stripped = strip_value(raw_value)

            if key == "FIREBASE_APP_ID":
                new_value = app_id
                placeholder = "{FIREBASE_APP_ID}"
            else:
                new_value = tester_group
                placeholder = "{TESTER_GROUP}"

            if stripped == placeholder:
                out_lines.append('%s%s%s"%s"' % (indent, key, sep, new_value))
                file_replaced += 1
                print("  %s✓%s %s — %s: placeholder → %s" % (GREEN, NC, rel, key, new_value))
            elif stripped == new_value:
                out_lines.append(line)
                file_skipped += 1
                print("  %sℹ%s %s — %s: already the same value, SKIP" % (BLUE, NC, rel, key))
            else:
                if non_interactive:
                    out_lines.append(line)
                    file_skipped += 1
                    file_conflicts += 1
                    print("  %s⚠%s %s — %s: different value ('%s'), non-interactive SKIP"
                          % (YELLOW, NC, rel, key, stripped))
                else:
                    print()
                    print("%s⚠ Conflict detected: %s%s" % (YELLOW, rel, NC))
                    print("  key: %s" % key)
                    print("  current value: %s" % stripped)
                    print("  new value:     %s" % new_value)
                    try:
                        choice = input("  Overwrite? (y/n/abort): ")
                    except EOFError:
                        choice = ""
                    if choice in ("y", "Y"):
                        out_lines.append('%s%s%s"%s"' % (indent, key, sep, new_value))
                        file_replaced += 1
                        print("  %s✓%s overwritten" % (GREEN, NC))
                    elif choice in ("n", "N"):
                        out_lines.append(line)
                        file_skipped += 1
                        print("  %sℹ%s SKIP" % (BLUE, NC))
                    elif choice == "A" or choice.startswith("a"):
                        # same check as the sh case pattern `abort|A|a*`
                        print("%s❌ Aborted by user%s" % (RED, NC))
                        if not no_backup and not dry_run:
                            shutil.move(backup_path, file_path)
                        return 99
                    else:
                        out_lines.append(line)
                        file_skipped += 1
                        print("  %sℹ%s unknown input → SKIP" % (BLUE, NC))
        else:
            out_lines.append(line)

    if not dry_run:
        # sh: append LF after every line (including the last)
        new_content = "".join(l + "\n" for l in out_lines)
        with open(file_path, "wb") as f:
            f.write(new_content.encode("utf-8"))

    ctx.total_replaced += file_replaced
    ctx.total_skipped += file_skipped
    ctx.total_conflicts += file_conflicts
    ctx.summary.append("📝 %s — replaced %d, SKIP %d, conflicts %d"
                       % (rel, file_replaced, file_skipped, file_conflicts))
    return 0


class SetupArgumentParser(argparse.ArgumentParser):
    """Parser that keeps the same error text format/exit code (2) as sh."""

    def error(self, message):
        print("%s❌ %s%s" % (RED, message, NC))
        print_setup_usage()
        sys.exit(2)


def cmd_setup(argv):
    parser = SetupArgumentParser(prog=PROG, add_help=False, allow_abbrev=False)
    parser.add_argument("--project-path", default="")
    parser.add_argument("--app-id", default="")
    parser.add_argument("--tester-group", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument("-h", "--help", action="store_true", dest="show_help")
    args, unknown = parser.parse_known_args(argv)

    if args.show_help:
        print_setup_usage()
        return 0

    if unknown:
        print("%s❌ Unknown argument: %s%s" % (RED, unknown[0], NC))
        print_setup_usage()
        return 2

    project_path = args.project_path
    app_id = args.app_id
    tester_group = args.tester_group
    dry_run = 1 if args.dry_run else 0
    non_interactive = 1 if args.non_interactive else 0
    no_backup = 1 if args.no_backup else 0

    # ---- Argument validation ----
    if not project_path or not app_id or not tester_group:
        print("%s❌ --project-path, --app-id and --tester-group are all required%s" % (RED, NC))
        print_setup_usage()
        return 2

    if not os.path.isdir(project_path):
        print("%s❌ project-path directory does not exist: %s%s" % (RED, project_path, NC))
        return 2

    workflows_dir = os.path.join(project_path, ".github", "workflows")
    if not os.path.isdir(workflows_dir):
        print("%s❌ No .github/workflows folder. The template has not been applied to this project.%s" % (RED, NC))
        print("%s   checked path: %s%s" % (YELLOW, workflows_dir, NC))
        return 3

    # ---- Find target files (maxdepth 1, sorted by name — same as sh find) ----
    yaml_files = sorted(
        os.path.join(workflows_dir, name)
        for name in os.listdir(workflows_dir)
        if os.path.isfile(os.path.join(workflows_dir, name))
        and (name.endswith(".yaml") or name.endswith(".yml"))
    )

    if not yaml_files:
        print("%s⚠️ No yaml/yml files in the workflows folder%s" % (YELLOW, NC))
        return 0

    timestamp = int(time.time())
    ctx = Ctx()

    print("%s▶ Firebase Wizard Setup%s" % (CYAN, NC))
    print("  project-path: %s" % project_path)
    print("  app-id:       %s" % app_id)
    print("  tester-group: %s" % tester_group)
    print("  dry-run:      %d | non-interactive: %d | no-backup: %d"
          % (dry_run, non_interactive, no_backup))
    print()

    aborted = 0
    for f in yaml_files:
        rc = process_file(f, project_path, app_id, tester_group,
                          bool(dry_run), bool(non_interactive), bool(no_backup),
                          timestamp, ctx)
        if rc == 99:
            aborted = 1
            break

    print()
    print("%s===== Summary =====%s" % (CYAN, NC))
    for line in ctx.summary:
        print("  %s" % line)
    print()
    print("Total replaced: %d | SKIP: %d | conflicts (SKIP): %d"
          % (ctx.total_replaced, ctx.total_skipped, ctx.total_conflicts))

    if dry_run:
        print("%s※ --dry-run: no files were modified%s" % (YELLOW, NC))

    if aborted:
        print("%s❌ Stopped: aborted by user%s" % (RED, NC))
        return 4
    return 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(TOP_USAGE.format(prog=PROG), end="")
        return 0
    if argv[0] != "setup":
        print("%s❌ Unknown command: %s%s" % (RED, argv[0], NC))
        print(TOP_USAGE.format(prog=PROG), end="")
        return 2
    return cmd_setup(argv[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
