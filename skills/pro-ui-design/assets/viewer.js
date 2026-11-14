// pro-ui-design shared mockup tools window.UIDesign: shell settings, click log, animation, shared state, gestures
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
    }).catch(() => { /* Mockup interaction keeps working even if the server stops */ });
  }

  // Animation: apply speed multiplier to durations, track so restart can cancel
  function animate(element, keyframes, timing) {
    const scaled = typeof timing === "number" ? { duration: timing } : { ...timing };
    for (const key of ["duration", "delay", "endDelay"]) {
      if (typeof scaled[key] === "number") scaled[key] *= settings.speed;
    }
    const animation = element.animate(keyframes, scaled);
    runningAnimations.add(animation);
    return animation;
  }

  // Damped spring: pass position 0 > 1 to a per-frame callback (bounces at the end when dampingRatio < 1)
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

  // Register an option: play runs one option, reset restores the initial look
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

  // Shared state: read and subscribed by several screens
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

  // Restart: cancel motion > restore options > restore state > restore hints > mockup's own extra restore
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
    // Place the "try it" hints beside the screen
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
    // Keep a long-press release from counting as a normal press
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

  // Delegated handling: [data-play] plays, [data-choice] records a choice
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
