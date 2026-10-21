#!/usr/bin/env python3
"""공식 트러블슈팅 생성물 만들기: 항목 검증 > troubleshooting/index.json + references/troubleshooting.md (#889).

    python3 scripts/build_troubleshooting.py skills/pro-launch           # 생성
    python3 scripts/build_troubleshooting.py skills/pro-launch --check   # 쓰지 않고 최신인지만 (아니면 종료코드 1)

원본은 항목 파일(troubleshooting/<area>/<id>.json) 하나뿐이다. 두 생성물을 손으로 고치지 않는다.
출력: JSON 한 줄 (ok/code/summary/next). 다른 스킬도 자기 폴더를 넘겨 같은 스크립트를 쓴다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import troubleshoot  # noqa: E402
from common.emit import emit  # noqa: E402

DOC_PATH = Path("references") / "troubleshooting.md"
AREA_TITLES = {"web": "Web", "android": "Android", "ios": "iOS", "server": "Server",
               "ssh": "SSH", "general": "General"}


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _render_entry(entry: dict) -> list[str]:
    match = entry["match"]
    lines = [f"### `{entry['id']}` — {entry['title']}", ""]
    if match.get("codes"):
        lines.append("- Codes: " + " · ".join(f"`{c}`" for c in match["codes"]))
    if match.get("keywords"):
        lines.append("- Keywords: " + ", ".join(match["keywords"]))
    if entry.get("applies_to"):
        applies = entry["applies_to"]
        lines.append("- Applies to: " + (", ".join(applies) if isinstance(applies, list) else applies))
    lines += [f"- Symptom: {entry['symptom']}", f"- Cause: {entry['cause']}", "- Fix:"]
    lines += [f"  {n}. {f}" for n, f in enumerate(entry["fix"], 1)]
    refs = ", ".join(f"#{r}" for r in entry["refs"]) or "—"
    lines.append(f"- Refs: {refs} · verified {entry['verified_at']}")
    if entry.get("see_also"):
        lines.append("- See also: " + ", ".join(f"`{s}`" for s in entry["see_also"]))
    return lines + [""]


def render_markdown(skill_dir: Path) -> str:
    """항목 > 사람용 문서 (영역별 표 + 항목 상세)."""
    rows, _ = troubleshoot.read_entries(skill_dir)
    entries = sorted((e for _, e in rows if not troubleshoot.validate_entry(e)),
                     key=lambda e: (troubleshoot.AREAS.index(e["area"]), e["id"]))
    lines = ["# Official troubleshooting", "",
             "> Generated file — do not edit by hand. Source: `troubleshooting/<area>/<id>.json`.",
             "> Rebuild: `python3 scripts/build_troubleshooting.py skills/<skill>` (from the repo root).",
             "> Writing rules: `skills/references/memory-principles.md` §6. The `known_fix` in failure responses summarizes these entries.", ""]
    if not entries:
        return "\n".join(lines + ["No entries yet.", ""])
    for area in troubleshoot.AREAS:
        in_area = [e for e in entries if e["area"] == area]
        if not in_area:
            continue
        lines += [f"## {AREA_TITLES.get(area, area)} (`{area}`)", "",
                  "| id | Title | Codes |", "|---|---|---|"]
        lines += [f"| `{e['id']}` | {_cell(e['title'])} | "
                  f"{' · '.join(f'`{c}`' for c in e['match'].get('codes', [])) or '—'} |" for e in in_area]
        lines.append("")
        for e in in_area:
            lines += _render_entry(e)
    return "\n".join(lines).rstrip("\n") + "\n"


def expected_outputs(skill_dir: Path) -> dict[Path, str]:
    """생성물 경로 > 내용."""
    return {troubleshoot.index_path(skill_dir): troubleshoot.render_index(troubleshoot.build_index(skill_dir)),
            skill_dir / DOC_PATH: render_markdown(skill_dir)}


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def run(skill_dir: Path, is_check_only: bool) -> int:
    # 입력 검증 (폴더, 항목 스키마)
    if not troubleshoot.troubleshooting_dir(skill_dir).is_dir():
        return emit({"ok": False, "code": "no_troubleshooting_dir",
                     "error": f"{troubleshoot.troubleshooting_dir(skill_dir)} does not exist",
                     "next": "Create troubleshooting/<area>/<id>.json entries first"})
    problems = troubleshoot.validate_entries(skill_dir)
    if problems:
        return emit({"ok": False, "code": "invalid_entries", "problems": problems,
                     "summary": f"{len(problems)} entry problems", "next": "Fix the entries and run again"})
    # 생성물 비교 > 검사만 하거나 쓴다
    outputs = expected_outputs(skill_dir)
    stale = [path for path, text in outputs.items() if _read(path) != text]
    relative = [path.relative_to(skill_dir).as_posix() for path in stale]
    count = len(troubleshoot.entry_files(skill_dir))
    if is_check_only:
        if stale:
            return emit({"ok": False, "code": "stale", "stale": relative,
                         "error": "Generated files differ from the entries (edited by hand or not regenerated)",
                         "next": f"python3 scripts/build_troubleshooting.py {skill_dir}"})
        return emit({"ok": True, "code": "ok", "entries": count, "summary": f"Up to date ({count} entries)"})
    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[path], encoding="utf-8")
    return emit({"ok": True, "code": "ok", "entries": count, "written": relative,
                 "summary": f"{count} entries, {len(relative)} files rewritten"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_troubleshooting", description="Build the official troubleshooting outputs: validate entries > troubleshooting/index.json + references/troubleshooting.md")
    parser.add_argument("skill_dir", help="skill folder (e.g. skills/pro-launch)")
    parser.add_argument("--check", action="store_true", help="only check that outputs are up to date, without writing")
    args = parser.parse_args(argv)
    return run(Path(args.skill_dir).resolve(), args.check)


if __name__ == "__main__":
    sys.exit(main())
