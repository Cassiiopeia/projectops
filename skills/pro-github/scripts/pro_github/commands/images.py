"""증적 이미지 서브커맨드: 릴리스 자산 업로드(마크다운 반환)·삭제."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from common.emit import emit
from common.gh_client import EVIDENCE_TAG, GitHubAPIError
from pro_github.registry import Command
from pro_github.responses import api_error, missing_pat


def _release_tag(value: str) -> str:
    """태그로 쓸 수 없는 값(공백·제어문자·~^:?*[\\ 등)을 인자 단계에서 거절한다 (#701).

    URL 에 그대로 넣으면 InvalidURL 예외가 handler_error 로 새므로, 다른 서브커맨드처럼 bad_args 로 알린다.
    """
    if not value or re.search(r"[\s\x00-\x1f\x7f~^:?*\[\\]", value) or value.startswith(("-", "/")):
        raise argparse.ArgumentTypeError(
            f"태그 형식이 올바르지 않습니다: {value!r} (공백·제어문자·~^:?*[ 사용 불가)")
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
            "error": "올릴 파일이 없습니다",
            "failed": [{"file": f, "error": "파일이 없습니다"} for f in missing],
        })

    try:
        # private이면 익명 접근이 막혀 이미지가 깨진다. 올리기 전에 알린다 —
        # 올리고 나서 알면 이미 이슈에 깨진 이미지가 박힌 뒤다.
        warning = None
        if api.is_repo_private(args.owner, args.repo, pat):
            warning = ("private 레포라 이미지가 렌더링되지 않습니다(익명 접근 차단). "
                       "URL은 발급되지만 이슈에서는 깨져 보입니다.")

        images, failed = [], []
        for f in args.files:
            try:
                images.append(api.upload_evidence_image(
                    args.owner, args.repo, f, pat, tag=args.tag, prefix=args.prefix))
            except FileNotFoundError as e:
                failed.append({"file": f, "error": str(e)})

        if not images:
            return emit({"ok": False, "code": "no_image_uploaded",
                         "error": "올린 이미지가 없습니다", "failed": failed})

        return emit({
            "count": len(images),
            "images": images,
            # 그대로 본문·댓글 파일에 붙여넣을 수 있게 합쳐서 준다
            "markdown": "\n".join(i["markdown"] for i in images),
            "failed": failed or None,
            "private_warning": warning,
            "summary": f"이미지 {len(images)}개 업로드 완료",
            "next": f"add-comment {args.owner} {args.repo} <이슈번호> <본문파일>",
        })
    except GitHubAPIError as e:
        return api_error(e)


def cmd_delete_image(args, api) -> int:
    """올린 증적을 지운다. 검증용으로 올린 것을 치울 때 쓴다."""
    pat = api.get_github_pat(args.owner, args.repo)
    if not pat:
        return missing_pat()
    try:
        api.delete_release_asset(args.owner, args.repo, args.asset_id, pat)
        return emit({"asset_id": args.asset_id, "status": "deleted",
                     "summary": f"증적 {args.asset_id} 삭제 완료"})
    except GitHubAPIError as e:
        return api_error(e)


# ── 인자 ──

def _configure_upload_image(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("files", nargs="+", help="이미지 파일 경로 (여러 개 가능)")
    parser.add_argument("--tag", type=_release_tag, default=EVIDENCE_TAG, help=f"증적 릴리스 태그 (기본 {EVIDENCE_TAG})")
    parser.add_argument("--prefix", default=None, help="자산 이름 앞에 붙일 말 (예: issue585)")


def _configure_delete_image(parser) -> None:
    parser.add_argument("owner")
    parser.add_argument("repo")
    parser.add_argument("asset_id", type=int, help="증적 자산 ID (정수)")


COMMANDS = [
    Command(name="upload-image", help="이미지를 증적 릴리스에 올려 마크다운을 받는다", run=cmd_upload_image,
            configure=_configure_upload_image),
    Command(name="delete-image", help="올린 증적 이미지를 지운다", run=cmd_delete_image,
            configure=_configure_delete_image),
]
