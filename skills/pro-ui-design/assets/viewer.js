// pro-ui-design 시안 공통 도구 window.UIDesign: 셸 설정 수신, 클릭 기록, 애니메이션, 공유 상태, 제스처
(() => {
  const DEFAULT_LONG_PRESS_MILLISECONDS = 450;
  const LONG_PRESS_MOVE_TOLERANCE_PIXELS = 8;
  const DRAG_THRESHOLD_PIXELS = 4;
  const DEFAULT_TOAST_MILLISECONDS = 2000;
  const PLAY_ALL_GAP_MILLISECONDS = 300;
  const SPRING_SETTLE_DISTANCE = 0.001;
  const SPRING_MAX_SECONDS = 3;

  const screenName = decodeURIComponent(location.pathname.split("/").pop() || "");
  const query = new URLSearchParams(location.search);
  const settings = { device: query.get("device") || "phone", theme: query.get("theme") || "light", speed: Number(query.get("speed")) || 1 };

  const options = new Map();
  const stores = [];
  const stepPanels = [];
  const resetCallbacks = [];
  const runningAnimations = new Set();
  const runningSpringIds = new Set();
  const playTimers = new Set();

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

  // 애니메이션: 시간 값에 속도 배율 적용, 처음부터 할 때 취소되도록 추적
  function animate(element, keyframes, timing) {
    const scaled = typeof timing === "number" ? { duration: timing } : { ...timing };
    for (const key of ["duration", "delay", "endDelay"]) {
      if (typeof scaled[key] === "number") scaled[key] *= settings.speed;
    }
    const animation = element.animate(keyframes, scaled);
    runningAnimations.add(animation);
    return animation;
  }

  // 감쇠 스프링: 위치 0 > 1 을 매 프레임 콜백으로 전달 (dampingRatio 1 미만이면 끝에서 튕김)
  function spring(onFrame, { dampingRatio = 0.6, frequency = 14 } = {}) {
    const damping = Math.min(dampingRatio, 0.999);
    const dampedFrequency = frequency * Math.sqrt(1 - damping * damping);
    const startTime = performance.now();
    const speed = settings.speed;
    const handle = { id: 0 };
    const step = (now) => {
      runningSpringIds.delete(handle);
      const seconds = (now - startTime) / 1000 / speed;
      const decay = Math.exp(-damping * frequency * seconds);
      const remaining = decay * (Math.cos(dampedFrequency * seconds)
        + (damping * frequency / dampedFrequency) * Math.sin(dampedFrequency * seconds));
      const isSettled = decay < SPRING_SETTLE_DISTANCE || seconds > SPRING_MAX_SECONDS;
      onFrame(isSettled ? 1 : 1 - remaining);
      if (isSettled) return;
      handle.id = requestAnimationFrame(step);
      runningSpringIds.add(handle);
    };
    handle.id = requestAnimationFrame(step);
    runningSpringIds.add(handle);
    return handle;
  }

  function cancelRunningMotion() {
    runningAnimations.forEach((animation) => animation.cancel());
    runningAnimations.clear();
    runningSpringIds.forEach((handle) => cancelAnimationFrame(handle.id));
    runningSpringIds.clear();
    playTimers.forEach((timer) => clearTimeout(timer));
    playTimers.clear();
  }

  // 안 등록: play 는 안 하나 재생, reset 은 처음 모습으로
  function registerOption(id, { play, reset = () => {} }) {
    options.set(String(id), { play, reset });
  }

  function play(id) {
    const option = options.get(String(id));
    if (!option) return;
    option.reset();
    return option.play();
  }

  function playAll() {
    cancelRunningMotion();
    options.forEach((option) => option.reset());
    [...options.keys()].forEach((id, index) => {
      const timer = setTimeout(() => { playTimers.delete(timer); options.get(id).play(); },
        index * PLAY_ALL_GAP_MILLISECONDS * settings.speed);
      playTimers.add(timer);
    });
  }

  // 공유 상태: 여러 화면이 함께 읽고 구독
  function createStore(initial) {
    const initialCopy = structuredClone(initial);
    let current = structuredClone(initial);
    const listeners = new Set();
    const notify = () => listeners.forEach((listener) => listener(current));
    const store = {
      get: () => current,
      set(change) {
        const patch = typeof change === "function" ? change(current) : change;
        current = { ...current, ...patch };
        notify();
      },
      subscribe(listener) {
        listeners.add(listener);
        listener(current);
        return () => listeners.delete(listener);
      },
      reset() {
        current = structuredClone(initialCopy);
        notify();
      },
    };
    stores.push(store);
    return store;
  }

  // 처음부터: 움직임 취소 > 안 복원 > 상태 복원 > 안내 복원 > 시안의 추가 복원
  function reset() {
    cancelRunningMotion();
    options.forEach((option) => option.reset());
    stores.forEach((store) => store.reset());
    stepPanels.forEach((panel) => panel.reset());
    resetCallbacks.forEach((callback) => callback());
  }

  function setScreens(screens, store, container = document.body) {
    const wrapper = document.createElement("div");
    wrapper.className = "ui-screens";
    const rendered = screens.map((screen) => {
      const column = document.createElement("div");
      if (screen.label) {
        const label = document.createElement("div");
        label.className = "ui-screen-label";
        label.textContent = screen.label;
        column.append(label);
      }
      const device = document.createElement("div");
      device.className = "ui-device";
      if (screen.device) device.dataset.device = screen.device;
      const element = document.createElement("div");
      element.className = "ui-device-screen";
      element.dataset.screen = screen.id;
      device.append(element);
      column.append(device);
      wrapper.append(column);
      return { screen, element };
    });
    container.append(wrapper);
    // "따라 해 보기" 안내는 화면 옆에 배치
    const stepsPanel = document.querySelector(".ui-steps");
    if (stepsPanel) wrapper.prepend(stepsPanel);
    const renderAll = (state) => rendered.forEach(({ screen, element }) => screen.render(element, state));
    if (store) store.subscribe(renderAll); else renderAll({});
    return wrapper;
  }

  function showSteps(steps, { title = "", into = document.body } = {}) {
    const panel = document.createElement("div");
    panel.className = "ui-steps";
    if (title) {
      const heading = document.createElement("h4");
      heading.textContent = title;
      panel.append(heading);
    }
    const list = document.createElement("ol");
    const stepElements = steps.map((text) => {
      const stepElement = document.createElement("li");
      stepElement.textContent = text;
      list.append(stepElement);
      return stepElement;
    });
    panel.append(list);
    into.append(panel);
    const controls = {
      complete(index) { stepElements[index]?.classList.add("ui-step-done"); },
      reset() { stepElements.forEach((stepElement) => stepElement.classList.remove("ui-step-done")); },
    };
    stepPanels.push(controls);
    return controls;
  }

  function toast(text, { milliseconds = DEFAULT_TOAST_MILLISECONDS } = {}) {
    let element = document.querySelector(".ui-toast");
    if (!element) {
      element = document.createElement("div");
      element.className = "ui-toast";
      document.body.append(element);
    }
    element.textContent = text;
    element.classList.add("ui-on");
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => element.classList.remove("ui-on"), milliseconds);
  }

  function onLongPress(element, callback, { milliseconds = DEFAULT_LONG_PRESS_MILLISECONDS } = {}) {
    let timer = null;
    let start = null;
    let hasFired = false;
    const cancel = () => { clearTimeout(timer); timer = null; };
    element.addEventListener("pointerdown", (event) => {
      start = { x: event.clientX, y: event.clientY };
      hasFired = false;
      timer = setTimeout(() => { hasFired = true; timer = null; callback(event); }, milliseconds);
    });
    element.addEventListener("pointermove", (event) => {
      if (timer && Math.hypot(event.clientX - start.x, event.clientY - start.y) > LONG_PRESS_MOVE_TOLERANCE_PIXELS) cancel();
    });
    element.addEventListener("pointerup", cancel);
    element.addEventListener("pointercancel", cancel);
    element.addEventListener("pointerleave", cancel);
    // 길게 누른 뒤 손을 뗄 때 일반 누름으로 처리되지 않게
    element.addEventListener("click", (event) => {
      if (hasFired) { event.stopPropagation(); event.preventDefault(); hasFired = false; }
    }, true);
  }

  function onDrag(element, { start, move, end } = {}) {
    let origin = null;
    let isDragging = false;
    const describe = (event) => {
      const dx = event.clientX - origin.x;
      const dy = event.clientY - origin.y;
      return { x: event.clientX, y: event.clientY, dx, dy, distance: Math.hypot(dx, dy), event };
    };
    element.addEventListener("pointerdown", (event) => {
      origin = { x: event.clientX, y: event.clientY, pointerId: event.pointerId };
      isDragging = false;
    });
    element.addEventListener("pointermove", (event) => {
      if (!origin) return;
      const dragPosition = describe(event);
      if (!isDragging && dragPosition.distance >= DRAG_THRESHOLD_PIXELS) {
        isDragging = true;
        element.setPointerCapture?.(origin.pointerId);
        start?.(dragPosition);
      }
      if (isDragging) move?.(dragPosition);
    });
    const finish = (event) => {
      if (origin && isDragging) end?.(describe(event));
      origin = null;
      isDragging = false;
    };
    element.addEventListener("pointerup", finish);
    element.addEventListener("pointercancel", finish);
  }

  // 위임 처리: [data-play] 재생, [data-choice] 선택 기록
  document.addEventListener("click", (domEvent) => {
    const playButton = domEvent.target.closest?.("[data-play]");
    if (playButton) play(playButton.dataset.play);
    const target = domEvent.target.closest?.("[data-choice]");
    if (!target) return;
    const option = target.closest(".ui-option");
    const text = (option?.querySelector("h3")?.textContent || target.textContent || "").trim();
    document.querySelectorAll(".ui-option.ui-picked").forEach((element) => element.classList.remove("ui-picked"));
    option?.classList.add("ui-picked");
    sendEvent({ type: "click", choice: target.dataset.choice, text });
    if (window.parent !== window) window.parent.postMessage({ type: "ui-design-choice", text }, location.origin);
  });

  window.addEventListener("message", (message) => {
    if (message.origin !== location.origin) return;
    const type = message.data?.type;
    if (type === "ui-design-settings") {
      Object.assign(settings, { device: message.data.device, theme: message.data.theme, speed: Number(message.data.speed) || 1 });
      applySettings();
    } else if (type === "ui-design-play-all") {
      playAll();
    } else if (type === "ui-design-reset") {
      reset();
    }
  });

  window.UIDesign = {
    registerOption, play, playAll, reset, animate, spring, createStore, setScreens, showSteps, toast, onLongPress, onDrag,
    onReset: (callback) => resetCallbacks.push(callback),
    getSpeed: () => settings.speed,
    getSettings: () => ({ ...settings }),
  };
  applySettings();
})();
