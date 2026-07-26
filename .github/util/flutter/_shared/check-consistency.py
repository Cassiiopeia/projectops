#!/usr/bin/env python3
"""projectops Flutter 마법사 3종 정합성 검증.

왜 필요한가
-----------
과거 iOS(testflight) 마법사만 집중적으로 개선되고 나머지 둘에 전파되지 않아
같은 클래스명이 정반대 의미로 쓰이거나, 한쪽에만 있는 기능이 생겼다.
이 스크립트는 그 드리프트를 CI/로컬에서 즉시 잡는다.

검사 항목
---------
1. 공통 자산 로드      — 3종 HTML이 _shared/wizard.css, wizard-common.js를 참조하는가
2. 공통 함수 재정의    — 마법사 JS가 공통 유틸을 다시 정의해 덮어쓰고 있지 않은가
3. 필수 기능 균일성    — 3종이 같은 이름의 핵심 기능을 모두 제공하는가
4. 미정의 CSS 클래스   — HTML이 쓰는 프로젝트 클래스가 어딘가에 정의돼 있는가
5. 버전 동기화         — version.json 과 HTML 인라인 versionJson 이 일치하는가
6. 낡은 링크           — 구 레포명·존재하지 않는 경로를 가리키고 있지 않은가
7. 첫 사용자 안내      — 준비물/소요시간/문서링크/재개안내가 3종에 모두 있는가

사용법
------
    python3 .github/util/flutter/_shared/check-consistency.py
    python3 .github/util/flutter/_shared/check-consistency.py --json

종료 코드: 0 = 통과, 1 = 위반 있음
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

WIZARDS = ("testflight", "playstore", "firebase")
SHARED_DIR = Path(__file__).resolve().parent
FLUTTER_DIR = SHARED_DIR.parent
REPO_SLUG = "Cassiiopeia/projectops"

# 공통 유틸에 정의된 함수 — 마법사 JS가 재정의하면 정본이 무력화된다
SHARED_FUNCS_RE = re.compile(r"^(?:async )?function ([A-Za-z0-9_]+)", re.M)

# 3종이 모두 제공해야 하는 기능 (이름 통일 대상)
REQUIRED_FUNCS = (
    "showStep",
    "goToStep",
    "nextStep",
    "prevStep",
    "saveState",
    "loadState",
    "resetWizard",
    "updateProgress",
    "downloadAsJson",
    "downloadAsTxt",
    "downloadAsZip",
    "addCustomSecret",
    "removeCustomSecret",
    "renderCustomSecrets",
)

# 3종 HTML에 모두 있어야 하는 첫 사용자 안내 요소 (id 또는 클래스)
REQUIRED_MARKERS = (
    ("securityWarning", 'id="securityWarning"'),
    ("changelogModal", 'id="changelogModal"'),
    ("소요시간·준비물 배너", 'class="wizard-meta"'),
    ("재개 안내", 'class="resume-hint"'),
    ("문서 링크", "docs/FLUTTER-"),
)


def wizard_paths(name: str) -> dict[str, Path]:
    base = FLUTTER_DIR / f"{name}-wizard"
    return {
        "html": base / f"{name}-wizard.html",
        "js": base / f"{name}-wizard.js",
        "py": base / f"{name}-wizard.py",
        "version": base / "version.json",
        "sync": base / "version-sync.sh",
    }


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def check() -> list[str]:
    problems: list[str] = []

    shared_css = SHARED_DIR / "wizard.css"
    shared_js = SHARED_DIR / "wizard-common.js"
    for p in (shared_css, shared_js):
        if not p.exists():
            problems.append(f"[공통자산] {p.name} 이 없습니다")
    if problems:
        return problems

    shared_funcs = set(SHARED_FUNCS_RE.findall(read(shared_js)))
    # 공통 CSS에 정의된 클래스
    shared_classes = set(re.findall(r"^\.([a-zA-Z][\w-]*)", read(shared_css), re.M))

    for name in WIZARDS:
        paths = wizard_paths(name)
        tag = f"[{name}]"

        for key, p in paths.items():
            if not p.exists():
                problems.append(f"{tag} {p.name} 이 없습니다")
        html, js = read(paths["html"]), read(paths["js"])
        if not html or not js:
            continue

        # 1. 공통 자산 로드
        # 주석에 경로 문자열만 있어도 통과하지 않도록 실제 태그로 판정한다
        if not re.search(r'<link[^>]+href="\.\./_shared/wizard\.css"', html):
            problems.append(f"{tag} HTML이 ../_shared/wizard.css 를 로드하지 않습니다")
        if not re.search(r'<script[^>]+src="\.\./_shared/wizard-common\.js"', html):
            problems.append(f"{tag} HTML이 ../_shared/wizard-common.js 를 로드하지 않습니다")
        else:
            # 공통 JS가 마법사 JS보다 먼저 로드되어야 오버라이드 사고가 없다
            i_common = html.find("../_shared/wizard-common.js")
            i_own = html.find(f"{name}-wizard.js")
            if i_own != -1 and i_common > i_own:
                problems.append(f"{tag} 공통 JS가 마법사 JS보다 늦게 로드됩니다 (순서 교정 필요)")

        # 2. 공통 함수 재정의
        own_funcs = set(SHARED_FUNCS_RE.findall(js))
        redefined = sorted(own_funcs & shared_funcs)
        if redefined:
            problems.append(f"{tag} 공통 유틸을 재정의하고 있습니다: {', '.join(redefined)}")

        # 3. 필수 기능 균일성
        available = own_funcs | shared_funcs
        missing = [f for f in REQUIRED_FUNCS if f not in available]
        if missing:
            problems.append(f"{tag} 필수 기능 누락: {', '.join(missing)}")

        # 4. 미정의 CSS 클래스 (프로젝트 자체 클래스만 대상 — Tailwind 유틸은 제외)
        own_css = set(re.findall(r"^\s*\.([a-zA-Z][\w-]*)", html, re.M))
        used = set(re.findall(r'class="([^"]+)"', html))
        used_classes = {c for chunk in used for c in chunk.split()}
        known = shared_classes | own_css
        project_prefixes = ("tooltip-", "code-", "file-", "custom-", "secret-", "type-",
                            "usage-", "dependency-", "result-", "copy-btn", "add-secret",
                            "remove-secret", "step-", "modal-", "wizard-", "resume-",
                            "skip-", "input-", "error-", "success-", "toast", "fade-in")
        undefined = sorted(
            c for c in used_classes
            if c.startswith(project_prefixes) and c not in known
        )
        if undefined:
            problems.append(f"{tag} 정의되지 않은 클래스 사용: {', '.join(undefined)}")

        # 5. 버전 동기화
        try:
            vjson = json.loads(read(paths["version"]))
            inline = re.search(
                r'<script type="application/json" id="versionJson">(.*?)</script>', html, re.S
            )
            if not inline:
                problems.append(f"{tag} HTML에 versionJson 블록이 없습니다")
            elif json.loads(inline.group(1)) != vjson:
                problems.append(f"{tag} version.json 과 HTML이 다릅니다 — ./version-sync.sh 실행 필요")
        except (json.JSONDecodeError, ValueError) as e:
            problems.append(f"{tag} version.json 파싱 실패: {e}")

        # 6. 낡은 링크
        # ⚠️ 문자열 포함 여부가 아니라 "실제 URL"만 본다.
        #    version.json 변경 이력에 "구 레포명을 교정했다"는 설명이 들어가는데,
        #    그 텍스트는 HTML에 주입되므로 단순 포함 검사는 오탐이 된다.
        for blob, label in ((html, "HTML"), (js, "JS")):
            seen = set()
            for m in re.finditer(r"github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)", blob):
                slug = m.group(1)
                if slug != REPO_SLUG and slug not in seen:
                    seen.add(slug)
                    hint = " (구 레포명 — 리브랜딩 후 projectops)" if "SUH-DEVOPS-TEMPLATE" in slug else ""
                    problems.append(f"{tag} {label}가 다른 레포를 가리킵니다: {slug}{hint}")

        # 7. 첫 사용자 안내
        for label, marker in REQUIRED_MARKERS:
            if marker not in html:
                problems.append(f"{tag} 첫 사용자 안내 누락: {label}")

    # version-sync.sh 3종이 파일명만 빼고 동일한지
    norm = []
    for name in WIZARDS:
        s = read(wizard_paths(name)["sync"]).replace(f"{name}-wizard.html", "<HTML>")
        norm.append((name, s))
    if len({s for _, s in norm}) > 1:
        problems.append("[공통] version-sync.sh 3종이 서로 다릅니다 (파일명 외 차이 없어야 함)")

    # ── Python CLI 계약 ────────────────────────────────────────────
    # 3종은 같은 방식으로 호출돼야 한다: 명명 플래그 정본 + 공통 부울 플래그.
    # 과거 testflight는 위치인자만, firebase는 플래그만 받아 사용법이 갈렸다.
    for name in WIZARDS:
        py = read(wizard_paths(name)["py"])
        if not py:
            continue
        tag = f"[{name}]"
        for flag in ("--dry-run", "--non-interactive", "--no-backup"):
            if flag not in py:
                problems.append(f"{tag} CLI 공통 옵션 미지원: {flag}")
        # dry-run이 "선언만 되고 실제로는 파일을 쓰는" 상태를 막는다
        if "--dry-run" in py and not re.search(r"\bDRY_RUN\b|\bdry_run\b", py):
            problems.append(f"{tag} --dry-run을 받지만 실제 동작에 연결되어 있지 않습니다")

    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="Flutter 마법사 3종 정합성 검증")
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = ap.parse_args()

    problems = check()

    if args.json:
        print(json.dumps({"ok": not problems, "count": len(problems), "problems": problems},
                         ensure_ascii=False, indent=2))
    elif problems:
        print(f"❌ 정합성 위반 {len(problems)}건\n")
        for p in problems:
            print(f"  - {p}")
        print("\n수정 후 다시 실행하세요.")
    else:
        print("✅ 마법사 3종 정합성 통과")

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
