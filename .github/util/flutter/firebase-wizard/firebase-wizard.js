/**
 * Firebase App Distribution Wizard
 * 정적 HTML/JS 마법사 - GitHub API 호출 안 함
 */

// ============================================
// OS Detection
// ============================================
let detectedOS = 'mac';

// ============================================
// State
// ============================================
const state = {
    currentStep: 1,
    maxReachedStep: 1,
    totalSteps: 5,
    detectedOS: 'mac',
    // Step 3
    firebaseAppId: '',
    firebaseTesterGroup: '',
    projectPath: '.',
    // Step 4
    serviceAccountBase64: '',
    serviceAccountFileName: '',
    googleServicesJson: '',
    googleServicesFileName: '',
    // Step 5
    repoOwner: '',
    repoName: '',
    // Custom Secrets
    customSecrets: []
};

const STORAGE_KEY = 'firebase_wizard_state';

function loadState() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const s = JSON.parse(saved);
            const total = state.totalSteps;
            Object.assign(state, s);
            state.totalSteps = total;
            state.detectedOS = detectOS();
            if (state.currentStep > state.totalSteps) state.currentStep = state.totalSteps;
            if (!state.maxReachedStep || state.maxReachedStep < state.currentStep) state.maxReachedStep = state.currentStep;
            if (state.maxReachedStep > state.totalSteps) state.maxReachedStep = state.totalSteps;
            return true;
        }
    } catch (e) { console.warn('localStorage load failed:', e); }
    return false;
}

// ============================================
// Helpers
// ============================================

function copySecret(name) {
    const map = {
        'FIREBASE_SERVICE_ACCOUNT_JSON_BASE64': state.serviceAccountBase64,
        'GOOGLE_SERVICES_JSON': state.googleServicesJson
    };
    const value = map[name] || '';
    if (!value) { showToast(translate('toast.secretEmpty', { name })); return; }
    copyToClipboard(value);
}

// ============================================
// Navigation
// ============================================
function updateProgress() {
    $$('.step-indicator').forEach((indicator, index) => {
        const stepNum = index + 1;
        const circle = indicator.querySelector('.step-circle');
        const label = indicator.querySelector('span');

        if (stepNum < state.currentStep) {
            // 완료된 스텝
            circle.className = 'step-circle w-8 h-8 rounded-full bg-green-500 text-slate-900 flex items-center justify-center font-bold text-xs z-10 shadow-lg';
            circle.innerHTML = '✓';
            if (label) label.className = 'text-[9px] mt-1 text-green-400 text-center hidden md:block';
        } else if (stepNum === state.currentStep) {
            // 현재 스텝
            circle.className = 'step-circle w-8 h-8 rounded-full bg-firebase-primary text-slate-900 flex items-center justify-center font-bold text-xs z-10 shadow-lg';
            circle.innerHTML = stepNum;
            if (label) label.className = 'text-[9px] mt-1 text-firebase-accent text-center hidden md:block';
        } else {
            // 아직 안 한 스텝
            circle.className = 'step-circle w-8 h-8 rounded-full bg-slate-700 text-slate-400 flex items-center justify-center font-bold text-xs z-10';
            circle.innerHTML = stepNum;
            if (label) label.className = 'text-[9px] mt-1 text-slate-500 text-center hidden md:block';
        }

        // 어느 단계로든 자유롭게 이동 가능 (3종 공통 동작)
        indicator.style.cursor = 'pointer';
        indicator.onclick = () => goToStep(stepNum);
    });
}

