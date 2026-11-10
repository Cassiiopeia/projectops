// 연습 화면: 덱 읽기 > 장 그리기 > 고친 대본·메모 저장 > 덱 파일이 바뀌면 다시 그리기
"use strict";

const VERSION_CHECK_MILLISECONDS = 2000;
// 분리 창 주소 ?view=slide|script|notes (popout.js): 그 부분만 보이는 창, 크게 보기 없음
const VIEW_NAME = new URLSearchParams(location.search).get("view");
const SLIDE_WIDTH_PIXELS = 1920;
// 에이전트용 카드 (화면에 안 보임): 장 제목 · 가져온 원본 글 · 다시 지을 표시
const HIDDEN_NOTE_TITLES = new Set(["title", "original text", "rebuild"]);
const ENGLISH_TEXT = {
  estimate: "Script estimate", start: "Start", pause: "Pause", reset: "Reset", big: "Big view", small: "Normal view",
  fullscreen: "Full screen (F)", presenter: "Presenter view", practice: "Practice view", previous: "Previous",
  next: "Next", script: "Script", take: "What you said", feedback: "Feedback", older_takes: "Earlier takes",
  recording: "Said in the recording", memo: "My memo", no_recording: "Nothing said on this slide",
  next_slide: "Next", last_slide: "Last slide", about: "about", seconds: "s", recorded: "recorded",
  saved: "Saved", save_failed: "Save failed", changed_on_disk: "The file changed on disk, reloaded",
  missing_slide: "This slide has no slide.html or picture",
  // 카드 제목에 이 말이 있으면 주의 카드 색 (| 로 구분, 언어 사전이 덧붙임)
  warn_card_words: "caution|warning|recording",
  flow: "Flow", flow_help: "Drag a slide to change the order. Click one to open it.", close_flow: "Back to practice",
  record: "Record", stop_recording: "Stop", recording_saving: "Saving the recording...", recording_saved: "Recording saved",
  recording_failed: "Recording was not saved", mic_denied: "Microphone access was blocked",
  record_unsupported: "This browser cannot record audio",
  text_smaller: "Smaller text", text_larger: "Larger text", text_reset: "Back to the default text size",
  resize_hint: "Drag to resize, double-click to reset", pop_out: "Open in its own window (close it to bring this back)",
  popup_blocked: "The browser blocked the new window",
  out_hint: "Some parts are open in their own windows. Close a window to bring its part back here.", view_slide: "Slide", view_notes: "Feedback and notes",
  help: "Arrow keys move between slides. Edit the script in place; it saves to the deck when you leave the box. Click a recording time to open the video there. Record captures the microphone and the moment each slide is shown.",
};

const elements = Object.fromEntries(
  [...document.querySelectorAll("[id]")].map((element) => [element.id.replace(/-(\w)/g, (_, letter) => letter.toUpperCase()), element])
);
let deck = null;
let text = ENGLISH_TEXT;
let currentIndex = 0;
let selectedRecordingIndex = -1;
let renderedSlideKey = "";

