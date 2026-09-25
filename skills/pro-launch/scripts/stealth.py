"""자동화 표식 가리기 — Google·Apple 로그인이 자동화 브라우저를 막는 것을 피한다.

gstack browse 의 `src/stealth.ts`(Layer C 기본값 + 자동화 흔적 정리)에서 옮겼다.
gstack 전체(TS 2.6만 줄, Bun 바이너리 119MB)를 들이지 않고 로그인 차단을 피하는 핵심만 가져온다.

옮긴 것
  - 실행 인자 `--disable-blink-features=AutomationControlled`
      navigator.webdriver 를 브라우저 자체가 false 로 둔다. **페이지 스크립트가 아니라
      실행 인자라서, 우리가 연결을 끊은 뒤 뜨는 로그인 팝업 창에도 걸린다** — 이 스킬은
      명령마다 붙었다 떨어지므로 init 스크립트만으로는 팝업을 못 덮는다.
  - UA 보정: headless 는 UA 에 `HeadlessChrome` 이 박힌다. 같은 버전의 일반 Chrome UA 로 바꾼다
  - init 스크립트 두 개: 표식 가리기(webdriver · window.chrome · Notification 권한 ·
    toString 위장 · 자동화 전역 삭제) + 흔적 정리(cdc_ 전역 · Permissions 응답)

옮기지 않은 것
  - EXTENDED 모드(플러그인·WebGL 위조): 원본도 "적극적으로 속여 사이트를 깨뜨릴 수 있다"며
    기본값에서 뺀 탈출구다
  - --gstack-* 인자: gstack 이 패치한 Chromium 에서만 뜻이 있다. 일반 Chromium 은 모른다

실측(#604): 소셜 로그인 통과를 가른 것은 stealth 가 아니라 **--headed** 였다. 그래서 이것은
headed 를 대신하지 않는다 — 로그인이 막히면 여전히 `web open --headed` 가 먼저다.
이 층은 headless 에서의 통과율을 올리고, 봇 판정으로 추가 인증이 붙는 것을 줄인다.

---------------------------------------------------------------------------
원본 라이선스 (gstack — https://github.com/garrytan/gstack)

MIT License

Copyright (c) 2026 Garry Tan

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
---------------------------------------------------------------------------
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

LAUNCH_ARGS = ["--disable-blink-features=AutomationControlled"]

# 버전을 못 읽을 때 쓰는 값. 너무 낡으면 그 자체가 표식이 된다
_FALLBACK_VERSION = "131.0.0.0"


def _platform_token() -> str:
    """UA 의 OS 부분. 실제 OS 와 어긋나면 navigator.platform 과 교차 검사에 걸린다."""
    if sys.platform == "darwin":
        return "Macintosh; Intel Mac OS X 10_15_7"   # 실제 Chrome 도 Apple Silicon 에서 이렇게 보낸다
    if sys.platform == "win32":
        return "Windows NT 10.0; Win64; x64"
    return "X11; Linux x86_64"


def user_agent(chrome_exe: str) -> str:
    """같은 버전의 일반 Chrome UA. 브랜드 문구를 넣지 않는다 — 그것 자체가 식별자가 된다."""
    version = _FALLBACK_VERSION
    try:
        out = subprocess.run([chrome_exe, "--version"], capture_output=True, text=True,
                             timeout=5).stdout
        m = re.search(r"(\d+\.\d+\.\d+\.\d+)", out)
        if m:
            version = m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return (f"Mozilla/5.0 ({_platform_token()}) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{version} Safari/537.36")


def launch_args(chrome_exe: str) -> list[str]:
    return LAUNCH_ARGS + [f"--user-agent={user_agent(chrome_exe)}"]


def _hw() -> tuple[int, int]:
    """이 기계의 실제 코어 수. 고정값을 쓰면 이 스킬을 쓰는 모든 사람이 같은 지문으로 묶인다."""
    cores = os.cpu_count() or 8
    return cores, 8   # deviceMemory 는 브라우저가 8 이상을 8 로 자른다


def stealth_script() -> str:
    cores, memory = _hw()
    return _STEALTH_TEMPLATE.replace("__HW_CONCURRENCY__", str(cores)) \
                            .replace("__DEVICE_MEMORY__", str(memory))


def init_scripts() -> list[str]:
    """등록 순서가 곧 실행 순서다. toString 위장이 먼저 깔려야 뒤의 getter 가 가려진다."""
    return [stealth_script(), CLEANUP_SCRIPT]


# gstack buildStealthScript — 순서가 중요하다: toString Proxy 가 먼저 설치되어야 뒤에서
# 바꾼 getter 들이 모두 '[native code]' 로 보인다.
_STEALTH_TEMPLATE = r"""(() => {
  if (window.__projectops_stealth) return;
  try { Object.defineProperty(window, '__projectops_stealth', { value: true }); } catch {}

  const patchedFns = new WeakSet();
  const nativeToString = Function.prototype.toString;
  const toStringProxy = new Proxy(nativeToString, {
    apply(target, thisArg, args) {
      if (patchedFns.has(thisArg)) {
        const name = (thisArg && thisArg.name) || '';
        return 'function ' + name + '() { [native code] }';
      }
      return Reflect.apply(target, thisArg, args);
    },
  });
  Object.defineProperty(Function.prototype, 'toString', {
    value: toStringProxy, writable: true, configurable: true,
  });
  const markNative = (fn, name) => {
    if (name) { try { Object.defineProperty(fn, 'name', { value: name }); } catch {} }
    patchedFns.add(fn);
    return fn;
  };

  try {
    const webdriverGetter = markNative(function() { return false; }, 'get webdriver');
    Object.defineProperty(navigator, 'webdriver', { get: webdriverGetter, configurable: true });
  } catch {}

  try {
    if (!('chrome' in window)) { window.chrome = {}; }
    const chrome = window.chrome;
    if (!chrome.runtime) {
      chrome.runtime = {
        OnInstalledReason: { CHROME_UPDATE: 'chrome_update', INSTALL: 'install',
                            SHARED_MODULE_UPDATE: 'shared_module_update', UPDATE: 'update' },
        OnRestartRequiredReason: { APP_UPDATE: 'app_update', OS_UPDATE: 'os_update', PERIODIC: 'periodic' },
        PlatformArch: { ARM: 'arm', ARM64: 'arm64', MIPS: 'mips', MIPS64: 'mips64',
                       X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformNaclArch: { ARM: 'arm', MIPS: 'mips', MIPS64: 'mips64',
                           X86_32: 'x86-32', X86_64: 'x86-64' },
        PlatformOs: { ANDROID: 'android', CROS: 'cros', LINUX: 'linux',
                     MAC: 'mac', OPENBSD: 'openbsd', WIN: 'win' },
        RequestUpdateCheckStatus: { NO_UPDATE: 'no_update', THROTTLED: 'throttled',
                                   UPDATE_AVAILABLE: 'update_available' },
        connect: markNative(function connect() {
          throw new TypeError('Error in invocation of runtime.connect: No matching signature.');
        }, 'connect'),
        sendMessage: markNative(function sendMessage() {
          throw new TypeError('Error in invocation of runtime.sendMessage: No matching signature.');
        }, 'sendMessage'),
        id: undefined,
      };
    }
    if (!chrome.app) {
      chrome.app = {
        isInstalled: false,
        InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' },
        RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' },
      };
    }
    if (typeof chrome.csi !== 'function') {
      chrome.csi = markNative(function csi() {
        return { onloadT: Date.now(), pageT: performance.now(), startE: Date.now() - 1000, tran: 15 };
      }, 'csi');
    }
    if (typeof chrome.loadTimes !== 'function') {
      chrome.loadTimes = markNative(function loadTimes() {
        const t = performance.timing;
        return {
          requestTime: t.requestStart / 1000, startLoadTime: t.requestStart / 1000,
          commitLoadTime: t.responseStart / 1000,
          finishDocumentLoadTime: t.domContentLoadedEventEnd / 1000,
          finishLoadTime: t.loadEventEnd / 1000, firstPaintTime: t.responseEnd / 1000,
          firstPaintAfterLoadTime: 0, navigationType: 'Other',
          wasFetchedViaSpdy: true, wasNpnNegotiated: true, npnNegotiatedProtocol: 'h2',
          wasAlternateProtocolAvailable: false, connectionInfo: 'h2',
        };
      }, 'loadTimes');
    }
  } catch (err) {}

  try {
    if (typeof Notification !== 'undefined') {
      const g = markNative(function() { return 'default'; }, 'get permission');
      Object.defineProperty(Notification, 'permission', { get: g, configurable: true });
    }
  } catch {}

  try {
    const g = markNative(function() { return __HW_CONCURRENCY__; }, 'get hardwareConcurrency');
    Object.defineProperty(navigator, 'hardwareConcurrency', { get: g, configurable: true });
  } catch {}
  try {
    const g = markNative(function() { return __DEVICE_MEMORY__; }, 'get deviceMemory');
    Object.defineProperty(navigator, 'deviceMemory', { get: g, configurable: true });
  } catch {}

  try {
    const auto = [
      '__driver_evaluate', '__webdriver_evaluate', '__selenium_evaluate', '__fxdriver_evaluate',
      '__driver_unwrapped', '__webdriver_unwrapped', '__selenium_unwrapped', '__fxdriver_unwrapped',
      '_Selenium_IDE_Recorder', '_selenium', 'calledSelenium', '$chrome_asyncScriptInfo',
      '__$webdriverAsyncExecutor', '__webdriverFunc', 'domAutomation', 'domAutomationController',
      '__lastWatirAlert', '__lastWatirConfirm', '__lastWatirPrompt',
      '__webdriver_script_fn', '_WEBDRIVER_ELEM_CACHE',
      'callPhantom', '_phantom', 'phantom', '__nightmare',
      '__pwInitScripts', '__playwright__binding__',
    ];
    for (const k of auto) { try { delete window[k]; } catch {} }
    try { delete document.__webdriver_script_fn; } catch {}
  } catch {}
})();"""

# gstack AUTOMATION_ARTIFACT_CLEANUP_SCRIPT — CDP 가 심는 cdc_ 전역과, 자동화 Chromium 이
# 알림 권한을 'denied' 로 답하는 표식을 정리한다 ('prompt' 로 맞춰 위 Notification 과 어긋나지 않게).
CLEANUP_SCRIPT = r"""(() => {
  const cleanup = () => {
    for (const key of Object.keys(window)) {
      if (key.startsWith('cdc_') || key.startsWith('__webdriver')) {
        try { delete window[key]; } catch (e) { if (!(e instanceof TypeError)) throw e; }
      }
    }
  };
  cleanup();
  setTimeout(cleanup, 0);
  const originalQuery = window.navigator.permissions && window.navigator.permissions.query;
  if (originalQuery && !originalQuery.__projectops) {
    const q = (params) => {
      if (params && params.name === 'notifications') {
        return Promise.resolve({ state: 'prompt', onchange: null });
      }
      return originalQuery.call(window.navigator.permissions, params);
    };
    q.__projectops = true;
    window.navigator.permissions.query = q;
  }
})();"""
