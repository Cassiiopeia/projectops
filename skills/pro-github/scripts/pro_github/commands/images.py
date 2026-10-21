"""증적 이미지 서브커맨드: 릴리스 자산 업로드(마크다운 반환)·삭제."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common.emit import emit
from common.gh_client import EVIDENCE_TAG, GitHubAPIError, ReleaseAssetLimitError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat


def _release_tag(value: str) -> str:
    """태그로 쓸 수 없는 값(공백·제어문자·~^:?*[\\ 등)을 인자 단계에서 거절한다 (#701).

    URL 에 그대로 넣으면 InvalidURL 예외가 handler_error 로 새므로, 다른 서브커맨드처럼 bad_args 로 알린다.
    """
    if not value or re.search(r"[\s\x00-\x1f\x7f~^:?*\[\\]", value) or value.startswith(("-", "/")):
        raise argparse.ArgumentTypeError(
            f"invalid tag: {value!r} (no spaces, control characters or ~^:?*[)")
    return value


def cmd_upload_image(args, api) -> int:
    """이미지를 증적 릴리스에 올리고 바로 붙여넣을 마크다운까지 돌려준다.

    GitHub 공식 첨부 업로드는 브라우저 세션이 필요해 PAT로 쓸 수 없다. 릴리스 자산이
    유일하게 PAT로 가능한 경로이고, 실측으로 이슈 본문·댓글 양쪽에서 <img>로 렌더링되는
    것을 확인했다 (자세한 근거는 gh_client의 주석).
    """
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    # 파일 확인이 먼저다. 네트워크를 먼저 치면 "파일이 없다"가 "레포가 없다"(404)로
    # 둔갑해 원인을 못 짚는다. 올릴 것이 하나도 없으면 API를 부를 이유도 없다.
    missing = [f for f in args.files if not Path(f).expanduser().is_file()]
    if len(missing) == len(args.files):
        return emit({
            "ok": False, "code": "no_image_uploaded",
            "error": "no files to upload",
            "failed": [{"file": f, "error": "file not found"} for f in missing],
        })

    try:
        # private이면 익명 접근이 막혀 이미지가 깨진다. 올리기 전에 알린다 —
        # 올리고 나서 알면 이미 이슈에 깨진 이미지가 박힌 뒤다.
        warning = None
        if api.is_repo_private(args.owner, args.repo, pat):
            warning = ("images do not render in a private repo (anonymous access is blocked). "
                       "The URL is issued, but the image shows as broken in issues.")

        images, failed = [], []
        # 한도로 이월된 태그를 다음 파일에도 쓴다 (매 파일 꽉 찬 릴리스부터 다시 두드리지 않게)
        current_tag = args.tag
        limit_error = None
        for position, f in enumerate(args.files):
            try:
                image = api.upload_evidence_image(args.owner, args.repo, f, pat, tag=current_tag, prefix=args.prefix)
            except FileNotFoundError as e:
                failed.append({"file": f, "error": str(e)})
                continue
            except ReleaseAssetLimitError as e:
                # 이미 올린 것은 살려 보고하고, 남은 파일은 실패로 남긴다
                limit_error = e
                failed.extend({"file": rest, "error": "release_asset_limit"} for rest in args.files[position:])
                break
            # 로컬 경로 — design-brief rewrite-images 가 파일 이름 대신 경로로 짝을 맞춘다 (#974)
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
            # 그대로 본문·댓글 파일에 붙여넣을 수 있게 합쳐서 준다
            "markdown": "\n".join(i["markdown"] for i in images),
            "tag": current_tag,
            "failed": failed or None,
            "private_warning": warning,
            "summary": f"uploaded {len(images)} image(s) (release {current_tag})",
            "next": f"add-comment {args.owner} {args.repo} <issue_number> <body_file>",
        }
        # 1개면 images.0.url 을 짐작하지 않게 최상위에 둔다
        if len(images) == 1:
            out["url"] = images[0]["url"]
        return emit(out)
    except GitHubAPIError as e:
        return api_error(e)


def _asset_limit_response(args, error) -> int:
    """이어 쓸 증적 릴리스까지 모두 찬 경우: 시도한 태그와 다음 행동"""
    return emit({"ok": False, "code": "release_asset_limit", "error": str(error), "tried_tags": error.tried_tags,
                 "next": (f"delete old evidence with delete-image {args.owner} {args.repo} <asset_id>, or upload again with "
                          f"upload-image {args.owner} {args.repo} <file> --tag <new tag>")})


def cmd_delete_image(args, api) -> int:
    """올린 증적을 지운다. 검증용으로 올린 것을 치울 때 쓴다."""
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        api.delete_release_asset(args.owner, args.repo, args.asset_id, pat)
        return emit({"asset_id": args.asset_id, "status": "deleted",
                     "summary": f"deleted evidence asset {args.asset_id}"})
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

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
