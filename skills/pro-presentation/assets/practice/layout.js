// 연습 화면 배치: 글자 크기(A- A+) · 경계 끌기(오른쪽 열 너비, 슬라이드 높이) > 덱에 저장 (.presentation/layout.json)
// practice.js 의 전역(elements · fitSlideFrame)을 씀. 바뀌면 "layout-changed" 이벤트 (popout.js 가 다른 창에 전달)
"use strict";

// 글자 배율 한 번에 10%
const SCALE_STEP = 0.1;
const SCALE_RANGE = [0.5, 2.5];
const PANEL_WIDTH_RANGE_PIXELS = [200, 2400];
// 오른쪽 열 최대 너비 (창 너비 대비, practice.css main 의 70vw 와 같은 값)
const PANEL_WIDTH_MAXIMUM_RATIO = 0.7;
const SLIDE_HEIGHT_RATIO_RANGE = [0.1, 0.9];
const SLIDE_ASPECT_RATIO = 16 / 9;
const LAYOUT_SAVE_DELAY_MILLISECONDS = 300;
// 배치 값 > CSS 변수 (값이 없으면 변수를 지워 practice.css 기본값)
const LAYOUT_CSS_VARIABLES = {
  script_scale: ["--script-scale", (scale) => String(scale)],
  panel_scale: ["--panel-scale", (scale) => String(scale)],
  panel_width_pixels: ["--panel-width", (pixels) => `${pixels}px`],
  slide_height_ratio: ["--slide-height", (ratio) => `${ratio * 100}vh`],
};

let layout = {};
let layoutSaveTimer = null;

const clampToRange = (number, [minimum, maximum]) => Math.min(maximum, Math.max(minimum, number));

// 배치 > 화면 (CSS 변수 + 배율 표시)
function applyLayout(nextLayout) {
  layout = nextLayout;
  for (const [name, [property, formatValue]] of Object.entries(LAYOUT_CSS_VARIABLES)) {
    if (layout[name] == null) document.documentElement.style.removeProperty(property);
    else document.documentElement.style.setProperty(property, formatValue(layout[name]));
  }
  for (const group of document.querySelectorAll("[data-scale]")) {
    group.querySelector(".scale-value").textContent = `${Math.round((layout[group.dataset.scale] ?? 1) * 100)}%`;
  }
}

// 값 하나 바꾸기 (null = 기본값): 화면 반영 > 다른 창에 알림 > 잠시 뒤 저장 (끄는 동안 요청이 몰리지 않게)
function changeLayout(name, nextValue) {
  const nextLayout = { ...layout };
  if (nextValue == null) delete nextLayout[name];
  else nextLayout[name] = nextValue;
  applyLayout(nextLayout);
  window.dispatchEvent(new CustomEvent("layout-changed", { detail: layout }));
  clearTimeout(layoutSaveTimer);
  layoutSaveTimer = setTimeout(saveLayout, LAYOUT_SAVE_DELAY_MILLISECONDS);
}

async function saveLayout() {
  try {
    await fetch("/api/layout", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(layout) });
  } catch { /* 저장 실패: 화면 배치는 그대로, 다음 변경 때 다시 저장 */ }
}

// 글자 크기 단추: data-step -1 작게 · 0 기본값 · 1 크게
for (const group of document.querySelectorAll("[data-scale]")) {
  group.addEventListener("click", (event) => {
    const button = event.target.closest("[data-step]");
    if (!button) return;
    const step = Number(button.dataset.step);
    const scale = clampToRange((layout[group.dataset.scale] ?? 1) + step * SCALE_STEP, SCALE_RANGE);
    changeLayout(group.dataset.scale, step === 0 ? null : Math.round(scale * 10) / 10);
  });
}

// 경계 끌기: 누른 채 움직이면 값 계산, 두 번 누르면 기본값
function enableSplitter(splitter, name, readValueAtPointer) {
  splitter.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    splitter.setPointerCapture(event.pointerId);
    splitter.classList.add("dragging");
  });
  splitter.addEventListener("pointermove", (event) => {
    if (splitter.hasPointerCapture(event.pointerId)) changeLayout(name, readValueAtPointer(event));
  });
  for (const endEvent of ["pointerup", "pointercancel"]) {
    splitter.addEventListener(endEvent, () => splitter.classList.remove("dragging"));
  }
  splitter.addEventListener("dblclick", () => changeLayout(name, null));
}

// 오른쪽 열 너비: 열 오른쪽 끝 <-> 손잡이 가운데 (손잡이와 열 사이 간격 제외)
enableSplitter(elements.columnSplitter, "panel_width_pixels", (event) => {
  const panelRight = elements.sidePanel.getBoundingClientRect().right;
  const gapPixels = elements.sidePanel.getBoundingClientRect().left - elements.columnSplitter.getBoundingClientRect().right;
  const widthPixels = panelRight - event.clientX - elements.columnSplitter.offsetWidth / 2 - gapPixels;
  const maximumPixels = Math.min(PANEL_WIDTH_RANGE_PIXELS[1], window.innerWidth * PANEL_WIDTH_MAXIMUM_RATIO);
  return Math.round(clampToRange(widthPixels, [PANEL_WIDTH_RANGE_PIXELS[0], maximumPixels]));
});

// 슬라이드 높이: 슬라이드 위 끝 <-> 손잡이 (사이의 이전·다음 줄 높이 제외). 무대 너비가 허락하는 높이까지만
enableSplitter(elements.rowSplitter, "slide_height_ratio", (event) => {
  const frame = elements.slideFrame.getBoundingClientRect();
  const navigationPixels = elements.rowSplitter.getBoundingClientRect().top - frame.bottom;
  const heightPixels = event.clientY - frame.top - navigationPixels - elements.rowSplitter.offsetHeight / 2;
  const maximumRatio = Math.min(SLIDE_HEIGHT_RATIO_RANGE[1], elements.slideFrame.parentElement.clientWidth / SLIDE_ASPECT_RATIO / window.innerHeight);
  return Math.round(clampToRange(heightPixels / window.innerHeight, [SLIDE_HEIGHT_RATIO_RANGE[0], maximumRatio]) * 1000) / 1000;
});

// 슬라이드 칸 크기가 바뀌면 (경계 끌기 · 창 분리 · 창 크기) iframe 배율 다시 맞춤
new ResizeObserver(fitSlideFrame).observe(elements.slideFrame);

(async function loadLayout() {
  try {
    applyLayout(await (await fetch("/api/layout", { cache: "no-store" })).json());
  } catch { applyLayout({}); }
})();
