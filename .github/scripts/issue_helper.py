#!/usr/bin/env python3
"""SUH-ISSUE-HELPER — 이슈 생성/제목수정 시 브랜치명·커밋 메시지 댓글 생성 (내재화 버전).

구 외부 액션(Cassiiopeia/github-issue-helper@deploy)을 대체한다. stdlib 전용.

⚠️ 불변 계약 — 아래 형식을 기계 파싱하는 소비자가 있으므로 절대 깨지 마라:
  1. 브랜치명 `{prefix}YYYYMMDD_#이슈번호_정규화제목`
     - PROJECT-FLUTTER-ANDROID-TEST-APK.yaml      : sed 's/.*#\\([0-9]*\\).*/\\1/p'
     - PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml   : 동일
     - PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml : /#(\\d+)/
     - scripts/common/issue_number.py             : \\d{8}_(\\d+)_ (worktree)
  2. 댓글 본문의 `### 브랜치` 제목 + 코드블록, 그리고 서명 문구
     - PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml
       : /### 브랜치\\s*```\\s*([\\s\\S]*?)\\s*```/ (구버전이 사용자 레포에서 계속 실행됨)
     - 서명 문구는 설정(guide_signature, 기본 `Guide by ProjectOps`)으로 바뀐다.
       구버전 소비자가 옛 문구 `Guide by SUH-LAB`를 includes로 찾으므로,
       눈에 보이지 않는 HTML 주석으로 옛 표식을 항상 한 줄 남긴다 (LEGACY_SIGNATURE).

설정: version.yml metadata.template.options.issue_helper (없으면 전부 기본값).
"""
from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from i18n.contracts import BRANCH_HEADING, LEGACY_COMMENT, LEGACY_SIGNATURE  # 번역하지 않는 계약 문자열 (#787)
from i18n.messages import resolve_language, t

# ── 기본 설정 (version.yml에 issue_helper 섹션이 없을 때) ─────────────────
DEFAULT_CONFIG = {
    "branch_prefix": "",
    "max_branch_length": 100,
    "timezone": "Asia/Seoul",
    "commit_template": "${issueTitle} : ${commitType} : {변경 사항에 대한 설명} ${issueUrl}",
    "commit_type_map": {},
    "comment_marker": "<!-- SUH-ISSUE-HELPER -->",
    "guide_signature": "Guide by ProjectOps",
    "show_guide": True,
}

# 옛 서명(LEGACY_SIGNATURE)은 i18n/contracts.py 가 정본이다. 구버전 소비자 워크플로우(앱 빌드 트리거,
# PR 프리뷰)가 댓글에서 이 문구를 찾으므로 화면에는 보이지 않게 HTML 주석으로만 남긴다.

# 제목 태그 → 커밋 타입 (이슈 템플릿 4종의 제목 태그 기준). 설정 commit_type_map이 병합됨.
# 한글과 영문을 항상 둘 다 안다: 템플릿 언어(options.language)와 무관하게 동작해야 하고,
# 추가만 하므로 기존 레포에 영향이 없다 (#769).
DEFAULT_COMMIT_TYPE_MAP = {
    "버그": "fix",
    "기능요청": "feat",
    "기능추가": "feat",
    "기능개선": "feat",
    "문서": "docs",
    "디자인": "design",
    "시험요청": "test",
    "Bug": "fix",
    "Feature Request": "feat",
    "Feature": "feat",
    "Improvement": "feat",
    "Docs": "docs",
    "Design": "design",
    "QA": "test",
}

_TAG = re.compile(r"\[([^\]]*)\]")
# 유니코드 글자·숫자(가나·한자·악센트 라틴 포함)를 보존하고 그 외(공백·기호)만 _ 로 바꾼다.
# \w 는 `_` 도 포함하지만 어차피 구분자와 같아 무해하다.
_KEEP = re.compile(r"[^\w]")
_MULTI_UNDERSCORE = re.compile(r"_+")


def _strip_emoji(text: str) -> str:
    """이모지(So)·제어문자(C*)·변형선택자 제거 — 구 TS \\p{So}|\\p{C}|\\uFE0F|\\u200D 패리티."""
    out = []
    for ch in text:
        if ch in ("️", "‍"):
            continue
        cat = unicodedata.category(ch)
        if cat == "So" or cat.startswith("C"):
            continue
        out.append(ch)
    return "".join(out)


