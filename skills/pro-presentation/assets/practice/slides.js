// 슬라이드 본체 · 썸네일 줄 그리기: 필요한 때만 다시 그림 (장을 넘길 때마다 그림을 다시 받지 않게)
// practice.js 의 전역(deck · text · elements · currentIndex · showSlide · createElement · VIEW_NAME · SLIDE_WIDTH_PIXELS)을 씀
"use strict";

// 그려 둔 슬라이드 본체 (지금 장 + 앞뒤 장): 열쇠 > 요소 · 썸네일 줄을 마지막으로 만든 열쇠
const slideBodies = new Map();
let renderedThumbnailsKey = "";

// 본체 열쇠: 그 장의 본체 파일이나 테마가 바뀔 때만 달라짐 (대본 · 카드 · 다른 장이 바뀌어도 다시 그리지 않음)
const slideBodyKey = (slide) => `${slide.id}:${slide.version}:${deck.theme_version}`;

function createSlideBody(slide) {
  const version = encodeURIComponent(slideBodyKey(slide));
  if (slide.html != null) return createElement("iframe", { src: `/render/${encodeURIComponent(slide.id)}?v=${version}`, title: slide.title });
  if (slide.image) return createElement("img", { src: `/${slide.image}?v=${version}`, alt: slide.title, decoding: "async" });
  return createElement("div", { className: "slide-error", textContent: text.missing_slide });
}

// 지금 장 + 앞뒤 장을 미리 그려 두고, 넘길 때는 보이는 것만 바꿈 (넘김이 바로 그려짐)
function renderSlideBody() {
  // 대본 · 카드만 보이는 분리 창은 슬라이드를 그리지 않음
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

// 작은 그림 주소 (가로 320 사본): 본체나 사본이 바뀌면 주소가 달라져 브라우저가 오래 기억해도 됨
const thumbnailUrl = (slide) => `/${slide.thumbnail || slide.image}?w=320&v=${slide.version}-${deck.images_generation}`;

// 썸네일 줄: 장 목록 · 그림이 바뀔 때만 다시 만들고, 장을 넘길 때는 표시만 옮김
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
