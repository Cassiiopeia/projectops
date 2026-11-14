"""rewrite-images: replace image paths in md using upload results (local image > URL) (#974)

2 input kinds (--uploads may repeat):
- upload-image output JSON as is: match by `images[].file` (local path) first, else by `![original file stem](url)` in `images[].markdown`
- hand-made map: {"board/states.png": "https://..."} (path relative to md, absolute path, or file name)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.emit import emit

# 2 md image forms: ![alt](path "title") and <img src="path">
MARKDOWN_IMAGE_PATTERN = re.compile(r'(!\[[^\]]*\]\()([^)\s]+)((?:\s+"[^"]*")?\))')
HTML_IMAGE_PATTERN = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.IGNORECASE)
# Markdown produced by upload-image: ![original stem](url)
UPLOADED_MARKDOWN_PATTERN = re.compile(r"^!\[([^\]]*)\]\((\S+)\)$")
REMOTE_PREFIXES = ("http://", "https://", "data:")


def _load_uploads(upload_files: list[str]) -> tuple[dict, dict, list]:
    """Upload result files > (path map, stem map, failures)"""
    url_by_path, url_by_stem, failed = {}, {}, []
    for upload_file in upload_files:
        loaded = json.loads(Path(upload_file).expanduser().read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("images"), list):
            for image in (i for i in loaded["images"] if isinstance(i, dict)):
                matched = UPLOADED_MARKDOWN_PATTERN.match(str(image.get("markdown", "")))
                if matched:
                    url_by_stem.setdefault(matched.group(1), set()).add(matched.group(2))
                # When upload-image gives the local path (file), match by path instead of name
                if image.get("file") and image.get("url"):
                    url_by_path[str(Path(image["file"]).expanduser().resolve())] = str(image["url"])
            failed += [f.get("file") for f in loaded.get("failed") or [] if isinstance(f, dict)]
        elif isinstance(loaded, dict):
            url_by_path.update({str(k): str(v) for k, v in loaded.items()})
        else:
            raise ValueError(f"{upload_file}: not upload-image output or a {{path: url}} object")
    return url_by_path, url_by_stem, failed


def _url_for(target: str, md_dir: Path, url_by_path: dict, url_by_stem: dict) -> str | None:
    """Local image path > URL (path match > absolute path match > name match > stem match). None if ambiguous"""
    absolute = (md_dir / target).resolve()
    for key, url in url_by_path.items():
        if key == target or Path(key).expanduser().resolve() == absolute:
            return url
    by_name = {url for key, url in url_by_path.items() if Path(key).name == absolute.name}
    if len(by_name) == 1:
        return by_name.pop()
    by_stem = url_by_stem.get(absolute.stem) or set()
    return next(iter(by_stem)) if len(by_stem) == 1 else None


def cmd_rewrite_images(args) -> int:
    """Read md > replace each local image with its upload URL > stop without writing if any is missing"""
    md_path = Path(args.md).expanduser()
    if not md_path.is_file():
        return emit({"ok": False, "code": "md_not_found", "error": f"md not found: {md_path}",
                     "next": "Create brief.md first with board --md"})
    try:
        url_by_path, url_by_stem, upload_failed = _load_uploads(args.uploads)
    except (OSError, ValueError) as e:
        return emit({"ok": False, "code": "bad_uploads", "error": str(e),
                     "next": "Save the upload-image output JSON to a file and pass it with --uploads"})

    md_dir = md_path.parent.resolve()
    replaced, unmatched = [], []

    def replace(match: re.Match) -> str:
        target = match.group(2)
        if target.startswith(REMOTE_PREFIXES):
            return match.group(0)
        url = _url_for(target, md_dir, url_by_path, url_by_stem)
        if not url:
            unmatched.append(target)
            return match.group(0)
        replaced.append(target)
        return match.group(1) + url + match.group(3)

    text = md_path.read_text(encoding="utf-8")
    rewritten = HTML_IMAGE_PATTERN.sub(replace, MARKDOWN_IMAGE_PATTERN.sub(replace, text))
    # A partly rewritten body would send broken images in designer notifications — do not write
    if unmatched:
        return emit({"ok": False, "code": "unmatched_images", "unmatched": sorted(set(unmatched)),
                     "upload_failed": upload_failed or None,
                     "error": f"{len(set(unmatched))} image(s) without an uploaded URL",
                     "next": "Upload the missing images with upload-image, add that output to --uploads too, and run again"})
    out_path = Path(args.out).expanduser() if args.out else md_path.with_name(f"{md_path.stem}.issue.md")
    out_path.write_text(rewritten, encoding="utf-8")
    return emit({"ok": True, "code": "ok", "out": str(out_path), "replaced": len(replaced),
                 "summary": f"Replaced {len(replaced)} image(s) with uploaded URLs and wrote {out_path.name}",
                 "next": f"github_cli.py create-issue {{owner}} {{repo}} \"{{title}}\" \"{out_path}\" ..."})