function showStep(step) {
    state.currentStep = step;
    if (step > state.maxReachedStep) state.maxReachedStep = step;
    $$('.step-content').forEach(el => {
        el.classList.toggle('hidden', parseInt(el.dataset.step) !== step);
        el.classList.add('fade-in');
    });
    updateProgress();
    saveState();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function nextStep() {
    if (state.currentStep < state.totalSteps) showStep(state.currentStep + 1);
}

function prevStep() {
    if (state.currentStep > 1) showStep(state.currentStep - 1);
}

// 단계 이동에 순서 제약을 두지 않는다.
// 이미 발급받은 값이 있거나 특정 단계만 다시 확인하려는 경우가 많아,
// 앞 단계 완료를 강제하면 오히려 진행을 막는다. (testflight/playstore 마법사와 동일 동작)
function goToStep(step) {
    if (step === state.currentStep) return;
    if (step >= 1 && step <= state.totalSteps) showStep(step);
}

function resetWizard() {
    if (!confirm(translate('confirm.reset'))) return;
    clearState();
    Object.assign(state, {
        currentStep: 1, maxReachedStep: 1, totalSteps: 5, detectedOS: detectOS(),
        firebaseAppId: '', firebaseTesterGroup: '', projectPath: '.',
        serviceAccountBase64: '', serviceAccountFileName: '',
        googleServicesJson: '', googleServicesFileName: '',
        repoOwner: '', repoName: '', customSecrets: []
    });
    showStep(1);
    showToast(translate('toast.reset'));
}

function updateSetupCommands() {
    const path = state.projectPath || '.';
    const appId = shellEscape(state.firebaseAppId);
    const tester = shellEscape(state.firebaseTesterGroup);

    const bashCmd = `python3 .github/util/flutter/firebase-wizard/firebase-wizard.py setup --project-path ${path} --app-id "${appId}" --tester-group "${tester}"`;
    const psPath = (path === '.') ? '.' : path.replace(/\//g, '\\');
    const psCmd = `python .github\\util\\flutter\\firebase-wizard\\firebase-wizard.py setup --project-path ${psPath} --app-id "${appId}" --tester-group "${tester}"`;

    const bashEl = document.getElementById('cmdBashCode');
    const psEl = document.getElementById('cmdPsCode');
    if (bashEl) bashEl.textContent = bashCmd;
    if (psEl) psEl.textContent = psCmd;
}

function selectOsTab(which) {
    const bash = document.getElementById('osCmdBash');
    const ps = document.getElementById('osCmdPs');
    const tabBash = document.getElementById('osTabBash');
    const tabPs = document.getElementById('osTabPs');
    if (which === 'bash') {
        bash.classList.remove('hidden');
        ps.classList.add('hidden');
        tabBash.classList.add('bg-firebase-primary', 'text-slate-900');
        tabPs.classList.remove('bg-firebase-primary', 'text-slate-900');
    } else {
        ps.classList.remove('hidden');
        bash.classList.add('hidden');
        tabPs.classList.add('bg-firebase-primary', 'text-slate-900');
        tabBash.classList.remove('bg-firebase-primary', 'text-slate-900');
    }
}

function onFirebaseAppIdChange(v) { state.firebaseAppId = v.trim(); updateSetupCommands(); saveState(); }
function onFirebaseTesterGroupChange(v) { state.firebaseTesterGroup = v.trim(); updateSetupCommands(); saveState(); }
function onProjectPathChange(v) { state.projectPath = v.trim() || '.'; updateSetupCommands(); saveState(); }

function onStep3Next() {
    if (!state.firebaseAppId) { showToast(translate('toast.appIdRequired')); return; }
    if (!state.firebaseTesterGroup) { showToast(translate('toast.testerGroupRequired')); return; }
    nextStep();
}

// Step 진입 시 초기화 — showStep 함수 wrap
const _origShowStep = showStep;
showStep = function (step) {
    _origShowStep(step);
    if (step === 3) {
        const inputs = {
            firebaseAppIdInput: state.firebaseAppId,
            firebaseTesterGroupInput: state.firebaseTesterGroup,
            projectPathInput: state.projectPath || '.'
        };
        Object.keys(inputs).forEach(id => {
            const el = document.getElementById(id);
            if (el) el.value = inputs[id];
        });
        updateSetupCommands();
        selectOsTab(state.detectedOS === 'windows' ? 'ps' : 'bash');
    }
};

// ============================================
// Step 4: File uploads
// ============================================
async function handleServiceAccountUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!file.name.endsWith('.json')) {
        showToast(translate('toast.jsonOnly'));
        return;
    }
    try {
        const text = await fileToText(file);
        const parsed = JSON.parse(text);
        if (!parsed.client_email || !parsed.private_key) {
            showToast(translate('toast.notServiceAccount'));
        }
        const b64 = btoa(unescape(encodeURIComponent(text)));
        state.serviceAccountBase64 = b64;
        state.serviceAccountFileName = file.name;

        document.getElementById('saUploadText').textContent = `✅ ${file.name} (${(file.size/1024).toFixed(1)}KB)`;
        const info = document.getElementById('saInfo');
        info.style.display = 'block';
        info.textContent = `client_email: ${parsed.client_email || translate('upload.missing')}`;
        const preview = document.getElementById('saPreview');
        preview.classList.remove('hidden');
        document.getElementById('saPreviewText').textContent = b64.substring(0, 100) + '...';
        saveState();
        showToast(translate('toast.serviceAccountUploaded'));
    } catch (e) {
        showToast(translate('toast.jsonParseFailed', { message: e.message }));
    }
}

