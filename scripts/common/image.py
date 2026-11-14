"""Shrinking captures — WebP conversion and long-side downscale (shared by pro-launch and pro-agent-test, #629).

Screen captures get heavy as they pile up. **Two** things need shrinking, and the methods differ (measured).

  file size      →  convert to WebP.  495KB → 34KB (-93%)
  session tokens →  **reduce resolution.** Format has no effect on tokens.
                1080x2400 as is costs 1,473 tokens; long side 1200 costs 864.

So we do **both together**.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from common.proc import run
from common.state import venv_python

WEBP_QUALITY = 75
SHOT_MAX_SIDE = 1200          # small text still readable. Cuts tokens by about 41%


def has_pillow() -> bool:
    try:
        import PIL  # noqa: F401
        return True
    except ImportError:
        return False


# Conversion run by the venv Python. Args: src dst quality max_side (0 = no downscale)
PILLOW_SNIPPET = (
    "import sys\n"
    "from PIL import Image\n"
    "src, dst, q, side = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])\n"
    "im = Image.open(src)\n"
    "if side:\n"
    "    im.thumbnail((side, side), Image.LANCZOS)\n"
    "im.save(dst, 'WEBP', quality=q, method=4)\n"
)


# Args: src dst rects_json. Prints one JSON line (checks before writing; no file on failure)
PILLOW_MASK_SNIPPET = (
    "import json, sys\n"
    "from PIL import Image, ImageDraw\n"
    "src, dst, rects = sys.argv[1], sys.argv[2], json.loads(sys.argv[3])\n"
    "im = Image.open(src)\n"
    "if getattr(im, 'is_animated', False):\n"
    "    print(json.dumps({'error': 'animated_not_supported'})); sys.exit(0)\n"
    "w, h = im.size\n"
    "if any(x >= w or y >= h for x, y, _, _ in rects):\n"
    "    print(json.dumps({'error': 'bad_rect', 'width': w, 'height': h})); sys.exit(0)\n"
    "im = im.convert('RGB')\n"
    "draw = ImageDraw.Draw(im)\n"
    "for x, y, rw, rh in rects:\n"
    "    draw.rectangle([x, y, x + rw - 1, y + rh - 1], fill=(0, 0, 0))\n"
    "im.save(dst)\n"
    "print(json.dumps({'width': w, 'height': h}))\n"
)


class ImageMaskError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def mask_regions(src: Path, rects: list[list[int]], dst: Path) -> dict:
    """Black out image regions and save as a new file > {width, height}. No blur, since blur can be reversed"""
    interpreter = sys.executable if has_pillow() else None
    if interpreter is None and (vpy := venv_python()) and venv_has_pillow(vpy):
        interpreter = str(vpy)
    if interpreter is None:
        raise ImageMaskError("pillow_missing", "Pillow is required to mask images")
    output = subprocess.run([interpreter, "-c", PILLOW_MASK_SNIPPET, str(src), str(dst), json.dumps(rects)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    try:
        result = json.loads(output.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        raise ImageMaskError("mask_failed", output.stderr.strip()[-300:] or "Could not read this image") from None
    if result.get("error") == "bad_rect":
        raise ImageMaskError("bad_rect", f"A rectangle starts outside the image ({result['width']}x{result['height']})")
    if result.get("error"):
        raise ImageMaskError(result["error"], "Animated images cannot be masked; fix the source and record again")
    return result


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
    """cwebp marks keep-aspect as 0, so we need to know which side is longer."""
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
    """Convert an image to WebP and, if max_side is set, fit the long side to it.

    Uses whatever is available in order: Pillow (system) → Pillow (dedicated venv) → cwebp → ffmpeg.
    **Having none of them never blocks screenshots** — the original stays, just a bit heavier.
    macOS sips cannot write WebP, so it is not in the ladder (measured).
    """
    if src.suffix.lower() == ".webp" and not max_side:
        return src
    dst = src.with_suffix(".webp")
    side = str(max_side or 0)
    try:
        if has_pillow():
            _pillow_webp(src, dst, quality, max_side)
        elif (vpy := venv_python()) and venv_has_pillow(vpy):
            # Pillow is installed with the web venv — the system Python is left alone
            run([str(vpy), "-c", PILLOW_SNIPPET, str(src), str(dst), str(quality), side],
                timeout=60)
        elif shutil.which("cwebp"):
            cmd = ["cwebp", "-quiet", "-q", str(quality)]
            if max_side:
                # 0 means "keep aspect". Many screens are tall, so fit by the long side
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
    """Name of the downscale tool available now. None if none."""
    vpy = venv_python()
    if has_pillow():
        return "pillow"
    if vpy and venv_has_pillow(vpy):
        return "pillow (dedicated venv)"
    if shutil.which("cwebp"):
        return "cwebp"
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    return None


def shrink(paths: list[Path], max_side: int = SHOT_MAX_SIDE,
           quality: int = WEBP_QUALITY, keep_format: bool = False) -> dict:
    """Shrink the long side of an image for issue attachments and convert to WebP.

    Picks whatever is available: Pillow → sips (macOS) → ffmpeg. Any one of the three
    is enough, so it is not tied to an OS. Returns a dict to pass straight to emit.
    """
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        return {"ok": False, "code": "file_not_found", "error": f"files not found: {missing}"}
    # Reject directories and negative sizes before reaching the tool — JSON error instead of a traceback (#705)
    not_files = [str(p) for p in paths if not p.is_file()]
    if not_files:
        return {"ok": False, "code": "not_a_file", "error": f"not a file: {not_files}",
                "next": "pass image file paths directly"}
    if max_side < 0:
        return {"ok": False, "code": "bad_args", "error": f"--max-side must be 0 or greater ({max_side})",
                "next": "0 keeps the original size"}

    done, method = [], None
    if has_pillow():
        from PIL import Image
        method = "pillow"
        for f in paths:
            try:
                with Image.open(f) as im:
                    im.load()
                    if max_side:
                        im.thumbnail((max_side, max_side), Image.LANCZOS)
                    im.save(f)
            except Exception as e:   # not an image file (UnidentifiedImageError etc.)
                return {"ok": False, "code": "image_unreadable",
                        "error": f"cannot open the image: {f} ({type(e).__name__})",
                        "files": done, "next": "check that it is an image file (png, jpg, webp)"}
            done.append(str(f))
    elif shutil.which("sips"):
        method = "sips"
        for f in paths:
            if max_side:
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
                "error": "no tool available to shrink images",
                "hint": "pip install pillow (recommended) or install ffmpeg"}

    # Downscaling alone still leaves PNG heavy. The goal is attaching/sending, so export as WebP.
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
           "summary": f"shrank {len(done)} image(s) ({method}, long side {max_side}px)"}
    if not keep_format:
        out["format"] = "png (no converter available)" if failed_convert else "webp"
        out["summary"] += " · WebP" if not failed_convert else " · kept PNG (no converter available)"
        if failed_convert:
            out["hint"] = "install pillow (pip install pillow), cwebp or ffmpeg to make files much smaller"
    return out
