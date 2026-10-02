📝 현재 문제점
---

- README와 docs/SKILLS.md에 더 이상 없는 스킬명(`/pro-flutter-e2e`)이 남아 있고, 현재 이름인 `pro-agent-test`는 스킬 표에 없다.
- README의 체인지로그 설명에 2026-07-30에 종료된 GitHub Models가 provider로 적혀 있다.
- 완료된 이슈를 닫지 않는 운영 정책 때문에 열린 이슈가 400개를 넘는데, 방문자는 이유를 알 수 없어 방치로 읽을 수 있다.
- 의존성 갱신 봇(dependabot)이 없다.

🛠️ 해결 방안 / 제안 기능
---

- 낡은 서술을 현재 동작에 맞게 교정한다.
- README 지원 절에 이슈 운영 정책을 한 줄로 안내한다.
- github-actions와 npm을 주 1회 갱신하는 `.github/dependabot.yml`을 추가한다.

⚙️ 작업 내용
---

- README.md: 스킬 표, 체인지로그 설명, 지원 절 수정
- docs/SKILLS.md: pro-flutter-e2e 섹션을 pro-agent-test로 교체
- .github/dependabot.yml 신규 추가
