"""브랜치명 계산 모듈 — SUH-ISSUE-HELPER TypeScript 로직의 Python 포팅."""

from __future__ import annotations

import re
from datetime import date


# 한글(가-힣), 영문, 숫자만 유지. 나머지는 _로 치환
_KEEP_PATTERN = re.compile(r"[^\uAC00-\uD7A3a-zA-Z0-9]")

# 연속 언더스코어를 단일 언더스코어로 변환
_MULTI_UNDERSCORE = re.compile(r"_+")

# Git branch 최대 길이 제한 (GitHub의 reference 제약)
_MAX_BRANCH_LEN = 100

# 제목 태그 → 커밋 타입.
#
# ⚠️ 정본은 `.github/scripts/issue_helper.py` 의 DEFAULT_COMMIT_TYPE_MAP 이다.
# 배포 경로가 달라(워크플로용 / 스킬용) import 할 수 없어 값을 맞춰 둔다.
# 어긋나면 **이슈 댓글이 안내한 커밋 타입과 스킬이 만드는 타입이 달라진다.**
# 동기화는 테스트가 강제한다 (test_commit_template.py).
COMMIT_TYPE_MAP = {
    "버그": "fix",
    "기능요청": "feat",
    "기능추가": "feat",
    "기능개선": "feat",
    "문서": "docs",
    "디자인": "design",
    "시험요청": "test",
}

# 제목 앞에 붙는 이모지. 변이 선택자(U+FE0F)·ZWJ 결합까지 함께 걷는다.
_LEADING_EMOJI = re.compile(
    r"^[🀀-🫿←-⯿ -⁯︀-️‍\s]+"
)

# 제목 **앞의** 연속된 [태그]. 중간에 나오는 대괄호는 건드리지 않는다
# (`.env[테스트] 처리` 같은 제목이 깨지면 안 된다).
_LEADING_TAGS = re.compile(r"^(?:\[[^\]]*\]\s*)+")

# 타입을 못 알아낼 때. issue_helper 와 같은 기본값이다.
_FALLBACK_COMMIT_TYPE = "feat"

# 제목에서 [태그]를 뽑는다
_TAG_PATTERN = re.compile(r"\[([^\]]*)\]")


def strip_issue_decorations(title: str) -> str:
    """이슈 제목에서 선행 이모지와 [태그]를 벗긴다.

    커밋 메시지에 이모지·태그를 넣지 않는 것이 이 저장소의 규칙인데,
    그것을 agent 의 기억력에 맡기면 반드시 빠뜨린다.

    Args:
        title: 원본 이슈 제목

    Returns:
        장식을 벗긴 제목. 벗기고 나면 빈 문자열이 되는 경우엔 원본을 돌려준다
        (제목이 통째로 사라지는 것이 더 나쁘다).
    """
    stripped = _LEADING_TAGS.sub("", _LEADING_EMOJI.sub("", title)).strip()
    return stripped or title.strip()


def infer_commit_type(issue_title: str, type_map: dict | None = None) -> str:
    """제목의 [태그]로 커밋 타입을 정한다 — 버그 이슈면 fix, 기능이면 feat.

    `semver_auto` 가 켜진 저장소에서는 이 값이 릴리스 승격 폭을 정한다.
    항상 feat 를 주면 오타 수정도 minor 가 된다.
    """
    merged = dict(COMMIT_TYPE_MAP)
    if type_map:
        merged.update(type_map)
    for tag in _TAG_PATTERN.findall(issue_title):
        commit_type = merged.get(tag.strip())
        if commit_type:
            return commit_type
    return _FALLBACK_COMMIT_TYPE


def normalize_title(title: str) -> str:
    """이슈 제목을 브랜치명용 문자열로 정규화한다.

    Args:
        title: 정규화할 제목 문자열

    Returns:
        정규화된 문자열 (한글/영문/숫자/언더스코어만 포함)
    """
    # 한글, 영문, 숫자 외의 문자를 언더스코어로 치환
    normalized = _KEEP_PATTERN.sub("_", title)

    # 연속 언더스코어를 단일 언더스코어로 변환
    normalized = _MULTI_UNDERSCORE.sub("_", normalized)

    # 양쪽 언더스코어 제거
    return normalized.strip("_")


def create_branch_name(
    issue_title: str,
    issue_number: int,
    date_yyyymmdd: str | None = None,
) -> str:
    """YYYYMMDD_#이슈번호_정규화제목 형식의 브랜치명을 생성한다.

    Args:
        issue_title: 이슈 제목
        issue_number: 이슈 번호
        date_yyyymmdd: 날짜 (YYYYMMDD 형식). None이면 현재 날짜 사용

    Returns:
        100자 이내의 브랜치명 (형식: YYYYMMDD_#123_제목)
    """
    if date_yyyymmdd is None:
        date_yyyymmdd = date.today().strftime("%Y%m%d")

    # prefix: "YYYYMMDD_#이슈번호_"
    prefix = f"{date_yyyymmdd}_#{issue_number}_"

    # 남은 길이에서 제목 길이 계산
    max_title_len = _MAX_BRANCH_LEN - len(prefix)

    # prefix만으로도 제한을 초과하면 prefix만 반환 (트레일 언더스코어 제거)
    if max_title_len <= 0:
        return prefix.rstrip("_")

    # 제목 정규화 및 길이 제한
    normalized = normalize_title(issue_title)[:max_title_len].rstrip("_")

    return f"{prefix}{normalized}"


def get_commit_template(issue_title: str, issue_url: str,
                       commit_type: str | None = None) -> str:
    """커밋 메시지 템플릿을 반환한다.

    제목의 이모지·태그를 벗기고, 그 태그에서 커밋 타입을 유도한다.
    예전에는 제목을 그대로 붙이고 타입을 feat 로 박아, 규칙 위반 커밋과
    잘못된 버전 승격을 agent 가 매번 손으로 막아야 했다.

    Args:
        issue_title: 이슈 제목 (이모지·태그가 붙어 있어도 된다)
        issue_url: 이슈 URL
        commit_type: 직접 정할 때. 생략하면 제목 태그에서 유도한다

    Returns:
        커밋 메시지 템플릿 문자열
    """
    clean_title = strip_issue_decorations(issue_title)
    resolved_type = commit_type or infer_commit_type(issue_title)
    return f"{clean_title} : {resolved_type} : {{설명}} {issue_url}"
