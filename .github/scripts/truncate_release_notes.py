#!/usr/bin/env python3
# ===================================================================
# truncate_release_notes.py — release notes length limit (Python move of the .sh, #448)
# ===================================================================
#
# Safely truncates text to each store's release notes (changelog) length
# limit. Over the limit it cuts at a line boundary first and appends an ellipsis (…).
# It never exits abnormally (exit 0), so it never breaks the deploy
# pipeline.
#
# Background: Google Play (500 chars), TestFlight (4000 bytes), Firebase, etc.
# limits and units (chars/bytes) differ per platform. Related issue: #347
#
# Usage:
#   python truncate_release_notes.py <input file> <max length> <mode> [output file]
#   - mode: char (Unicode character count) | byte (UTF-8 byte count)
#   - without an output file the input file is modified in place
# ===================================================================

import sys
import unicodedata

ELLIPSIS = "…"


def _is_regional(ch):
    """Whether it is a regional indicator character (U+1F1E6-1F1FF) that forms a flag."""
    return 0x1F1E6 <= ord(ch) <= 0x1F1FF


def _joins_previous(text, n):
    """Whether text[n] joins the previous character into one cluster (= cutting at n breaks it)."""
    if n <= 0 or n >= len(text):
        return False
    cur, prev = text[n], text[n - 1]
    code = ord(cur)
    if cur == "‍" or prev == "‍":  # ZWJ sequences (family emoji, etc.)
        return True
    if 0xFE00 <= code <= 0xFE0F or 0x1F3FB <= code <= 0x1F3FF:  # variation selectors, skin tones
        return True
    if unicodedata.category(cur) in ("Mn", "Me"):  # combining characters
        return True
    if _is_regional(cur) and _is_regional(prev):
        # Flags come in pairs — an odd count of preceding indicators means cur is the second of a pair
        run, i = 0, n - 1
        while i >= 0 and _is_regional(text[i]):
            run += 1
            i -= 1
        return run % 2 == 1
    return False


def safe_cut(text, n):
    """Cut before n characters, but if that lands inside an emoji sequence, back off before it."""
    n = min(n, len(text))
    while n > 0 and _joins_previous(text, n):
        n -= 1
    return n


def write_out(path, content):
    """Write the output. On failure only warn and return False so the deploy is not blocked."""
    try:
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        return True
    except OSError as e:
        print(f"⚠️ truncate_release_notes: could not write the output file ({path}): {e}. Skipped.")
        return False


def main(argv):
    input_file = argv[1] if len(argv) > 1 else ""
    max_raw = argv[2] if len(argv) > 2 else ""
    mode = (argv[3] if len(argv) > 3 else "char").strip().lower()
    output_file = argv[4] if len(argv) > 4 else input_file

    # --- Input validation (exit 0 even on failure so the deploy is not blocked) ---
    if not input_file or not max_raw:
        print("⚠️ truncate_release_notes: missing arguments (usage: <input-file> <max-length> <mode> [output-file]). Skipped.")
        return 0

    try:
        max_len = int(max_raw)
    except ValueError:
        print("⚠️ truncate_release_notes: max length is not an integer. Skipped.")
        return 0

    if mode not in ("char", "byte"):
        print(f"⚠️ truncate_release_notes: unknown mode '{mode}' → using char mode.")
        mode = "char"

    try:
        # Non-UTF-8 input must not crash either; broken bytes are read as replacement characters
        with open(input_file, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError:
        print(f"⚠️ truncate_release_notes: input file not found ({input_file}). Skipped.")
        return 0

    # Newline normalization: CRLF/CR -> LF. (Prevents \r in input made on Windows from being
    # missed in the length count and exceeding the limit after truncation.)
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    def measure(s):
        """Measure length per mode: char = character count, byte = UTF-8 byte count."""
        return len(s.encode("utf-8")) if mode == "byte" else len(s)

    orig_len = measure(text)

    if orig_len <= max_len:
        # Within the limit — no change
        if output_file != input_file:
            write_out(output_file, text)
        print(f"✅ truncate_release_notes: within the limit ({orig_len}/{max_len} {mode}). No change.")
        return 0

    # Effective limit minus room for the ellipsis
    effective = max(max_len - measure(ELLIPSIS), 0)

    def truncate_to(s, limit):
        """Cut by character so it fits the effective limit.
        byte mode guarantees character boundaries so multibyte characters are not split."""
        if measure(s) <= limit:
            return s
        if mode == "char":
            return s[:safe_cut(s, limit)]
        # byte mode: binary search for the character boundary meeting the byte limit
        lo, hi = 0, len(s)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if len(s[:mid].encode("utf-8")) <= limit:
                lo = mid
            else:
                hi = mid - 1
        return s[:safe_cut(s, lo)]

    # First pass: cut to within the effective limit
    hard_cut = truncate_to(text, effective)

    # Line boundary first: cut at the last newline within the hard_cut range
    nl_idx = hard_cut.rfind("\n")
    candidate = hard_cut[:nl_idx] if nl_idx > 0 else hard_cut

    # Trim trailing spaces/newlines, then append the ellipsis
    result = candidate.rstrip() + ELLIPSIS

    # Safety: if the result still exceeds the limit, force one more cut
    while measure(result) > max_len and len(candidate) > 0:
        candidate = candidate[:safe_cut(text, len(candidate) - 1)]
        result = candidate.rstrip() + ELLIPSIS

    if not write_out(output_file, result):
        return 0

    print(f"✂️ truncate_release_notes: {orig_len} → {measure(result)} {mode} (limit {max_len}). Truncated.")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main(sys.argv))
