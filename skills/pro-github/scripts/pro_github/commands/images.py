"""Evidence image subcommands: upload release assets (returns markdown), delete."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common.emit import emit
from common.gh_client import EVIDENCE_TAG, GitHubAPIError, ReleaseAssetLimitError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat


def _release_tag(value: str) -> str:
    """Reject values unusable as a tag (whitespace, control chars, ~^:?*[\\ etc.) at the argument stage (#701).

    Put into a URL as is, they leak an InvalidURL exception as handler_error, so report bad_args like other subcommands.
    """
    if not value or re.search(r"[\s\x00-\x1f\x7f~^:?*\[\\]", value) or value.startswith(("-", "/")):
        raise argparse.ArgumentTypeError(
            f"invalid tag: {value!r} (no spaces, control characters or ~^:?*[)")
    return value


def cmd_upload_image(args, api) -> int:
    """Upload images to the evidence release and return the markdown ready to paste.

    GitHub's official attachment upload needs a browser session, so a PAT cannot use it. Release assets
    are the only PAT-capable path, and they were measured to render as <img> in both issue bodies and comments
    (details in the gh_client comments).
    """
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    # Check files first. Hitting the network first turns "file missing" into "repo missing" (404)
    # and hides the cause. If there is nothing to upload, there is no reason to call the API.
    missing = [f for f in args.files if not Path(f).expanduser().is_file()]
    if len(missing) == len(args.files):
        return emit({
            "ok": False, "code": "no_image_uploaded",
            "error": "no files to upload",
            "failed": [{"file": f, "error": "file not found"} for f in missing],
        })

    try:
        # If private, anonymous access is blocked and images break. Warn before uploading —
        # finding out after means the broken image is already in the issue.
        warning = None
        if api.is_repo_private(args.owner, args.repo, pat):
            warning = ("images do not render in a private repo (anonymous access is blocked). "
                       "The URL is issued, but the image shows as broken in issues.")

        images, failed = [], []
        # Reuse the tag rolled over by the limit for the next file (so each file does not start again from a full release)
        current_tag = args.tag
        limit_error = None
        for position, f in enumerate(args.files):
            try:
                image = api.upload_evidence_image(args.owner, args.repo, f, pat, tag=current_tag, prefix=args.prefix)
            except FileNotFoundError as e:
                failed.append({"file": f, "error": str(e)})
                continue
            except ReleaseAssetLimitError as e:
                # Report what was already uploaded, and mark the remaining files as failed
                limit_error = e
                failed.extend({"file": rest, "error": "release_asset_limit"} for rest in args.files[position:])
                break
            # Local path — ui-design rewrite-images matches by path instead of file name (#974)
            images.append({**image, "file": str(Path(f).expanduser().resolve())})
            current_tag = image.get("tag", current_tag)

        if not images and limit_error is not None:
            return _asset_limit_response(args, limit_error)
        if not images:
            return emit({"ok": False, "code": "no_image_uploaded",
                         "error": "no images were uploaded", "failed": failed})

        out = {
            "count": len(images),
            "images": images,
            # Joined so it can be pasted into a body or comment file as is
            "markdown": "\n".join(i["markdown"] for i in images),
            "tag": current_tag,
            "failed": failed or None,
            "private_warning": warning,
            "summary": f"uploaded {len(images)} image(s) (release {current_tag})",
            "next": f"add-comment {args.owner} {args.repo} <issue_number> <body_file>",
        }
        # With one image, put it at the top level so nobody guesses images.0.url
        if len(images) == 1:
            out["url"] = images[0]["url"]
        return emit(out)
    except GitHubAPIError as e:
        return api_error(e)


def _asset_limit_response(args, error) -> int:
    """Every evidence release to roll over into is full: tried tags and next action"""
    return emit({"ok": False, "code": "release_asset_limit", "error": str(error), "tried_tags": error.tried_tags,
                 "next": (f"delete old evidence with delete-image {args.owner} {args.repo} <asset_id>, or upload again with "
                          f"upload-image {args.owner} {args.repo} <file> --tag <new tag>")})


def cmd_delete_image(args, api) -> int:
    """Delete uploaded evidence. Used to clean up what was uploaded for verification."""
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        api.delete_release_asset(args.owner, args.repo, args.asset_id, pat)
        return emit({"asset_id": args.asset_id, "status": "deleted",
                     "summary": f"deleted evidence asset {args.asset_id}"})
    except GitHubAPIError as e:
        return api_error(e)


# ── Arguments ──

def _configure_upload_image(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("files", nargs="+", help="image file paths (one or more)")
    parser.add_argument("--tag", type=_release_tag, default=EVIDENCE_TAG, help=f"evidence release tag (default {EVIDENCE_TAG})")
    parser.add_argument("--prefix", default=None, help="prefix for the asset name (e.g. issue585)")


def _configure_delete_image(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("asset_id", type=int, help="evidence asset ID (integer)")


COMMANDS = [
    Command(name="upload-image", help="upload images to the evidence release and get markdown", run=cmd_upload_image,
            configure=_configure_upload_image),
    Command(name="delete-image", help="delete an uploaded evidence image", run=cmd_delete_image,
            configure=_configure_delete_image),
]