def extract_issue_title(raw_title: str) -> str:
    """[태그]·이모지 제거. 결과가 비면 원본 trim 반환 (구 동작 보존)."""
    title = _TAG.sub("", raw_title).strip()
    title = _strip_emoji(title).strip()
    return title if title else raw_title.strip()


def normalize_title(title: str) -> str:
    normalized = _KEEP.sub("_", title)
    normalized = _MULTI_UNDERSCORE.sub("_", normalized)
    return normalized.strip("_")


def infer_commit_type(raw_title: str, type_map: dict | None = None) -> str:
    """원본 제목의 [태그]들을 순서대로 매핑 조회. 미매치 시 feat."""
    merged = dict(DEFAULT_COMMIT_TYPE_MAP)
    if type_map:
        merged.update(type_map)
    lowered = {k.lower(): v for k, v in merged.items()}  # 영문 태그는 대소문자를 무시한다
    for tag in _TAG.findall(raw_title):
        key = tag.strip()
        commit_type = merged.get(key) or lowered.get(key.lower())
        if commit_type:
            return commit_type
    return "feat"


def create_branch_name(
    title: str,
    issue_number: int | str,
    date_yyyymmdd: str,
    branch_prefix: str = "",
    max_branch_length: int = 100,
) -> str:
    """불변 계약 1: 코어 `YYYYMMDD_#번호_제목` 고정. 길이 제한은 코어부에만 적용(구 TS 패리티)."""
    # 제목이 이모지·기호뿐이면 정규화 결과가 비므로 번호 기반 대체 문구로 제목 자리를 채운다
    slug = normalize_title(title) or f"issue-{issue_number}"
    base = f"{date_yyyymmdd}_#{issue_number}_{slug}"
    if max_branch_length > 0:
        # 자르다 구분자에서 끊기면 `_` 로 끝나므로 끝의 `_` 를 정리한다
        base = base[:max_branch_length].rstrip("_")
    return f"{branch_prefix}{base}"


def render_commit_message(template: str, ctx: dict) -> str:
    """${변수} 치환 — 기존 5종 + commitType/labels/assignees. 미지 변수는 그대로 둔다."""
    out = template
    for key in ("issueTitle", "issueUrl", "issueNumber", "branchName",
                "date", "commitType", "labels", "assignees"):
        out = out.replace("${" + key + "}", str(ctx.get(key, "")))
    return out.strip()


