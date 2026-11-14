// Pop-out: slide · script · feedback/cards each in its own window (for another monitor) > windows sync the current slide and layout
// Pop-out window = same page with ?view=slide|script|notes. The main window hides popped-out parts and restores them when that window closes
// Uses practice.js globals (deck · text · elements · currentIndex · showSlide · isEditing · VIEW_NAME) and layout.js applyLayout
"use strict";

// Parts that can pop out > initial size of the new window (px)
const POP_OUT_WINDOW_SIZES = { slide: [1280, 720], script: [760, 420], notes: [480, 760] };
// Interval for a pop-out window to report it is alive · no news for this long counts as closed
const VIEW_ALIVE_INTERVAL_MILLISECONDS = 1000;
const VIEW_ALIVE_TIMEOUT_MILLISECONDS = 3500;
const isViewWindow = VIEW_NAME in POP_OUT_WINDOW_SIZES;
// Only windows on the same address (port) talk = windows of one deck server
const windowChannel = "BroadcastChannel" in window ? new BroadcastChannel("presentation-practice") : null;

// Last slide synced with other windows · slide received while typing (applied when leaving the field)
let syncedSlideIndex = null;
let waitingSlideIndex = null;
// Last news time per pop-out window (main window only)
const viewLastSeenAt = {};

if (isViewWindow) document.body.classList.add("view", `view-${VIEW_NAME}`);

function openViewWindow(viewName) {
  const [width, height] = POP_OUT_WINDOW_SIZES[viewName];
  // Port in the window name: two decks open at once do not steal each other's pop-out windows
  const opened = window.open(`/?view=${viewName}`, `presentation-${location.port}-${viewName}`, `popup,width=${width},height=${height}`);
  if (opened) return;
  elements.saveStatus.classList.add("error");
  elements.saveStatus.textContent = text.popup_blocked;
}

function showSyncedSlide(index) {
  if (!deck) return;
  syncedSlideIndex = index;
  showSlide(index);
}

function setViewOpen(viewName, isOpen) {
  viewLastSeenAt[viewName] = isOpen ? Date.now() : 0;
  document.body.classList.toggle(`out-${viewName}`, isOpen);
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-pop-out]");
  if (button) openViewWindow(button.dataset.popOut);
});

// Tell other windows when this window changes slide (a slide received from them is not sent back)
window.addEventListener("slide-shown", () => {
  if (isViewWindow) document.title = `${deck.title} · ${{ slide: text.view_slide, script: text.script, notes: text.view_notes }[VIEW_NAME]}`;
  if (currentIndex === syncedSlideIndex) return;
  syncedSlideIndex = currentIndex;
  windowChannel?.postMessage({ type: "slide", index: currentIndex });
});
window.addEventListener("layout-changed", (event) => windowChannel?.postMessage({ type: "layout", layout: event.detail }));

// News from other windows: slide move · layout font size/borders · view-alive/view-closed pop-out opened/closed
windowChannel?.addEventListener("message", ({ data }) => {
  if (data.type === "slide") {
    // Defer while typing: changing now would save the script being edited onto another slide
    if (isEditing()) waitingSlideIndex = data.index;
    else showSyncedSlide(data.index);
  } else if (data.type === "layout") {
    applyLayout(data.layout);
  } else if (!isViewWindow && data.view in POP_OUT_WINDOW_SIZES) {
    setViewOpen(data.view, data.type === "view-alive");
  }
});

for (const field of [elements.script, elements.memo]) {
  field.addEventListener("blur", () => {
    if (waitingSlideIndex == null) return;
    const index = waitingSlideIndex;
    waitingSlideIndex = null;
    showSyncedSlide(index);
  });
}

if (isViewWindow) {
  const announceAlive = () => windowChannel?.postMessage({ type: "view-alive", view: VIEW_NAME });
  announceAlive();
  setInterval(announceAlive, VIEW_ALIVE_INTERVAL_MILLISECONDS);
  window.addEventListener("pagehide", () => windowChannel?.postMessage({ type: "view-closed", view: VIEW_NAME }));
} else {
  // Pop-out window gone without a close message (force quit etc.): when news stops, return that part to the main window
  setInterval(() => {
    for (const viewName of Object.keys(POP_OUT_WINDOW_SIZES)) {
      if (viewLastSeenAt[viewName] && Date.now() - viewLastSeenAt[viewName] > VIEW_ALIVE_TIMEOUT_MILLISECONDS) setViewOpen(viewName, false);
    }
  }, VIEW_ALIVE_INTERVAL_MILLISECONDS);
}
