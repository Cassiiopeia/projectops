/* ===================================================================
 * projectops Flutter wizard shared utils (source of truth)
 * ===================================================================
 *
 * Shared by the testflight / playstore / firebase wizards.
 * Loaded **before** each wizard's JS:
 *
 *   <script src="../_shared/wizard-common.js"></script>
 *   <script src="testflight-wizard.js"></script>
 *
 * ⚠️ Rules
 * -------------------------------------------------------------------
 * 1. Pure utils + the flow base implementations that were character-identical in testflight/playstore
 *    (showStep/prevStep/saveState/clearState, custom Secrets) live here.
 *    Diverging flows (goToStep/nextStep/loadState/initializeStep) and
 *    output generation (generateXxx) stay in each wizard's file.
 * 2. Redefining the same name in wizard JS overrides this source of truth.
 *    Register intentional overrides in check-consistency.py INTENTIONAL_OVERRIDES.
 *    (other duplicate definitions are caught by the checker)
 * 3. Changing a function signature affects all wizards. Always check them together.
 * 4. Screen text goes through translate(key) (wizard-i18n.js — loaded before this file, #769)
 *
 * Why these implementations — the safest of the diverging versions was adopted:
 *   escapeHtml   : firebase version (null-safe + escapes quotes too)
 *   getInputValue: testflight/playstore version (trims)
 *   showToast    : testflight/playstore version (works without #toast in the DOM)
 *   getDateString: unified to YYYY-MM-DD; YYYYMMDD for file names split out as getDateStamp
 * =================================================================== */

/* eslint-disable no-unused-vars */

// ============================================
// Strings / escaping
// ============================================

/** Escaping for innerHTML interpolation. null/undefined are safely treated as empty strings. */
function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/** Escape values placed inside JS string literals such as onclick="fn('...')" */
function escapeJsString(value) {
    return String(value == null ? '' : value)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '');
}