# ── 설정 로드 (version.yml — pyyaml 없이 이 섹션만 파싱) ────────────────────
def _strip_comment(raw: str) -> str:
    """값 뒤 줄 끝 주석 제거. 따옴표로 시작하면 닫는 따옴표까지를 값으로 읽어 안의 ` #`는 보존한다."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        end = raw.find(raw[0], 1)
        if end != -1:
            return raw[: end + 1]
    return re.sub(r"\s+#.*$", "", raw)


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def load_config(repo_root: str = ".") -> dict:
    """version.yml의 issue_helper 블록을 파싱해 DEFAULT_CONFIG에 병합한다.

    파일/섹션이 없으면 기본값 그대로 — 기존 통합 레포의 무설정 동작을 보존한다.
    향후 마법사 '설정 중앙관리' 메뉴가 이 섹션을 읽고 쓴다 (플랫 스칼라 + 얕은 맵 1개 유지).
    """
    cfg = dict(DEFAULT_CONFIG)
    cfg["commit_type_map"] = dict(DEFAULT_CONFIG["commit_type_map"])
    path = Path(repo_root) / "version.yml"
    if not path.exists():
        return cfg

    lines = path.read_text(encoding="utf-8").splitlines()
    section_indent = None
    in_type_map = False
    type_map_indent = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())

        if section_indent is None:
            if re.match(r"^issue_helper:\s*(#.*)?$", stripped):
                section_indent = indent
            continue

        if indent <= section_indent:  # 섹션 종료
            break

        m = re.match(r"""^["']?([^"':]+)["']?\s*:\s*(.*?)\s*$""", stripped)
        if not m:
            continue
        key, raw = m.group(1).strip(), _strip_comment(m.group(2))

        if in_type_map and indent > type_map_indent:
            cfg["commit_type_map"][key] = _unquote(raw)
            continue
        in_type_map = False

        if key == "commit_type_map":
            in_type_map = True
            type_map_indent = indent
        elif key == "max_branch_length":
            try:
                cfg[key] = int(_unquote(raw))
            except ValueError:
                pass  # 잘못된 값은 기본값 유지
        elif key == "show_guide":
            cfg[key] = _unquote(raw).lower() != "false"
        elif key in ("branch_prefix", "timezone", "commit_template", "comment_marker", "guide_signature"):
            cfg[key] = _unquote(raw)
    return cfg


# ── 동적 가이드 — 레포에 실존하는 워크플로우만 안내 (거짓 안내 원천 차단) ────
# ⚠️ 확장 규칙: 새 워크플로우가 브랜치 규칙(YYYYMMDD_#번호_)에 의존하게 되면 여기 한 줄 추가.
#    파일 실존 기반이므로 마법사 setting에서 타입 변경 시 자동 추종된다.
# 값은 문구 자체가 아니라 메시지 카탈로그 키다 (i18n/en.json, #787). 언어는 version.yml 이 정한다.
GUIDE_LINES = [
    ("PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml", "issue_helper.guide.app_build"),
    ("PROJECT-FLUTTER-ANDROID-TEST-APK.yaml", "issue_helper.guide.test_apk"),
    ("PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT.yaml", "issue_helper.guide.test_testflight"),
]

_GUIDE_ALWAYS = ["issue_helper.guide.skills"]


def effective_commit_template(cfg: dict, lang: str) -> str:
    """커밋 템플릿. 사용자가 정하지 않은 기본값일 때만 언어에 맞는 자리표시자 문구를 쓴다 (#790).

    기본값 문자열에 한국어 자리표시자 `{변경 사항에 대한 설명}` 이 박혀 있어 영문 댓글에도 그대로 나왔다.
    version.yml 의 commit_template 을 직접 정한 레포는 그 값을 언어와 무관하게 그대로 쓴다.
    """
    template = cfg["commit_template"]
    if template == DEFAULT_CONFIG["commit_template"]:
        return t("issue_helper.commit_template", lang)
    return template


def build_guide(workflows_dir: Path, lang: str | None = None) -> str:
    """접이식(details) 안내 본문. 레포에 의존 기능이 있으면 그 목록을, 없으면 권장 한 줄만."""
    lang = lang or resolve_language()
    active = [key for fname, key in GUIDE_LINES if (workflows_dir / fname).exists()]
    items = "\n".join(f"- {t(key, lang)}" for key in active + _GUIDE_ALWAYS)
    return (
        "<details>\n"
        f"<summary>{t('issue_helper.guide.summary', lang)}</summary>\n\n"
        f"{t('issue_helper.guide.intro', lang)}\n"
        f"{items}\n\n"
        f"{t('issue_helper.guide.outro', lang)}\n"
        "</details>"
    )


def build_comment_body(cfg: dict, branch_name: str, commit_message: str, guide: str, lang: str | None = None) -> str:
    """불변 계약 2: ### 브랜치 코드블록 구조 유지 + 서명 문구(설정 가능, 옛 서명은 숨김 주석으로 보존)."""
    marker = cfg["comment_marker"]
    signature = cfg.get("guide_signature") or DEFAULT_CONFIG["guide_signature"]
    guide_block = f"\n{guide}\n" if (cfg.get("show_guide", True) and guide) else ""
    # 서명을 바꿨어도 구버전 소비자가 찾는 옛 문구는 보이지 않게 한 줄 남긴다
    # ⚠️ 서명 바로 아래 줄에 주석을 끼우면 `서명\n---`(제목 렌더링)이 깨지므로 서명 위에 둔다
    legacy = "" if LEGACY_SIGNATURE in signature else f"{LEGACY_COMMENT}\n\n"
    lang = lang or resolve_language()
    return (
        f"{marker}\n\n"
        f"{legacy}"
        f"{signature}\n"
        "---\n\n"
        f"{BRANCH_HEADING}\n"
        f"```\n{branch_name}\n```\n\n"
        f"### {t('issue_helper.heading.commit', lang)}\n"
        f"```\n{commit_message}\n```\n"
        f"{guide_block}\n"
        f"{marker}"
    )


# ── 이벤트 처리 ──────────────────────────────────────────────────────────
def should_process(payload: dict) -> bool:
    """opened 또는 edited(제목 변경)만 처리 — 구 워크플로우 if 조건과 동일."""
    action = payload.get("action")
    if action == "opened":
        return True
    return action == "edited" and bool(payload.get("changes", {}).get("title"))


def today_yyyymmdd(tz_name: str) -> str:
    """설정 타임존 기준 오늘 날짜. 구 액션의 UTC 러너 시각 오차(한국 새벽 -9h)를 개선."""
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(tz_name)).strftime("%Y%m%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y%m%d")