async function handleGoogleServicesUpload(event) {
    const file = event.target.files[0];
    if (!file) return;
    if (!file.name.endsWith('.json')) {
        showToast(translate('toast.jsonOnly'));
        return;
    }
    try {
        const text = await fileToText(file);
        JSON.parse(text); // 형식 검증
        state.googleServicesJson = text;
        state.googleServicesFileName = file.name;
        document.getElementById('gsUploadText').textContent = `✅ ${file.name} (${(file.size/1024).toFixed(1)}KB)`;
        const info = document.getElementById('gsInfo');
        info.style.display = 'block';
        info.textContent = `${file.size} bytes`;
        saveState();
        showToast(translate('toast.googleServicesUploaded'));
    } catch (e) {
        showToast(translate('toast.jsonParseFailed', { message: e.message }));
    }
}

function onStep4Next() {
    if (!state.serviceAccountBase64) {
        showToast(translate('toast.serviceAccountRequired'));
        return;
    }
    nextStep();
}

// Step 4 진입 시 setup — showStep 함수 wrap (Step 3 wrap 위에 다시 wrap)
const _showStepStep4 = showStep;
showStep = function (step) {
    _showStepStep4(step);
    if (step === 4) {
        if (state.serviceAccountFileName) {
            const t = document.getElementById('saUploadText');
            if (t) t.textContent = translate('upload.restored', { fileName: state.serviceAccountFileName });
            const preview = document.getElementById('saPreview');
            if (preview && state.serviceAccountBase64) {
                preview.classList.remove('hidden');
                document.getElementById('saPreviewText').textContent = state.serviceAccountBase64.substring(0, 100) + '...';
            }
        }
        if (state.googleServicesFileName) {
            const t = document.getElementById('gsUploadText');
            if (t) t.textContent = translate('upload.restored', { fileName: state.googleServicesFileName });
        }
        renderUploadDropHints();
        setupDragAndDrop();
    }
};

/** 아직 안 올린 업로드 칸의 안내 문구 (올린 칸은 파일명 표시 유지) */
function renderUploadDropHints() {
    if (!state.serviceAccountFileName) setElementText('saUploadText', translate('upload.dropHint'));
    if (!state.googleServicesFileName) setElementText('gsUploadText', translate('upload.dropHint'));
}

// ============================================
// Custom Secrets
// ============================================
const TEXT_EXTS = ['.txt', '.env', '.json', '.yaml', '.yml', '.md', '.properties', '.xml', '.ini', '.conf', '.cfg'];

