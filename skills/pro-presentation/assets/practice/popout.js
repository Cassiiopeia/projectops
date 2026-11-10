// 창 분리: 슬라이드 · 대본 · 피드백/카드를 각자 창으로 (다른 모니터에 놓기) > 창끼리 지금 장 · 배치를 맞춤
// 분리 창 = 같은 페이지의 ?view=slide|script|notes. 본 창은 분리된 부분을 숨기고, 분리 창이 닫히면 되돌림
// practice.js 의 전역(deck · text · elements · currentIndex · showSlide · isEditing · VIEW_NAME), layout.js 의 applyLayout 을 씀
"use strict";

// 분리할 수 있는 부분 > 새 창 처음 크기 (px)
const POP_OUT_WINDOW_SIZES = { slide: [1280, 720], script: [760, 420], notes: [480, 760] };
// 분리 창이 살아 있다고 알리는 주기 · 이 시간 동안 소식이 없으면 닫힌 것으로 봄
const VIEW_ALIVE_INTERVAL_MILLISECONDS = 1000;
const VIEW_ALIVE_TIMEOUT_MILLISECONDS = 3500;
const isViewWindow = VIEW_NAME in POP_OUT_WINDOW_SIZES;
// 같은 주소(포트)의 창끼리만 통함 = 덱 서버 하나의 창들
const windowChannel = "BroadcastChannel" in window ? new BroadcastChannel("presentation-practice") : null;

// 마지막으로 다른 창과 맞춘 장 · 입력 중에 받은 장 (칸을 떠나면 적용)
let syncedSlideIndex = null;
let waitingSlideIndex = null;
// 분리 창마다 마지막 소식 시각 (본 창에서만 씀)
const viewLastSeenAt = {};

if (isViewWindow) document.body.classList.add("view", `view-${VIEW_NAME}`);

function openViewWindow(viewName) {
  const [width, height] = POP_OUT_WINDOW_SIZES[viewName];
  // 창 이름에 포트: 덱 두 개를 동시에 열어도 서로의 분리 창을 가로채지 않음
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

// 이 창에서 장이 바뀌면 다른 창에 알림 (받아서 바꾼 장은 다시 보내지 않음)
window.addEventListener("slide-shown", () => {
  if (isViewWindow) document.title = `${deck.title} · ${{ slide: text.view_slide, script: text.script, notes: text.view_notes }[VIEW_NAME]}`;
  if (currentIndex === syncedSlideIndex) return;
  syncedSlideIndex = currentIndex;
  windowChannel?.postMessage({ type: "slide", index: currentIndex });
});
window.addEventListener("layout-changed", (event) => windowChannel?.postMessage({ type: "layout", layout: event.detail }));

// 다른 창 소식: slide 장 이동 · layout 글자 크기·경계 · view-alive/view-closed 분리 창 열림·닫힘
windowChannel?.addEventListener("message", ({ data }) => {
  if (data.type === "slide") {
    // 입력 중이면 미룸: 지금 바꾸면 고치던 대본이 다른 장에 저장됨
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
  // 닫힘 소식 없이 사라진 분리 창 (강제 종료 등): 소식이 끊기면 그 부분을 본 창에 되돌림
  setInterval(() => {
    for (const viewName of Object.keys(POP_OUT_WINDOW_SIZES)) {
      if (viewLastSeenAt[viewName] && Date.now() - viewLastSeenAt[viewName] > VIEW_ALIVE_TIMEOUT_MILLISECONDS) setViewOpen(viewName, false);
    }
  }, VIEW_ALIVE_INTERVAL_MILLISECONDS);
}
