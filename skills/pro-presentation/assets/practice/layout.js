// Practice screen layout: font size (A- A+) · border drag (right column width, slide height) > saved to the deck (.presentation/layout.json)
// Uses practice.js globals (elements) and slides.js fitSlideFrame. Fires a "layout-changed" event on change (popout.js relays it to other windows)
"use strict";

// Font scale step: 10%
const SCALE_STEP = 0.1;
const SCALE_RANGE = [0.5, 2.5];
const PANEL_WIDTH_RANGE_PIXELS = [200, 2400];
// Max right column width (relative to window width, same as 70vw in practice.css main)
const PANEL_WIDTH_MAXIMUM_RATIO = 0.7;
const SLIDE_HEIGHT_RATIO_RANGE = [0.1, 0.9];
const SLIDE_ASPECT_RATIO = 16 / 9;
const LAYOUT_SAVE_DELAY_MILLISECONDS = 300;
// Layout values > CSS variables (a missing value removes the variable, falling back to practice.css defaults)
const LAYOUT_CSS_VARIABLES = {
  script_scale: ["--script-scale", (scale) => String(scale)],
  panel_scale: ["--panel-scale", (scale) => String(scale)],
  panel_width_pixels: ["--panel-width", (pixels) => `${pixels}px`],
  slide_height_ratio: ["--slide-height", (ratio) => `${ratio * 100}vh`],
};

let layout = {};
let layoutSaveTimer = null;

const clampToRange = (number, [minimum, maximum]) => Math.min(maximum, Math.max(minimum, number));

// Layout > screen (CSS variables + scale display)
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

// Change one value (null = default): apply on screen > notify other windows > save shortly after (so dragging does not flood requests)
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
  } catch { /* Save failed: keep the on-screen layout, retry on the next change */ }
}

// Font size buttons: data-step -1 smaller · 0 default · 1 larger
for (const group of document.querySelectorAll("[data-scale]")) {
  group.addEventListener("click", (event) => {
    const button = event.target.closest("[data-step]");
    if (!button) return;
    const step = Number(button.dataset.step);
    const scale = clampToRange((layout[group.dataset.scale] ?? 1) + step * SCALE_STEP, SCALE_RANGE);
    changeLayout(group.dataset.scale, step === 0 ? null : Math.round(scale * 10) / 10);
  });
}

// Border drag: compute value while held and moved, double-click resets to default
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

// Right column width: column right edge <-> handle center (excluding the gap between handle and column)
enableSplitter(elements.columnSplitter, "panel_width_pixels", (event) => {
  const panelRight = elements.sidePanel.getBoundingClientRect().right;
  const gapPixels = elements.sidePanel.getBoundingClientRect().left - elements.columnSplitter.getBoundingClientRect().right;
  const widthPixels = panelRight - event.clientX - elements.columnSplitter.offsetWidth / 2 - gapPixels;
  const maximumPixels = Math.min(PANEL_WIDTH_RANGE_PIXELS[1], window.innerWidth * PANEL_WIDTH_MAXIMUM_RATIO);
  return Math.round(clampToRange(widthPixels, [PANEL_WIDTH_RANGE_PIXELS[0], maximumPixels]));
});

// Slide height: slide top edge <-> handle (excluding the prev/next row in between). Only up to the height the stage width allows
enableSplitter(elements.rowSplitter, "slide_height_ratio", (event) => {
  const frame = elements.slideFrame.getBoundingClientRect();
  const navigationPixels = elements.rowSplitter.getBoundingClientRect().top - frame.bottom;
  const heightPixels = event.clientY - frame.top - navigationPixels - elements.rowSplitter.offsetHeight / 2;
  const maximumRatio = Math.min(SLIDE_HEIGHT_RATIO_RANGE[1], elements.slideFrame.parentElement.clientWidth / SLIDE_ASPECT_RATIO / window.innerHeight);
  return Math.round(clampToRange(heightPixels / window.innerHeight, [SLIDE_HEIGHT_RATIO_RANGE[0], maximumRatio]) * 1000) / 1000;
});

// When the slide cell size changes (border drag · pop-out · window size), refit the iframe scale
new ResizeObserver(fitSlideFrame).observe(elements.slideFrame);

(async function loadLayout() {
  try {
    applyLayout(await (await fetch("/api/layout", { cache: "no-store" })).json());
  } catch { applyLayout({}); }
})();
