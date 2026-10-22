"""언어별 데모 문구: 이슈·커밋·PR 내용과 GIF 단계 설명 (en 원문, ko 번역)"""

DEMO_TEXTS = {
    "en": {
        "issue_title": "⚙️[Feature][Notifications] Add push notification settings screen",
        "issue_body": (
            "📝 Current problem\n---\n\n"
            "- Users cannot choose which notifications they get, so they receive alerts they do not need.\n\n"
            "🛠️ Proposed solution / feature\n---\n\n"
            "- Add on/off settings per notification type to the My Page screen.\n"
        ),
        "commit_descriptions": ["Add notification settings model", "Add notification settings API"],
        "pull_request_title": "Add push notification settings screen",
        "pull_request_summary_heading": "Change summary",
        "issue_helper_marker": "Guide by ProjectOps",
        "captions": {
            "issue": {
                1: "Open an issue",
                2: "GitHub Actions runs on its own",
                3: "A comment suggests the branch name and commit message",
                4: "Use this branch name and the issue links to your commits and reports",
            },
            "pull_request": {
                1: "Open a PR from your work branch",
                2: "The change summary workflow runs on its own",
                3: "A comment summarizes the changes from your commits",
            },
            "release": {
                1: "Open a release PR from the development branch to main",
                2: "Release notes, version bump and auto-merge run on their own",
                3: "The version is set and the PR merges itself",
                4: "A version tag is created automatically",
            },
        },
    },
    "ko": {
        "issue_title": "⚙️[기능추가][알림] 푸시 알림 설정 화면 추가",
        "issue_body": (
            "📝 현재 문제점\n---\n\n"
            "- 사용자가 알림 종류를 고를 수 없어 불필요한 알림이 많다.\n\n"
            "🛠️ 해결 방안 / 제안 기능\n---\n\n"
            "- 마이페이지에 알림 종류별 켜기/끄기 설정을 추가한다.\n"
        ),
        "commit_descriptions": ["알림 종류별 설정 모델 추가", "알림 설정 조회 API 추가"],
        "pull_request_title": "푸시 알림 설정 화면 추가",
        "pull_request_summary_heading": "변경 요약",
        "issue_helper_marker": "Guide by ProjectOps",
        "captions": {
            "issue": {
                1: "이슈를 등록하면",
                2: "GitHub Actions가 자동으로 실행됩니다",
                3: "브랜치명과 커밋 메시지 템플릿이 댓글로 달립니다",
                4: "이 브랜치명을 쓰면 이슈 번호가 커밋·보고서에 자동 연동됩니다",
            },
            "pull_request": {
                1: "작업 브랜치로 PR을 열면",
                2: "변경 요약 워크플로우가 자동으로 실행됩니다",
                3: "커밋을 분석한 변경 요약이 댓글로 달립니다",
            },
            "release": {
                1: "개발 브랜치에서 main으로 릴리스 PR을 열면",
                2: "릴리스 노트 작성 → 버전 확정 → 자동 머지가 진행됩니다",
                3: "버전이 확정되고 PR이 자동으로 머지됩니다",
                4: "버전 태그도 자동으로 만들어집니다",
            },
        },
    },
}
