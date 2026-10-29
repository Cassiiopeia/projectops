# Official troubleshooting

> Generated file — do not edit by hand. Source: `troubleshooting/<area>/<id>.json`.
> Rebuild: `python3 scripts/build_troubleshooting.py skills/<skill>` (from the repo root).
> Writing rules: `skills/references/memory-principles.md` §6. The `known_fix` in failure responses summarizes these entries.

## Web (`web`)

| id | Title | Codes |
|---|---|---|
| `browser-start-stale-process-or-lock` | web open fails with browser_start_failed — a problem left after self-recovery | `browser_start_failed` · `browser_hung` |
| `web-browser-gone` | web commands fail with browser_gone — could not attach to the running browser | `browser_gone` |
| `web-browser-not-open-other-root` | browser_not_open right after opening — called from another project's location | `browser_not_open` |
| `web-click-wait-with-expect` | Do not wait with sleep — use click's --expect-url · --expect-text | `expect_not_met` |
| `web-find-nothing-found` | web find returns nothing_found — by default it finds only clickable elements | `nothing_found` |
| `web-goto-failed` | web open · goto navigation fails — check the URL, the server, the certificate | `goto_failed` |
| `web-iframe-login-fields` | Cannot find login fields inside an iframe (App Store Connect, etc.) | — |
| `web-orphan-headless-chrome` | Double-clicking an HTML file does not open Chrome — orphan headless Chrome | `browser_hung` |
| `web-page-changed-by-other-session` | Another session moves the same tab and your input is lost | `page_changed_by_other_session` · `tab_gone` |
| `web-playwright-or-browser-missing` | playwright_missing · browser_missing — web setup is needed | `playwright_missing` · `browser_missing` |
| `web-readonly-mutating-blocked` | Save · submit buttons return mutating_blocked in a read-only session | `mutating_blocked` |
| `web-save-by-network` | Judge whether a save worked by the request response, not on-screen text | — |
| `web-script-browser-memory-exceeded` | Bulk scraping in web script bloats browser memory — use cookies + HTTP | `browser_memory_exceeded` |
| `web-scroll-container-capture` | Inner-scroll screens (Google Forms editor, etc.) are not captured by full-page | — |
| `web-secret-in-input` | A secret value exists only inside an input or behind a copy button | — |
| `web-selector-guess-timeout` | A guessed --selector misses — pick from candidates in the result, press by --ref | `selector_not_found` · `element_not_actionable` · `element_disabled` |
| `web-viewport-width-height` | web viewport --width --height returns bad_viewport — set the size with --preset | `bad_viewport` |

### `browser-start-stale-process-or-lock` — web open fails with browser_start_failed — a problem left after self-recovery

- Codes: `browser_start_failed` · `browser_hung`
- Keywords: SingletonLock, SingletonSocket, profile_locked, stderr_tail, recovered, 브라우저가 뜨지 않았습니다
- Symptom: web open ends with browser_start_failed and no browser appears (error: "Browser did not start"). The response carries causes · recovered · stderr_tail
- Cause: web open first checks the recorded browser: if it is dead, it clears leftover locks; if it is alive but CDP does not answer within 3 s, it kills it and starts a new one (recovered lists dead_pid · stale_lock · hung_browser). If it still fails, an unrecorded process is using the same profile (locks are not deleted then), or the browser itself dies immediately
- Fix:
  1. Read stderr_tail in the response — it holds the reason the browser died immediately
  2. If profile_locked is true, find the browser process using the response's profile folder (ps · Task Manager), confirm with the user, then end it
  3. launch_cli.py web open --url <url>
  4. If the response is browser_still_alive, end that pid with the kill command in next (kill -9 <pid> or taskkill)
- Refs: #711, #712, #887 · verified 2026-10-17

### `web-browser-gone` — web commands fail with browser_gone — could not attach to the running browser

- Codes: `browser_gone`
- Symptom: web text · shot · click end with browser_gone (could not attach to the open browser)
- Cause: It could not connect to the browser (CDP port) recorded in the state file — that browser was closed or does not respond. The CLI removes only the dead browser's info (cdp · pid) from the state file and keeps the viewport and route rules
- Fix:
  1. launch_cli.py web open --url <url>
  2. If open fails with browser_start_failed: kb show browser-start-stale-process-or-lock
  3. For sites that need a login, reopen and first check the login state with web text
- Refs: #825, #889 · verified 2026-10-17
- See also: `browser-start-stale-process-or-lock`

### `web-browser-not-open-other-root` — browser_not_open right after opening — called from another project's location

- Codes: `browser_not_open`
- Symptom: web open succeeded, but the next web text · shot returns browser_not_open (no open browser). The --root path in next is a scripts folder, the plugin cache or a temp folder
- Cause: Each project (git remote owner/repo) has its own browser state file. If open and the next command use different working folders (--root, default '.'), they read different state files. cd into the scripts folder or calling from a temp folder splits them like this
- Fix:
  1. launch_cli.py web text --root <project path>
  2. Call open with the same --root too. Do not cd into the scripts folder; call the script by absolute path
  3. If it really is not running: launch_cli.py web open --root <project path> --url <url>
- Refs: #833, #836, #889 · verified 2026-10-17
- See also: `general-root-unknown-skill-folder`

### `web-click-wait-with-expect` — Do not wait with sleep — use click's --expect-url · --expect-text

- Codes: `expect_not_met`
- Symptom: A fixed wait such as sleep 5 follows the click, then web text checks the result. Slow screens get read before they change; fast screens waste time. Sometimes expect_not_met appears
- Cause: Given --expect-url · --expect-text, web click waits until it appears (--timeout seconds) and reports expect_not_met if it does not. Without them it waits only briefly (a few seconds). web type waits by itself up to --timeout for the field to appear
- Fix:
  1. launch_cli.py web click --ref <number> --expect-text <text on the next screen> --timeout 30
  2. launch_cli.py web click --ref <number> --expect-url <part of the new URL>
  3. On expect_not_met, read the current screen with web text — if you pressed the wrong thing, pick again with web find
  4. --selector on web text · assert does not wait — if you will read right away, wait first with click's expect
- Refs: #825, #889 · verified 2026-10-17

### `web-find-nothing-found` — web find returns nothing_found — by default it finds only clickable elements

- Codes: `nothing_found`
- Symptom: The text is visible on screen, but web find returns nothing_found (no visible element matches)
- Cause: Without --selector · --role it looks only at click targets such as links, buttons and elements with a role. Plain inputs (input · textarea) are not included. --role finds only elements with an actual role attribute (--role textbox does not find <input>). It does not look inside iframes either
- Fix:
  1. launch_cli.py web text --max-chars 3000
  2. launch_cli.py web find --text <text exactly as seen in web text>
  3. Find inputs with CSS: launch_cli.py web find --selector input
  4. If still nothing, it may be inside an iframe — kb show web-iframe-login-fields
