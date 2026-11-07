// pro-ui-design 시안 안에서 도는 공통 코드: 셸 설정 수신, 클릭 기록
(() => {
  const screenName = decodeURIComponent(location.pathname.split("/").pop() || "");
  const query = new URLSearchParams(location.search);
  const settings = { device: query.get("device") || "phone", theme: query.get("theme") || "light", speed: Number(query.get("speed")) || 1 };

  function applySettings() {
    document.documentElement.dataset.device = settings.device;
    document.documentElement.dataset.theme = settings.theme;
  }

  function sendEvent(event) {
    fetch("/api/events", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...event, screen: screenName }), keepalive: true,
    }).catch(() => { /* 서버가 멈춰도 시안 조작은 계속 */ });
  }

  // 안 선택: 카드 표시 + 서버 기록 + 셸 안내
  document.addEventListener("click", (domEvent) => {
    const target = domEvent.target.closest?.("[data-choice]");
    if (!target) return;
    const text = (target.closest(".ui-option")?.querySelector("h3")?.textContent || target.textContent || "").trim();
    document.querySelectorAll(".ui-option.ui-picked").forEach((option) => option.classList.remove("ui-picked"));
    target.closest(".ui-option")?.classList.add("ui-picked");
    sendEvent({ type: "click", choice: target.dataset.choice, text });
    if (window.parent !== window) window.parent.postMessage({ type: "ui-design-choice", text }, location.origin);
  });

  window.addEventListener("message", (message) => {
    if (message.origin !== location.origin) return;
    if (message.data?.type === "ui-design-settings") {
      Object.assign(settings, { device: message.data.device, theme: message.data.theme, speed: Number(message.data.speed) || 1 });
      applySettings();
    }
  });

  applySettings();
})();