const storageKey = (name) => `presentation:${deck?.title ?? ""}:${name}`;
const formatSeconds = (seconds) => `${Math.floor(seconds / 60)}:${String(Math.round(seconds) % 60).padStart(2, "0")}`;
const isEditing = () => document.activeElement === elements.script || document.activeElement === elements.memo;
const createElement = (tag, properties = {}) => Object.assign(document.createElement(tag), properties);
const countSpoken = (value) => value.replace(/\([^)]*\)/g, "").replace(/[\s.,!?·'"‘’“”~:;\-]/g, "").length;
const estimateSeconds = (value) => Math.round(countSpoken(value) / deck.characters_per_second);

async function loadText(language) {
  if (language === "en") return ENGLISH_TEXT;
  try {
    const response = await fetch(`/assets/i18n.${language}.json`, { cache: "no-store" });
    return response.ok ? { ...ENGLISH_TEXT, ...(await response.json()) } : ENGLISH_TEXT;
  } catch { return ENGLISH_TEXT; }
}

function applyStaticText() {
  for (const element of document.querySelectorAll("[data-text]")) element.textContent = text[element.dataset.text] ?? element.textContent;
  for (const element of document.querySelectorAll("[data-title]")) element.title = text[element.dataset.title] ?? "";
  document.documentElement.lang = deck.language;
  document.title = deck.title;
  elements.deckTitle.textContent = deck.title;
}

// 녹화: 이 장 구간의 줄
function recordingSegment(slide) {
  const recording = deck.recordings[selectedRecordingIndex];
  const range = recording?.ranges[slide.id];
  if (!range) return null;
  return { recording, start: range[0], end: range[1], lines: recording.lines.filter((line) => line.at >= range[0] && line.at < range[1]) };
}

function videoLink(url, seconds) {
  const match = url.match(/(?:youtu\.be\/|v=)([\w-]{6,})/);
  return match ? `https://youtu.be/${match[1]}?t=${seconds}` : url;
}

function renderTotals() {
  const total = deck.slides.reduce((sum, slide) => sum + estimateSeconds(slide.script), 0);
  elements.totalEstimate.textContent = formatSeconds(total) + (deck.time_limit_seconds ? ` / ${formatSeconds(deck.time_limit_seconds)}` : "");
  const recording = deck.recordings[selectedRecordingIndex];
  const ends = recording ? Object.values(recording.ranges).map((range) => range[1]) : [];
  elements.recordingTotal.innerHTML = "";
  if (recording && ends.length) {
    elements.recordingTotal.append(`${recording.label} `, createElement("b", { textContent: formatSeconds(Math.max(...ends)) }));
  }
}

function renderSlideBody(slide) {
  const key = `${slide.id}:${deck.version}`;
  if (key === renderedSlideKey) return;
  renderedSlideKey = key;
  elements.slideFrame.replaceChildren();
  if (slide.html != null) {
    const frame = createElement("iframe", { src: `/render/${encodeURIComponent(slide.id)}?v=${deck.version}`, title: slide.title });
    elements.slideFrame.append(frame);
    fitSlideFrame();
  } else if (slide.image) {
    elements.slideFrame.append(createElement("img", { src: `/${slide.image}?v=${deck.version}`, alt: slide.title }));
  } else {
    elements.slideFrame.append(createElement("div", { className: "slide-error", textContent: text.missing_slide }));
  }
}

function fitSlideFrame() {
  const frame = elements.slideFrame.querySelector("iframe");
  if (frame) frame.style.transform = `scale(${elements.slideFrame.clientWidth / SLIDE_WIDTH_PIXELS})`;
}

function renderList(container, items) {
  container.replaceChildren(...items.map((item) => createElement("li", { textContent: item })));
}

// notes.md 카드: '- ' 줄은 목록, 나머지는 문단
function renderNoteCard(note) {
  const card = createElement("div", { className: `card${new RegExp(text.warn_card_words, "i").test(note.title) ? " warn" : ""}` });
  card.append(createElement("h2", { textContent: note.title }));
  let list = null;
  for (const line of note.body.split("\n")) {
    if (line.trim().startsWith("- ")) {
      list ??= card.appendChild(createElement("ul"));
      list.append(createElement("li", { textContent: line.trim().slice(2) }));
    } else if (line.trim()) {
      list = null;
      card.append(createElement("p", { textContent: line }));
    }
  }
  return card;
}

function renderTakes(slide) {
  const [latest, ...older] = slide.takes;
  elements.takeCard.hidden = !latest;
  if (!latest) return;
  elements.takeBadge.textContent = latest.label;
  elements.takeText.textContent = latest.spoken;
  renderList(elements.takeFeedback, latest.feedback);
  elements.olderTakes.hidden = older.length === 0;
  elements.olderTakesBody.replaceChildren(...older.map((take) => renderNoteCard({ title: take.label, body: [take.spoken, ...take.feedback.map((item) => `- ${item}`)].join("\n") })));
}

function renderRecording(slide) {
  const segment = recordingSegment(slide);
  elements.recordingLines.replaceChildren();
  elements.recordingBadge.textContent = segment ? `${segment.end - segment.start}${text.seconds}` : "";
  if (!segment || segment.lines.length === 0) {
    elements.recordingLines.textContent = text.no_recording;
    return;
  }
  for (const line of segment.lines) {
    const row = createElement("div", { className: "recording-line" });
    const link = createElement("a", { href: videoLink(segment.recording.url, line.at), target: "_blank", rel: "noopener" });
    link.append(createElement("time", { textContent: formatSeconds(line.at) }));
    row.append(link, createElement("span", { textContent: line.text }));
    elements.recordingLines.append(row);
  }
}

function renderEstimate(slide) {
  const segment = recordingSegment(slide);
  const estimate = `${text.about} ${estimateSeconds(elements.script.innerText || slide.script)}${text.seconds}`;
  elements.estimateBadge.textContent = segment ? `${estimate} (${text.recorded} ${segment.end - segment.start}${text.seconds})` : estimate;
}

function renderThumbnails() {
  elements.thumbnails.replaceChildren(...deck.slides.map((slide, index) => {
    const button = createElement("button", { className: index === currentIndex ? "active" : "", title: slide.title });
    if (slide.thumbnail || slide.image) button.append(createElement("img", { src: `/${slide.thumbnail || slide.image}`, alt: "", loading: "lazy" }));
    else button.append(createElement("span", { className: "name", textContent: slide.title }));
    button.append(createElement("span", { className: `label${slide.memo ? " has-memo" : ""}`, textContent: slide.number }));
    button.addEventListener("click", () => showSlide(index));
    return button;
  }));
  elements.thumbnails.children[currentIndex]?.scrollIntoView({ inline: "center", block: "nearest" });
}

function showSlide(index) {
  currentIndex = Math.max(0, Math.min(deck.slides.length - 1, index));
  localStorage.setItem(storageKey("index"), currentIndex);
  const slide = deck.slides[currentIndex];
  const nextSlide = deck.slides[currentIndex + 1];
  renderSlideBody(slide);
  elements.slideTitle.textContent = `${slide.number} / ${deck.slides.length} · ${slide.title}`;
  elements.nextTitle.textContent = nextSlide ? `${text.next_slide}: ${nextSlide.title}` : text.last_slide;
  if (!isEditing()) {
    elements.script.textContent = slide.script;
    elements.memo.value = slide.memo;
  }
  elements.noteCards.replaceChildren(...slide.notes
    .filter((note) => note.body.trim() && !HIDDEN_NOTE_TITLES.has(note.title.toLowerCase())).map(renderNoteCard));
  renderTakes(slide);
  renderEstimate(slide);
  renderRecording(slide);
  renderThumbnails();
  renderTotals();
  elements.problems.hidden = deck.problems.length === 0;
  renderList(elements.problems, deck.problems);
  renderFlow();
  refreshRecordingSelect();
  window.dispatchEvent(new CustomEvent("slide-shown", { detail: slide.id }));
}

// 녹화 목록: 개수가 바뀌면 (연습 화면 녹음 · recording add) 다시 채우고 최신 녹화 선택
function refreshRecordingSelect() {
  if (elements.recordingSelect.options.length === deck.recordings.length) return;
  selectedRecordingIndex = deck.recordings.length - 1;
  elements.recordingSelect.replaceChildren(...deck.recordings.map((recording, index) => new Option(recording.label, index)));
  elements.recordingSelect.value = selectedRecordingIndex;
  elements.recordingCard.hidden = deck.recordings.length === 0;
  renderRecording(deck.slides[currentIndex]);
  renderEstimate(deck.slides[currentIndex]);
  renderTotals();
}

async function fetchDeck() {
  const response = await fetch("/api/deck", { cache: "no-store" });
  deck = await response.json();
}

// 저장: 칸을 떠날 때. 읽은 뒤 파일이 바뀌었으면 서버가 409 > 다시 읽음
async function saveSlideFile(file, value) {
  const slide = deck.slides[currentIndex];
  const original = file === "script" ? slide.script : slide.memo;
  if (value.trim() === original.trim()) return;
  const response = await fetch("/api/save", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slide: slide.id, file, text: value, base_version: deck.version }),
  });
  const result = await response.json().catch(() => ({}));
  elements.saveStatus.classList.toggle("error", !response.ok);
  elements.saveStatus.textContent = response.ok ? text.saved : (result.code === "changed_on_disk" ? text.changed_on_disk : text.save_failed);
  await fetchDeck();
  showSlide(currentIndex);
}

