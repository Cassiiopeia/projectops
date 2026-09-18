# Claude Scripts

이 디렉토리는 Claude에서 공통으로 사용할 수 있는 Python 유틸리티 스크립트를 포함합니다.

## 📦 포함된 모듈

### `worktree_manager.py` (v1.0.0)

Git worktree를 자동으로 생성하고 관리하는 스크립트입니다.

#### 기능
- 브랜치가 없으면 자동 생성 (현재 브랜치에서 분기)
- 브랜치명의 특수문자(`#`, `/`, `\` 등)를 안전하게 처리
- `myapp-Worktree` 폴더에 worktree 자동 생성
- 이미 존재하는 worktree는 건너뛰고 경로만 출력

#### 사용법

**직접 실행:**

```bash
python .claude/scripts/worktree_manager.py "20260120_#163_Github_Projects_에_대한_템플릿_개발_필요"
```

#### 출력 예시

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌿 Git Worktree Manager v1.0.0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 입력된 브랜치: 20260120_#163_Github_Projects_에_대한_템플릿_개발_필요
📁 폴더명: 20260120_163_Github_Projects_에_대한_템플릿_개발_필요

🔍 브랜치 확인 중...
⚠️  브랜치가 존재하지 않습니다.
🔄 현재 브랜치(main)에서 새 브랜치 생성 중...
✅ 브랜치 생성 완료!

📂 Worktree 경로: /Users/.../project/myapp-Worktree/20260120_163_Github_Projects_에_대한_템플릿_개발_필요

🔄 Worktree 생성 중...
✅ Worktree 생성 완료!

📍 경로: /Users/.../project/myapp-Worktree/20260120_163_Github_Projects_에_대한_템플릿_개발_필요
```

## ✅ 장점

- 🌏 **한글 경로 완벽 지원**: UTF-8 인코딩으로 저장되어 안전
- 🔄 **재사용 가능**: 모든 프로젝트에서 사용 가능
- 📝 **영구 보관**: 삭제되지 않고 계속 사용 가능
- 🤖 **자동화**: 브랜치 생성부터 worktree 생성까지 자동화
- 📚 **문서화**: 모든 함수에 docstring 포함
