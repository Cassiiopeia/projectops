📝 현재 문제점
---

- `pro-figma-verify/references/rendering.md`가 앱 화면을 찍는 법(`simctl`, `adb`, Playwright locator 캡처)을 따로 안내한다. 같은 안내가 `pro-agent-test` 문서에도 있어 **두 벌**이다.
- `get-output-path`도 `figma_verify_cli.py:860`에 따로 구현돼 있다.
- #629, #632로 실행·캡처·렌더가 `pro-launch`에 모이면 figma-verify 쪽 안내는 낡은 복사본이 된다.

🛠️ 해결 방안 / 제안 기능
---

- 찍는 법은 `pro-launch`(`app shot` · `web shot` · `render run` · `references/render.md`)를 가리키게 바꾼다.
- **figma-verify에만 해당하는 내용은 남긴다**: RepaintBoundary 3배 캡처(시안 배율 맞추기), "골든 파일은 대조 대상이 아니다", 안전영역 재현값.
- 선행: #632 (render), #630 (Figma 규칙 공용화와 같은 문서를 건드리므로 순서를 맞춘다)
- 설계: `docs/superpowers/specs/2026-09-25-pro-launch-design.md` §8

⚙️ 작업 내용
---

- [ ] `references/rendering.md`에서 스택별 찍는 법을 `pro-launch` 링크 + 호출 예로 바꾼다
- [ ] 시안 대조 전용 내용(3배 캡처, 골든 ≠ 대조 기준, 안전영역)은 남기고 "왜 pro-launch 기본값과 다른가"를 한 줄씩 적는다
- [ ] `figma_verify_cli.py get-output-path`가 `common/paths.py`의 `resolve_output_path`를 쓰는지 확인한다. 아니면 맞춘다
- [ ] SKILL.md Phase 5(픽셀로 맞댄다)의 캡처 단계를 `launch_cli.py render run` / `app shot` 호출로 바꾼다
- [ ] 옛 안내 문구(`xcrun simctl io booted screenshot` 등)가 figma-verify 안에 남지 않았는지 grep으로 확인한다

**완료 기준**
- [ ] `pytest skills/pro-figma-verify/tests scripts/tests` 통과
- [ ] 실측: Flutter 레포 한 화면을 `render run` → `diff`까지 새 안내대로 끝까지 수행

🙋‍♂️ 담당자
---

- 백엔드: 
- 프론트엔드: 
- 디자인: 
