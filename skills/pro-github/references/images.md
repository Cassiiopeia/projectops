# 이미지 첨부 (이슈 본문 · 댓글 · PR 본문 공통)

> 언제 읽나: 스크린샷·증적 이미지를 이슈·댓글·PR에 넣을 때.

명령은 `PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py ...` 형태다 (SKILL.md "스크립트 찾기").

글로만 남기던 테스트 결과에 화면을 함께 붙인다. GitHub 공식 첨부 업로드는 **브라우저 세션이 필요해 PAT로 쓸 수 없다.** 그래서 증적 전용 릴리스(`qa-evidence`)에 자산으로 올리고 그 URL을 마크다운에 넣는다 — 이슈 본문과 댓글 양쪽에서 `<img>`로 렌더링되는 것을 실측으로 확인했다.

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py upload-image {owner} {repo} {파일...} --prefix issue585
# --tag {태그} : 증적 릴리스 태그 (기본 qa-evidence)
```

출력 JSON의 **`markdown` 필드를 본문 파일에 그대로 붙여넣는다.** 여러 장을 한 번에 올릴 수 있다.

```json
{"count": 2, "markdown": "![step1](https://...)\n![step2](https://...)",
 "images": [{"name": "...", "url": "...", "asset_id": 123, "renderable": true}],
 "private_warning": null}
```

**쓰는 순서**: `upload-image`로 URL을 받는다 → 그 마크다운을 본문 `.md` 파일에 넣는다 → `create-issue` / `add-comment` / `update-pr`로 올린다. 순서를 뒤집으면 이미지 없는 본문이 먼저 올라간다.

| 알아둘 것 | 내용 |
|---|---|
| **private 레포** | 익명 접근이 막혀 **렌더링되지 않는다.** `private_warning`으로 미리 알려준다 |
| 렌더링되는 형식 | `.png` `.jpg` `.gif` `.webp` `.svg` — 그 밖(mp4 등)은 링크로만 남는다 |
| 파일 이름 | 한글·공백은 URL에서 깨지므로 자동으로 영숫자로 정리하고 시각을 붙여 고유화한다 |
| 되돌리기 | `delete-image {owner} {repo} {asset_id}` — 검증용으로 올린 것을 치울 때 |

```bash
PYTHONIOENCODING=utf-8 {PYTHON} {SCRIPTS}/github_cli.py delete-image {owner} {repo} {asset_id}
```

> 레포에 커밋하는 방식은 쓰지 않는다 — 이미지가 git 히스토리에 영구히 남아 레포가 무거워진다.
