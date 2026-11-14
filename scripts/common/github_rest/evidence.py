"""Evidence images: ensure a dedicated release, upload/delete assets, markdown to paste."""

from __future__ import annotations

import datetime
import mimetypes
import pathlib
import re
import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE, GitHubAPIError


# The upload endpoint GitHub uses for issue attachments **needs a browser session and cannot be used with a PAT.**
# So release assets are used instead. Verified by measurement:
#
#   - Anonymous access 200, Content-Type is application/octet-stream (not image/png)
#   - Content-Disposition: attachment is set but ignored by <img> tags
#   - **No X-Content-Type-Options (nosniff)** → browsers sniff the magic number and render it
#   - Rendered as <img> in both issue bodies and comments (confirmed via body_html)
#
# Committing to the repo is not used: images would stay in git history forever.

# Release tag for evidence only. Mixing with version releases would flood the release list with evidence.
EVIDENCE_TAG = "qa-evidence"

# Formats rendered as <img>. Anything else (mp4, etc.) stays a link only;
# GitHub renders video only for the official attachment path, which release assets are not.
_RENDERABLE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

# Number of overflow releases after one release's asset limit (1000): {tag}-2 … {tag}-{this value}
_MAX_EVIDENCE_RELEASES = 20
# Error text of the asset-limit 422 (errors[].field=file_count, message contains 1000 assets)
_ASSET_LIMIT_MARKERS = ("file_count", "limited to 1000 assets")


class ReleaseAssetLimitError(GitHubAPIError):
    """All overflow releases hit the asset limit too. tried_tags: tags tried, in order"""

    def __init__(self, message: str, tried_tags: list[str]) -> None:
        super().__init__(422, message)
        self.tried_tags = tried_tags


def is_asset_limit_error(error: GitHubAPIError) -> bool:
    """Whether it is the 1000-asset-per-release limit 422"""
    return error.status_code == 422 and any(marker in str(error) for marker in _ASSET_LIMIT_MARKERS)


def evidence_tag_candidates(tag: str) -> list[str]:
    """qa-evidence > [qa-evidence, qa-evidence-2, …, qa-evidence-20] (overflow in this order past the limit)"""
    return [tag] + [f"{tag}-{index}" for index in range(2, _MAX_EVIDENCE_RELEASES + 1)]


def ensure_evidence_release(owner: str, repo: str, pat: str, tag: str = EVIDENCE_TAG) -> dict:
    """Ensure the evidence release exists. Create it if missing (idempotent).

    Created as a prerelease: users get confused if the latest-release badge turns into evidence.
    """
    try:
        return client._request("GET", f"{_API_BASE}/repos/{owner}/{repo}/releases/tags/{urllib.parse.quote(tag, safe='')}", None, pat)
    except GitHubAPIError as e:
        if e.status_code != 404:
            raise
    return client._request(
        "POST", f"{_API_BASE}/repos/{owner}/{repo}/releases",
        {
            "tag_name": tag,
            "name": "QA evidence store",
            "body": ("A release that only holds test and QA evidence images. It is not a code release.\n"
                     "Issue and PR bodies and comments reference these images."),
            "draft": False,
            "prerelease": True,
        },
        pat,
    )


def _asset_name(path: str, prefix: str | None = None) -> str:
    """Build the asset name. GitHub rejects duplicate names with 422, so append a timestamp to make it unique.

    Keep only letters, digits and some symbols; Hangul file names get URL-encoded and break the markdown.
    """
    p = pathlib.PurePath(path)
    # Hangul file names are filtered out entirely, leaving debris like "__2". Strip separators at both ends
    # and use image if nothing remains; the timestamp guarantees uniqueness anyway.
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", p.stem)
    stem = re.sub(r"[-_.]{2,}", "-", stem).strip("-_.") or "image"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    head = f"{prefix}_" if prefix else ""
    return f"{head}{stamp}_{stem}{p.suffix.lower()}"


def upload_evidence_image(
    owner: str, repo: str, file_path: str, pat: str,
    tag: str = EVIDENCE_TAG, prefix: str | None = None,
) -> dict:
    """Upload one image file to the evidence release and return it with the markdown."""
    src = pathlib.Path(file_path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"file not found: {src}")

    data = src.read_bytes()
    ctype = mimetypes.guess_type(src.name)[0] or "application/octet-stream"
    name = client._asset_name(src.name, prefix)

    used_tag, asset = _upload_with_rollover(owner, repo, pat, tag, name, data, ctype)

    url = asset["browser_download_url"]
    renderable = src.suffix.lower() in _RENDERABLE
    return {
        "name": name,
        "url": url,
        "size": len(data),
        "content_type": ctype,
        # Non-rendering formats inserted as ![]() show a broken image. Give a link.
        "markdown": f"![{src.stem}]({url})" if renderable else f"[{src.name}]({url})",
        "renderable": renderable,
        "asset_id": asset["id"],
        # Overflowed past the limit, so it differs from the requested tag; upload the next file from this tag
        "tag": used_tag,
    }


def _upload_with_rollover(owner, repo, pat, tag, name, data, ctype) -> tuple[str, dict]:
    """Upload to the tag's release > on asset-limit 422, overflow to the next tag's release (create if missing) > (tag used, asset)"""
    tried: list[str] = []
    for candidate in evidence_tag_candidates(tag):
        tried.append(candidate)
        release = client.ensure_evidence_release(owner, repo, pat, candidate)
        upload_url = release["upload_url"].split("{")[0] + f"?name={urllib.parse.quote(name)}"
        try:
            return candidate, client._upload_request(upload_url, data, ctype, pat)
        except GitHubAPIError as error:
            if not is_asset_limit_error(error):
                raise
    raise ReleaseAssetLimitError(f"all {len(tried)} evidence releases are at the asset limit (1000)", tried)


def delete_release_asset(owner: str, repo: str, asset_id: int, pat: str) -> None:
    """Delete uploaded evidence. Used to clean up uploads made for verification."""
    client._request("DELETE", f"{_API_BASE}/repos/{owner}/{repo}/releases/assets/{asset_id}", None, pat)