def prepare_comment(payload: dict, cfg: dict, workflows_dir: Path, date_yyyymmdd: str):
    """페이로드 → (브랜치명, 커밋 메시지, 댓글 본문). 네트워크 무의존 — 테스트 가능 단위."""
    issue = payload["issue"]
    raw_title = issue["title"]
    title = extract_issue_title(raw_title)
    issue_number = str(issue["number"])

    branch = create_branch_name(
        title, issue_number, date_yyyymmdd,
        branch_prefix=cfg["branch_prefix"], max_branch_length=cfg["max_branch_length"])

    ctx = {
        "issueTitle": title,
        "issueUrl": issue["html_url"],
        "issueNumber": issue_number,
        "branchName": branch,
        "date": date_yyyymmdd,
        "commitType": infer_commit_type(raw_title, cfg["commit_type_map"]),
        "labels": ", ".join(l["name"] for l in issue.get("labels", [])),
        "assignees": ", ".join(a["login"] for a in issue.get("assignees", [])),
    }
    lang = resolve_language()  # 한 번 정해 댓글 전체에 같은 언어를 쓴다
    commit_message = render_commit_message(effective_commit_template(cfg, lang), ctx)
    body = build_comment_body(cfg, branch, commit_message, build_guide(workflows_dir, lang), lang)
    return branch, commit_message, body


# ── GitHub API (urllib — 같은 레포 이슈 댓글이라 redirect 없음) ──────────────
_API = "https://api.github.com"

# 구 액션이 남긴 댓글도 upsert 대상으로 매칭 (중복 댓글 방지 — 하위호환)
LEGACY_MARKER_HINTS = ("github-issue-helper", "SUH-ISSUE-HELPER 에 의해 자동으로")


def _request(method: str, url: str, token: str, data: dict | None = None):
    req = urllib.request.Request(url, method=method)
    req.add_header("Authorization", f"token {token}")
    req.add_header("Accept", "application/vnd.github+json")
    payload = None
    if data is not None:
        payload = json.dumps(data).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, payload) as res:
        return json.loads(res.read().decode("utf-8"))


def find_existing_comment(comments: list, marker: str):
    """신형 마커 우선, 없으면 구 액션 마커 힌트로 매칭."""
    for c in comments:
        if marker in (c.get("body") or ""):
            return c
    for c in comments:
        body = c.get("body") or ""
        if any(hint in body for hint in LEGACY_MARKER_HINTS):
            return c
    return None


def upsert_comment(owner: str, repo: str, issue_number: int, marker: str, body: str, token: str):
    comments = []
    page = 1
    while True:
        batch = _request(
            "GET",
            f"{_API}/repos/{owner}/{repo}/issues/{issue_number}/comments?per_page=100&page={page}",
            token)
        comments.extend(batch)
        if len(batch) < 100:
            break
        page += 1

    existing = find_existing_comment(comments, marker)
    if existing:
        _request("PATCH", f"{_API}/repos/{owner}/{repo}/issues/comments/{existing['id']}",
                 token, {"body": body})
        return "updated"
    _request("POST", f"{_API}/repos/{owner}/{repo}/issues/{issue_number}/comments",
             token, {"body": body})
    return "created"


def main() -> int:
    event_path = os.environ.get("GITHUB_EVENT_PATH", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    if not event_path or not Path(event_path).exists():
        print("❌ GITHUB_EVENT_PATH가 없습니다 (Actions 환경 전용)", file=sys.stderr)
        return 1
    if not token:
        print("❌ GITHUB_TOKEN이 없습니다", file=sys.stderr)
        return 1

    payload = json.loads(Path(event_path).read_text(encoding="utf-8"))
    if not should_process(payload):
        print("ℹ️ 처리 대상 이벤트가 아님 (opened/제목 edited만) → 종료", file=sys.stderr)
        return 0

    cfg = load_config(".")
    branch, commit_message, body = prepare_comment(
        payload, cfg, Path(".github") / "workflows", today_yyyymmdd(cfg["timezone"]))

    owner = payload["repository"]["owner"]["login"]
    repo = payload["repository"]["name"]
    result = upsert_comment(
        owner, repo, payload["issue"]["number"], cfg["comment_marker"], body, token)
    print(f"✅ 댓글 {result}: {branch}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