function detectSecretType(filename) {
    const lower = (filename || '').toLowerCase();
    return TEXT_EXTS.some(ext => lower.endsWith(ext)) ? 'text' : 'binary';
}

function suggestSecretKey(filename, type) {
    const base = (filename || '').replace(/\.[^.]+$/, '').toUpperCase().replace(/[^A-Z0-9]/g, '_');
    return type === 'binary' ? `${base}_BASE64` : base;
}

function addCustomSecret() {
    state.customSecrets.push({ key: '', value: '', fileName: '', type: 'text' });
    saveState();
    renderCustomSecrets();
}

function updateCustomSecretKey(index, value) {
    state.customSecrets[index].key = value;
    saveState();
}

function updateCustomSecretValue(index, value) {
    state.customSecrets[index].value = value;
    state.customSecrets[index].type = 'text';
    state.customSecrets[index].fileName = '';
    saveState();
}

async function handleCustomSecretFile(index, event) {
    const file = event.target.files[0];
    if (!file) return;
    const type = detectSecretType(file.name);
    let value;
    if (type === 'text') {
        value = await fileToText(file);
    } else {
        value = await fileToBase64(file);
    }
    state.customSecrets[index].value = value;
    state.customSecrets[index].fileName = file.name;
    state.customSecrets[index].type = type;
    if (!state.customSecrets[index].key) {
        state.customSecrets[index].key = suggestSecretKey(file.name, type);
    }
    saveState();
    renderCustomSecrets();
    showToast(`✅ ${file.name} (${type})`);
}

function renderCustomSecrets() {
    const container = document.getElementById('customSecretsContent');
    if (!container) return;
    if (state.customSecrets.length === 0) {
        container.innerHTML = `<p class="text-xs text-slate-500 italic">${translate('custom.empty')}</p>`;
        return;
    }
    container.innerHTML = state.customSecrets.map((s, i) => {
        const safeKey = escapeHtml(s.key || '');
        const safeType = escapeHtml(s.type || 'text');
        const safeFileName = escapeHtml(s.fileName || '');
        const safeValuePreview = s.fileName ? '' : escapeHtml((s.value || '').substring(0, 100));
        const typeBadgeClass = s.type === 'binary' ? 'bg-purple-600/30 text-purple-300' : 'bg-blue-600/30 text-blue-300';
        return `
        <div class="bg-slate-900 border border-slate-700 rounded-lg p-3 mb-3">
            <div class="flex items-center gap-2 mb-2">
                <input type="text" placeholder="SECRET_KEY_NAME" value="${safeKey}"
                    class="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-1.5 text-xs font-mono"
                    oninput="updateCustomSecretKey(${i}, this.value)">
                <span class="text-xs px-2 py-1 rounded ${typeBadgeClass}">${safeType}</span>
                <button class="text-red-400 hover:text-red-300 text-sm" onclick="removeCustomSecret(${i})">✕</button>
            </div>
            <div class="flex gap-2">
                <input type="file" id="csFile${i}" class="hidden" onchange="handleCustomSecretFile(${i}, event)">
                <button class="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-xs" onclick="document.getElementById('csFile${i}').click()">
                    ${safeFileName ? `📎 ${safeFileName}` : translate('custom.chooseFile')}
                </button>
                <span class="text-xs text-slate-500 self-center">${translate('custom.or')}</span>
                <input type="text" placeholder="${escapeHtml(translate('custom.valuePlaceholder'))}" value="${safeValuePreview}"
                    class="flex-1 bg-slate-950 border border-slate-700 rounded px-3 py-1.5 text-xs font-mono"
                    oninput="updateCustomSecretValue(${i}, this.value)">
            </div>
        </div>
        `;
    }).join('');
}

// Step 4 진입 시 custom secrets도 렌더 (Task 10 wrap)
const _showStepCustom = showStep;
showStep = function (step) {
    _showStepCustom(step);
    if (step === 4) {
        renderCustomSecrets();
    }
};

