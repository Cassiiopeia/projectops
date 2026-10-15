# JavaScript 스택 규칙 (TypeScript · React · Next · Node 포함)

> 언제 읽나: 대상에 `package.json`이 있을 때. audit·refactor·init 공통.

## 계층 지도

| 계층 | 위치 (React/Next 기준) | 들어가는 것 |
|---|---|---|
| 표현 | `app/`·`pages/`·`components/` | 화면, 컴포넌트, 화면 상태 |
| 응용 | `hooks/`·`services/`·`store/` | 화면 밖 흐름, 서버 상태 |
| 도메인 | `types/`·`models/`·`domain/` | 타입, 순수 규칙 |
| 인프라 | `api/`·`clients/`·`lib/http` | fetch·axios 클라이언트, 인증 헤더 |
| 공통 | `styles/tokens`·`tailwind.config`·`components/ui` | 토큰, 공통 컴포넌트 |

Node CLI·라이브러리는 `src/cli`(진입점·인자) → `src/core`(로직) 단방향으로 본다. 진입점에 기본값·로직이 다시 생기면 위반.

## 자주 나오는 AI 냄새

- 서버 API 타입을 손으로 복사 (`types/api/*`가 서버 클래스를 흉내) — OpenAPI 생성으로 바꾼다
- 서버 enum·에러 코드를 문자열 리터럴로 비교
- 운영 base URL 하드코딩, 인증 헤더를 인터셉터와 유틸 두 곳에서 붙임
- `#4F46E5` 같은 색 값·`[#hex]` Tailwind 임의값·`style={{` 인라인 스타일 (토큰 우회)
- 같은 이름 다른 구현 (검색바·페이지네이션 2~3종), 아무도 import하지 않는 사본
- `loading`·`open`·`disabled` state (접두사 없음), `any` 타입으로 막기
- `/* eslint-disable */` 파일 머리, 린트 설정 없음

## 첫 규칙 후보

```
# no-hex-color-in-components.rule
description=컴포넌트에서 색 값 직접 사용 금지 (토큰·Tailwind 테마 사용)
paths=src/components/,src/app/
extensions=.tsx,.jsx
pattern=["'`]#[0-9a-fA-F]{6}\b|-\[#[0-9a-fA-F]{3,8}\]

# components-must-not-import-api-client.rule
description=컴포넌트가 HTTP 클라이언트를 직접 import 금지 (hooks·services 경유)
paths=src/components/
extensions=.ts,.tsx,.js,.jsx
pattern=from\s+['"][^'"]*/api/client['"]
```

계층 import는 dependency-cruiser·eslint-plugin-boundaries가 더 정확하다 — 새 의존성이라 **제안만** 한다.

## 규칙 테스트

`install-tests PATH --stack javascript --module <패키지 폴더>` → `test/architecture/architecture.rules.test.mjs`.
`node --test test/architecture`로 돈다 (Node 18+, 추가 의존성 없음). vitest·jest 프로젝트면 `npm test` 스크립트에 이 명령을 덧붙인다.

## 모범 파일 지정

컴포넌트 1개(토큰만 씀), hook 1개(서버 상태가 한 곳), API 모듈 1개(생성된 타입 사용).
