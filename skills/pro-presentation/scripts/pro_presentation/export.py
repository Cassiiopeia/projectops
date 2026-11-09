"""export: 덱 > exports/v<n>/ (덮어쓰지 않음, 열린 PPT 잠금과 무관)
흐름: 서버 확인 > 브라우저로 장 PNG·조각 값(layout.json)·PDF > PPT 조립 > 검수(글자 대조 · 그림 부분 · 글꼴 · 되그리기 대조)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from common.emit import emit
from common.state import venv_python

from pro_presentation.config import option_value
from pro_presentation.deck import load_deck
from pro_presentation.session import _spawn_server, read_server_info
from pro_presentation.settings import EXPORTS_DIR_NAME

HERE = Path(__file__).resolve().parent
WORKER_SCRIPT = HERE / "export_worker.py"
BUILDER_SCRIPT = HERE / "pptx_builder.py"
PIP_TIMEOUT_SECONDS = 300
RENDER_BACK_TIMEOUT_SECONDS = 300
VERSION_PATTERN = re.compile(r"^v(\d+)$")
FONT_DIRECTORIES = (Path.home() / "Library/Fonts", Path("/Library/Fonts"), Path("/System/Library/Fonts"),
                    Path("/usr/share/fonts"), Path.home() / ".fonts", Path("C:/Windows/Fonts"))
GENERIC_FONTS = {"sans-serif", "serif", "monospace", "-apple-system", "system-ui", ""}
LIBREOFFICE_NAMES = ("soffice", "libreoffice")
MAC_LIBREOFFICE = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")


def find_libreoffice() -> str | None:
    for name in LIBREOFFICE_NAMES:
        if shutil.which(name):
            return shutil.which(name)
    return str(MAC_LIBREOFFICE) if MAC_LIBREOFFICE.is_file() else None


def next_version_dir(deck_dir: Path) -> Path:
    exports = deck_dir / EXPORTS_DIR_NAME
    numbers = [int(match.group(1)) for path in exports.glob("v*") if (match := VERSION_PATTERN.match(path.name))] \
        if exports.is_dir() else []
    target = exports / f"v{max(numbers, default=0) + 1}"
    target.mkdir(parents=True)
    return target


def _run_json(command: list[str], timeout_seconds: int) -> dict:
    try:
        output = subprocess.run(command, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        return {"ok": False, "code": "timeout", "error": f"Took over {timeout_seconds} seconds"}
    try:
        return json.loads(output.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return {"ok": False, "code": "worker_failed", "error": output.stderr.strip()[-600:] or "No result"}


def python_with_pptx() -> str | None:
    """python-pptx 가 있는 파이썬: 현재 > pro-launch 가상환경(없으면 설치 1회)"""
    candidates = [sys.executable] + ([str(venv_python())] if venv_python() else [])
    for interpreter in candidates:
        if subprocess.run([interpreter, "-c", "import pptx"], capture_output=True).returncode == 0:
            return interpreter
    if venv_python():
        subprocess.run([str(venv_python()), "-m", "pip", "install", "--quiet", "python-pptx"],
                       capture_output=True, encoding="utf-8", errors="replace", timeout=PIP_TIMEOUT_SECONDS)
        if subprocess.run([str(venv_python()), "-c", "import pptx"], capture_output=True).returncode == 0:
            return str(venv_python())
    return None


def find_missing_fonts(layout: dict) -> list[str]:
    """쓴 글꼴 중 이 컴퓨터 글꼴 폴더에 파일이 안 보이는 것 (받는 쪽에도 없을 수 있음)"""
    families = {piece.get("font_family", "").split(",")[0].strip().strip("\"'")
                for slide in layout["slides"] for piece in slide["pieces"] if piece["kind"] in ("text", "title", "table")}
    installed = " ".join(path.stem.lower().replace(" ", "") for directory in FONT_DIRECTORIES if directory.is_dir()
                         for path in directory.rglob("*") if path.suffix.lower() in (".ttf", ".otf", ".ttc", ".woff2"))
    return sorted(family for family in families - GENERIC_FONTS if family.lower().replace(" ", "") not in installed)


def compare_render_back(pptx_file: Path, out_dir: Path, slide_count: int) -> dict:
    """LibreOffice 로 PPT 를 다시 그려 HTML 캡처와 장마다 비교 (없으면 건너뜀)"""
    libreoffice = find_libreoffice()
    if libreoffice is None:
        return {"render_back": "skipped_no_libreoffice"}
    back_dir = out_dir / "render-back"
    back_dir.mkdir(exist_ok=True)
    subprocess.run([libreoffice, "--headless", "--convert-to", "pdf", "--outdir", str(back_dir), str(pptx_file)],
                   capture_output=True, encoding="utf-8", errors="replace", timeout=RENDER_BACK_TIMEOUT_SECONDS)
    pdf_files = list(back_dir.glob("*.pdf"))
    if not pdf_files or shutil.which("pdftoppm") is None:
        return {"render_back": "failed"}
    subprocess.run(["pdftoppm", "-png", "-scale-to-x", "960", "-scale-to-y", "540", str(pdf_files[0]), str(back_dir / "back")],
                   capture_output=True, encoding="utf-8", errors="replace", timeout=RENDER_BACK_TIMEOUT_SECONDS)
    return {"render_back": "done", "render_back_dir": str(back_dir),
            "render_back_pages": len(list(back_dir.glob("back*.png"))), "slide_count": slide_count}


def verify(layout: dict, built: dict, out_dir: Path, pptx_file: Path) -> dict:
    """장마다 HTML 조각 글이 PPT 글에 다 있는지 + 그림으로 들어간 부분 + 글꼴 + 되그리기"""
    built_by_id = {slide["id"]: slide for slide in built["slides"]}
    slides = []
    for slide in layout["slides"]:
        ppt_text = "\n".join(built_by_id.get(slide["id"], {}).get("texts", []))
        expected = [line.strip() for piece in slide["pieces"] for line in (piece.get("lines") or []) if line.strip()]
        expected += [cell for piece in slide["pieces"] for row in (piece.get("rows") or []) for cell in row if cell]
        missing = [line for line in expected if line not in ppt_text]
        slides.append({"id": slide["id"], "text_match": not missing, "missing_text": missing[:5],
                       "picture_parts": len(slide["pictures"]),
                       "missing_images": built_by_id.get(slide["id"], {}).get("missing_images", [])})
    report = {"slides": slides, "missing_fonts": find_missing_fonts(layout),
              **compare_render_back(pptx_file, out_dir, len(slides))}
    (out_dir / "verify.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def cmd_export(args) -> int:
    deck_dir = Path(args.deck).expanduser().resolve()
    deck = load_deck(deck_dir)
    if not deck["slides"]:
        return emit({"ok": False, "code": "empty_deck", "error": "deck.json lists no slides"})
    formats = [name for name, wanted in (("pdf", args.pdf), ("pptx", args.pptx)) if wanted] \
        or option_value(deck_dir, "export_formats")
    info = read_server_info(deck_dir) or _spawn_server(deck_dir, option_value(deck_dir, "idle_timeout_minutes"))
    if info is None:
        return emit({"ok": False, "code": "server_failed", "error": "The deck server did not start", "next": "start --deck D"})
    out_dir = next_version_dir(deck_dir)
    base_name = re.sub(r"[\\/:*?\"<>|]+", "_", deck["title"]).strip() or "deck"
    pdf_file = out_dir / f"{base_name}.pdf"
    job = {"base_url": f"http://127.0.0.1:{info['port']}", "key": info["key"], "out_dir": str(out_dir),
           "pdf": str(pdf_file) if "pdf" in formats else None,
           "slides": [{"id": slide["id"], "number": slide["number"]} for slide in deck["slides"] if slide["html"] is not None]}
    (out_dir / "job.json").write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    worker = _run_json([str(venv_python() or sys.executable), str(WORKER_SCRIPT), "--job", str(out_dir / "job.json")], args.timeout)
    if not worker.get("ok"):
        return emit({**worker, "ok": False, "out_dir": str(out_dir),
                     "next": "Run launch_cli.py web setup if the browser is missing, then export again"})
    result = {"version": out_dir.name, "out_dir": str(out_dir), "pdf": str(pdf_file) if "pdf" in formats else None}
    if "pptx" in formats:
        interpreter = python_with_pptx()
        if interpreter is None:
            return emit({"ok": False, "code": "tool_missing", "error": "python-pptx is not available", **result,
                         "next": "pip install python-pptx in the pro-launch venv, then export again"})
        pptx_file = out_dir / f"{base_name}.pptx"
        build_job = {"out_dir": str(out_dir), "deck_dir": str(deck_dir), "pptx": str(pptx_file),
                     "scripts": {slide["id"]: slide["script"] for slide in deck["slides"]}}
        (out_dir / "build.json").write_text(json.dumps(build_job, ensure_ascii=False), encoding="utf-8")
        built = _run_json([interpreter, str(BUILDER_SCRIPT), "--job", str(out_dir / "build.json")], args.timeout)
        if not built.get("ok"):
            return emit({**built, "ok": False, **result})
        layout = json.loads((out_dir / "layout.json").read_text(encoding="utf-8"))
        report = verify(layout, built, out_dir, pptx_file)
        mismatched = [slide["id"] for slide in report["slides"] if not slide["text_match"]]
        pictures = sum(slide["picture_parts"] for slide in report["slides"])
        result.update({"pptx": str(pptx_file), "verify": str(out_dir / "verify.json"), "text_mismatch_slides": mismatched,
                       "picture_parts": pictures, "missing_fonts": report["missing_fonts"],
                       "render_back": report["render_back"]})
    summary = f"Exported {out_dir.name}: {', '.join(formats)}"
    if result.get("pptx"):
        summary += f"; text match {len(deck['slides']) - len(result['text_mismatch_slides'])}/{len(deck['slides'])}, picture parts {result['picture_parts']}"
    return emit({"summary": summary, **result,
                 "next": ("Open verify.json and look at the slide PNGs (and render-back images if present) before "
                          "telling the user it is done. Name the version to the user")})
