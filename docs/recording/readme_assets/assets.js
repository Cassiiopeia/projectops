// README 이미지 공통: 주소의 ?theme=light|dark&lang=en|ko > 테마 적용 + [data-text] 문구 채움
(() => {
  const query = new URLSearchParams(location.search);
  const theme = query.get("theme") === "dark" ? "dark" : "light";
  const language = query.get("lang") || "en";
  document.documentElement.dataset.theme = theme;
  document.documentElement.lang = language;

  // 문구 사전 (en 기본, 없는 키는 en 으로 폴백) > data-text 요소에 채움 (data-html 이면 HTML 허용)
  window.applyAssetText = (textByLanguage) => {
    const fallback = textByLanguage.en;
    const text = { ...fallback, ...(textByLanguage[language] || {}) };
    document.querySelectorAll("[data-text]").forEach((element) => {
      const value = text[element.dataset.text];
      if (value === undefined) return;
      if (element.hasAttribute("data-html")) element.innerHTML = value; else element.textContent = value;
    });
    return text;
  };
})();
