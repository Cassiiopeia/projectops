"""증적 이미지: 전용 릴리스 확보, 자산 업로드·삭제, 붙여넣을 마크다운."""

from __future__ import annotations

import datetime
import mimetypes
import pathlib
import re
import urllib.parse

from common import gh_client as client
from common.github_rest.transport import _API_BASE, GitHubAPIError


# GitHub이 이슈 첨부에 쓰는 업로드 엔드포인트는 **브라우저 세션이 필요해 PAT로 쓸 수 없다.**
# 그래서 릴리스 자산(Release assets)으로 우회한다. 실측으로 확인한 것:
#
#   - 익명 접근 200, Content-Type은 application/octet-stream (image/png가 아니다)
#   - Content-Disposition: attachment 가 붙지만 <img> 태그에서는 무시된다
#   - **X-Content-Type-Options(nosniff)가 없다** → 브라우저가 매직넘버로 스니핑해 그린다
#   - 이슈 본문·댓글 모두 <img>로 렌더링된다 (body_html로 확인)
#
# 레포에 커밋하는 방식은 쓰지 않는다 — 이미지가 git 히스토리에 영구히 남는다.

# 증적 전용 릴리스 태그. 버전 릴리스와 섞으면 릴리스 목록이 증적으로 뒤덮인다.
EVIDENCE_TAG = "qa-evidence"

# <img>로 렌더링되는 형식. 이 밖의 것(mp4 등)은 링크로만 남는다 —
# GitHub이 video로 그려주는 것은 공식 첨부 경로뿐이라 릴리스 자산은 해당되지 않는다.
_RENDERABLE = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}

# 릴리스 하나의 자산 한도(1000개)를 넘으면 이어 쓸 릴리스 수: {tag}-2 … {tag}-{이 값}
_MAX_EVIDENCE_RELEASES = 20
# 자산 한도 초과 422 의 오류 문구 (errors[].field=file_count, message 에 1000 assets)
_ASSET_LIMIT_MARKERS = ("file_count", "limited to 1000 assets")


class ReleaseAssetLimitError(GitHubAPIError):
    """이어 쓸 릴리스까지 모두 자산 한도에 걸림. tried_tags: 시도한 태그 순서"""

    def __init__(self, message: str, tried_tags: list[str]) -> None:
        super().__init__(422, message)
        self.tried_tags = tried_tags


def is_asset_limit_error(error: GitHubAPIError) -> bool:
    """릴리스 자산 1000개 한도 422 인지"""
    return error.status_code == 422 and any(marker in str(error) for marker in _ASSET_LIMIT_MARKERS)


def evidence_tag_candidates(tag: str) -> list[str]:
    """qa-evidence > [qa-evidence, qa-evidence-2, …, qa-evidence-20] (한도를 넘으면 이 순서로 이월)"""
    return [tag] + [f"{tag}-{index}" for index in range(2, _MAX_EVIDENCE_RELEASES + 1)]


def ensure_evidence_release(owner: str, repo: str, pat: str, tag: str = EVIDENCE_TAG) -> dict:
    """증적 릴리스를 확보한다. 없으면 만든다(멱등).

    prerelease로 만든다 — 최신 릴리스 배지가 증적으로 바뀌면 사용자가 혼란스럽다.
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
            "name": "QA 증적 저장소",
            "body": ("테스트·QA 증적 이미지를 담는 전용 릴리스입니다. 코드 릴리스가 아닙니다.\n"
                     "이슈·PR 본문과 댓글에서 이미지로 참조됩니다."),
            "draft": False,
            "prerelease": True,
        },
        pat,
    )


def _asset_name(path: str, prefix: str | None = None) -> str:
    """자산 이름을 만든다. 같은 이름이 있으면 GitHub이 422로 거절하므로 시각을 붙여 고유화한다.

    영문·숫자·일부 기호만 남긴다 — 한글 파일명은 URL에서 인코딩돼 마크다운이 깨진다.
    """
    p = pathlib.PurePath(path)
    # 한글 파일명은 통째로 걸러지므로 "__2" 같은 찌꺼기가 남는다. 양끝 구분자를 걷어내고
    # 아무것도 안 남으면 image로 둔다 — 고유성은 어차피 시각이 보장한다.
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", p.stem)
    stem = re.sub(r"[-_.]{2,}", "-", stem).strip("-_.") or "image"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    head = f"{prefix}_" if prefix else ""
    return f"{head}{stamp}_{stem}{p.suffix.lower()}"


def upload_evidence_image(
    owner: str, repo: str, file_path: str, pat: str,
    tag: str = EVIDENCE_TAG, prefix: str | None = None,
) -> dict:
    """이미지 파일 하나를 증적 릴리스에 올리고 마크다운까지 만들어 돌려준다."""
    src = pathlib.Path(file_path).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"파일이 없습니다: {src}")

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
        # 렌더링되지 않는 형식을 ![]()로 넣으면 깨진 이미지가 뜬다. 링크로 준다.
        "markdown": f"![{src.stem}]({url})" if renderable else f"[{src.name}]({url})",
        "renderable": renderable,
        "asset_id": asset["id"],
        # 한도로 이월했으면 요청한 태그와 다르다 — 다음 파일은 이 태그부터 올린다
        "tag": used_tag,
    }


def _upload_with_rollover(owner, repo, pat, tag, name, data, ctype) -> tuple[str, dict]:
    """태그 릴리스에 업로드 > 자산 한도 422 면 다음 태그 릴리스(없으면 생성)로 이월 > (쓴 태그, 자산)"""
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
    raise ReleaseAssetLimitError(f"증적 릴리스 {len(tried)}개가 모두 자산 한도(1000개)에 찼다", tried)


def delete_release_asset(owner: str, repo: str, asset_id: int, pat: str) -> None:
    """올린 증적을 지운다. 검증용으로 올린 것을 치울 때 쓴다."""
    client._request("DELETE", f"{_API_BASE}/repos/{owner}/{repo}/releases/assets/{asset_id}", None, pat)