function buildSecretsArray() {
    const list = [];
    if (state.serviceAccountBase64) {
        list.push({ key: 'FIREBASE_SERVICE_ACCOUNT_JSON_BASE64', value: state.serviceAccountBase64, source: 'Service Account JSON', type: 'binary' });
    }
    if (state.googleServicesJson) {
        list.push({ key: 'GOOGLE_SERVICES_JSON', value: state.googleServicesJson, source: 'google-services.json', type: 'text' });
    }
    state.customSecrets.forEach(s => {
        if (s.key && s.value) {
            list.push({ key: s.key, value: s.value, source: s.fileName || translate('secrets.manualEntry'), type: s.type });
        }
    });
    return list;
}

function renderSecretsTable() {
    const tbody = document.getElementById('secretsTableBody');
    if (!tbody) return;
    const list = buildSecretsArray();
    if (list.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="py-3 text-center text-slate-500 italic">${translate('secrets.empty')}</td></tr>`;
        return;
    }
    tbody.innerHTML = list.map(s => {
        const safeKey = escapeHtml(s.key);
        const safeSource = escapeHtml(s.source);
        const safeJsKey = escapeJsString(s.key);
        return `
        <tr class="border-b border-slate-700/50 hover:bg-slate-700/30">
            <td class="py-2 px-2 font-mono text-yellow-400">${safeKey}</td>
            <td class="py-2 px-2 text-slate-400">${safeSource}</td>
            <td class="py-2 px-2 text-slate-400">${(s.value.length / 1024).toFixed(1)} KB</td>
            <td class="py-2 px-2 text-right">
                <button class="px-3 py-1 bg-firebase-primary text-slate-900 rounded text-xs hover:opacity-90" onclick="copySecretValue('${safeJsKey}')">${translate('secrets.copy')}</button>
            </td>
        </tr>
        `;
    }).join('');
}

function copySecretValue(key) {
    const list = buildSecretsArray();
    const item = list.find(x => x.key === key);
    if (!item) { showToast(translate('toast.itemNotFound')); return; }
    copyToClipboard(item.value);
    showToast(translate('toast.secretCopied', { key }));
}

function onRepoOwnerChange(v) {
    state.repoOwner = v.trim();
    saveState();
    updateSecretsPageLink();
}

function onRepoNameChange(v) {
    state.repoName = v.trim();
    saveState();
    updateSecretsPageLink();
}

function updateSecretsPageLink() {
    const link = document.getElementById('secretsPageLink');
    if (!link) return;
    if (state.repoOwner && state.repoName) {
        link.href = `https://github.com/${state.repoOwner}/${state.repoName}/settings/secrets/actions`;
    } else {
        link.href = 'https://github.com';
    }
}

function downloadAsJson() {
    const list = buildSecretsArray();
    if (list.length === 0) { showToast(translate('toast.noSecrets')); return; }
    const out = {};
    list.forEach(s => { out[s.key] = s.value; });
    const blob = new Blob([JSON.stringify(out, null, 2)], { type: 'application/json' });
    triggerDownload(blob, `firebase-secrets-${(state.firebaseAppId || 'app').slice(0,12)}-${getDateStamp()}.json`);
    showToast(translate('toast.jsonDownloaded'));
}

function downloadAsTxt() {
    const list = buildSecretsArray();
    if (list.length === 0) { showToast(translate('toast.noSecrets')); return; }
    const lines = list.map(s => `=== ${s.key} ===\n${s.value}\n`);
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    triggerDownload(blob, `firebase-secrets-${(state.firebaseAppId || 'app').slice(0,12)}-${getDateStamp()}.txt`);
    showToast(translate('toast.txtDownloaded'));
}

