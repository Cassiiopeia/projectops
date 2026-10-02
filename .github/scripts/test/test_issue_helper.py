"""issue_helper.py 테스트 — 구 TS 액션(normalize.ts)과의 패리티 + 신규 기능."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from issue_helper import (
    DEFAULT_COMMIT_TYPE_MAP,
    create_branch_name,
    extract_issue_title,
    infer_commit_type,
    normalize_title,
    render_commit_message,
)


# ── 제목 추출 (구 extractIssueTitle 패리티) ──────────────────────────────
def test_extract_title_removes_tags():
    assert extract_issue_title("❗ [버그][로그인] 소셜 로그인 실패") == "소셜 로그인 실패"

def test_extract_title_removes_emoji():
    assert extract_issue_title("🚀 기능 개선") == "기능 개선"

def test_extract_title_fallback_when_empty():
    # 태그·이모지 제거 후 빈 문자열이면 원본 trim 반환 (구 동작 보존)
    assert extract_issue_title("  [버그]  ") == "[버그]"


# ── 정규화 (구 normalizeTitle 패리티, scripts/common/gh_branch.py와 규칙 동일) ──
def test_normalize_replaces_special_chars():
    assert normalize_title("FCM 푸시: 라우팅용 데이터!") == "FCM_푸시_라우팅용_데이터"

def test_normalize_collapses_underscores():
    assert normalize_title("a - - b") == "a_b"

def test_normalize_strips_edge_underscores():
    assert normalize_title("!한글 제목!") == "한글_제목"


# ── 브랜치명 (구 createBranchName 패리티 — base slice, prefix 제외) ─────────
def test_branch_name_core_format():
    b = create_branch_name("로그인 버그 수정", 123, "20260712")
    assert b == "20260712_#123_로그인_버그_수정"

def test_branch_name_prefix_excluded_from_limit():
    b = create_branch_name("가" * 200, 5, "20260712", branch_prefix="feat/", max_branch_length=30)
    assert b.startswith("feat/20260712_#5_")
    assert len(b) == len("feat/") + 30

def test_branch_name_contains_issue_number_token():
    # 불변 계약: 소비자 정규식 #(\d+) 이 반드시 매치해야 한다
    import re
    b = create_branch_name("제목", 42, "20260712", branch_prefix="fix/")
    assert re.search(r"#(\d+)", b).group(1) == "42"


# ── 커밋 타입 추론 (신규) ────────────────────────────────────────────────
def test_infer_type_bug():
    assert infer_commit_type("❗ [버그][로그인] 실패") == "fix"

def test_infer_type_feature_variants():
    assert infer_commit_type("[기능추가] X") == "feat"
    assert infer_commit_type("[기능개선] X") == "feat"

def test_infer_type_docs_design_test():
    assert infer_commit_type("[문서] X") == "docs"
    assert infer_commit_type("[디자인] X") == "design"
    assert infer_commit_type("[시험요청] X") == "test"

def test_infer_type_default_feat():
    assert infer_commit_type("태그 없는 제목") == "feat"

def test_infer_type_user_override():
    assert infer_commit_type("[버그] X", {"버그": "hotfix"}) == "hotfix"

def test_infer_type_unknown_tag_skipped():
    # 미등록 태그([긴급])는 건너뛰고 다음 태그로 판정
    assert infer_commit_type("[긴급][버그] X") == "fix"


# ── 커밋 템플릿 렌더링 (기존 5종 + 신규 3종 변수) ─────────────────────────
def test_render_all_variables():
    ctx = {
        "issueTitle": "로그인 수정", "issueUrl": "https://github.com/o/r/issues/9",
        "issueNumber": "9", "branchName": "20260712_#9_로그인_수정",
        "date": "20260712", "commitType": "fix", "labels": "작업전", "assignees": "Cassiiopeia",
    }
    out = render_commit_message(
        "${issueTitle} : ${commitType} : {설명} ${issueUrl} by ${assignees}", ctx)
    assert out == "로그인 수정 : fix : {설명} https://github.com/o/r/issues/9 by Cassiiopeia"

def test_render_leaves_unknown_placeholders():
    # {변경 사항에 대한 설명} 같은 사용자 안내 placeholder는 그대로 남긴다
    ctx = {"issueTitle": "t", "issueUrl": "u", "issueNumber": "1",
           "branchName": "b", "date": "d", "commitType": "feat", "labels": "", "assignees": ""}
    assert "{변경 사항에 대한 설명}" in render_commit_message(
        "${issueTitle} : feat : {변경 사항에 대한 설명}", ctx)


import re as _re

from issue_helper import (
    DEFAULT_CONFIG,
    GUIDE_LINES,
    build_comment_body,
    build_guide,
    load_config,
)


# ── 설정 로드 ────────────────────────────────────────────────────────────
def test_load_config_defaults_when_no_file(tmp_path):
    cfg = load_config(str(tmp_path))
    assert cfg == DEFAULT_CONFIG

def test_load_config_defaults_when_no_section(tmp_path):
    (tmp_path / "version.yml").write_text('version: "1.0.0"\nmetadata:\n  last_updated: "x"\n', encoding="utf-8")
    assert load_config(str(tmp_path)) == DEFAULT_CONFIG

def test_load_config_reads_section(tmp_path):
    (tmp_path / "version.yml").write_text(
        'version: "1.0.0"\n'
        "metadata:\n"
        "  template:\n"
        "    options:\n"
        "      issue_helper:\n"
        '        branch_prefix: "feat/"\n'
        "        max_branch_length: 80\n"
        '        commit_template: "${issueTitle} : ${commitType} : ${issueUrl}"\n'
        "        show_guide: false\n"
        "        commit_type_map:\n"
        '          "버그": "hotfix"\n'
        '          "디자인": "style"\n',
        encoding="utf-8",
    )
    cfg = load_config(str(tmp_path))
    assert cfg["branch_prefix"] == "feat/"
    assert cfg["max_branch_length"] == 80
    assert cfg["show_guide"] is False
    assert cfg["commit_type_map"] == {"버그": "hotfix", "디자인": "style"}
    assert cfg["timezone"] == "Asia/Seoul"  # 미지정 키는 기본값 유지


# ── 동적 가이드 (파일 실존 기반 — 마법사 setting에서 타입 변경 시 자동 추종) ──
def test_guide_lists_only_existing_workflows(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER.yaml").write_text("name: x\n", encoding="utf-8")
    guide = build_guide(wf)
    assert "@projectops app build" in guide
    assert "테스트 APK 빌드" not in guide  # 파일 없으면 안내 안 함 (거짓 안내 차단)

def test_guide_always_mentions_skills(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    guide = build_guide(wf)
    # 스킬 연동은 레포 구성 무관 — 항상 포함
    assert "이슈 번호를 자동 추출" in guide


# ── 댓글 본문 — 불변 계약 2 (BUILD-TRIGGER 파서 하위호환) ───────────────────
def _body(show_guide=True):
    cfg = dict(DEFAULT_CONFIG, show_guide=show_guide)
    return build_comment_body(cfg, "20260712_#9_제목", "제목 : fix : {설명} url", "가이드텍스트")

def test_comment_default_signature_is_projectops():
    """화면에 보이는 서명은 기본값 Guide by ProjectOps 다 (#749)."""
    assert "Guide by ProjectOps" in _body()

def test_comment_keeps_legacy_signature_hidden():
    """구버전 소비자가 includes('Guide by SUH-LAB')로 찾으므로 HTML 주석으로 남긴다."""
    body = _body()
    assert "Guide by SUH-LAB" in body
    # 화면에 보이는 줄(주석 제외)에는 옛 서명이 없어야 한다
    visible = _re.sub(r"<!--.*?-->", "", body, flags=_re.S)
    assert "Guide by SUH-LAB" not in visible

def test_comment_signature_is_configurable():
    cfg = dict(DEFAULT_CONFIG, guide_signature="Guide by MyTeam")
    body = build_comment_body(cfg, "20260712_#9_제목", "m", "")
    assert "Guide by MyTeam" in body
    assert "Guide by SUH-LAB" in body  # 호환 표식은 서명 설정과 무관하게 유지

def test_comment_legacy_signature_not_duplicated():
    """서명을 옛 문구로 되돌려도 표식이 두 번 들어가지 않는다."""
    cfg = dict(DEFAULT_CONFIG, guide_signature="Guide by SUH-LAB")
    assert build_comment_body(cfg, "b", "m", "").count("Guide by SUH-LAB") == 1

def test_comment_contract_branch_block_parseable():
    # BUILD-TRIGGER.yaml:220 의 JS 정규식과 동일 패턴으로 파싱 가능해야 한다
    m = _re.search(r"### 브랜치\s*```\s*([\s\S]*?)\s*```", _body())
    assert m and m.group(1).strip() == "20260712_#9_제목"

def test_comment_contains_marker_twice():
    body = _body()
    assert body.count(DEFAULT_CONFIG["comment_marker"]) == 2  # 구 액션과 동일: 상단+하단

def test_comment_guide_hidden_when_disabled():
    assert "가이드텍스트" not in _body(show_guide=False)


from issue_helper import (
    LEGACY_MARKER_HINTS,
    find_existing_comment,
    prepare_comment,
    should_process,
    today_yyyymmdd,
)


def _payload(action="opened", title="[버그] 로그인 실패", changes=None):
    p = {
        "action": action,
        "issue": {
            "number": 7,
            "title": title,
            "html_url": "https://github.com/o/r/issues/7",
            "labels": [{"name": "작업전"}],
            "assignees": [{"login": "Cassiiopeia"}],
        },
        "repository": {"name": "r", "owner": {"login": "o"}},
    }
    if changes is not None:
        p["changes"] = changes
    return p


# ── 이벤트 필터링 ────────────────────────────────────────────────────────
def test_process_opened():
    assert should_process(_payload("opened")) is True

def test_process_edited_with_title_change():
    assert should_process(_payload("edited", changes={"title": {"from": "old"}})) is True

def test_skip_edited_body_only():
    assert should_process(_payload("edited", changes={"body": {"from": "old"}})) is False

def test_skip_other_actions():
    assert should_process(_payload("closed")) is False


# ── 종단 조립 ────────────────────────────────────────────────────────────
def test_prepare_comment_end_to_end(tmp_path):
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    branch, commit, body = prepare_comment(_payload(), dict(DEFAULT_CONFIG), wf, "20260712")
    assert branch == "20260712_#7_로그인_실패"
    assert commit.startswith("로그인 실패 : fix : ")           # [버그] → fix 추론
    assert "https://github.com/o/r/issues/7" in commit
    m = _re.search(r"### 브랜치\s*```\s*([\s\S]*?)\s*```", body)  # 계약 재확인
    assert m.group(1).strip() == branch


# ── upsert 매칭 (구 액션 댓글 하위호환) ──────────────────────────────────────
def test_find_comment_by_new_marker():
    comments = [{"id": 1, "body": "무관"}, {"id": 2, "body": "x <!-- SUH-ISSUE-HELPER --> y"}]
    assert find_existing_comment(comments, "<!-- SUH-ISSUE-HELPER -->")["id"] == 2

def test_find_comment_by_legacy_marker():
    # 구 액션 기본 마커 — github-issue-helper URL 포함
    legacy = ("<!-- 이 댓글은 SUH-ISSUE-HELPER 에 의해 자동으로 생성되었습니다."
              " - https://github.com/Cassiiopeia/github-issue-helper -->")
    comments = [{"id": 3, "body": f"{legacy}\nGuide by SUH-LAB"}]
    assert find_existing_comment(comments, "<!-- SUH-ISSUE-HELPER -->")["id"] == 3

def test_find_comment_none():
    assert find_existing_comment([{"id": 1, "body": "그냥 댓글"}], "<!-- SUH-ISSUE-HELPER -->") is None


# ── 날짜 (KST 개선 — 구 액션은 UTC 러너 시각) ────────────────────────────────
def test_today_is_8_digits():
    assert _re.fullmatch(r"\d{8}", today_yyyymmdd("Asia/Seoul"))

def test_today_invalid_tz_falls_back():
    assert _re.fullmatch(r"\d{8}", today_yyyymmdd("No/Such_Zone"))


# ── #690: 한글·영문 외 글자 보존 / 빈 제목 대체 / 자른 뒤 끝 `_` 정리 ──────────
def test_branch_name_keeps_japanese_title():
    name = create_branch_name(extract_issue_title("日本語のタイトル"), 7, "20261001")
    assert name == "20261001_#7_日本語のタイトル"


def test_branch_name_keeps_accented_latin():
    name = create_branch_name(extract_issue_title("Ünïcödé café"), 7, "20261001")
    assert name == "20261001_#7_Ünïcödé_café"


def test_branch_name_emoji_only_title_gets_fallback():
    # 제목이 비어도 코어 계약(YYYYMMDD_#번호_제목)의 제목 자리를 채운다
    name = create_branch_name(extract_issue_title("🚀"), 7, "20261001")
    assert name == "20261001_#7_issue-7"


def test_branch_name_trailing_underscore_trimmed_after_truncate():
    # 코어부 12자 + 제목 87자 직후가 구분자라 100자에서 `_`로 끝나게 잘린다
    name = create_branch_name("a" * 87 + " bbb", 7, "20261001")
    assert len(name) <= 100
    assert not name.endswith("_")


# ── #691: 따옴표 안의 ` #`는 주석이 아니다 ─────────────────────────────────────
def test_load_config_keeps_hash_inside_quotes(tmp_path):
    (tmp_path / "version.yml").write_text(
        'version: "1.0.0"\n'
        "issue_helper:\n"
        '  commit_template: "${issueTitle} #${issueNumber} : ${commitType}"\n'
        "  branch_prefix: 'feat/ #x' # 줄 끝 주석\n"
        "  timezone: Asia/Seoul # 따옴표 없는 값의 주석\n",
        encoding="utf-8",
    )
    cfg = load_config(str(tmp_path))
    assert cfg["commit_template"] == "${issueTitle} #${issueNumber} : ${commitType}"
    assert cfg["branch_prefix"] == "feat/ #x"
    assert cfg["timezone"] == "Asia/Seoul"