elements.script.addEventListener("input", () => renderEstimate(deck.slides[currentIndex]));
elements.script.addEventListener("blur", () => saveSlideFile("script", elements.script.innerText));
elements.memo.addEventListener("blur", () => saveSlideFile("memo", elements.memo.value));
elements.previous.addEventListener("click", () => showSlide(currentIndex - 1));
elements.next.addEventListener("click", () => showSlide(currentIndex + 1));
elements.recordingSelect.addEventListener("change", () => {
  selectedRecordingIndex = Number(elements.recordingSelect.value);
  showSlide(currentIndex);
});

// 키: 장 이동 · F 전체 화면 (한글 입력 상태에서도 물리 키 code 기준)
const toggleFullscreen = () => document.fullscreenElement ? document.exitFullscreen() : document.querySelector(".stage").requestFullscreen();
document.addEventListener("keydown", (event) => {
  if (isEditing()) return;
  if (["ArrowRight", "PageDown", " "].includes(event.key)) { event.preventDefault(); showSlide(currentIndex + 1); }
  if (["ArrowLeft", "PageUp"].includes(event.key)) { event.preventDefault(); showSlide(currentIndex - 1); }
  if (event.code === "KeyF") toggleFullscreen();
});
elements.fullscreenToggle.addEventListener("click", toggleFullscreen);
document.addEventListener("fullscreenchange", () => requestAnimationFrame(fitSlideFrame));
window.addEventListener("resize", fitSlideFrame);

