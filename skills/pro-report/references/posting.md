# GitHub 포스팅 · 이미지 첨부 상세

> 언제 읽나: 보고서를 이슈 댓글로 올리기 전(이슈 번호·PAT·repo 판정), 스크린샷을 함께 올릴 때.

## 이슈 번호 자동 감지 순서

1. 현재 작업 디렉토리 경로(worktree 폴더명)에서 `YYYYMMDD_숫자_제목` 패턴 추출
2. git 브랜치명에서 추출 (`git rev-parse --abbrev-ref HEAD`의 `YYYYMMDD_#번호_제목`)
3. 대화에서 사용자가 말한 이슈 번호 (develop 직행처럼 브랜치명에 번호가 없을 때)
4. 위 방법 모두 실패 시 사용자에게 이슈 번호 질문

## PAT · repo 확인

1. **PAT 확인**: `../../references/config-rules.md` §2~3 절차로 config 읽기. 파일이 없으면 로컬 저장만 하고 종료. 해당 repo의 `pat`(non-null) 또는 `global_pat` 사용.

   > ⚠️ **config는 탐색 금지.** config.json은 고정 경로 `{HOME}/.projectops/config/config.json` 한 곳뿐 — Read tool로 바로 읽는다. 스크립트(`report_cli.py`) 탐색용 `ls ~/.claude/plugins/cache/...` 패턴을 config 찾기에 쓰지 마라. config는 그 캐시 안에 없다.

2. **repo 확인**: `git remote get-url origin`에서 `owner`/`repo` 추출, 실패 시 config의 `repos`에서 `default: true`인 repo 사용.

## `add-comment` 동작

- 인라인 Python 작성 금지. 보고서 본문은 이미 저장된 `.md` 파일을 `body_file`로 그대로 전달하므로 한국어·이모지·줄바꿈·mermaid 블록이 안전하게 보존된다.
- **PAT는 report_cli가 config.json에서 자동 로드하므로 `GITHUB_PAT=`는 생략 가능**하다(환경변수가 있으면 우선 사용).
- 출력은 JSON: `{"ok": true, "id": ..., "url": "https://github.com/.../issues/{번호}#issuecomment-...", "summary": ..., "next": null}`. `url` 필드를 완료 메시지에 사용한다.
- **Windows + macOS/WSL 호환**: self-contained 5줄 패턴이라 cwd·환경변수 상태 무관하게 동작.
- GitHub 댓글은 mermaid 블록을 렌더링하므로 흐름도가 그대로 표시된다.

## 스크린샷·증적 이미지 첨부

보고서에 **화면이 필요하면 이미지를 함께 올린다.** 테스트 결과·장애 재현·UI 변경은 글보다 화면이 증거가 된다.

```bash
# pro-github의 upload-image로 URL을 먼저 받는다 (본문에 넣기 전에)
PYTHONIOENCODING=utf-8 "{PYTHON}" "{pro-github/scripts}/github_cli.py" \
  upload-image {owner} {repo} {이미지파일...} --prefix report{이슈번호}
```

출력 JSON의 `markdown` 필드를 보고서 `.md`에 붙여넣은 뒤 `add-comment`로 올린다.
**순서를 지킨다** — 보고서를 먼저 올리면 이미지 없는 본문이 게시된다.

상세 규칙(형식 제한·private 레포 제약·되돌리기)은 `pro-github` SKILL.md의 "이미지 첨부" 절.

> 이미지가 없으면 넣지 않는다. 의미 없는 스크린샷은 보고서를 길게만 만든다.
