"""export: deck > exports/v<n>/ (never overwrites, unaffected by an open PPT's lock)
Flow: check server > browser renders slide PNG, piece values (layout.json), PDF > pick converter > build PPT > review (text match · image parts · fonts · redraw comparison)
2 converters: built-in (pptx_builder.py, piece values > python-pptx) · dom-to-pptx (dom_to_pptx.py, DOM > PPT inside the browser)
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from common.emit import emit
from common.state import base_dir, venv_python

from pro_presentation.config import option_value
from pro_presentation.deck import load_deck
from pro_presentation.dom_to_pptx import CONVERTER_NAME as CONVERTER_DOM, ensure_bundle
from pro_presentation.session import _spawn_server, read_server_info
from pro_presentation.settings import EXPORTS_DIR_NAME

HERE = Path(__file__).resolve().parent
WORKER_SCRIPT = HERE / "export_worker.py"
BUILDER_SCRIPT = HERE / "pptx_builder.py"
DOM_CONVERTER_SCRIPT = HERE / "dom_to_pptx.py"
CONVERTER_AUTO = "auto"
CONVERTER_BUILTIN = "builtin"
# Downloaded dom-to-pptx bundle location (~/.projectops/presentation/vendor/)
VENDOR_RELATIVE = Path("presentation") / "vendor"
WHITESPACE_PATTERN = re.compile(r"\s+")
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
    """Python with python-pptx: current > pro-launch venv (installs once if missing)"""
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
    """Fonts used that have no file in this computer's font folders (the recipient may lack them too)"""
    families = {piece.get("font_family", "").split(",")[0].strip().strip("\"'")
                for slide in layout["slides"] for piece in slide["pieces"] if piece["kind"] in ("text", "title", "table")}
    installed = " ".join(path.stem.lower().replace(" ", "") for directory in FONT_DIRECTORIES if directory.is_dir()
                         for path in directory.rglob("*") if path.suffix.lower() in (".ttf", ".otf", ".ttc", ".woff2"))
    return sorted(family for family in families - GENERIC_FONTS if family.lower().replace(" ", "") not in installed)


def compare_render_back(pptx_file: Path, out_dir: Path, slide_count: int) -> dict:
    """Redraw the PPT with LibreOffice and compare with the HTML capture per slide (skipped if absent)"""
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


def unmapped_styles(layout: dict) -> list[str]:
    """Slides with shapes the built-in converter cannot carry ('slide 3: shadow, table style')"""
    return [f"slide {slide['number']}: {', '.join(slide['unmapped'])}" for slide in layout["slides"] if slide.get("unmapped")]


def build_with_dom_to_pptx(job: dict, out_dir: Path, timeout_seconds: int) -> dict:
    """Prepare bundle (downloaded or download now) > convert in the browser. ok False on failure (caller falls back to the built-in converter)"""
    bundle, bundle_state = ensure_bundle(base_dir() / VENDOR_RELATIVE)
    if bundle is None:
        return {"ok": False, "code": "converter_unavailable", "error": f"dom-to-pptx bundle: {bundle_state}"}
    job_file = out_dir / "convert.json"
    job_file.write_text(json.dumps({**job, "bundle": str(bundle)}, ensure_ascii=False), encoding="utf-8")
    return _run_json([str(venv_python() or sys.executable), str(DOM_CONVERTER_SCRIPT), "--job", str(job_file)], timeout_seconds)


def build_with_builtin(job: dict, out_dir: Path, deck_dir: Path, timeout_seconds: int) -> dict:
    interpreter = python_with_pptx()
    if interpreter is None:
        return {"ok": False, "code": "tool_missing", "error": "python-pptx is not available",
                "next": "pip install python-pptx in the pro-launch venv, then export again"}
    job_file = out_dir / "build.json"
    job_file.write_text(json.dumps({"out_dir": str(out_dir), "deck_dir": str(deck_dir), "pptx": job["pptx"],
                                    "scripts": job["scripts"]}, ensure_ascii=False), encoding="utf-8")
    return {"converter": CONVERTER_BUILTIN, **_run_json([interpreter, str(BUILDER_SCRIPT), "--job", str(job_file)], timeout_seconds)}


