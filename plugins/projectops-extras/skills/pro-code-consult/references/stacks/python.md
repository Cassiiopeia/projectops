# Python 스택 규칙

> 언제 읽나: 대상에 `pyproject.toml`·`requirements.txt`·`setup.py`가 있을 때. audit·refactor·init 공통.

## 계층 지도

| 계층 | 위치 (FastAPI 기준) | 들어가는 것 |
|---|---|---|
| 표현 | `routers/` | 요청·응답 모델 변환, 의존성 주입 |
| 응용 | `services/` | 업무 규칙 |
| 도메인 | `domain/`·`models/` | 순수 모델·규칙 |
| 인프라 | `repositories/`·`clients/`·`config` | DB, 외부 API, 설정 읽기 |
| 공통 | `core/` (설정·예외·로깅) | |

의존 방향: routers → services → domain ← repositories. **router가 repository·client를 import하면 위반.**
스크립트·CLI 저장소(계층이 없는 경우)는 계층 대신 "진입점은 얇게, 로직은 재사용 모듈에" 하나로 본다.

## 자주 나오는 AI 냄새

- `except Exception: pass` (삼키는 예외), `catch-all`에서 원문 메시지 노출
- 설정 키 문자열·환경변수 이름이 여러 파일에 반복
- "아직 구현되지 않음" 스텁이 운영 경로에 남음
- 여러 줄 docstring이 함수보다 김, 모듈 머리 docstring에 작업 경위
- `ok: bool`·`strict: bool` (접두사 없음), 함수 `-> bool`인데 이름이 동사(`create_branch`)
- `tmp`·`res`·`cfg`·`util` 같은 약어·뜻 없는 이름

## 첫 규칙 후보

```
# router-must-not-import-repository.rule
description=라우터가 저장소·외부 클라이언트를 직접 import 금지 (서비스 경유)
paths=app/routers/
extensions=.py
pattern=^(?:from|import)\s+[\w.]*(?:repositories|clients)\b

# no-swallowed-exception.rule
description=예외를 조용히 삼키기 금지 (로그 또는 재발생)
paths=app/
extensions=.py
pattern=except[^:\n]*:\s*\n\s*pass\b
```

계층 import는 import-linter(`[importlinter]` contracts)가 더 정확하다 — 새 의존성이라 **제안만** 한다.

## 규칙 테스트

`install-tests PATH --stack python --module <패키지 폴더>` → `tests/architecture/test_architecture_rules.py`. pytest만 쓴다.

## 모범 파일 지정

라우터 1개(얇음), 서비스 1개(단계 머리글 주석·질문형 boolean), 클라이언트 1개(타임아웃·재시도가 한 곳).
