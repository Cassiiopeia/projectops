// 흐름 보기: 전체 장 카드를 격자로, 끌어서 순서 바꾸기 > deck.json 저장
// practice.js 의 전역(deck · text · elements · showSlide · fetchDeck · createElement)과 slides.js 의 thumbnailUrl · slideBodyKey 를 씀
"use strict";

let draggedSlideId = null;
function renderFlow() {
  if (!document.body.classList.contains("flow")) return;
  elements.flowGrid.replaceChildren(...deck.slides.map((slide, index) => {
    const card = createElement("div", { className: "flow-card", draggable: true });
    const thumb = createElement("div", { className: "flow-thumb" });
    if (slide.thumbnail || slide.image) thumb.append(createElement("img", { src: thumbnailUrl(slide), alt: "", loading: "lazy", decoding: "async" }));
    else if (slide.html != null) thumb.append(createElement("iframe", { src: `/render/${encodeURIComponent(slide.id)}?v=${encodeURIComponent(slideBodyKey(slide))}`, loading: "lazy" }));
    const meta = createElement("div", { className: "flow-meta" });
    meta.append(createElement("span", { className: "badge", textContent: slide.number }),
      createElement("span", { textContent: slide.kind || "" }),
      createElement("span", { textContent: `${text.about} ${slide.estimate_seconds}${text.seconds}` }));
    card.append(thumb, meta, createElement("div", { className: "flow-title", textContent: slide.title }),
      createElement("div", { className: "flow-script", textContent: slide.script }));
    card.addEventListener("click", () => { setFlowMode(false); showSlide(index); });
    card.addEventListener("dragstart", () => { draggedSlideId = slide.id; card.classList.add("dragging"); });
    card.addEventListener("dragend", () => card.classList.remove("dragging"));
    card.addEventListener("dragover", (event) => { event.preventDefault(); card.classList.add("drop-target"); });
    card.addEventListener("dragleave", () => card.classList.remove("drop-target"));
    card.addEventListener("drop", (event) => { event.preventDefault(); card.classList.remove("drop-target"); moveSlide(draggedSlideId, slide.id); });
    return card;
  }));
  requestAnimationFrame(() => {
    for (const frame of elements.flowGrid.querySelectorAll("iframe")) frame.style.transform = `scale(${frame.parentElement.clientWidth / SLIDE_WIDTH_PIXELS})`;
  });
}

async function moveSlide(fromId, toId) {
  if (!fromId || fromId === toId) return;
  const order = deck.slides.map((slide) => slide.id).filter((id) => id !== fromId);
  order.splice(order.indexOf(toId), 0, fromId);
  const response = await fetch("/api/order", { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order, base_version: deck.version }) });
  elements.saveStatus.classList.toggle("error", !response.ok);
  elements.saveStatus.textContent = response.ok ? text.saved : text.changed_on_disk;
  await fetchDeck();
  showSlide(Math.min(currentIndex, deck.slides.length - 1));
}

const setFlowMode = (isFlow) => {
  document.body.classList.toggle("flow", isFlow);
  elements.flow.hidden = !isFlow;
  elements.flowToggle.textContent = isFlow ? text.close_flow : text.flow;
  renderFlow();
};
elements.flowToggle.addEventListener("click", () => setFlowMode(!document.body.classList.contains("flow")));
