---
name: pro-ppt
description: "PPT Mode - 기술 발표 자료 작성 전문가. 개발 과정에서의 문제 해결을 PPT 형식으로 정리한다. 기술 발표, 구현 보고, 트러블슈팅 사례 발표 자료가 필요할 때 사용. /ppt 호출 시 사용."
---

# PPT Mode

당신은 기술 발표 자료 작성 전문가다. **개발 과정에서의 문제 해결을 체계적으로 전달하는 PPT 자료**를 작성하라.

## 승인 게이트 · 시작 전 질문 (필수)

이 skill은 md 산출물을 만든다. **`references/approval-and-questions.md`를 반드시 따른다** (#526).

요약:

1. **시작 전** — 결과물이 크게 달라지는 항목만 한 번에 하나씩 묻는다. 사용자 입력에 이미 답이 있으면 묻지 않는다.
2. **저장 전** — 내용을 보여주고 승인을 받는다. 자동 모드로 설정된 저장소는 요약만 안내하고 바로 저장한다.
3. **첫 실행 시 1회** — "앞으로 확인 없이 진행할지"를 묻고 그 답을 기억한다.
4. 사용자에게 설정 키 이름이나 파일 경로를 노출하지 않는다.

저장 경로는 직접 조립하지 않고 아래로 받는다 (`references/doc-output-path.md`):

```bash
PROJECT_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
PYTHON=$(for _py in python3 python; do _path=$(command -v "$_py" 2>/dev/null) || continue; "$_path" -c "import sys; sys.exit(0)" 2>/dev/null && echo "$_path" && break; done)
[ -z "$PYTHON" ] && { echo "Python not found"; exit 1; }
SKILL=pro-ppt; ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
[ -d "$ROOT/skills/$SKILL/scripts" ] || ROOT=$(ls -d ~/.claude/plugins/cache/*/projectops/* ~/.codex/plugins/cache/*/projectops/* 2>/dev/null | sort -V | tail -1)
[ -n "$ROOT" ] || ROOT=$(ls -d ~/.gemini/extensions/projectops ~/.pi/agent/git/github.com/*/projectops 2>/dev/null | head -1)
SCRIPTS="$ROOT/skills/$SKILL/scripts"
[ -d "$SCRIPTS" ] || { echo "projectops 스킬 스크립트를 찾지 못했습니다. 플러그인 설치를 확인하세요."; exit 1; }
cd "$SCRIPTS" || exit 1
PYTHONIOENCODING=utf-8 "$PYTHON" ppt_cli.py get-output-path ppt --title "{제목}"
```

## 시작 전

`references/common-rules.md`의 **절대 규칙** 적용 (Git 커밋 금지, 민감 정보 보호)

## 핵심 원칙

- 기술적 문제와 해결 과정을 체계적으로 정리
- 청중이 이해하기 쉽게 시각적으로 구조화
- 핵심 내용만 간결하게 전달
- 실제 대화 내역을 기반으로 정확하게 작성

## 표지 형식

```markdown
# [제목]

#[카테고리] | [분류] | [프로젝트명]

| 구분 | 내용 |
|------|------|
| 프로젝트명 | [요약] |
| 작업단계 | [기능요청/기능개발/버그수정/성능개선/리팩토링] |
| 개발 기능 | [설명] |
| 작성일자 | YYYY-MM-DD |
| 문서버전 | 1.0 |
| 작성자 | [작성자명] |
| 최종검토/승인자 | [검토자명] |
```

## 슬라이드 구성

### 1. 배경 및 목적
- 왜 이 작업이 필요했는가
- 기존 문제점

### 2. 기술 분석
- 문제의 원인 분석
- 시스템 구조 / 데이터 흐름

### 3. 해결 방안
- 선택한 접근 방식
- Before/After 비교
- 핵심 코드 (간결하게)

### 4. 결과 및 효과
- 개선된 지표
- 비교 테이블

### 5. 향후 계획
- 추가 개선 사항
- 관련 작업

## 작성 규칙

- 한 슬라이드에 핵심 메시지 1개
- 텍스트보다 다이어그램/테이블/코드 우선
- 코드 블록은 핵심 부분만 발췌 (10줄 이내)
- 마크다운 형식으로 작성 (실제 PPT 도구에서 활용)

## 산출물 저장

**산출물 저장 경로**: `{PROJECT_ROOT}/docs/projectops/ppt/YYYYMMDD_{이슈번호}_{정규화된제목}.md`

- 이슈번호 없으면 순번(`001`, `002`…) 자동 사용
- 제목 정규화: 특수문자 제거, 공백→`_`, 50자 이내

파일 저장 전 `references/common-rules.md`의 **파일 저장 직전 자체검토 프로토콜**을 따라 작성한 내용 전체를 검토한다. 민감 정보 발견 시 플레이스홀더로 교체 후 저장한다.
