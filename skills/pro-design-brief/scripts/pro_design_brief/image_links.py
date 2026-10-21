"""rewrite-images: 업로드 결과(로컬 그림 > URL)로 md 의 그림 경로를 바꾼다 (#974)

입력 2종 (--uploads 여러 번 가능):
- upload-image 출력 JSON 그대로: `images[].file`(로컬 경로)로 먼저, 없으면 `images[].markdown` 의 `![원래 파일 stem](url)` 로 짝을 찾는다
- 직접 만든 대응표: {"board/states.png": "https://..."} (md 기준 상대경로 · 절대경로 · 파일 이름)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from common.emit import emit

# md 그림 2형식: ![alt](경로 "제목") · <img src="경로">
MARKDOWN_IMAGE_PATTERN = re.compile(r'(!\[[^\]]*\]\()([^)\s]+)((?:\s+"[^"]*")?\))')
HTML_IMAGE_PATTERN = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")', re.IGNORECASE)
# upload-image 가 만든 마크다운: ![원래 stem](url)
UPLOADED_MARKDOWN_PATTERN = re.compile(r"^!\[([^\]]*)\]\((\S+)\)$")
REMOTE_PREFIXES = ("http://", "https://", "data:")


def _load_uploads(upload_files: list[str]) -> tuple[dict, dict, list]:
    """업로드 결과 파일들 > (경로 대응표, stem 대응표, 실패 목록)"""
    url_by_path, url_by_stem, failed = {}, {}, []
    for upload_file in upload_files:
        loaded = json.loads(Path(upload_file).expanduser().read_text(encoding="utf-8"))
        if isinstance(loaded, dict) and isinstance(loaded.get("images"), list):
            for image in (i for i in loaded["images"] if isinstance(i, dict)):
                matched = UPLOADED_MARKDOWN_PATTERN.match(str(image.get("markdown", "")))
                if matched:
                    url_by_stem.setdefault(matched.group(1), set()).add(matched.group(2))
                # upload-image 가 로컬 경로(file)를 주면 이름 대신 경로로 짝을 맞춘다
                if image.get("file") and image.get("url"):
                    url_by_path[str(Path(image["file"]).expanduser().resolve())] = str(image["url"])
            failed += [f.get("file") for f in loaded.get("failed") or [] if isinstance(f, dict)]
        elif isinstance(loaded, dict):
            url_by_path.update({str(k): str(v) for k, v in loaded.items()})
        else:
            raise ValueError(f"{upload_file}: upload-image 출력 또는 {{경로: url}} 객체가 아니다")
    return url_by_path, url_by_stem, failed


def _url_for(target: str, md_dir: Path, url_by_path: dict, url_by_stem: dict) -> str | None:
    """로컬 그림 경로 > URL (경로 일치 > 절대경로 일치 > 이름 일치 > stem 일치 순). 겹치면 None"""
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
    """md 읽기 > 로컬 그림마다 업로드 URL 로 치환 > 하나라도 못 찾으면 쓰지 않고 멈춤"""
    md_path = Path(args.md).expanduser()
    if not md_path.is_file():
        return emit({"ok": False, "code": "md_not_found", "error": f"md 가 없다: {md_path}",
                     "next": "board --md 로 brief.md 를 먼저 만든다"})
    try:
        url_by_path, url_by_stem, upload_failed = _load_uploads(args.uploads)
    except (OSError, ValueError) as e:
        return emit({"ok": False, "code": "bad_uploads", "error": str(e),
                     "next": "upload-image 출력 JSON 을 파일로 저장해 --uploads 로 넘긴다"})

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
    # 일부만 바뀐 본문이 게시되면 깨진 그림이 디자이너 알림으로 나간다 — 쓰지 않는다
    if unmatched:
        return emit({"ok": False, "code": "unmatched_images", "unmatched": sorted(set(unmatched)),
                     "upload_failed": upload_failed or None,
                     "error": f"업로드 URL 을 못 찾은 그림 {len(set(unmatched))}개",
                     "next": "빠진 그림을 upload-image 로 올리고 그 출력도 --uploads 에 더해 다시"})
    out_path = Path(args.out).expanduser() if args.out else md_path.with_name(f"{md_path.stem}.issue.md")
    out_path.write_text(rewritten, encoding="utf-8")
    return emit({"ok": True, "code": "ok", "out": str(out_path), "replaced": len(replaced),
                 "summary": f"그림 {len(replaced)}개를 업로드 URL 로 바꿔 {out_path.name} 에 썼다",
                 "next": f"github_cli.py create-issue {{owner}} {{repo}} \"{{제목}}\" \"{out_path}\" ..."})
