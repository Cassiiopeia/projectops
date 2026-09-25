"""캡처 줄이기 — WebP 변환과 긴 변 축소 (pro-launch · pro-agent-test 공용, #629).

화면 캡처는 쌓이면 무겁다. 줄여야 하는 것이 **둘**인데 방법이 서로 다르다(실측).

  파일 크기  →  WebP 로 바꾼다.  495KB → 34KB (-93%)
  세션 토큰  →  **해상도를 줄인다.** 포맷은 토큰에 아무 영향이 없다.
                1080x2400 그대로면 1,473 토큰, 긴 변 1200 으로 줄이면 864 토큰.

그래서 **둘을 함께** 한다.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from common.proc import run
from common.state import venv_python

WEBP_QUALITY = 75
SHOT_MAX_SIDE = 1200          # 작은 글자까지 읽히는 선. 토큰은 약 41% 줄어든다


def has_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


# venv 파이썬에게 시킬 변환. 인자: src dst quality max_side(0이면 축소 안 함)
PILLOW_SNIPPET = (
    "import sys\n"
    "from PIL import Image\n"
    "src, dst, q, side = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])\n"
    "im = Image.open(src)\n"
    "if side:\n"
    "    im.thumbnail((side, side), Image.LANCZOS)\n"
    "im.save(dst, 'WEBP', quality=q, method=4)\n"
)


def _pillow_webp(src: Path, dst: Path, quality: int, max_side: int | None) -> None:
    from PIL import Image
    with Image.open(src) as im:
        if max_side:
            im.thumbnail((max_side, max_side), Image.LANCZOS)
        im.save(dst, "WEBP", quality=quality, method=4)


def venv_has_pillow(vpy: Path) -> bool:
    try:
        return subprocess.run([str(vpy), "-c", "import PIL"],
                              capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def is_portrait(src: Path) -> bool:
    """cwebp 는 비율 유지를 0 으로 표시하므로 어느 변이 긴지 알아야 한다."""
    if has_pillow():
        from PIL import Image
        with Image.open(src) as im:
            return im.height >= im.width
    out = run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(src)])
    w = h = 0
    for line in out.splitlines():
        if "pixelWidth" in line:
            w = int(line.split(":")[1])
        if "pixelHeight" in line:
            h = int(line.split(":")[1])
    return h >= w if (w and h) else True


def to_webp(src: Path, quality: int = WEBP_QUALITY,
            max_side: int | None = None) -> Path | None:
    """이미지를 WebP 로 바꾸고, max_side 가 있으면 긴 변을 거기에 맞춘다.

    Pillow(시스템) → Pillow(전용 venv) → cwebp → ffmpeg 순으로 가진 것을 쓴다.
    **하나도 없다고 해서 화면을 못 찍게 하지는 않는다** — 원본이 남고 조금 무거울 뿐이다.
    macOS 의 sips 는 WebP 쓰기를 못 해 사다리에 넣지 않았다(실측).
    """
    if src.suffix.lower() == ".webp" and not max_side:
        return src
    dst = src.with_suffix(".webp")
    side = str(max_side or 0)
    try:
        if has_pillow():
            _pillow_webp(src, dst, quality, max_side)
        elif (vpy := venv_python()) and venv_has_pillow(vpy):
            # 웹용 venv 에 Pillow 가 함께 깔린다 — 시스템 파이썬을 건드리지 않는다
            run([str(vpy), "-c", PILLOW_SNIPPET, str(src), str(dst), str(quality), side],
                timeout=60)
        elif shutil.which("cwebp"):
            cmd = ["cwebp", "-quiet", "-q", str(quality)]
            if max_side:
                # 0 은 "비율 유지". 세로가 긴 화면이 많아 긴 변 기준으로 맞춘다
                cmd += ["-resize", "0", side] if is_portrait(src) else ["-resize", side, "0"]
            run(cmd + [str(src), "-o", str(dst)], timeout=60)
        elif shutil.which("ffmpeg"):
            vf = []
            if max_side:
                vf = ["-vf", f"scale='if(gt(iw,ih),{side},-2)':'if(gt(iw,ih),-2,{side})'"]
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src)]
                + vf + ["-quality", str(quality), str(dst)], timeout=60)
        else:
            return None
    except Exception:
        return None
    if dst.exists() and dst.stat().st_size > 0:
        if dst != src:
            src.unlink(missing_ok=True)
        return dst
    dst.unlink(missing_ok=True)
    return None


def resize_tool() -> str | None:
    """지금 쓸 수 있는 축소 수단 이름. 없으면 None."""
    vpy = venv_python()
    if has_pillow():
        return "pillow"
    if vpy and venv_has_pillow(vpy):
        return "pillow (전용 venv)"
    if shutil.which("cwebp"):
        return "cwebp"
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    return None


def shrink(paths: list[Path], max_side: int = SHOT_MAX_SIDE,
           quality: int = WEBP_QUALITY, keep_format: bool = False) -> dict:
    """이슈 첨부용으로 이미지 긴 변을 줄이고 WebP 로 바꾼다.

    Pillow → sips(macOS) → ffmpeg 순으로 쓸 수 있는 것을 고른다. 세 가지 중
    하나만 있으면 되므로 특정 OS에 묶이지 않는다. 반환은 emit 에 그대로 넘길 dict.
    """
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        return {"ok": False, "code": "file_not_found", "error": f"없는 파일: {missing}"}

    done, method = [], None
    if has_pillow():
        from PIL import Image
        method = "pillow"
        for f in paths:
            im = Image.open(f)
            im.thumbnail((max_side, max_side), Image.LANCZOS)
            im.save(f)
            done.append(str(f))
    elif shutil.which("sips"):
        method = "sips"
        for f in paths:
            run(["sips", "-Z", str(max_side), str(f)])
            done.append(str(f))
    elif shutil.which("ffmpeg"):
        method = "ffmpeg"
        for f in paths:
            tmp = f.with_suffix(".shrink.png")
            run(["ffmpeg", "-y", "-i", str(f), "-vf",
                 f"scale='min({max_side},iw)':-1", str(tmp)])
            if tmp.exists():
                tmp.replace(f)
                done.append(str(f))
    else:
        return {"ok": False, "code": "no_resize_tool",
                "error": "이미지를 줄일 수단이 없습니다",
                "hint": "pip install pillow (권장) 또는 ffmpeg 설치"}

    # 축소만으로는 PNG 가 여전히 무겁다. 첨부·전송이 목적이므로 WebP 로 내보낸다.
    converted, failed_convert = [], False
    if not keep_format:
        for f in [Path(x) for x in done]:
            got = to_webp(f, quality=quality)
            if got is None:
                failed_convert = True
                converted.append(str(f))
            else:
                converted.append(str(got))
        done = converted

    out = {"files": done, "method": method,
           "summary": f"{len(done)}장 축소 ({method}, 긴 변 {max_side}px)"}
    if not keep_format:
        out["format"] = "png(변환 수단 없음)" if failed_convert else "webp"
        out["summary"] += " · WebP" if not failed_convert else " · PNG 유지(변환 수단 없음)"
        if failed_convert:
            out["hint"] = "pip install pillow 또는 cwebp·ffmpeg 를 설치하면 크게 줄어듭니다"
    return out
