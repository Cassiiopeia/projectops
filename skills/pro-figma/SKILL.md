---
name: pro-figma
description: "Figma Design Mode - Figma 디자인을 반응형 코드로 지능적으로 변환한다. Figma에서 복사한 CSS/값을 받아 React(Tailwind/Styled), React Native, Flutter 코드로 변환할 때 사용. px 하드코딩 대신 반응형 단위를 사용한다. /figma 호출 시 사용."
---

# Figma Design Mode

당신은 디자인 시스템 전문가다. **Figma 디자인을 반응형 코드로 지능적으로 변환**하라.

## 시작 전

1. `../references/common-rules.md`의 **작업 시작 프로토콜** 수행
2. 스타일링 방식 추가 확인:
   - React: `tailwind.config.js` / `styled-components` / CSS Modules / Emotion
   - React Native: `StyleSheet`, `Dimensions` 패턴
   - Flutter: `Theme`, `MediaQuery` 패턴
3. 기존 디자인 시스템 확인 (spacing scale, typography, color tokens, breakpoints)

## 덤프가 있으면 먼저 센다 ⚠️

Figma MCP 로 노드를 받았다면(붙여넣은 CSS 몇 줄이 아니라) **코드를 쓰기 전에 덤프의
스타일 항목을 전부 나열**하고 그것을 작업 목록으로 삼는다.

```bash
# 덤프를 JSON 파일로 저장한 뒤
PYTHONIOENCODING=utf-8 {PYTHON} {pro-figma-verify/scripts}/figma_verify_cli.py coverage \
  --dump {덤프.json} --node {노드 id}
```

나온 항목을 **하나도 남기지 않고** 구현 / 근사(사유) / 생략(사유) 로 처리한다.

> **왜 세어야 하나.** 덤프의 `effects` 가 네 줄인데 그중 **한 줄만 옮긴 채** 배포된
> 적이 있다. 나머지 세 줄이 그 버튼을 "빛나는" 것으로 보이게 하는 부분이었고,
> 디자이너가 배포 **후에** 알려줬다. 그림만 보고 옮기면 작고 은은한 효과는 그냥
> 빠진다 — 빠진 줄은 애초에 눈에 안 띄기 때문이다.
>
> 이 스킬은 오랫동안 **크기·여백·글자 크기·모서리** 만 다뤘다. 채움·테두리·효과를
> 볼 자리가 없어서 빠뜨려도 아무도 몰랐다.

프레임워크가 시안 값을 그대로 못 받는 자리(예: 안쪽 그림자)는
`../pro-figma-verify/references/framework-gaps.md` 에 정리돼 있다.
**근사·생략은 코드 주석에 사유를 남긴다** — 남기지 않으면 못 옮긴 것인지 안 옮기기로
한 것인지 나중에 아무도 구분하지 못한다.

## 핵심 원칙

- **px 하드코딩 절대 금지** — 반응형 단위 사용
- **디자인 기준 화면 대비 비율 계산**
- **디자인 토큰/시스템 활용**
- **프로젝트 기존 스타일 패턴 준수**

## 변환 로직

### Width/Height

| 상황 | 변환 |
|------|------|
| 전체 너비 (90%+) | `width: 100%` + 부모 padding |
| 고정 크기 (아이콘/버튼) | `rem` 단위 또는 고정값 |
| 중간 크기 | `%` 또는 `clamp(min, preferred, max)` |

### Padding/Margin

| 상황 | 변환 |
|------|------|
| 디자인 시스템 간격 | spacing token (p-4, 1rem 등) |
| 화면 비례 여백 | `vw` 또는 `clamp()` |

### Font Size
- `rem` 기준, 반응형은 `clamp(min, preferred, max)`

### Border Radius
- `rem` 또는 프레임워크 토큰 (rounded-xl 등)

## 기술별 변환

### React + Tailwind
```
Figma 343px (375 기준) → w-full + px-4 부모
Figma 56px height → h-14
Figma 16px font → text-base
Figma 12px radius → rounded-xl
```

### React + Styled Components
```
pxToVw 헬퍼 사용, theme spacing/breakpoints 활용
clamp() 적극 활용
```

### React Native
```
Dimensions.get('window') 기준
scale(size) = (SCREEN_WIDTH / DESIGN_WIDTH) * size
Math.max/min으로 최소/최대 제한
```

### Flutter
```
MediaQuery 기반 SizeConfig
Extension: 343.w, 56.h, 16.sp
EdgeInsets.symmetric(horizontal: 24.w, vertical: 16.h)
```

## 출력 형식

```markdown
### 🎨 디자인 분석
**프로젝트 타입**: [타입]  **스타일링**: [방식]
**Figma 기준**: 캔버스 [크기], 컨테이너 padding [크기]

### 📐 Figma 값 분석
[원본 CSS] → [지능적 계산 과정]

### ✨ 변환된 코드
[프로젝트 스타일 준수한 반응형 코드]

### 📱 반응형 전략
[모바일 → 태블릿 → 데스크톱 전략]

### 🎯 디자인 토큰
[Spacing + Typography 토큰]
```

## 체크리스트

- [ ] px 하드코딩 제거
- [ ] 반응형 단위 사용 (%, rem, vw)
- [ ] 디자인 토큰 활용
- [ ] 프로젝트 스타일 준수
- [ ] 최소/최대 크기 제한 (clamp)
- [ ] 브레이크포인트 고려

**시안 값이 다 왔는가** (덤프가 있을 때)

- [ ] `coverage` 가 나열한 항목을 **하나도 남기지 않고** 분류했다
- [ ] `fills` · `strokes` · `effects` 를 **배열 원소마다** 확인했다
- [ ] 근사·생략에 **사유**를 코드 주석으로 남겼다
- [ ] 기존 에셋·컴포넌트를 재사용했다면 **색·굵기까지** 시안과 맞는지 봤다

> 옮긴 뒤에는 `pro-figma-verify` 로 **픽셀까지** 맞대 본다. 그림자·발광·1px 테두리는
> 전체 화면에서 보면 있으나 없으나 비슷해 보여서, 값 확인만으로는 남는 구멍이 있다.
