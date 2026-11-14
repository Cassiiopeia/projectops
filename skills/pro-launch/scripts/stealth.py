"""Hide automation markers — avoids Google·Apple sign-in blocking automated browsers.

Ported from gstack browse `src/stealth.ts` (Layer C defaults + automation artifact cleanup).
Takes only the core that avoids sign-in blocks, without pulling in all of gstack (26k lines of TS, 119MB Bun binary).

Ported
  - Launch arg `--disable-blink-features=AutomationControlled`
      The browser itself keeps navigator.webdriver false. **Because it is a launch arg, not a page script,
      it also applies to sign-in popups that open after we disconnect** — this skill attaches and detaches
      per command, so init scripts alone cannot cover popups.
  - UA fix: headless puts `HeadlessChrome` in the UA. Replace it with the regular Chrome UA of the same version
  - Two init scripts: marker hiding (webdriver · window.chrome · Notification permission ·
    toString disguise · delete automation globals) + artifact cleanup (cdc_ globals · Permissions response)

Not ported
  - EXTENDED mode (plugin·WebGL spoofing): an escape hatch the original also leaves off by default, saying
    "aggressive spoofing can break sites"
  - --gstack-* args: meaningful only in gstack's patched Chromium. Regular Chromium does not know them

Observed (#604): what decided social sign-in success was **--headed**, not stealth. So this does
not replace headed — when sign-in is blocked, `web open --headed` still comes first.
This layer raises the pass rate in headless and reduces extra verification triggered by bot detection.

---------------------------------------------------------------------------
Original license (gstack — https://github.com/garrytan/gstack)

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

# Value used when the version cannot be read. If too old, it becomes a marker itself
_FALLBACK_VERSION = "131.0.0.0"


def _platform_token() -> str:
    """OS part of the UA. If it disagrees with the real OS it fails the cross-check with navigator.platform."""
    if sys.platform == "darwin":
        return "Macintosh; Intel Mac OS X 10_15_7"   # real Chrome sends this on Apple Silicon too
    if sys.platform == "win32":
        return "Windows NT 10.0; Win64; x64"
    return "X11; Linux x86_64"


def user_agent(chrome_exe: str) -> str:
    """Regular Chrome UA of the same version. No brand text — that alone becomes an identifier."""
    version = _FALLBACK_VERSION
    try:
        out = subprocess.run([chrome_exe, "--version"], capture_output=True, text=True, errors="replace",
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
    """Actual core count of this machine. A fixed value would group everyone using this skill under one fingerprint."""
    cores = os.cpu_count() or 8
    return cores, 8   # browsers clamp deviceMemory of 8 or more to 8


def stealth_script() -> str:
    cores, memory = _hw()
    return _STEALTH_TEMPLATE.replace("__HW_CONCURRENCY__", str(cores)) \
                            .replace("__DEVICE_MEMORY__", str(memory))


def init_scripts() -> list[str]:
    """Registration order is execution order. The toString disguise must be installed first so later getters are hidden."""
    return [stealth_script(), CLEANUP_SCRIPT]


# gstack buildStealthScript — order matters: the toString Proxy must be installed first so getters
# changed later all look like '[native code]'.
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

# gstack AUTOMATION_ARTIFACT_CLEANUP_SCRIPT — cleans up the cdc_ globals CDP plants and the marker of automated Chromium
# answering notification permission as 'denied' (set to 'prompt' so it agrees with Notification above).
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