async function downloadAsZip() {
    const list = buildSecretsArray();
    if (list.length === 0) { showToast(translate('toast.noSecrets')); return; }
    if (typeof JSZip === 'undefined') { showToast(translate('toast.jszipFailed')); return; }

    const zip = new JSZip();
    const folder = zip.folder('github-secrets');
    list.forEach(s => folder.file(`${s.key}.txt`, s.value));

    // setup 스크립트 — GitHub raw에서 fetch 시도, 실패 시 README 안내만
    const wizardBaseUrl = 'https://raw.githubusercontent.com/Cassiiopeia/projectops/main/.github/util/flutter/firebase-wizard';
    try {
        const pyResp = await fetch(`${wizardBaseUrl}/firebase-wizard.py`).then(r => r.ok ? r.text() : null).catch(() => null);
        if (pyResp) zip.file('firebase-wizard.py', pyResp);
    } catch (e) {
        console.warn('[firebase wizard] setup script fetch failed:', e);
    }

    const notEntered = translate('zip.notEntered');
    const readme = `${translate('zip.readmeTitle')}

${translate('zip.generatedAt', { value: new Date().toISOString() })}
${translate('zip.appId', { value: state.firebaseAppId || notEntered })}
${translate('zip.testerGroup', { value: state.firebaseTesterGroup || notEntered })}

${translate('zip.folderTitle')}

${translate('zip.folderSecrets')}
${translate('zip.folderScript')}

${translate('zip.registerTitle')}

${translate('zip.register1')}
${translate('zip.register2')}
${translate('zip.register3')}

${translate('zip.runTitle')}

### macOS / Linux
\`\`\`bash
python3 firebase-wizard.py setup \\
  --project-path /path/to/project \\
  --app-id "${state.firebaseAppId}" \\
  --tester-group "${state.firebaseTesterGroup}"
\`\`\`

### Windows (PowerShell)
\`\`\`powershell
python firebase-wizard.py setup \`
  --project-path C:\\path\\to\\project \`
  --app-id "${state.firebaseAppId}" \`
  --tester-group "${state.firebaseTesterGroup}"
\`\`\`

${translate('zip.optionsTitle')}

${translate('zip.optionDryRun')}
${translate('zip.optionNonInteractive')}
${translate('zip.optionNoBackup')}
`;
    zip.file('README.md', readme);

    const blob = await zip.generateAsync({ type: 'blob' });
    triggerDownload(blob, `firebase-setup-${(state.firebaseAppId || 'app').slice(0,12)}-${getDateStamp()}.zip`);
    showToast(translate('toast.zipDownloaded'));
}

// Step 5 진입 시 렌더 (Task 11 wrap)
const _showStepStep5 = showStep;
showStep = function (step) {
    _showStepStep5(step);
    if (step === 5) {
        const r1 = document.getElementById('repoOwnerInput'); if (r1) r1.value = state.repoOwner || '';
        const r2 = document.getElementById('repoNameInput'); if (r2) r2.value = state.repoName || '';
        renderSecretsTable();
        updateSecretsPageLink();
    }
};

// ============================================
// 언어 전환 (#769) — JS 가 그리는 영역만 다시 그린다 (정적 문구는 엔진이 처리)
// ============================================
document.addEventListener('wizardlanguagechange', () => {
    renderUploadDropHints();
    if (state.serviceAccountFileName) setElementText('saUploadText', `✅ ${state.serviceAccountFileName}`);
    if (state.googleServicesFileName) setElementText('gsUploadText', `✅ ${state.googleServicesFileName}`);
    renderCustomSecrets();
    renderSecretsTable();
});

// ============================================
// Init
// ============================================
window.addEventListener('DOMContentLoaded', () => {
    state.detectedOS = detectOS();
    detectedOS = state.detectedOS;
    loadState();
    showStep(state.currentStep);
    // 3종 공통 초기화 (../_shared/wizard-common.js)
    syncVersionBadge();
    showSecurityWarning();
});
