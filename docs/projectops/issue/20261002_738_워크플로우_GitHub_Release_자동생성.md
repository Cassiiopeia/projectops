📝 현재 문제점
---

- 버전 태그는 릴리스마다 만들어지지만(520개) GitHub Releases는 만들어지지 않는다.
- Releases 탭에 정식 릴리스가 없고 증적 보관용 프리릴리스(`qa-evidence`) 하나만 보인다. 방문자가 최신 버전과 변경 내용을 Releases 탭에서 확인할 수 없다.

🛠️ 해결 방안 / 제안 기능
---

- 이 레포 전용 워크플로우인 `PROJECT-TEMPLATE-NPM-PUBLISH`에서 main push 때 version.yml 버전의 GitHub Release를 만든다.
- 릴리스 노트는 `changelog_manager.py export`가 만든 CHANGELOG 내용을 쓴다.
- 이미 Release가 있으면 건너뛰어 재실행해도 안전하게 한다.
- 설치 대상 레포로 복사되는 공통 워크플로우(`RELEASE-CHANGELOG`)는 건드리지 않는다.

⚙️ 작업 내용
---

- PROJECT-TEMPLATE-NPM-PUBLISH.yaml에 `contents: write` 권한과 Release 생성 단계 추가
- 태그가 아직 없을 때를 대비한 재시도와 명확한 실패 메시지
