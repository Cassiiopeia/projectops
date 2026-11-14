// Draw slide body · thumbnail row: redraw only when needed (so images are not refetched on every slide change)
// Uses practice.js globals (deck · text · elements · currentIndex · showSlide · createElement · VIEW_NAME · SLIDE_WIDTH_PIXELS)
"use strict";

// Drawn slide bodies (current + adjacent slides): key > element · key the thumbnail row was last built with
const slideBodies = new Map();
let renderedThumbnailsKey = "";

// Body key: changes only when that slide's body file or theme changes (script, cards or other slides changing does not redraw)
const slideBodyKey = (slide) => `${slide.id}:${slide.version}:${deck.theme_version}`;

function createSlideBody(slide) {
  const version = encodeURIComponent(slideBodyKey(slide));
  if (slide.html != null) return createElement("iframe", { src: `/render/${encodeURIComponent(slide.id)}?v=${version}`, title: slide.title });
  if (slide.image) return createElement("img", { src: `/${slide.image}?v=${version}`, alt: slide.title, decoding: "async" });
  return createElement("div", { className: "slide-error", textContent: text.missing_slide });
}

// Pre-draw the current and adjacent slides; on navigation only visibility changes (slides appear instantly)
function renderSlideBody() {
  // Pop-out windows showing only script or cards do not draw slides
  if (VIEW_NAME && VIEW_NAME !== "slide") return;
  const wanted = new Map([0, 1, -1].map((offset) => deck.slides[currentIndex + offset]).filter(Boolean).map((slide) => [slideBodyKey(slide), slide]));
  for (const [key, body] of slideBodies) {
    if (wanted.has(key)) continue;
    body.remove();
    slideBodies.delete(key);
  }
  for (const [key, slide] of wanted) {
    if (slideBodies.has(key)) continue;
    slideBodies.set(key, createSlideBody(slide));
    elements.slideFrame.append(slideBodies.get(key));
  }
  const currentKey = slideBodyKey(deck.slides[currentIndex]);
  for (const [key, body] of slideBodies) body.classList.toggle("ahead", key !== currentKey);
  fitSlideFrame();
}

function fitSlideFrame() {
  const scale = `scale(${elements.slideFrame.clientWidth / SLIDE_WIDTH_PIXELS})`;
  for (const frame of elements.slideFrame.querySelectorAll("iframe")) frame.style.transform = scale;
}

// Small image URL (320-wide copy): the URL changes when the body or copy changes, so long browser caching is safe
const thumbnailUrl = (slide) => `/${slide.thumbnail || slide.image}?w=320&v=${slide.version}-${deck.images_generation}`;

// Thumbnail row: rebuilt only when the slide list or images change; navigation only moves the highlight
function renderThumbnails() {
  const key = `${deck.images_generation}|${deck.slides.map((slide) => `${slide.id}:${slide.version}:${slide.title}`).join("|")}`;
  if (key !== renderedThumbnailsKey) {
    renderedThumbnailsKey = key;
    elements.thumbnails.replaceChildren(...deck.slides.map((slide, index) => {
      const button = createElement("button", { title: slide.title });
      if (slide.thumbnail || slide.image) button.append(createElement("img", { src: thumbnailUrl(slide), alt: "", loading: "lazy", decoding: "async" }));
      else button.append(createElement("span", { className: "name", textContent: slide.title }));
      button.append(createElement("span", { className: "label", textContent: slide.number }));
      button.addEventListener("click", () => showSlide(index));
      return button;
    }));
  }
  [...elements.thumbnails.children].forEach((button, index) => {
    button.classList.toggle("active", index === currentIndex);
    button.querySelector(".label").classList.toggle("has-memo", Boolean(deck.slides[index].memo));
  });
  elements.thumbnails.children[currentIndex]?.scrollIntoView({ inline: "center", block: "nearest" });
}