/** For inserting values into shell commands (wraps in single quotes) */
function shellEscape(value) {
    const s = String(value == null ? '' : value);
    return `'${s.replace(/'/g, `'\\''`)}'`;
}

// ============================================
// Dates
// ============================================

/** Date for display (2026-07-27) */
function getDateString() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

/** Date for file names (20260727) — sortable, without spaces or hyphens */
function getDateStamp() {
    return getDateString().replace(/-/g, '');
}

// ============================================
// DOM access
// ============================================

/** Return the trimmed input/textarea value. Empty string if the element is missing. */
function getInputValue(id) {
    const element = document.getElementById(id);
    return element?.value?.trim() || '';
}

function setElementText(id, text) {
    const element = document.getElementById(id);
    if (element) element.textContent = text;
}

function setElementHtml(id, html) {
    const element = document.getElementById(id);
    if (element) element.innerHTML = html;
}

// ============================================
// Notifications / clipboard
// ============================================

/**
 * Bottom-right toast. Created every time so it works without a #toast in the DOM.
 * (the "fixed #toast reference" approach firebase used threw when the element was missing)
 */
function showToast(message) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * Clipboard copy. Falls back to execCommand when navigator.clipboard is missing (old browsers, insecure contexts)
 * or fails. The fallback is required because it must work when opened via file://.
 */
async function copyToClipboard(text, successMessage = translate('common.copied')) {
    const value = String(text == null ? '' : text);
    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(value);
            showToast(successMessage);
            return true;
        }
        throw new Error('clipboard API unavailable');
    } catch (err) {
        try {
            const ta = document.createElement('textarea');
            ta.value = value;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            const ok = document.execCommand('copy');
            document.body.removeChild(ta);
            showToast(ok ? successMessage : translate('common.copyFailed'));
            return ok;
        } catch (fallbackErr) {
            showToast(translate('common.copyFailed'));
            return false;
        }
    }
}

/** Copy a code block — leaves a temporary done mark on the button */
async function copyCode(elementId, buttonEl) {
    const el = document.getElementById(elementId);
    if (!el) return false;
    const ok = await copyToClipboard(el.textContent, translate('common.commandCopied'));
    if (ok && buttonEl) {
        const original = buttonEl.textContent;
        buttonEl.textContent = translate('common.copiedButton');
        buttonEl.classList.add('copied');
        setTimeout(() => {
            buttonEl.textContent = original;
            buttonEl.classList.remove('copied');
        }, 1500);
    }
    return ok;
}

// ============================================
// File handling
// ============================================

/** Text/binary decision by extension and MIME. Decides how the Secret value is converted. */
function getFileType(file) {
    const textExtensions = ['.json', '.txt', '.yml', '.yaml', '.xml', '.plist', '.env', '.properties', '.pem', '.cer', '.crt', '.key', '.md', '.conf', '.config', '.xcconfig'];
    const name = (file.name || '').toLowerCase();
    if (textExtensions.some((ext) => name.endsWith(ext))) return 'text';
    if (file.type && file.type.startsWith('text/')) return 'text';
    if (file.type === 'application/json') return 'text';
    return 'binary';
}

/** File → base64 string (data URL prefix removed) */
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = String(reader.result || '');
            resolve(result.includes(',') ? result.split(',')[1] : result);
        };
        reader.onerror = () => reject(reader.error || new Error(translate('common.fileReadFailed')));
        reader.readAsDataURL(file);
    });
}

/** File → raw text */
function fileToText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(reader.error || new Error(translate('common.fileReadFailed')));
        reader.readAsText(file);
    });
}

/** File name → GitHub Secret key candidate (_BASE64 suffix for binaries) */
function generateKeyName(fileName, fileType) {
    const base = fileName
        .replace(/\.[^.]+$/, '')
        .replace(/[^a-zA-Z0-9]/g, '_')
        .replace(/_+/g, '_')
        .replace(/^_|_$/g, '')
        .toUpperCase();
    return fileType === 'binary' ? `${base}_BASE64` : base;
}

/** Drag & drop area wiring — the pattern all wizards used identically */
function setupDragAndDrop(dropZoneId, onFile) {
    const zone = document.getElementById(dropZoneId);
    if (!zone) return;
    ['dragenter', 'dragover'].forEach((evt) => {
        zone.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('dragover');
        });
    });
    ['dragleave', 'drop'].forEach((evt) => {
        zone.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('dragover');
        });
    });
    zone.addEventListener('drop', (e) => {
        const file = e.dataTransfer?.files?.[0];
        if (file) onFile(file);
    });
}

// ============================================
// OS detection
// ============================================

/** 'windows' | 'mac' | 'linux' — mac when undecidable (the wizards' main environment) */
function detectOS() {
    const ua = navigator.userAgent || navigator.appVersion || navigator.platform || '';
    if (/Win/i.test(ua)) return 'windows';
    if (/Mac/i.test(ua)) return 'mac';
    if (/Linux|X11|Android/i.test(ua)) return 'linux';
    return 'mac';
}

/** POSIX path → Windows path (for command generation) */
function toWinPath(p) {
    return String(p || '').replace(/\//g, '\\');
}

/** Accepts both POSIX (/...) and Windows (C:\...) absolute paths */
function isAbsolutePath(p) {
    const v = String(p || '').trim();
    return v.startsWith('/') || /^[A-Za-z]:[\\/]/.test(v);
}

// ============================================
// Progress saving (localStorage)
// ============================================

/**
 * Read state. Passing legacyKeys migrates progress saved under old keys automatically.
 * (so existing users' saved data is not lost when key names are unified)
 */
function readWizardState(key, legacyKeys = []) {
    try {
        let raw = localStorage.getItem(key);
        if (!raw) {
            for (const legacy of legacyKeys) {
                const old = localStorage.getItem(legacy);
                if (old) {
                    localStorage.setItem(key, old);
                    localStorage.removeItem(legacy);
                    raw = old;
                    break;
                }
            }
        }
        return raw ? JSON.parse(raw) : null;
    } catch (err) {
        console.warn('[wizard state] read failed:', err);
        return null;
    }
}

function writeWizardState(key, state) {
    try {
        localStorage.setItem(key, JSON.stringify(state));
        return true;
    } catch (err) {
        // Keep the wizard alive even on quota exceeded (several large certificates uploaded)
        console.warn('[wizard state] save failed:', err);
        showToast(translate('common.stateSaveFailed'));
        return false;
    }
}

function clearWizardState(key, legacyKeys = []) {
    try {
        localStorage.removeItem(key);
        legacyKeys.forEach((k) => localStorage.removeItem(k));
    } catch (err) {
        console.warn('[wizard state] clear failed:', err);
    }
}

// ============================================
// Version / changelog
// ============================================

/** Parse the versionJson block inlined in the HTML (injected by version-sync.sh) */
function getVersionData() {
    try {
        const el = document.getElementById('versionJson');
        return el ? JSON.parse(el.textContent) : null;
    } catch (err) {
        console.warn('[wizard version] read failed:', err);
        return null;
    }
}

/**
 * Changelog modal — shared by all wizards.
 *
 * ⚠️ Markup contract (structure every wizard HTML must have):
 *   <div id="changelogModal" class="modal-backdrop hidden" onclick="closeChangelogModal(event)">
 *     <div class="modal-content" onclick="event.stopPropagation()">
 *       ... <div id="changelogContent"></div>
 *           <p id="changelogLastUpdated"></p>
 *     </div>
 *   </div>
 *
 * The HTML owns the shell (close button, backdrop click area); this function only fills the content.
 * Replacing the whole modal via innerHTML would lose backdrop-click closing, so it does not.
 */
function openChangelogModal() {
    const modal = document.getElementById('changelogModal');
    const content = document.getElementById('changelogContent');
    const lastUpdated = document.getElementById('changelogLastUpdated');
    if (!modal || !content) return;

    const data = getVersionData();
    if (!data) {
        content.innerHTML = `<div class="text-center text-red-400 py-4">${escapeHtml(translate('common.versionLoadFailed'))}</div>`;
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        return;
    }

    const releases = data.changelog || [];
    content.innerHTML = releases.map((release, index) => {
        const isLatest = index === 0;
        const divider = index < releases.length - 1 ? 'border-b border-slate-700 mb-4' : '';
        const items = (release.changes || []).map((change) => `
                        <li class="text-sm text-slate-400 flex items-start gap-2">
                            <span class="text-slate-600 mt-1">•</span>
                            <span>${escapeHtml(change)}</span>
                        </li>`).join('');
        return `
            <div class="pb-4 ${divider}">
                <div class="flex items-center gap-2 mb-2">
                    <span class="text-white font-semibold">v${escapeHtml(release.version)}</span>
                    ${isLatest ? '<span class="px-2 py-0.5 text-xs bg-blue-500/20 text-blue-400 rounded-full">Latest</span>' : ''}
                    <span class="text-slate-500 text-xs">${escapeHtml(release.date)}</span>
                </div>
                <ul class="space-y-1.5 pl-2">${items}</ul>
            </div>`;
    }).join('');

    if (lastUpdated) lastUpdated.textContent = `Last updated: ${data.lastUpdated || '-'}`;

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

/** Close only when the backdrop is clicked — clicks in the content area must not close it */
function closeChangelogModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('changelogModal');
    if (modal) modal.classList.add('hidden');
    document.body.style.overflow = '';
}

/** Fill the header version badge from version.json (avoids hard-coding in HTML) */
function syncVersionBadge() {
    const badge = document.getElementById('versionBadge');
    const data = getVersionData();
    if (badge && data?.version) badge.textContent = `v${data.version}`;
}

// ============================================
// Security warning banner
// ============================================

/** Tells users their input stays only in the browser. Once closed it does not show again this session. */
function showSecurityWarning() {
    if (sessionStorage.getItem('wizardSecurityWarningClosed') === '1') return;
    const el = document.getElementById('securityWarning');
    if (el) el.classList.remove('hidden');
}

function closeSecurityWarning() {
    const el = document.getElementById('securityWarning');
    if (el) el.classList.add('hidden');
    try {
        sessionStorage.setItem('wizardSecurityWarningClosed', '1');
    } catch (err) {
        /* Ignore session storage failures — closing the banner is enough */
    }
}

// ============================================
// Download
// ============================================

/** Save a Blob as a file (shared download entry point) */
function triggerDownload(blob, fileName) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}

// ============================================
// DOM selectors
// ============================================

function $(selector) {
    return document.querySelector(selector);
}

function $$(selector) {
    return document.querySelectorAll(selector);
}

// ============================================
// Base implementation of step navigation and state saving
// ============================================
// Globals wizard JS must provide: state (currentStep, customSecrets), STORAGE_KEY,
// updateProgress, initializeStep, saveCurrentStepData
// firebase has a different flow and overrides some with its own implementation (check-consistency.py INTENTIONAL_OVERRIDES)

function saveState() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
        console.warn('[wizard state] localStorage save failed:', e);
    }
}

function clearState() {
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
        console.warn('[wizard state] localStorage clear failed:', e);
    }
}

/** Show only that step's screen > per-step initialization */
function showStep(stepNumber) {
    $$('.step-content').forEach(step => {
        step.classList.add('hidden');
        step.classList.remove('fade-in');
    });

    const currentStepElement = $(`.step-content[data-step="${stepNumber}"]`);
    if (currentStepElement) {
        currentStepElement.classList.remove('hidden');
        currentStepElement.classList.add('fade-in');
    }

    initializeStep(stepNumber);
}

/** Save the current step's input > show the previous step > save progress and state */
function prevStep() {
    if (state.currentStep > 1) {
        saveCurrentStepData();
        state.currentStep--;
        showStep(state.currentStep);
        updateProgress();
        saveState();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// ============================================
// Custom Secrets (automatic handling per file type)
// ============================================

/** File > Secret value (text as is, binary as Base64) */
async function processFile(file) {
    if (getFileType(file) === 'text') {
        return { value: await fileToText(file), type: 'text', hint: translate('common.textHint') };
    }
    return { value: await fileToBase64(file), type: 'binary', hint: translate('common.binaryHint') };
}

function addCustomSecret() {
    state.customSecrets.push({
        key: '',
        value: '',
        fileName: '',
        type: null,
        hint: ''
    });
    renderCustomSecrets();
    saveState();
}

function removeCustomSecret(index) {
    state.customSecrets.splice(index, 1);
    renderCustomSecrets();
    saveState();
}

/** Normalize to the Secret naming rule (uppercase, digits, _) and save */
function updateCustomSecretKey(index, key) {
    if (state.customSecrets[index]) {
        state.customSecrets[index].key = key.toUpperCase().replace(/[^A-Z0-9_]/g, '_');
        saveState();
    }
}

/** File upload > value conversion > key generated from the file name if empty */
async function handleCustomFileUpload(index, file) {
    if (!file) return;

    try {
        const result = await processFile(file);
        const suggestedKey = generateKeyName(file.name, result.type);

        state.customSecrets[index] = {
            key: state.customSecrets[index]?.key || suggestedKey,
            value: result.value,
            fileName: file.name,
            type: result.type,
            hint: result.hint
        };

        renderCustomSecrets();
        saveState();
        showToast(translate('common.uploadDone', {
            fileName: file.name,
            fileType: result.type === 'text' ? translate('common.fileTypeText') : 'Base64'
        }));
    } catch (error) {
        showToast(translate('common.uploadFailed', { message: error.message }));
    }
}

function copyCustomSecretValue(index) {
    const secret = state.customSecrets[index];
    if (secret && secret.value) {
        navigator.clipboard.writeText(secret.value).then(() => {
            showToast(translate('common.secretValueCopied', { key: secret.key }));
        }).catch(() => {
            showToast(translate('common.clipboardFailed'));
        });
    }
}

function renderCustomSecrets() {
    const container = document.getElementById('customSecretsList');
    if (!container) return;

    if (state.customSecrets.length === 0) {
        container.innerHTML = '';
        return;
    }

    container.innerHTML = state.customSecrets.map((secret, index) => {
        const hasFile = secret.value && secret.fileName;
        const typeIcon = secret.type === 'text' ? '📄' : '🔐';
        const typeBadge = secret.type === 'text' ? 'Raw Text' : 'Base64';
        const typeClass = secret.type === 'text' ? 'text' : 'binary';

        return `
            <div class="custom-secret-item">
                <div class="flex items-center justify-between gap-3 mb-3">
                    ${hasFile ? `<span class="type-badge ${typeClass}">${typeIcon} ${typeBadge}</span>` : '<span></span>'}
                    <button class="remove-secret-btn" onclick="removeCustomSecret(${index})">${translate('common.remove')}</button>
                </div>

                <div class="mb-3">
                    <label class="block text-xs text-slate-400 mb-1">${translate('common.secretName')}</label>
                    <input type="text"
                           class="secret-key-input"
                           placeholder="SECRET_NAME"
                           value="${secret.key || ''}"
                           onchange="updateCustomSecretKey(${index}, this.value)"
                           oninput="this.value = this.value.toUpperCase().replace(/[^A-Z0-9_]/g, '_')">
                </div>

                <div class="custom-file-upload ${hasFile ? 'has-file' : ''}"
                     onclick="document.getElementById('customFile${index}').click()">
                    <input type="file" id="customFile${index}" onchange="handleCustomFileUpload(${index}, this.files[0])">
                    ${hasFile
                        ? `<div class="text-green-400 text-sm">✅ ${escapeHtml(secret.fileName)}</div>`
                        : `<div class="text-slate-400 text-sm">${translate('common.chooseFile')}</div>`
                    }
                </div>

                ${hasFile ? `
                    <div class="usage-hint">💡 ${escapeHtml(secret.hint)}</div>
                    <div class="flex justify-end mt-2">
                        <button class="copy-btn-small" onclick="copyCustomSecretValue(${index})">${translate('common.copyValue')}</button>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

/** Only filled custom Secrets, in export format */
function getCustomSecretsForExport() {
    return state.customSecrets
        .filter(cs => cs.key && cs.value)
        .map(cs => ({
            key: cs.key,
            value: cs.value,
            desc: translate('common.customSecretDescription', { fileName: cs.fileName }),
            type: cs.type,
            hint: cs.hint
        }));
}
