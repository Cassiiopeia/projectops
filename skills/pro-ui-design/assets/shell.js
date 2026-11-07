// pro-ui-design 뷰어 셸 동작: 시안 목록, 기기, 테마, 속도 전환, 주기 확인
// 서버가 채우는 설정: 기기, 테마, 언어, 제목
const SETTINGS = window.UI_DESIGN_SETTINGS;
const POLL_INTERVAL_MILLISECONDS = 1000;
const SPEED_CHOICES = [{ value: 1, label: "Normal speed" }, { value: 3, label: "3x slower" }];
const DEVICE_LABELS = { phone: "Phone", tablet: "Tablet", desktop: "Desktop" };
const THEME_LABELS = { light: "Light", dark: "Dark" };
const STORAGE_PREFIX = "ui-design:";

const elements = {
  frame: document.getElementById("screen"), waiting: document.getElementById("waiting"),
  list: document.getElementById("screen-list"), status: document.getElementById("status-bar"),
  stopped: document.getElementById("stopped"),
};
let translations = {};
let lastRevision = null;
let currentScreen = null;
let isFollowingNewest = true;
const viewerSettings = {
  device: readStored("device", (SETTINGS.devices || ["phone"])[0]),
  theme: readStored("theme", (SETTINGS.themes || ["light"])[0]),
  speed: Number(readStored("speed", 1)),
};

function readStored(name, fallback) {
  try { return localStorage.getItem(STORAGE_PREFIX + name) ?? fallback; } catch { return fallback; }
}
function storeValue(name, value) {
  try { localStorage.setItem(STORAGE_PREFIX + name, value); } catch { /* 저장 불가 브라우저는 이번 탭에서만 유지 */ }
}
function translate(text) { return translations[text] || text; }

// 묶음 토글: 하나만 켜짐, 선택지가 하나면 숨김
function buildSegment(containerId, choices, selected, onSelect) {
  const container = document.getElementById(containerId);
  container.hidden = choices.length < 2;
  container.replaceChildren();
  for (const choice of choices) {
    const button = document.createElement("button");
    button.textContent = translate(choice.label);
    button.className = String(choice.value) === String(selected) ? "on" : "";
    button.onclick = () => {
      container.querySelectorAll("button").forEach((item) => item.classList.remove("on"));
      button.classList.add("on");
      onSelect(choice.value);
    };
    container.append(button);
  }
}

function sendSettingsToScreen() {
  document.documentElement.classList.toggle("dark", viewerSettings.theme === "dark");
  elements.frame.contentWindow?.postMessage({ type: "ui-design-settings", ...viewerSettings }, location.origin);
}
function sendCommandToScreen(type) {
  elements.frame.contentWindow?.postMessage({ type }, location.origin);
}

function buildToolbar() {
  const devices = (SETTINGS.devices || []).map((value) => ({ value, label: DEVICE_LABELS[value] || value }));
  const themes = (SETTINGS.themes || []).map((value) => ({ value, label: THEME_LABELS[value] || value }));
  const update = (name) => (value) => { viewerSettings[name] = value; storeValue(name, value); sendSettingsToScreen(); };
  buildSegment("device-toggle", devices, viewerSettings.device, update("device"));
  buildSegment("theme-toggle", themes, viewerSettings.theme, update("theme"));
  buildSegment("speed-toggle", SPEED_CHOICES, viewerSettings.speed, update("speed"));
  document.getElementById("play-all").onclick = () => sendCommandToScreen("ui-design-play-all");
  document.getElementById("reset").onclick = () => sendCommandToScreen("ui-design-reset");
}

function showScreen(name, force) {
  if (name === currentScreen && !force) return;
  currentScreen = name;
  elements.frame.src = `/screens/${encodeURIComponent(name)}`;
  elements.frame.hidden = false;
  elements.waiting.hidden = true;
  elements.status.classList.remove("picked");
  elements.status.textContent = translate("Look, press around, then reply in the terminal.");
}

function renderList(screens, newest) {
  elements.list.replaceChildren();
  screens.forEach((screen) => {
    const button = document.createElement("button");
    button.className = "screen-link" + (screen.name === currentScreen ? " on" : "");
    button.textContent = screen.name.replace(/\.html$/i, "");
    const note = document.createElement("small");
    note.textContent = screen.name === newest ? translate("Newest") : new Date(screen.modified_ms).toLocaleTimeString();
    button.append(note);
    button.onclick = () => {
      isFollowingNewest = screen.name === newest;
      showScreen(screen.name);
      renderList(screens, newest);
    };
    elements.list.append(button);
  });
}

// 주기 확인: 새 시안이면 따라가고, 보던 이전 시안은 고정 유지
async function pollState() {
  try {
    const response = await fetch("/api/state", { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    const state = await response.json();
    elements.stopped.classList.remove("on");
    if (state.revision !== lastRevision) {
      const isFirstLoad = lastRevision === null;
      lastRevision = state.revision;
      if (state.current && (isFollowingNewest || isFirstLoad)) {
        showScreen(state.current, true);
      }
      renderList(state.screens, state.current);
    }
  } catch {
    elements.stopped.classList.add("on");
  }
}

elements.frame.addEventListener("load", sendSettingsToScreen);
window.addEventListener("message", (event) => {
  if (event.origin !== location.origin || event.source !== elements.frame.contentWindow) return;
  if (event.data?.type === "ui-design-choice") {
    elements.status.classList.add("picked");
    elements.status.textContent = `${translate("Selected")}: ${event.data.text}. ${translate("Reply in the terminal to continue.")}`;
  }
});

async function loadTranslations() {
  if (!String(SETTINGS.language || "").toLowerCase().startsWith("ko")) return;
  try {
    translations = await (await fetch("/assets/viewer-i18n.ko.json")).json();
  } catch { /* 사전을 못 읽으면 영어로 표시 */ }
}

async function main() {
  await loadTranslations();
  document.getElementById("session-title").textContent = SETTINGS.title || "";
  document.title = SETTINGS.title || "Mockups";
  document.querySelectorAll("[data-i18n]").forEach((element) => {
    element.textContent = translate(element.dataset.i18n);
  });
  buildToolbar();
  document.documentElement.classList.toggle("dark", viewerSettings.theme === "dark");
  await pollState();
  setInterval(pollState, POLL_INTERVAL_MILLISECONDS);
}
main();