- Refs: #825, #889 · verified 2026-10-17
- See also: `web-iframe-login-fields`

### `web-goto-failed` — web open · goto navigation fails — check the URL, the server, the certificate

- Codes: `goto_failed`
- Keywords: ERR_CERT_AUTHORITY_INVALID
- Symptom: web open --url ends with goto_failed, or web goto ends with web_action_failed. The error contains text such as Timeout, ERR_CONNECTION_REFUSED or ERR_CERT_*
- Cause: The navigation itself failed: the server is not up or the URL is wrong (Timeout · CONNECTION_REFUSED), or a private or self-signed certificate blocked it (ERR_CERT · ERR_SSL). web goto treats 404 and 500 pages as successful navigation and reports them in status
- Fix:
  1. For a local server, first check it is up: launch_cli.py http --url <url>
  2. Certificate error (test servers only): launch_cli.py web close
  3. launch_cli.py web open --ignore-cert-errors --url <url>  # applies only when a new browser starts
- Refs: #711, #889 · verified 2026-10-17

### `web-iframe-login-fields` — Cannot find login fields inside an iframe (App Store Connect, etc.)

- Keywords: iframe, enter-frame
- Applies to: web (Playwright selectors)
- Symptom: The login fields are visible, but web find cannot find them and web type · click --selector end with a timeout or assert_failed. Writing 'iframe >> input' does not match either
- Cause: The login form is inside an iframe (App Store Connect login, etc.). web find scans only the top-level document. --selector on type · click · text · assert is a Playwright selector, so it needs the step that enters the iframe (internal:control=enter-frame) to reach it
- Fix:
  1. launch_cli.py web type --selector "iframe >> internal:control=enter-frame >> input#account_name_text_field" --cred <name> --cred-field account
  2. launch_cli.py web click --selector "iframe >> internal:control=enter-frame >> #sign-in" --expect-text <text shown after login>
  3. With several iframes, narrow the first step to iframe#<id>. web find does not look inside iframes, so pick field names from a web shot
  4. In a read-only (--readonly) session the login button may be blocked too — tell the user and add --confirm-mutating
- Refs: #889 · verified 2026-10-17

### `web-orphan-headless-chrome` — Double-clicking an HTML file does not open Chrome — orphan headless Chrome

