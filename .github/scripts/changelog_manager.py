#!/usr/bin/env python3
"""
changelog_manager.py

통합 체인지로그 매니저 스크립트.

서브커맨드:
  - update-from-summary: CodeRabbit Summary Markdown을 파싱하여 CHANGELOG.json 갱신
  - generate-md        : CHANGELOG.json을 기반으로 CHANGELOG.md 재생성
  - export             : 특정 버전의 릴리즈 노트를 생성하여 stdout 또는 파일로 저장
  - classify-bump      : 커밋 제목 목록으로 semver 승격 폭(major/minor/patch) 판단

사용 예:
  python3 changelog_manager.py update-from-summary
  python3 changelog_manager.py generate-md
  python3 changelog_manager.py export --version 0.0.2 --output release_notes.txt

입력 파일:
  - pr_body.md: GitHub PR body (Markdown 형식)
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import traceback


# ----------------------------- 공통 유틸 -----------------------------

def _normalize_text(text: str) -> str:
    """텍스트 정규화: HTML 엔티티 디코딩 및 공백 정리."""
    return html.unescape(text).strip()


def _clean_summary_noise(text: str) -> str:
    """
    Summary 텍스트에서 불필요한 노이즈 제거.

    제거 대상:
    1. HTML 주석 (<!-- ... -->)
    2. CodeRabbit Tip 메시지
    3. 남은 HTML 태그
    4. 연속된 빈 줄
    """
    if not text:
        return text

    # 1. HTML 주석 제거
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)

    # 2. CodeRabbit Tip 줄 제거
    text = re.sub(r'^.*?✏️\s*Tip:.*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'<sub>.*?Tip:.*?</sub>', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'^\s*Tip:.*$', '', text, flags=re.MULTILINE | re.IGNORECASE)

    # 3. 남은 HTML 태그 제거
    text = re.sub(r'<[^>]+>', '', text)

    # 4. 연속된 빈 줄 정리 (3개 이상 → 2개)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def _make_safe_key(title: str, idx: int) -> str:
    """카테고리 제목을 안전한 키로 변환."""
    safe_key = re.sub(r'[^a-zA-Z0-9가-힣]', '_', title.lower()).strip('_')
    return safe_key if safe_key else f"category_{idx}"


# ----------------------- Markdown 파서 (통합) -----------------------

def _parse_summary_markdown(md_content: str) -> dict:
    """
    Markdown 형식의 CodeRabbit Summary 파싱.

    3단계 폴백 전략:
    1. 정밀 파싱 (현재 CodeRabbit 형식)
    2. 관대한 파싱 (형식 변형 대응)
    3. 휴리스틱 파싱 (최후 수단)

    예상 형식:
    ## Summary by CodeRabbit

    * **버그 수정**
      * OCR 입력 처리 개선
      * 빈 콘텐츠 응답 오류 감지 강화

    * **Chores**
      * 버전 0.1.39로 업그레이드
    """
    # 1단계: 정밀 파싱
    detected = _parse_markdown_precise(md_content)
    if detected:
        print("  → 정밀 파서 성공")
        return detected

    # 2단계: 관대한 파싱
    detected = _parse_markdown_lenient(md_content)
    if detected:
        print("  → 관대한 파서 성공")
        return detected

    # 3단계: 휴리스틱 파싱
    detected = _parse_markdown_heuristic(md_content)
    if detected:
        print("  → 휴리스틱 파서 성공")
    return detected


def _parse_markdown_precise(md_content: str) -> dict:
    """
    정밀 파서: 현재 CodeRabbit 형식에 최적화.

    형식: * **카테고리**\n  * 항목
    """
    detected: dict[str, dict] = {}

    # 패턴: * **카테고리** (bold, 들여쓰기 2칸)
    pattern = r'\*\s*\*\*(.+?)\*\*\s*\n((?:\s{2}\*\s+.+(?:\n|$))*)'
    matches = re.findall(pattern, md_content, re.MULTILINE)

    for idx, (category_title, items_text) in enumerate(matches):
        category_title = category_title.strip()

        # 항목 추출: "  * 항목 내용"
        items = re.findall(r'\s{2}\*\s+(.+)', items_text)
        items = [item.strip() for item in items if item.strip()]

        if not category_title and not items:
            continue

        safe_key = _make_safe_key(category_title, idx)
        detected[safe_key] = {
            'title': category_title,
            'items': items,
        }

    return detected


def _parse_markdown_lenient(md_content: str) -> dict:
    """
    관대한 파서: 형식 변형에 대응.

    지원:
    - 들여쓰기 1~8칸 (탭 포함)
    - bold 선택적 (**제목** 또는 제목)
    - 다양한 리스트 마커 (*, -, +)
    """
    content = md_content.replace('\t', '    ')
    detected: dict[str, dict] = {}

    # 패턴: 카테고리 + 중첩 항목
    pattern = r'(?:^|\n)([\*\-\+])\s*(\*\*)?([^\*\n]+?)(\*\*)?\s*\n((?:(?:^|\n)\s{1,8}[\*\-\+]\s+.+)*)'
    matches = re.findall(pattern, content, re.MULTILINE)

    for idx, (marker, bold_start, category_title, bold_end, items_text) in enumerate(matches):
        category_title = category_title.strip()

        # 항목 추출
        items = re.findall(r'(?:^|\n)\s{1,8}[\*\-\+]\s+(.+)', items_text, re.MULTILINE)
        items = [item.strip() for item in items if item.strip()]

        if not category_title and not items:
            continue

        # 너무 긴 제목은 카테고리가 아님
        if len(category_title) > 100:
            continue

        safe_key = _make_safe_key(category_title, idx)
        detected[safe_key] = {
            'title': category_title,
            'items': items,
        }

    return detected


def _parse_markdown_heuristic(md_content: str) -> dict:
    """
    휴리스틱 파서: 줄 단위로 카테고리/항목 추론.

    규칙:
    1. Bold 텍스트(**...**) → 카테고리
    2. 들여쓰기 있는 줄 → 항목
    """
    lines = md_content.split('\n')
    detected: dict[str, dict] = {}
    current_key = None

    for line in lines:
        stripped = line.strip()

        if not stripped or stripped.startswith('<!--') or stripped.startswith('##'):
            continue

        # Bold 텍스트 → 카테고리
        bold_match = re.search(r'\*\*([^\*]+)\*\*', stripped)
        if bold_match:
            title = bold_match.group(1).strip()
            title = re.sub(r'^[\*\-\+\d\.]+\s*', '', title).strip()

            if title and len(title) < 100:
                current_key = _make_safe_key(title, len(detected))
                detected[current_key] = {'title': title, 'items': []}
            continue

        # 들여쓰기 있는 줄 → 항목
        if line.startswith((' ', '\t')) and stripped:
            item = re.sub(r'^[\*\-\+\d\.]+\s*', '', stripped).strip()
            item = re.sub(r'<[^>]+>', '', item).strip()

            if current_key and item and len(item) > 3:
                detected[current_key]['items'].append(item)

    # 빈 카테고리 제거
    return {k: v for k, v in detected.items() if v.get('items')}


# ------------------------ 서브커맨드 구현부 ------------------------

def cmd_update_from_summary() -> int:
    """pr_body.md에서 Markdown을 파싱하여 CHANGELOG.json 갱신."""
    version = os.environ.get('VERSION')
    project_type = os.environ.get('PROJECT_TYPE')
    # 멀티타입 — PROJECT_TYPES(csv) env가 있으면 배열로, 없으면 단수 키 fallback
    project_types_csv = os.environ.get('PROJECT_TYPES', '')
    project_types = [t.strip() for t in project_types_csv.split(',') if t.strip()]
    if not project_types and project_type:
        project_types = [project_type]
    today = os.environ.get('TODAY')
    pr_number_raw = os.environ.get('PR_NUMBER')
    timestamp = os.environ.get('TIMESTAMP')

    try:
        pr_number = int(pr_number_raw) if pr_number_raw else None
    except ValueError:
        pr_number = None

    # 입력 파일 찾기 (pr_body.md 우선, 폴백으로 summary_section.html)
    input_file = None
    for filename in ['pr_body.md', 'summary_section.html']:
        if os.path.isfile(filename):
            input_file = filename
            break

    if not input_file:
        print("❌ 입력 파일을 찾을 수 없습니다 (pr_body.md 또는 summary_section.html)")
        return 1

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()

        print(f"📄 입력 파일: {input_file}")
        print(f"📝 파일 크기: {len(content)} bytes")

        # Markdown 파싱 (통합)
        print("\n🔍 Markdown 파싱 시작...")
        categories = _parse_summary_markdown(content)

        parse_method = 'markdown' if categories else 'markdown_failed'
        if categories:
            print(f"✅ 파싱 성공: {len(categories)}개 카테고리")
        else:
            print("⚠️ 파싱 실패, raw_summary만 저장")

        # raw_summary 생성 (노이즈 제거)
        raw_summary = _clean_summary_noise(content)

        # 릴리즈 데이터 생성
        new_release = {
            "version": version,
            "project_type": project_type,      # 기존 단수 키 — 유지 (하위 호환)
            "project_types": project_types,    # 신규 멀티타입 배열
            "date": today,
            "pr_number": pr_number,
            "raw_summary": raw_summary,
            "parsed_changes": categories or {},
            "parse_method": parse_method,
        }

        # 파싱 결과 출력
        print("\n📊 파싱 결과:")
        print(f"  - 파싱 방식: {parse_method}")
        print(f"  - raw_summary 길이: {len(raw_summary)} 문자")
        print(f"  - 파싱된 카테고리: {len(categories)}개")
        for key, value in categories.items():
            title = value.get('title', key)
            items_count = len(value.get('items', []))
            print(f"    • {title}: {items_count}개 항목")

        # CHANGELOG.json 업데이트
        try:
            with open('CHANGELOG.json', 'r', encoding='utf-8') as f:
                changelog_data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            changelog_data = {
                "metadata": {
                    "lastUpdated": timestamp,
                    "currentVersion": version,
                    "projectType": project_type,
                    "projectTypes": project_types,
                    "totalReleases": 0,
                },
                "releases": [],
            }

        changelog_data["metadata"]["lastUpdated"] = timestamp
        changelog_data["metadata"]["currentVersion"] = version
        changelog_data["metadata"]["projectType"] = project_type
        changelog_data["metadata"]["projectTypes"] = project_types
        changelog_data["metadata"]["totalReleases"] = len(changelog_data.get("releases", [])) + 1
        changelog_data.setdefault("releases", []).insert(0, new_release)

        with open('CHANGELOG.json', 'w', encoding='utf-8') as f:
            json.dump(changelog_data, f, indent=2, ensure_ascii=False)

        print("\n✅ CHANGELOG.json 업데이트 완료!")
        return 0

    except Exception as e:
        print(f"❌ update-from-summary 실패: {e}")
        traceback.print_exc()
        return 1


def cmd_generate_md() -> int:
    """CHANGELOG.json을 기반으로 CHANGELOG.md 재생성."""
    try:
        with open('CHANGELOG.json', 'r', encoding='utf-8') as f:
            data = json.load(f)

        with open('CHANGELOG.md', 'w', encoding='utf-8') as f:
            f.write("# Changelog\n\n")

            metadata = data.get('metadata', {})
            current_version = metadata.get('currentVersion', 'Unknown')
            last_updated = metadata.get('lastUpdated', 'Unknown')

            f.write(f"**현재 버전:** {current_version}  \n")
            f.write(f"**마지막 업데이트:** {last_updated}  \n\n")
            f.write("---\n\n")

            for release in data.get('releases', []):
                version = release.get('version', 'Unknown')
                date = release.get('date', 'Unknown')
                pr_number = release.get('pr_number')

                f.write(f"## [{version}] - {date}\n\n")

                if pr_number is not None:
                    f.write(f"**PR:** #{pr_number}  \n\n")

                parsed = release.get('parsed_changes') or {}

                if parsed:
                    # 구조화된 데이터 출력
                    for _, items in parsed.items():
                        if not items:
                            continue
                        if isinstance(items, dict) and 'items' in items:
                            actual_items = items.get('items') or []
                            title = items.get('title') or ''
                        else:
                            actual_items = items
                            title = _normalize_text(_)

                        f.write(f"**{title}**\n")
                        for item in actual_items:
                            f.write(f"- {item}\n")
                        f.write("\n")
                else:
                    # 파싱 실패 시 raw_summary 출력
                    raw_summary = release.get('raw_summary', '').strip()
                    if raw_summary:
                        raw_summary = _clean_summary_noise(raw_summary)
                        if raw_summary:
                            f.write(raw_summary + "\n\n")
                        else:
                            f.write("*변경사항 정보 없음*\n\n")
                    else:
                        f.write("*변경사항 정보 없음*\n\n")

                f.write("---\n\n")

        print("✅ CHANGELOG.md 재생성 완료!")
        return 0

    except Exception as e:
        print(f"❌ CHANGELOG.md 생성 실패: {e}")
        traceback.print_exc()
        return 1


def cmd_export_release_notes(version: str, output_path: str | None) -> int:
    """CHANGELOG에서 해당 버전 릴리즈 노트를 생성."""
    notes_text = ""

    # 1) CHANGELOG.json 시도
    try:
        if os.path.isfile('CHANGELOG.json'):
            with open('CHANGELOG.json', 'r', encoding='utf-8') as f:
                changelog = json.load(f)
            releases = changelog.get('releases') or []
            matched = next((r for r in releases if str(r.get('version')) == str(version)), None)
            if matched:
                header = f"버전 {matched.get('version')} 업데이트\n\n"
                parsed_changes = matched.get('parsed_changes') or {}
                if parsed_changes:
                    category_blocks: list[str] = []
                    for _, value in parsed_changes.items():
                        title = (value.get('title') or '').strip()
                        items = [it for it in (value.get('items') or []) if it]
                        if title and items:
                            block = "**" + title + "**\n" + "\n".join("- " + it for it in items)
                            category_blocks.append(block)
                    body = "\n\n".join(category_blocks) if category_blocks else (matched.get('raw_summary') or '').strip()
                else:
                    body = (matched.get('raw_summary') or '').strip()
                notes_text = (header + (body or "")).strip()
    except Exception:
        pass

    # 2) CHANGELOG.md 폴백
    if not notes_text and os.path.isfile('CHANGELOG.md'):
        try:
            with open('CHANGELOG.md', 'r', encoding='utf-8') as f:
                md = f.read()
            pattern = re.compile(rf"^## \[{re.escape(str(version))}\].*$", re.MULTILINE)
            m = pattern.search(md)
            if m:
                start = m.end()
                next_m = re.search(r"^## \\[", md[start:], re.MULTILINE)
                section = md[start: start + next_m.start()] if next_m else md[start:]
                body = section.strip()
                notes_text = (f"버전 {version} 업데이트\n\n" + body).strip()
        except Exception:
            pass

    # 3) 최종 폴백
    if not notes_text:
        notes_text = f"버전 {version} 업데이트\n앱 안정성 및 사용자 경험이 개선되었습니다."

    if output_path:
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(notes_text)
    else:
        sys.stdout.write(notes_text + "\n")
    return 0


# --------------------- semver 승격 폭 판정 (이슈 #546) ---------------------
#
# 릴리스 노트 렌더링(changelog_providers 사다리)과는 분리된 경로다. 여기서는 버킷을
# 구성하거나 문구를 다듬지 않고 "major/minor/patch 중 무엇인가"만 판정한다. 두 경로를
# 합치면 릴리스 노트 생성이 이원화되어 드리프트가 난다.
#
# 커밋 제목 한 줄만 본다(수집이 %s라 본문에 접근할 수 없다). Conventional Commits 조항
# 13이 `!` 마커 단독으로도 breaking 표기를 인정하므로, BREAKING CHANGE 푸터 미지원은
# 표준이 허용하는 부분집합이다.

# tier-1: projectops 컨벤션 "제목 : type[!] : 내용 [URL]".
# 타입 앞 콜론에 공백이 선행해야 하므로 제목 안의 맨몸 콜론("v1:2" 등)에서 잘리지 않는다.
_BUMP_TIER1_RE = re.compile(
    r'^.+?\s:\s*(feat|fix|chore|docs|refactor|test)(!)?\s*:\s*.+$'
)
# tier-2: Conventional Commits "type(scope)[!]: 내용".
_BUMP_TIER2_RE = re.compile(
    r'^(feat|fix|chore|docs|refactor|test|perf|style|build|ci)(?:\([^)]*\))?(!)?:\s*.+$'
)


def classify_bump_level(lines: list[str]) -> str:
    """커밋 제목 목록에서 semver 승격 폭을 규칙 기반으로 판단(결정적 — AI 미사용).

    - 타입 뒤 `!` 마커(두 컨벤션 모두) → major (즉시 확정)
    - feat 타입 → minor
    - 그 외(매칭 실패·자유형식 포함) → patch
    """
    level = 'patch'

    for raw_line in lines:
        line = raw_line.strip()
        if not line or '[skip ci]' in line or line.startswith('Merge '):
            continue

        # tier-1을 먼저 시도한다 — 제목이 앞에 붙는 우리 컨벤션이 우선이다.
        matched = _BUMP_TIER1_RE.match(line)
        if matched:
            commit_type, breaking = matched.group(1), matched.group(2)
        else:
            matched = _BUMP_TIER2_RE.match(line)
            if not matched:
                continue
            commit_type, breaking = matched.group(1), matched.group(2)

        if breaking:
            return 'major'  # 최고 등급 — 더 볼 필요 없다
        if commit_type == 'feat':
            level = 'minor'

    return level


def cmd_classify_bump(commits_file: str) -> int:
    """커밋 목록 파일을 읽어 승격 폭을 stdout 마지막 줄에 출력.

    파일을 읽지 못하면 patch로 떨어진다 — 판정 실패가 릴리스를 막지 않게 하기 위함이다.
    """
    try:
        with open(commits_file, 'r', encoding='utf-8') as f:
            commit_lines = [line.rstrip('\n').rstrip('\r') for line in f]
    except Exception as e:
        print(f"[warn] 커밋 목록을 읽지 못했습니다 ({e}) — patch로 처리합니다", file=sys.stderr)
        commit_lines = []

    print(classify_bump_level(commit_lines))
    return 0


# ------------------------------- CLI -------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog='changelog_manager',
        description='통합 체인지로그 매니저',
        add_help=True
    )
    sub = parser.add_subparsers(dest='command', required=True)

    sub.add_parser('update-from-summary', help='PR body에서 CHANGELOG.json 갱신')
    sub.add_parser('generate-md', help='CHANGELOG.json → CHANGELOG.md 생성')

    p_export = sub.add_parser('export', help='특정 버전 릴리즈 노트 추출')
    p_export.add_argument('--version', required=True, help='버전 번호')
    p_export.add_argument('--output', help='출력 파일 경로 (없으면 stdout)')

    p_classify_bump = sub.add_parser(
        'classify-bump', help='커밋 목록으로 semver 승격 폭(major/minor/patch) 판단')
    p_classify_bump.add_argument(
        '--commits-file', required=True, help='커밋 제목 목록 파일 (한 줄당 1개)')

    args = parser.parse_args(argv)

    if args.command == 'update-from-summary':
        return cmd_update_from_summary()
    if args.command == 'generate-md':
        return cmd_generate_md()
    if args.command == 'export':
        return cmd_export_release_notes(args.version, args.output)
    if args.command == 'classify-bump':
        return cmd_classify_bump(args.commits_file)
    return 2


if __name__ == '__main__':
    sys.exit(main())