def build_pptx(requested: str, layout: dict, job: dict, out_dir: Path, deck_dir: Path, timeout_seconds: int) -> dict:
    """Pick converter: auto uses dom-to-pptx only when the built-in converter cannot carry some shapes (falls back to built-in on failure)"""
    unmapped = unmapped_styles(layout)
    if requested == CONVERTER_BUILTIN or (requested == CONVERTER_AUTO and not unmapped):
        return {**build_with_builtin(job, out_dir, deck_dir, timeout_seconds), "unmapped_styles": unmapped}
    built = build_with_dom_to_pptx(job, out_dir, timeout_seconds)
    if built.get("ok") or requested == CONVERTER_DOM:
        return {**built, "converter": CONVERTER_DOM, "unmapped_styles": unmapped}
    fallback = build_with_builtin(job, out_dir, deck_dir, timeout_seconds)
    return {**fallback, "unmapped_styles": unmapped,
            "converter_fallback": f"{built.get('code')}: {built.get('error')}"}


def verify(layout: dict, built: dict, out_dir: Path, pptx_file: Path) -> dict:
    """Per slide: all HTML piece text present in the PPT text + parts placed as images + fonts + redraw"""
    built_by_id = {slide["id"]: slide for slide in built["slides"]}
    is_dom_converter = built.get("converter") == CONVERTER_DOM
    # dom-to-pptx may break lines differently from HTML > compare with whitespace removed
    normalize = (lambda text: WHITESPACE_PATTERN.sub("", text)) if is_dom_converter else (lambda text: text)
    slides = []
    for slide in layout["slides"]:
        ppt_text = normalize("\n".join(built_by_id.get(slide["id"], {}).get("texts", [])))
        expected = [line.strip() for piece in slide["pieces"] for line in (piece.get("lines") or []) if line.strip()]
        expected += [cell for piece in slide["pieces"] for row in (piece.get("rows") or []) for cell in row if cell]
        missing = [line for line in expected if normalize(line) not in ppt_text]
        # dom-to-pptx carries parts without data-pp as PPT objects too (not as images)
        slides.append({"id": slide["id"], "text_match": not missing, "missing_text": missing[:5],
                       "picture_parts": 0 if is_dom_converter else len(slide["pictures"]),
                       "missing_images": built_by_id.get(slide["id"], {}).get("missing_images", [])})
    report = {"converter": built.get("converter"), "converter_fallback": built.get("converter_fallback"),
              "unmapped_styles": built.get("unmapped_styles", []),
              "slides": slides, "missing_fonts": find_missing_fonts(layout),
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
        pptx_file = out_dir / f"{base_name}.pptx"
        layout = json.loads((out_dir / "layout.json").read_text(encoding="utf-8"))
        build_job = {"base_url": job["base_url"], "key": job["key"], "slides": job["slides"], "pptx": str(pptx_file),
                     "scripts": {slide["id"]: slide["script"] for slide in deck["slides"]}}
        built = build_pptx(getattr(args, "converter", None) or option_value(deck_dir, "pptx_converter"),
                           layout, build_job, out_dir, deck_dir, args.timeout)
        if not built.get("ok"):
            return emit({**built, "ok": False, **result})
        report = verify(layout, built, out_dir, pptx_file)
        mismatched = [slide["id"] for slide in report["slides"] if not slide["text_match"]]
        pictures = sum(slide["picture_parts"] for slide in report["slides"])
        result.update({"pptx": str(pptx_file), "converter": report["converter"],
                       "converter_fallback": report["converter_fallback"], "unmapped_styles": report["unmapped_styles"],
                       "verify": str(out_dir / "verify.json"), "text_mismatch_slides": mismatched,
                       "picture_parts": pictures, "missing_fonts": report["missing_fonts"],
                       "render_back": report["render_back"]})
    summary = f"Exported {out_dir.name}: {', '.join(formats)}"
    if result.get("pptx"):
        summary += (f" ({result['converter']}); text match {len(deck['slides']) - len(result['text_mismatch_slides'])}"
                    f"/{len(deck['slides'])}, picture parts {result['picture_parts']}")
        if result["converter_fallback"]:
            summary += "; dom-to-pptx was not available, so the built-in converter was used"
    return emit({"summary": summary, **result,
                 "next": ("Open verify.json and look at the slide PNGs (and render-back images if present) before "
                          "telling the user it is done. Name the version to the user")})