- Codes: `browser_hung`
- Keywords: headless, chrome
- Symptom: A double-clicked html file shows nothing, or web open hangs
- Cause: A headless Chrome whose profile is gone (PPID 1) is left running and receives the default Chrome requests
- Fix:
  1. Clean up orphans with launch_cli.py web close --stale (other people's live browsers are only reported)
  2. By hand: in ps -axo pid,ppid,command | grep -- --headless, look for entries with PPID 1
  3. If reconnecting hangs, open with a new absolute --root, keeping in mind the login will be gone
- Refs: #921 · verified 2026-10-18
- See also: `browser-start-stale-process-or-lock`

### `web-page-changed-by-other-session` — Another session moves the same tab and your input is lost

- Codes: `page_changed_by_other_session` · `tab_gone`
- Keywords: tab_warning, LAUNCH_TAB
- Symptom: web results carry tab_warning (page_changed_by_other_session), or the page you were on changed to an unrelated site
- Cause: Several sessions share the same repo's browser, and every unnamed session drives the same default tab
- Fix:
  1. launch_cli.py web tab new --name <name> --url <url>
  2. Prefix every web command in this session with LAUNCH_TAB=<name>
  3. On tab_gone, recreate it with web tab new --name <same name>
  4. Save long input after each step
- Refs: #878 · verified 2026-10-17

### `web-playwright-or-browser-missing` — playwright_missing · browser_missing — web setup is needed

- Codes: `playwright_missing` · `browser_missing`
- Symptom: web open ends with playwright_missing (no Playwright) or browser_missing (Chromium is not installed)
- Cause: Web control uses Playwright and a browser in a dedicated virtual environment (under ~/.projectops). It is not set up yet, or the package exists but the browser files are missing
- Fix:
  1. Ask the user before installing (about 100 MB): launch_cli.py web setup
  2. On an internal network, use an installed Chrome · Edge: prefix web open with LAUNCH_CHROMIUM_PATH=<browser executable path>
  3. If web setup fails with pip_failed, install playwright pillow from the internal PyPI mirror first (ask the user first)
- Refs: #857, #889 · verified 2026-10-17

### `web-readonly-mutating-blocked` — Save · submit buttons return mutating_blocked in a read-only session

- Codes: `mutating_blocked`
- Symptom: web click ends with mutating_blocked (not pressed because the session is read-only)
- Cause: In a session opened with web open --readonly, buttons whose text means delete · submit · save · publish (matched words include 삭제·제출·저장·게시) are not pressed without --confirm-mutating. Links, tabs and rows are navigation and are not blocked
- Fix:
  1. Tell the user what will change and get approval (hard to undo)
  2. After approval: launch_cli.py web click --ref <number> --confirm-mutating
  3. If you only need to look, navigate with links · tabs — first check whether you need to press the button at all
- Refs: #825, #889 · verified 2026-10-17

### `web-save-by-network` — Judge whether a save worked by the request response, not on-screen text

- Keywords: POST, 저장, save
- Symptom: The save button was pressed, but success is not visible on screen
- Cause: Console screens have no success message, or it disappears
- Fix:
  1. Check the POST/PUT response status with launch_cli.py web click --capture-requests
  2. Judge by status 2xx vs 4xx (URL query strings are masked)
- Refs: #930 · verified 2026-10-18

### `web-script-browser-memory-exceeded` — Bulk scraping in web script bloats browser memory — use cookies + HTTP

- Codes: `browser_memory_exceeded`
- Keywords: 스왑, swap, 대량 수집, bulk scraping
- Symptom: While web script walks thousands of pages, browser_memory_exceeded appears, or browser_hung repeats before that and the computer slows down from swapping
- Cause: Every page opened inside the browser piles up renderers and cache. Measured: one snippet grew Chrome to 275 GB with 40 GB of swap. The browser is a login tool, not a scraping engine
- Fix:
  1. Use the browser only to log in, and have web script write context.cookies() to a file in the run folder (do not print it as the result — it would stay in the records)
  2. Scrape over HTTP (urllib · requests) with those cookies in a Cookie header. If a list API exists, call the API instead of the screens
  3. If it must run in the browser, split pages into batches of a few dozen, call web script several times, and close opened tabs with page.close()
  4. The limit is web script --memory-limit-mb or PRO_LAUNCH_BROWSER_MEMORY_LIMIT_MB (default 32768). Going over kills the browser, so start it again with web open
- Refs: #973 · verified 2026-10-21
- See also: `web-orphan-headless-chrome`

### `web-scroll-container-capture` — Inner-scroll screens (Google Forms editor, etc.) are not captured by full-page

- Keywords: full-page, container
- Symptom: web shot --full-page is cut off at the first screen
- Cause: An inner container scrolls, not the document
- Fix:
  1. launch_cli.py web shot --container <selector> --tiles 5
  2. By hand: repeat web scroll --container <selector>, then web shot
- Refs: #930 · verified 2026-10-18

### `web-secret-in-input` — A secret value exists only inside an input or behind a copy button

- Keywords: Client Secret, SHA-1
- Symptom: The value does not appear in web text
- Cause: The value is only in input.value or behind a copy button
- Fix:
  1. launch_cli.py web value --selector <selector> --save-env NAME (saves without printing the value)
  2. For a copy button, click it, then web clipboard --save-env NAME
  3. Do not OCR a value shown on screen (I/l confusion)
- Refs: #930 · verified 2026-10-18

### `web-selector-guess-timeout` — A guessed --selector misses — pick from candidates in the result, press by --ref

- Codes: `selector_not_found` · `element_not_actionable` · `element_disabled`
- Keywords: waiting for locator, Timeout
- Symptom: web click · type end with selector_not_found · element_not_actionable or web_action_failed ('Timeout … exceeded … waiting for locator'). The same failure repeats as selectors are swapped
- Cause: The selector was guessed without reading the screen. No element matches, or it exists but is hidden or covered, so the target wait (--timeout; 4 s by default for actions, formerly 10 s) runs out. A disabled element ends at once with element_disabled
- Fix:
  1. Pick the right one from candidates in the failure result and call again with --ref as next says (earlier entries are closer to the guessed selector)
  2. launch_cli.py web click --ref <number> --expect-url <part of the new URL>
  3. If there are no candidates, pick with web find --text <button text>
  4. launch_cli.py web find --text <button text>
  5. launch_cli.py web inspect --role input
  6. For inputs, get a ref with web inspect --role input and enter it with web type --ref <number> --text <value>
  7. If disabled is true in find · inspect · candidates, or element_disabled comes back, first meet the condition that enables the button (required fields · checkboxes)
  8. If the screen is clearly slow to render, raise it, e.g. --timeout 10
- Refs: #825, #889, #888 · verified 2026-10-17

### `web-viewport-width-height` — web viewport --width --height returns bad_viewport — set the size with --preset

- Codes: `bad_viewport`
- Keywords: 뷰포트 모릅니다
- Symptom: web viewport --width 1280 --height 900 ends with bad_viewport (error: "Unknown viewport ''")
- Cause: viewport reads only --preset. --width · --height are window-size options for when web open starts a new window, so viewport does not use them
- Fix:
  1. launch_cli.py web viewport --preset 1280x900
  2. launch_cli.py web viewport --preset mobile
  3. Presets are mobile (390x844) · tablet (820x1180) · desktop (1280x800). To reset: web viewport --clear
- Refs: #889 · verified 2026-10-17

## Android (`android`)

| id | Title | Codes |
|---|---|---|
| `android-adb-missing` | adb_missing · android_tool_missing — adb not found | `adb_missing` · `android_tool_missing` |
| `android-app-not-foreground` | app launch is ok but another screen is on top | `not_foreground` |
| `android-emulator-unresponsive-host-swap` | Emulator does not respond — host memory is full | `device_unresponsive` · `ui_dump_failed` |
| `android-flutter-doubled-desc` | Android Flutter button desc appears twice | `not_found` |
| `android-korean-ime-jamo` | Android app type is ok but the Korean keyboard turns input into jamo | `typed_text_mismatch` |
| `android-maestro-driver-start-timeout` | maestro_driver_timeout — Maestro Android driver did not start in time | `maestro_driver_timeout` |
| `android-maps-locale` | Google Maps labels do not follow the app language | — |
| `android-no-focused-window` | no_focused_window — no focused window, screen structure unreadable (null root) | `no_focused_window` |
| `android-non-ascii-text` | Android app type returns non_ascii_unsupported — adb cannot type Korean | `non_ascii_unsupported` |
| `android-system-restart-loop` | android_system_not_ready · ui_automation_unavailable — emulator restart loop | `android_system_not_ready` · `ui_automation_unavailable` · `ui_dump_timeout` |

### `android-adb-missing` — adb_missing · android_tool_missing — adb not found

- Codes: `adb_missing` · `android_tool_missing`
- Symptom: Android device actions end with adb_missing or android_tool_missing
- Cause: adb is neither on PATH nor in a standard SDK location (platform-tools under ~/Library/Android/sdk, ~/Android/Sdk, $ANDROID_HOME, $ANDROID_SDK_ROOT)
- Fix:
  1. If the SDK is elsewhere, call again with ANDROID_HOME=<SDK path> in front
  2. launch_cli.py doctor
  3. Ask the user before installing SDK platform-tools
- Refs: #889 · verified 2026-10-17

### `android-app-not-foreground` — app launch is ok but another screen is on top

- Codes: `not_foreground`
- Keywords: mCurrentFocus, MinuteMaidActivity
- Symptom: launch · relaunch · back succeed but the screen does not change (e.g. another session's Google login)
- Cause: Another app (e.g. the com.google.android.gms login) holds the top of a shared emulator. back may not work
- Fix:
  1. Check blocking_activity in the response
  2. Check directly with adb shell dumpsys window | grep mCurrentFocus
  3. Check owner in device list to see if someone else uses the device; if so, ask first
  4. If it does not clear, launch_cli.py device reboot --cold (about 35 s)
- Refs: #923, #925 · verified 2026-10-18
- See also: `android-no-focused-window`

### `android-emulator-unresponsive-host-swap` — Emulator does not respond — host memory is full

- Codes: `device_unresponsive` · `ui_dump_failed`
- Keywords: swap, offline, system_server
- Symptom: adb install · shell time out, followed by ui_dump_failed (count 0) or offline
- Cause: Host swap is nearly full, or the AVD has 1 core/2 GB, so the watchdog keeps restarting system_server
- Fix:
  1. Check memory pressure with launch_cli.py doctor --resources
  2. Clean up and boot again with launch_cli.py device reboot --device <id> --cold
  3. If the AVD is small: emulator -avd <name> -no-snapshot -cores 4 -memory 4096
  4. 'Broken pipe'/'Can't find service: package' right after boot: wait until service check package says found, then retry
  5. With -no-snapshot-save, app data written while running is lost on shutdown
- Refs: #924 · verified 2026-10-18
- See also: `android-system-restart-loop`

### `android-flutter-doubled-desc` — Android Flutter button desc appears twice

- Codes: `not_found`
- Keywords: desc, Semantics
- Symptom: app tap --text returns not_found, but the desc in tree is 'label\nlabel'
- Cause: Flutter merges Semantics into content-desc, so the same line repeats
- Fix:
  1. launch_cli.py app tap --desc <label> (newer versions match line by line)
  2. On older versions, pass the whole string including the newline to --desc
- Refs: #927 · verified 2026-10-18

### `android-korean-ime-jamo` — Android app type is ok but the Korean keyboard turns input into jamo

- Codes: `typed_text_mismatch`
- Keywords: 자모, Gboard, IME, jamo
- Symptom: You typed an English ID with app type, but the field contains Korean jamo
- Cause: adb input text sends key events, so the Gboard Korean layout composes them. The result differs even for ASCII values
- Fix:
  1. launch_cli.py app type --ime ascii --text <value> (switches to the Maestro IME while typing, then restores)
  2. Manual: adb shell ime set dev.mobile.maestro/.input.MaestroInputMethodService, type, then restore the original IME
  3. The IME is a device-wide setting. If another session uses the device, ask first
- Refs: #926 · verified 2026-10-18
- See also: `android-non-ascii-text`

### `android-maestro-driver-start-timeout` — maestro_driver_timeout — Maestro Android driver did not start in time

- Codes: `maestro_driver_timeout`
- Keywords: did not start up in time
- Symptom: app flow (or a direct maestro test) stops with 'Maestro Android driver did not start up in time'. The same flow works at other times
- Cause: Emulator or host overload kept the on-device driver apps (dev.mobile.maestro, dev.mobile.maestro.test) from responding in time (reported 3 times, during builds)
- Fix:
  1. app flow already force-stops the driver apps and retries once before returning this code. Do not repeat the same command right away
  2. Check whether heavy work such as a build (gradle · xcodebuild) is running, and retry after it ends
  3. If it persists, ask the user about an emulator cold boot (emulator -avd <name> -no-snapshot-load)
- Refs: #862 · verified 2026-10-17

### `android-maps-locale` — Google Maps labels do not follow the app language

- Keywords: locale, Maps
- Symptom: You changed the Flutter app language, but the map labels stay the same
- Cause: Map labels follow the Activity locale. Right after a system language change, GMS caches the locale
- Fix:
  1. launch_cli.py device locale --device <id> --lang ja --region JP --app <package>
  2. Directly: adb shell cmd locale set-app-locales <pkg> --locales ja-JP (verify with get-app-locales)
  3. If tiles are blank, restart the app and Play services
  4. When done, revert with --restore
- Refs: #929 · verified 2026-10-18

### `android-no-focused-window` — no_focused_window — no focused window, screen structure unreadable (null root)

- Codes: `no_focused_window`
- Keywords: null root node returned by UiTestAutomationBridge
- Symptom: app tree · app tap --text · waits in app run fail, and uiautomator dump prints 'ERROR: null root node returned by UiTestAutomationBridge.'. The home screen seems to be showing
- Cause: Android has no window with focus (mCurrentFocus=null in dumpsys window). Happens right after a reboot, with the screen off, locked, or mid-transition (measured: 5 times in a row after an emulator soft reboot)
- Fix:
  1. The CLI already wakes the screen (WAKEUP · unlock) and reads up to three times before returning this code. Call app tree once more after a few seconds
  2. Look at the current screen with app shot. If it is a password lock screen, ask the user to unlock it
  3. If it persists, check with adb -s <serial> shell dumpsys window | grep mCurrentFocus whether a focused window appeared
- Refs: #894 · verified 2026-10-17

### `android-non-ascii-text` — Android app type returns non_ascii_unsupported — adb cannot type Korean

- Codes: `non_ascii_unsupported`
- Symptom: On Android, typing Korean text with app type ends with non_ascii_unsupported
- Cause: Android input uses adb input text, which accepts ASCII only
- Fix:
  1. If an English or numeric value works instead, use it
  2. If Korean text is required, ask the user before installing an IME such as ADBKeyboard
  3. Otherwise, ask the user to type it themselves
- Refs: #889 · verified 2026-10-17

### `android-system-restart-loop` — android_system_not_ready · ui_automation_unavailable — emulator restart loop

- Codes: `android_system_not_ready` · `ui_automation_unavailable` · `ui_dump_timeout`
- Keywords: Timeout while connecting UiAutomation, Can't find service, Transport endpoint is not connected
- Symptom: uiautomator dump ends with 'Killed' or hangs, and the screen stays on the Google boot logo. adb shell dumpsys activity gives 'Can't find service: activity'; /sdcard gives 'Transport endpoint is not connected'
- Cause: system_server restarts every few minutes (pidof system_server changes, getprop init.svc.bootanim = running). Seen on a long-running emulator (measured: up 1 day 10 hours · 100 MB free of 2 GB). sys.boot_completed stays 1, so boot looks finished
- Fix:
  1. adb -s <serial> shell getprop init.svc.bootanim — if running, the system is not up yet
  2. After the user confirms, adb -s <serial> reboot (soft reboot, keeps data). Measured: boot finished in 52 s and app run worked
  3. If nothing changes after a few minutes, ask about a cold boot: emulator -avd <AVD> -no-snapshot-load (another session may use it; do not shut it down on your own)
  4. If only ui_automation_unavailable persists, check whether other automation (Maestro · Appium) holds UiAutomation
- Refs: #894 · verified 2026-10-17

## iOS (`ios`)

| id | Title | Codes |
|---|---|---|
| `ios-app-vanishes-after-launch` | iOS app vanishes right after launch, and app shot captures the home screen | `app_exited` |
| `ios-label-in-desc-doubled` | iOS Flutter button label appears doubled in desc, so --text cannot tap it | `not_found` |
| `ios-maestro-driver-port-conflict` | iOS tree finds 0 elements with several simulators — driver port 22087 conflict | `ui_dump_failed` |
| `ios-maestro-log-keeps-input-text` | Maestro's record (maestro.log) keeps the real inputText value in plain text | — |
| `ios-maestro-not-installed` | iOS app tap · swipe · tree return ios_tool_missing — Maestro is not installed | `ios_tool_missing` |
| `ios-maestro-point-integer-percent` | Maestro flow point percentages accept integers only (NumberFormatException) | — |
| `ios-maestro-session-reconnect` | The resident session dropped — another maestro test attached to the same device | `session_start_failed` |
| `ios-maestro-slow-cold-start` | iOS app tap · swipe · tree take tens of seconds — Maestro JVM starts per call | — |
| `ios-maestro-stale-driver-or-overload` | iOS tap fails at 90 s and session start fails too — leftover driver or load | `session_start_failed` |
| `ios-status-bar-custom-time` | iOS capture status bar time must match the notification time | — |

### `ios-app-vanishes-after-launch` — iOS app vanishes right after launch, and app shot captures the home screen

- Codes: `app_exited`
- Keywords: SIGABRT, crash
- Symptom: app launch returns ok, but the app is not visible and shot shows the home screen
- Cause: The app crashes right after launch (e.g. Secrets.xcconfig is missing in the worktree, causing GADInvalidInitializationException)
- Fix:
  1. Read crash_report and the exception line in the launch_cli.py app launch response
  2. If absent, open the latest Runner-*.ips in ~/Library/Logs/DiagnosticReports
  3. See console errors with xcrun simctl launch --console-pty <UDID> <bundle>
  4. Check that local config files (Secrets.xcconfig, etc.) were copied into the worktree
- Refs: #923 · verified 2026-10-18

### `ios-label-in-desc-doubled` — iOS Flutter button label appears doubled in desc, so --text cannot tap it

- Codes: `not_found`
- Keywords: desc, Semantics
- Symptom: app tap --text returns not_found, but the text is in the tree ('GitHub로 계속하기\nGitHub로 계속하기', i.e. 'Continue with GitHub' twice)
- Cause: Flutter Semantics labels come out as desc, with the same line repeated twice. Older versions looked only at the text field
- Fix:
  1. Check the element's desc in app tree
  2. Tap with launch_cli.py app tap --desc <text> (the latest version matches desc and doubled labels automatically)
  3. If a button inside a webview cannot be found by name, use --at ratio coordinates
- Refs: #927 · verified 2026-10-18

### `ios-maestro-driver-port-conflict` — iOS tree finds 0 elements with several simulators — driver port 22087 conflict

- Codes: `ui_dump_failed`
- Keywords: 22087, count 0, Address already in use
- Symptom: With two or more simulators booted, app tree · tap return ui_dump_failed (count 0), or read another simulator's screen elements
- Cause: The Maestro iOS driver (XCTest runner) always uses host port 22087. If a driver for another simulator (including other sessions) holds that port, this device's driver cannot start or attaches to the wrong device
- Fix:
  1. Find the process holding the port with lsof -nP -iTCP:22087 -sTCP:LISTEN, and check which UDID's driver it is with ps -p <PID> -o command=
  2. If another session's driver holds it, do not kill it — wait for that work to finish or ask the user (Maestro drives one simulator at a time)
  3. If pro-launch left the driver behind, clean it up with launch_cli.py app session stop --device <that UDID> --kill-stale
  4. Then check that launch_cli.py app tree --device <UDID> reads elements; to keep driving, run app session start --device <UDID>
- Refs: #973 · verified 2026-10-21
- See also: `ios-maestro-stale-driver-or-overload`, `ios-maestro-session-reconnect`

### `ios-maestro-log-keeps-input-text` — Maestro's record (maestro.log) keeps the real inputText value in plain text

- Keywords: maestro.log, evaluatedCommand, InputTextCommand
- Symptom: ~/.maestro/tests/<timestamp>/maestro.log contains InputTextCommand(text=<real value>), even though it was passed as an environment variable (${...})
- Cause: maestro test records each command with environment variables expanded (evaluatedCommand). The default record location is ~/.maestro/tests, so it stays after the run ends (measured on Maestro 2.10.0)
- Fix:
  1. pro-launch's app type and type steps send the record to a temp folder (--debug-output <temp folder> --flatten-debug-output) and delete it; use the same options when you call maestro test yourself
  2. If records already remain, tell the user and ask whether to delete them (do not delete them on your own)
- Refs: #894, #895 · verified 2026-10-17

### `ios-maestro-not-installed` — iOS app tap · swipe · tree return ios_tool_missing — Maestro is not installed

- Codes: `ios_tool_missing`
- Applies to: macOS + iOS simulator
- Symptom: On an iOS simulator, app tap · app swipe · app tree stop with ios_tool_missing (no iOS control tool)
- Cause: simctl has no tap or screen-structure commands, so iOS control is delegated to Maestro. maestro is neither on PATH nor at ~/.maestro/bin/maestro
- Fix:
  1. Ask the user before installing: curl -fsSL "https://get.maestro.mobile.dev" | bash
  2. launch_cli.py app tree --device <simulator id>
  3. Each call starts a new Maestro (JVM) and takes 10–40 s — run long scenarios at once as the project's Maestro flow
- Refs: #826 · verified 2026-10-17

### `ios-maestro-point-integer-percent` — Maestro flow point percentages accept integers only (NumberFormatException)

- Keywords: NumberFormatException, point
- Symptom: tapOn point: "38%,72.7%" in a raw flow keeps failing on retry and looks like a driver problem
- Cause: Maestro point coordinates accept only integer percentages, so 72.7 raises NumberFormatException. A wrapper that only retries hides the real error
- Fix:
  1. Read the last error line in maestro.log first (~/.maestro/tests/<timestamp>/maestro.log)
  2. Round the percentage to an integer (72.7% → 73%)
  3. Prefer app tap --at ratio coordinates over raw flows when possible (pro-launch rounds them)
- Refs: #922 · verified 2026-10-18

### `ios-maestro-session-reconnect` — The resident session dropped — another maestro test attached to the same device

- Codes: `session_start_failed`
- Keywords: Device became unreachable, session_fallback, device_unreachable
- Symptom: After app session start, a fast tree · tap once takes about 9 s (session_reconnected: true), or falls back to per-call launches with session_fallback: device_unreachable
- Cause: While a maestro mcp session is attached, another maestro test on the same simulator (including app type and other sessions' tests) breaks the session's driver connection — 'Failed to run flow: Device became unreachable during deviceInfo' (measured on Maestro 2.10.0). The relay restarts maestro mcp and reattaches on the next call
- Fix:
  1. One slow call is normal — keep going
  2. If device_unreachable persists, check whether another session is running maestro on the same device (ps -ax | grep maestro)
  3. launch_cli.py app session stop --device <UDID>, then start again
- Refs: #894 · verified 2026-10-17
- See also: `ios-maestro-slow-cold-start`

### `ios-maestro-slow-cold-start` — iOS app tap · swipe · tree take tens of seconds — Maestro JVM starts per call

- Keywords: maestro, 90초, 90s
- Symptom: On an iOS simulator, app tap · swipe · tree take 20–50 s each or fail with 'maestro did not respond (90s)'. On Android they take a few seconds
- Cause: simctl has no tap or screen-structure commands, so iOS control goes to Maestro, and a new Maestro (JVM) starts on every call. The per-action limit is 90 s. This is expected slowness, not a fault
- Fix:
  1. If you look → decide → tap many times, start the resident session first: launch_cli.py app session start --device <UDID> (then tree 0.6 s · tap 1 s)
  2. Do not fire the same command again because it is slow — wait for the previous call to finish
  3. To check the screen, add --shot to the action instead of calling shot: launch_cli.py app tap --device <UDID> --text <text> --shot <name>
  4. Run long scenarios at once as the project's Maestro flow
- Refs: #826, #889, #894 · verified 2026-10-17
- See also: `ios-maestro-not-installed`, `ios-maestro-session-reconnect`

### `ios-maestro-stale-driver-or-overload` — iOS tap fails at 90 s and session start fails too — leftover driver or load

- Codes: `session_start_failed`
- Keywords: tools/call timed out, maestro 응답 없음, xcodebuild, maestro unresponsive, respond
- Symptom: tap_failed repeats with 'maestro did not respond (90s)', and app session start, as advised, fails with 'tools/call timed out after 120s'
- Cause: An xcodebuild (maestro-driver-ios-config.xctestrun) or maestro JVM left by an earlier run is still alive, or host load is high, so the driver cannot start. Starting a session does not fix this
- Fix:
  1. Check load with uptime (2x the core count or more means overload)
  2. In ps, check that maestro-driver-ios-config · maestro/lib are not owned by a pro-launch session
  3. Kill only the leftovers: pkill -f maestro-driver-ios-config; pkill -f maestro/lib, then confirm with launch_cli.py app tree
  4. If load is high, retry with MAESTRO_DRIVER_STARTUP_TIMEOUT=180000 (iOS driver not ready in time)
- Refs: #922 · verified 2026-10-18
- See also: `ios-maestro-slow-cold-start`, `ios-maestro-session-reconnect`

### `ios-status-bar-custom-time` — iOS capture status bar time must match the notification time

- Keywords: status_bar, 상태바, status bar
- Symptom: Store captures need a status bar time other than 9:41
- Cause: app shot --clean-status fixes the time at 9:41 by default. Set any other time directly with simctl status_bar
- Fix:
  1. launch_cli.py app shot --clean-status --time 7:42
  2. By hand: xcrun simctl status_bar <UDID> override --time 7:42, capture, then restore with status_bar clear
- Refs: #928 · verified 2026-10-18

## SSH (`ssh`)

| id | Title | Codes |
|---|---|---|
| `ssh-sshpass-missing` | Password ssh returns sshpass_missing — update the plugin (OpenSSH askpass path) | `sshpass_missing` |
| `ssh-windows-cmd-encoding` | Output from a Windows cmd (CP949) host is garbled | — |

### `ssh-sshpass-missing` — Password ssh returns sshpass_missing — update the plugin (OpenSSH askpass path)

- Codes: `sshpass_missing`
- Symptom: launch_cli.py ssh ends with sshpass_missing (an older plugin required sshpass for password logins)
- Cause: Plugins before #987 needed sshpass for passwords. Current versions fall back to OpenSSH SSH_ASKPASS (OpenSSH 8.4+) with a single password attempt
- Fix:
  1. Update the plugin, then rerun the same launch_cli.py ssh command
  2. With a key: launch_cli.py ssh --cred <server> --key-path <key file> --command '<command>'
  3. If ssh is older than OpenSSH 8.4 and still prompts or fails, use pro-ssh's scripts/ssh_connect.py (paramiko) — skills/pro-ssh/SKILL.md
- Refs: #841, #889, #987 · verified 2026-10-29

### `ssh-windows-cmd-encoding` — Output from a Windows cmd (CP949) host is garbled

- Keywords: UnicodeDecodeError, chcp
- Symptom: The ssh response has garbled characters, or older versions fail with UnicodeDecodeError
- Cause: Windows cmd outputs in CP949
- Fix:
  1. Newer versions decode UTF-8 > CP949 in that order (check stdout_encoding)
  2. On older versions, prefix the command with 'chcp 65001 >nul &'
- Refs: #933 · verified 2026-10-18

## General (`general`)

| id | Title | Codes |
|---|---|---|
| `general-app-no-device` | app command returns no_device — several devices attached or simulator not booted | `no_device` |
| `general-bad-args-option-names` | bad_args — wrong option name (--full-page · --field · positional argument) | `bad_args` |
| `general-cred-field-missing` | --cred returns cred_field_missing — without a field choice it types password | `cred_field_missing` |
| `general-cred-never-read-config` | Never read credentials straight from the config file | — |
| `general-env-not-set` | --text-env returns env_not_set — pass the variable name, not the value | `env_not_set` |
| `general-login-interstitial-policy` | Login stops every time at trust-device · stay-signed-in · upsell screens | — |
| `general-otp-no-resubmit` | Do not resubmit the login form while waiting for a verification code | — |
| `general-plugin-cache-version-drift` | Scripts called from a different plugin cache version path each session | — |
| `general-render-failed-first-error` | render run returns render_failed — start from first_error; usually services.dart | `render_failed` |
| `general-root-unknown-skill-folder` | Captures and state pile up in the wrong place, e.g. ~/.projectops/launch/scripts | — |
| `general-timeout-unit-seconds` | --timeout given in milliseconds — the unit is seconds | `timeout_too_large` |
| `general-zsh-variable-command` | In zsh a command stored in a variable is one word and fails with 'no such file' | — |

### `general-app-no-device` — app command returns no_device — several devices attached or simulator not booted

- Codes: `no_device`
- Symptom: app shot · tap · type end with no_device. The response lists android · ios_booted devices
- Cause: No --device and no $DEV, and the number of attached devices is not exactly one (with several, it stops rather than capture the wrong device). Or the UDID given with --device is not a booted simulator (the list shows only Booted)
- Fix:
  1. Pick one from android · ios_booted in the response and call again with --device <serial or UDID>
  2. Bind a role to pin it as $DEV in env.sh: launch_cli.py device bind --role <role> --serial <serial>
  3. If the list is empty, boot first: emulator -avd <AVD name> or xcrun simctl boot <UDID>
- Refs: #583, #889 · verified 2026-10-17

### `general-bad-args-option-names` — bad_args — wrong option name (--full-page · --field · positional argument)

- Codes: `bad_args`
- Keywords: 인자가 올바르지 않습니다
- Symptom: The command ends with bad_args ("Invalid arguments: unrecognized arguments …")
- Cause: You passed an option or positional argument that does not exist. Common mistakes: web shot takes --full (not --full-page), the credential field is --cred-field (not --field), cred show takes --name <name> (not positional), cred actions are only list · show · set · unset · import-ssh (no add)
- Fix:
  1. Read the unrecognized arguments · invalid choice part of error first
  2. launch_cli.py web --help
  3. launch_cli.py cred show --name <name>
  4. If the response has load_errors, a module is broken and its subcommand is hidden — check the plugin version
- Refs: #889 · verified 2026-10-17

### `general-cred-field-missing` — --cred returns cred_field_missing — without a field choice it types password

- Codes: `cred_field_missing`
- Keywords: password 값이 없습니다
- Symptom: web type · app type --cred end with cred_field_missing ("'<name>' has no 'password' value")
- Cause: Without --cred-field, --cred types the password field. You meant to fill the username box, or that credential lacks the field. The response's fields lists the fields that exist
- Fix:
  1. For the username box: launch_cli.py web type --selector <box> --cred <name> --cred-field account
  2. If the field really is missing, get the value from the user and fill it with cred set (do not write the value yourself)
- Refs: #604, #889 · verified 2026-10-17

### `general-cred-never-read-config` — Never read credentials straight from the config file

- Keywords: config.json, password
- Symptom: To pass a password to a raw tool (maestro, etc.), the agent reads config.json and writes a temporary file
- Cause: Saved values used through --cred are masked and never recorded. Reading them directly leaves plain text in files, command lines and the conversation
- Fix:
  1. Use app type --cred <name> --cred-field <field> / web type --cred
  2. Use cred references in app run steps too
  3. If plain text was already left behind, delete the file and suggest the user change the password
- Refs: #934 · verified 2026-10-18

### `general-env-not-set` — --text-env returns env_not_set — pass the variable name, not the value

- Codes: `env_not_set`
- Keywords: 환경변수 비어
- Symptom: web type · app type end with env_not_set ("Environment variable … is empty")
- Cause: --text-env takes an environment variable name. No variable with that name is in the launch_cli process environment: the value itself was passed, or it was set in another Bash call and is gone (Bash resets on every call)
- Fix:
  1. Prefix it on the same command line: CODE=<value> launch_cli.py web type --selector <box> --text-env CODE
  2. The command line stays in the session record — pass only values that may stay there this way, such as one-time codes
  3. For a saved login, do not handle the value; use --cred <name> (the value never reaches the command line or records)
- Refs: #604, #889 · verified 2026-10-17

### `general-login-interstitial-policy` — Login stops every time at trust-device · stay-signed-in · upsell screens

- Keywords: trust this device, 기기 신뢰, 다시 묻지, 로그인 상태 유지, stay signed in, passkey, 패스키, trust device, keep me signed in, don't ask again
- Applies to: web · android · ios
- Symptom: On every login the agent asks the user the same question at trust this device (don't ask again) · stay signed in · passkey or contact upsell screens. In remote-control the user cannot see the screen, so the flow breaks
- Cause: No interstitial login screen policy is saved (every key is ask). Screens differ per provider, so there is no auto-click code; the agent identifies the screen type and presses according to the saved policy
- Fix:
  1. launch_cli.py cred policy get --name <name>
  2. launch_cli.py cred policy set --name <name> --key trust_device --value always
  3. launch_cli.py cred policy set --key skip_nags --value always
  4. If login_policy in the web type --cred · app type --cred result is always · never, press without asking. If ask, ask with a capture and save 'this account / all sites / just once' via cred policy set
  5. Do not press screens you cannot identify — send a capture to the conversation and ask. Never disable 2FA or change account security settings
- Refs: #905 · verified 2026-10-18

### `general-otp-no-resubmit` — Do not resubmit the login form while waiting for a verification code

- Keywords: Invalid OTP, 인증 코드, verification code
- Symptom: The user sent the code, but entering it shows Invalid OTP
- Cause: Resubmitting the login sends a new code and invalidates the previous one
- Fix:
  1. Do not resubmit the form while waiting for the code
  2. First check with web text that the OTP screen is showing
  3. If you already resubmitted, ask the user for the new code
- Refs: #881, #934 · verified 2026-10-18

### `general-plugin-cache-version-drift` — Scripts called from a different plugin cache version path each session

- Keywords: plugins/cache, projectops-marketplace
- Symptom: The agent calls ~/.claude/plugins/cache/…/projectops/<version>/skills/pro-launch/scripts directly. The docs read and the script run differ in version, so an option is missing (bad_args) or behavior differs from the docs
- Cause: The plugin cache keeps several version folders. A version path copied from a past session or memory may not be the current one. 'Find the scripts' in SKILL.md picks the highest version with sort -V | tail -1
- Fix:
  1. At session start, rerun the 'Find the scripts' block in SKILL.md to get SCRIPTS — do not paste an old version path
  2. Read the docs from the same version folder too (references/ above SCRIPTS)
  3. Within a session, write the path you got as a literal value (Bash loses variables on every call)
- Refs: #889 · verified 2026-10-17

### `general-render-failed-first-error` — render run returns render_failed — start from first_error; usually services.dart

- Codes: `render_failed`
- Keywords: MethodChannel, services.dart, 렌더 명령 실패
- Symptom: render run ends with render_failed ("Render command failed") and collects nothing. The same failure repeats
- Cause: The render command (flutter test, etc.) failed to compile or run. The most common cause: the render skeleton lacks the package:flutter/services.dart import, so MethodChannel · SystemChrome are not found
- Fix:
  1. Read first_error in the response first (or output_tail if absent)
  2. On Undefined name · Couldn't find constructor 'MethodChannel', add import 'package:flutter/services.dart';
  3. If you use screen widgets or fake models, also add their package:<app>/... imports
  4. See the pitfalls table in references/render.md
- Refs: #901, #889 · verified 2026-10-17

### `general-root-unknown-skill-folder` — Captures and state pile up in the wrong place, e.g. ~/.projectops/launch/scripts

- Keywords: root_unknown, root_warning
- Symptom: Captures land in ~/.projectops/launch/scripts/shots or a shared location instead of the project. Responses carry root_unknown · root_warning. Browsers and memory opened earlier are not visible
- Cause: It was called with --root . (or without --root) after cd into the scripts folder. The state and capture location comes from the git remote of --root. A plugin cache maps to this computer's shared location, not a project (older versions split by the folder name scripts)
- Fix:
  1. Call the script by absolute path from the project folder and add --root <project path>
  2. Or prefix PROJECT_ROOT=<project path> (used when called from a scripts or cache folder)
  3. Get the capture location first: launch_cli.py get-output-path --root <project path> --title <title>, then source env.sh
- Refs: #833, #836, #889 · verified 2026-10-17
- See also: `web-browser-not-open-other-root`

### `general-timeout-unit-seconds` — --timeout given in milliseconds — the unit is seconds

- Codes: `timeout_too_large`
- Keywords: --timeout
- Symptom: web type --timeout 3000 hangs for 50 minutes
- Cause: --timeout is in seconds. 3000 is 50 minutes
- Fix:
  1. Give --timeout in seconds (default 10, max 300)
  2. If it already hung, recover with web close, then web open
- Refs: #931 · verified 2026-10-18

### `general-zsh-variable-command` — In zsh a command stored in a variable is one word and fails with 'no such file'

- Keywords: no such file or directory: python3, zsh
- Symptom: L="python3 …/launch_cli.py"; $L web … fails with 'no such file or directory: python3 /…/launch_cli.py'
- Cause: zsh does not split variables into words (unlike bash)
- Fix:
  1. Call the fixed entry point directly: python3 ~/.projectops/bin/launch_cli.py doctor
  2. To repeat it, wrap it in a function: launch() { python3 "$HOME/.projectops/bin/launch_cli.py" "$@"; }
  3. Do not store several arguments in one variable like 'web $a' (use bash -c if needed)
- Refs: #920 · verified 2026-10-18
- See also: `general-plugin-cache-version-drift`

## desktop (`desktop`)

| id | Title | Codes |
|---|---|---|
| `desktop-apple-2fa-code-window` | Apple Account 2FA on this Mac: allow the alert, read the code window | `mutating_blocked` · `window_not_found` |
| `desktop-browser-page-not-in-tree` | desktop tree of Chrome or an Electron app shows only the toolbar, not the page | `not_found` |
| `desktop-macos-permission-terminal` | macOS desktop returns permission_missing although Python was allowed | `permission_missing` |
| `desktop-notification-banner-expires` | A macOS notification banner disappears before it is pressed | `wait_timeout` · `ref_stale` · `window_not_found` |
| `desktop-window-listed-but-content-elsewhere` | A listed dialog shows almost no elements, or click returns ref_stale | `ref_stale` · `tree_unavailable` · `window_not_found` |

### `desktop-apple-2fa-code-window` — Apple Account 2FA on this Mac: allow the alert, read the code window

- Codes: `mutating_blocked` · `window_not_found`
- Keywords: Apple 계정, Apple Account, 허용함, Allow, FollowUpUI, 확인 코드, verification code
- Symptom: A web or app sign-in asks for a code sent to this Mac; the notification 'Apple Account signed in' must be allowed and the code read from a system window
- Cause: macOS shows the request as a Notification Center alert with hidden actions (Allow, Don't Allow) and the code in a floating FollowUpUI window (CoreFollowUp, layer 25) that also holds keyboard focus
- Fix:
  1. Ask the user first: Allow approves a sign-in to their Apple Account. Only for the sign-in this session just started
  2. launch_cli.py desktop wait --window overlay --text "Apple" --timeout 60, then click --ref <ref> --action "<Allow name from named_actions>" --confirm-mutating after the user agrees
  3. launch_cli.py desktop tree --window overlay  # the code is a static text with spaces, e.g. '4 1 9   2 0 1'; remove the spaces
  4. Press the code window's Done button with --confirm-mutating so it returns keyboard focus, then type the code with desktop type --ref <first box> --text <code> --keys or web type
  5. A wrong or partial entry invalidates the code; resend once from the page and do not retry in a loop (the account can be locked)
- Refs: #985 · verified 2026-10-22

### `desktop-browser-page-not-in-tree` — desktop tree of Chrome or an Electron app shows only the toolbar, not the page

- Codes: `not_found`
- Keywords: webarea, AXEnhancedUserInterface, AXManualAccessibility, 주소창
- Symptom: desktop find inside Chrome finds only the address bar; typed keys land in the address bar instead of a page field
- Cause: Chrome and Electron build the page accessibility tree only when an assistive client asks. desktop now turns it on (AXEnhancedUserInterface / AXManualAccessibility) when the web area is empty
- Fix:
  1. launch_cli.py desktop find --window "<title>" --role textfield --max-nodes 1500 --depth 60  # pages are deep
  2. Prefer web find / web type when the page belongs to a pro-launch web session
  3. Type into page fields with desktop type --ref <n> --text <value> --keys (focus is set without the mouse)
- Refs: #985 · verified 2026-10-22

### `desktop-macos-permission-terminal` — macOS desktop returns permission_missing although Python was allowed

- Codes: `permission_missing`
- Keywords: Accessibility, Screen Recording, 손쉬운 사용, 화면 기록
- Symptom: desktop doctor or click returns permission_missing (accessibility or screen_recording) on macOS
- Cause: macOS grants Accessibility and Screen Recording to the app that started the command (Terminal, iTerm, VS Code, Orca), not to python3
- Fix:
  1. System Settings > Privacy & Security > Accessibility: turn on the terminal app that runs the agent
  2. System Settings > Privacy & Security > Screen & System Audio Recording: turn on the same app
  3. Quit and reopen that terminal app, then launch_cli.py desktop doctor
- Refs: #985 · verified 2026-10-22

### `desktop-notification-banner-expires` — A macOS notification banner disappears before it is pressed

- Codes: `wait_timeout` · `ref_stale` · `window_not_found`
- Keywords: Notification Center, notification, 알림 센터
- Symptom: desktop wait or find sees the banner, but the next click returns ref_stale or the banner is gone
- Cause: Banners leave the screen after about 5 seconds; a find between wait and click costs one more process start
- Fix:
  1. launch_cli.py desktop wait --window overlay --text "<banner text>"  # returns matches with ref, no find needed
  2. launch_cli.py desktop click --ref <ref> --action "<name from named_actions>"  # hidden buttons (Close, Allow) need no hover
  3. If it was missed, do the step that sends the notification again
- Refs: #985 · verified 2026-10-22

### `desktop-window-listed-but-content-elsewhere` — A listed dialog shows almost no elements, or click returns ref_stale

- Codes: `ref_stale` · `tree_unavailable` · `window_not_found`
- Keywords: element is gone, OpenWith, 앱 선택, Open With
- Symptom: desktop windows lists a dialog (for example the Windows 'Open With' dialog), but desktop tree shows only the title bar and Close, and click --ref returns ref_stale (element is gone)
- Cause: Some dialogs draw their content in a separate window, or close the visible part when they lose focus and leave a placeholder window behind. The ref was taken from a window that no longer holds that element
- Fix:
  1. launch_cli.py desktop windows  # list again; pick the window that holds the content (zero-size placeholders are no longer listed)
  2. launch_cli.py desktop find --window "<that title>" --text "<button>"
  3. If the dialog closed by itself, do the step that opened it again and press it right away
- Refs: #985 · verified 2026-10-22
