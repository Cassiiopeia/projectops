// Shared by README images: ?theme=light|dark&lang=en|ko in the URL > apply theme + fill [data-text] text
(() => {
  const query = new URLSearchParams(location.search);
  const theme = query.get("theme") === "dark" ? "dark" : "light";
  const language = query.get("lang") || "en";
  document.documentElement.dataset.theme = theme;
  document.documentElement.lang = language;

  // Text dictionary (en default, missing keys fall back to en) > fill data-text elements (HTML allowed with data-html)
  window.applyAssetText = (textByLanguage) => {
    const fallback = textByLanguage.en;
    const text = { ...fallback, ...(textByLanguage[language] || {}) };
    document.querySelectorAll("[data-text]").forEach((element) => {
      const localizedText = text[element.dataset.text];
      if (localizedText === undefined) return;
      if (element.hasAttribute("data-html")) element.innerHTML = localizedText; else element.textContent = localizedText;
    });
    return text;
  };
})();
