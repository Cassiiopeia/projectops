"""번역하지 않는 문자열 — 이미 사용자 레포에서 도는 구버전 소비자가 정규식으로 읽는다 (#787).

이 값들은 메시지 카탈로그(*.json)에 넣지 않는다. 코드가 여기서 가져다 붙인다.
테스트(test_i18n_messages.py)가 카탈로그 값에 이 문자열이 섞이지 않았는지 확인한다.

소비자: 앱 빌드 트리거, 테스트 APK, 테스트플라이트 워크플로우 (docs/BRANCH-CONVENTION.md)
"""

# 이슈 헬퍼 댓글의 브랜치 코드블록 제목: /### 브랜치\s*```\s*([\s\S]*?)\s*```/
BRANCH_HEADING = "### 브랜치"
# 댓글 서명 (설정 guide_signature 로 바꿀 수 있지만 기본값이 계약이다)
SIGNATURE = "Guide by ProjectOps"
# 옛 서명: 구버전 소비자가 찾는다. 보이지 않는 주석으로 항상 남긴다 (괄호 안 문구까지 기존 바이트 그대로)
LEGACY_SIGNATURE = "Guide by SUH-LAB"
LEGACY_COMMENT = f"<!-- {LEGACY_SIGNATURE} (구버전 워크플로우 호환용 표식) -->"
# 릴리스 노트 본문 마커: 릴리스 워크플로우가 이 문구로 요약 존재 여부를 판단한다
CODERABBIT_MARKER = "Summary by CodeRabbit"

ALL = (BRANCH_HEADING, SIGNATURE, LEGACY_SIGNATURE, CODERABBIT_MARKER)