const setBigMode = (isBig) => {
  if (VIEW_NAME) return;
  document.body.classList.toggle("big", isBig);
  elements.bigToggle.textContent = isBig ? text.small : text.big;
  localStorage.setItem(storageKey("big"), isBig ? "1" : "");
  requestAnimationFrame(fitSlideFrame);
};
elements.slideFrame.addEventListener("click", () => setBigMode(!document.body.classList.contains("big")));
elements.bigToggle.addEventListener("click", () => setBigMode(!document.body.classList.contains("big")));
elements.modeToggle.addEventListener("click", () => {
  const isPresenter = document.body.classList.toggle("presenter");
  elements.modeToggle.textContent = isPresenter ? text.practice : text.presenter;
  requestAnimationFrame(fitSlideFrame);
});

// 타이머: 제한시간이 있으면 넘을 때 빨강
let timerStartedAt = null;
let timerElapsedMilliseconds = 0;
const readElapsedSeconds = () => Math.floor((timerElapsedMilliseconds + (timerStartedAt ? Date.now() - timerStartedAt : 0)) / 1000);
setInterval(() => {
  const elapsed = readElapsedSeconds();
  elements.timer.textContent = formatSeconds(elapsed);
  elements.timer.classList.toggle("over", Boolean(deck?.time_limit_seconds) && elapsed > deck.time_limit_seconds);
}, 250);
elements.timerToggle.addEventListener("click", () => {
  if (timerStartedAt) { timerElapsedMilliseconds += Date.now() - timerStartedAt; timerStartedAt = null; }
  else timerStartedAt = Date.now();
  elements.timerToggle.textContent = timerStartedAt ? text.pause : text.start;
});
elements.timerReset.addEventListener("click", () => {
  timerStartedAt = null; timerElapsedMilliseconds = 0;
  elements.timerToggle.textContent = text.start;
});

// 흐름 보기: 전체 장 카드 (끌어서 순서 바꾸기 > deck.json 저장)
let draggedSlideId = null;
function renderFlow() {
  if (!document.body.classList.contains("flow")) return;
  elements.flowGrid.replaceChildren(...deck.slides.map((slide, index) => {
    const card = createElement("div", { className: "flow-card", draggable: true });
    const thumb = createElement("div", { className: "flow-thumb" });
    if (slide.thumbnail || slide.image) thumb.append(createElement("img", { src: `/${slide.thumbnail || slide.image}`, alt: "", loading: "lazy" }));
    else if (slide.html != null) thumb.append(createElement("iframe", { src: `/render/${encodeURIComponent(slide.id)}?v=${deck.version}`, loading: "lazy" }));
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

// 자동 다시 그리기: 덱 파일이 바뀌면 (입력 중이면 미룸)
async function watchDeckVersion() {
  try {
    const response = await fetch("/api/version", { cache: "no-store" });
    const { version } = await response.json();
    if (version !== deck.version && !isEditing()) {
      await fetchDeck();
      showSlide(currentIndex);
    }
  } catch { /* 서버가 잠시 없음: 다음 주기에 다시 */ }
  setTimeout(watchDeckVersion, VERSION_CHECK_MILLISECONDS);
}

(async function startPractice() {
  await fetchDeck();
  text = await loadText(deck.language);
  applyStaticText();
  elements.recordingCard.hidden = deck.recordings.length === 0;
  setBigMode(Boolean(localStorage.getItem(storageKey("big"))));
  showSlide(Number(localStorage.getItem(storageKey("index")) || 0));
  setTimeout(watchDeckVersion, VERSION_CHECK_MILLISECONDS);
})();
