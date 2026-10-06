# projectops에 기여하기

도움을 주셔서 감사합니다. 이 문서는 아이디어에서 병합된 PR까지 필요한 것만 담았습니다.
영문 원본은 [CONTRIBUTING.md](../../CONTRIBUTING.md)입니다. 두 문서가 다르면 영문이 기준입니다.

## 이 프로젝트는

projectops는 저장소에 GitHub Actions 워크플로우, 버전 관리, 이슈/PR 템플릿, 에이전트 스킬을 설치하는
템플릿이자 설치기(`npx projectops`)입니다. 구조는 [docs/NPX-WIZARD.md](../NPX-WIZARD.md)와
[docs/SKILLS.md](../SKILLS.md)에서 시작하세요.

## 기여 방법

- **버그, 기능 요청**: 이슈를 열어 주세요. 이슈 폼을 쓰고, 설치기 문제는 projectops 버전, OS, 실행 로그를 함께 적어 주세요.
- **질문**: 이슈 대신 [Discussions](https://github.com/Cassiiopeia/projectops/discussions)를 써 주세요.
- **작은 수정**: `good first issue`, `help wanted` 라벨이 붙은 이슈를 찾아보세요.
- **큰 변경**(새 프로젝트 타입, 새 워크플로우, 동작 변경): 코드를 쓰기 전에 이슈를 열고 메인테이너의 방향 확인을 기다려 주세요.

## 개발 환경

Node.js 20.12 이상, Python 3.12(스크립트와 스킬 테스트용), Git이 필요합니다.

```bash
git clone https://github.com/<본인>/projectops.git
cd projectops
git remote add upstream https://github.com/Cassiiopeia/projectops.git
python3 -m pip install pytest pyyaml pillow numpy
```

## 테스트

```bash
npm test
python3 -m pytest .github/scripts/test/ -q
python3 -m pytest skills/ -q
python3 -m pytest scripts/tests/ -q
python3 .github/util/flutter/_shared/check-consistency.py   # Flutter 마법사를 고쳤을 때만
```

CI는 Linux, macOS, Windows에서 같은 명령을 돌립니다. 설치기는 macOS(bash 3.2, BSD 도구)와 Windows에서도 동작해야 하므로
`.sh` 파일에 Linux 전용 문법을 쓰지 마세요.

## 브랜치와 커밋

- 브랜치 이름은 `YYYYMMDD_#<이슈번호>_<짧은 제목>`입니다. 이슈 헬퍼 봇이 이슈에 정확한 이름을 댓글로 알려 줍니다.
- `develop`에 완료된 작업이 모이고, `main`은 릴리스 PR로만 갱신됩니다. PR은 `develop`으로 열어 주세요.
- 커밋 메시지: `<이슈 제목> : <type> : <변경 내용> <이슈 URL>`
  - `type`은 `feat`, `fix`, `docs`, `chore`, `refactor`, `test` 중 하나입니다.
  - `feat`는 다음 릴리스를 minor, `feat!`는 major, 나머지는 patch로 올립니다. `!`는 기존 사용자의 설정이나 CLI 인자가 더 이상 동작하지 않을 때만 붙입니다.

## 릴리스

- 릴리스는 묶어서 냅니다. 릴리스 PR(`develop` → `main`)은 하루 한 번까지만 만들고, 사용자가 기다리는 수정이 있을 때만 추가로 냅니다.
- 릴리스 PR의 제목은 `🚀 Deploy <날짜>-v<버전>`입니다. PR 목록에서 숨기려면 `is:pr -head:develop`로 거르세요.
- 이 프로젝트는 활발히 유지보수됩니다. PR은 `.github/CODEOWNERS`에 적힌 코드 오너가 리뷰합니다.

## PR 체크리스트

- [ ] 변경을 설명하는 이슈가 있고 PR이 연결돼 있다
- [ ] 로컬에서 테스트가 통과하고, 새 동작이나 고친 버그에 테스트를 추가했다
- [ ] 사용자에게 보이는 문구는 영문으로 쓰고 `src/i18n/`을 거친다. 한국어는 `ko` 카탈로그에 둔다. 워크플로우와 스크립트가 사용자 레포에 게시하는 문구는 `.github/scripts/i18n/`을 거친다 ([docs/TRANSLATING.md](../TRANSLATING.md) 참고)
- [ ] 공통 워크플로우를 고쳤다면 `.github/workflows/`와 `.github/workflows/project-types/common/` 두 사본을 모두 고쳤다
- [ ] 워크플로우에 `permissions:`가 있고, 새 워크플로우에는 `workflow_dispatch`와 `concurrency`가 있다

## AI 도구를 쓴 기여

AI 도구를 환영합니다. 제출하는 내용의 책임은 제출자에게 있습니다. 모든 줄을 읽고 이해한 뒤 직접 테스트를 돌려 주세요.
에이전트가 변경의 상당 부분을 썼다면 PR 설명에 밝혀 주세요. 사전 이슈 없이 올라온 대규모 자동 생성 리팩터링은 닫힐 수 있습니다.

## 보안, 라이선스

취약점은 공개 이슈로 올리지 마세요. [SECURITY.md](../../SECURITY.md)를 보세요.
기여한 내용은 [MIT 라이선스](../../LICENSE)로 배포되는 데 동의한 것으로 봅니다.
