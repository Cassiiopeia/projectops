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
AREA_TITLES = {"web": "웹", "android": "Android", "ios": "iOS", "server": "서버",
               "ssh": "SSH", "general": "공통"}


def _cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _render_entry(entry: dict) -> list[str]:
    match = entry["match"]
    lines = [f"### `{entry['id']}` — {entry['title']}", ""]
    if match.get("codes"):
        lines.append("- 코드: " + " · ".join(f"`{c}`" for c in match["codes"]))
    if match.get("keywords"):
        lines.append("- 핵심어: " + ", ".join(match["keywords"]))
    if entry.get("applies_to"):
        applies = entry["applies_to"]
        lines.append("- 해당: " + (", ".join(applies) if isinstance(applies, list) else applies))
    lines += [f"- 증상: {entry['symptom']}", f"- 원인: {entry['cause']}", "- 해결:"]
    lines += [f"  {n}. {f}" for n, f in enumerate(entry["fix"], 1)]
    refs = ", ".join(f"#{r}" for r in entry["refs"]) or "—"
    lines.append(f"- 근거: {refs} · 확인 {entry['verified_at']}")
    if entry.get("see_also"):
        lines.append("- 함께 볼 것: " + ", ".join(f"`{s}`" for s in entry["see_also"]))
    return lines + [""]


def render_markdown(skill_dir: Path) -> str:
    """항목 > 사람용 문서 (영역별 표 + 항목 상세)."""
    rows, _ = troubleshoot.read_entries(skill_dir)
    entries = sorted((e for _, e in rows if not troubleshoot.validate_entry(e)),
                     key=lambda e: (troubleshoot.AREAS.index(e["area"]), e["id"]))
    lines = ["# 공식 트러블슈팅", "",
             "> 생성물이다 — 손으로 고치지 않는다. 원본은 `troubleshooting/<area>/<id>.json`,",
             "> 다시 만들기: `python3 scripts/build_troubleshooting.py skills/<skill>` (레포 루트에서).",
             "> 작성 규칙: `skills/references/memory-principles.md` §6. 실패 응답의 `known_fix` 가 이 항목들의 요약이다.", ""]
    if not entries:
        return "\n".join(lines + ["아직 항목이 없다.", ""])
    for area in troubleshoot.AREAS:
        in_area = [e for e in entries if e["area"] == area]
        if not in_area:
            continue
        lines += [f"## {AREA_TITLES.get(area, area)} (`{area}`)", "",
                  "| id | 제목 | 코드 |", "|---|---|---|"]
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
                     "error": f"{troubleshoot.troubleshooting_dir(skill_dir)} 가 없다",
                     "next": "troubleshooting/<area>/<id>.json 항목을 먼저 만든다"})
    problems = troubleshoot.validate_entries(skill_dir)
    if problems:
        return emit({"ok": False, "code": "invalid_entries", "problems": problems,
                     "summary": f"항목 문제 {len(problems)}건", "next": "항목을 고친 뒤 다시 실행"})
    # 생성물 비교 > 검사만 하거나 쓴다
    outputs = expected_outputs(skill_dir)
    stale = [path for path, text in outputs.items() if _read(path) != text]
    relative = [path.relative_to(skill_dir).as_posix() for path in stale]
    count = len(troubleshoot.entry_files(skill_dir))
    if is_check_only:
        if stale:
            return emit({"ok": False, "code": "stale", "stale": relative,
                         "error": "생성물이 항목과 다르다 (손으로 고쳤거나 다시 만들지 않았다)",
                         "next": f"python3 scripts/build_troubleshooting.py {skill_dir}"})
        return emit({"ok": True, "code": "ok", "entries": count, "summary": f"최신 (항목 {count}건)"})
    for path in stale:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(outputs[path], encoding="utf-8")
    return emit({"ok": True, "code": "ok", "entries": count, "written": relative,
                 "summary": f"항목 {count}건, 다시 쓴 파일 {len(relative)}개"})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build_troubleshooting", description=__doc__.splitlines()[0])
    parser.add_argument("skill_dir", help="스킬 폴더 (예: skills/pro-launch)")
    parser.add_argument("--check", action="store_true", help="쓰지 않고 최신인지만 검사")
    args = parser.parse_args(argv)
    return run(Path(args.skill_dir).resolve(), args.check)


if __name__ == "__main__":
    sys.exit(main())
