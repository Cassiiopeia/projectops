/**
 * Flutter iOS TestFlight all-in-one wizard
 * Includes file upload, Base64 conversion and localStorage progress saving
 */

// ============================================
// State Management
// ============================================

const state = {
    currentStep: 1,
    totalSteps: 9,
    projectPath: '',
    repoRoot: '',
    bundleId: '',
    teamId: '',
    profileName: '',
    appName: '',
    encryptionType: 'none',
    // File data (Base64)
    p12Base64: '',
    p12Password: '',
    provisionBase64: '',
    p8Base64: '',
    apiKeyId: '',
    issuerId: '',
    // Custom Secrets (added by the user)
    customSecrets: []
    // [{
    //   key: 'SECRET_NAME',
    //   value: '...',
    //   fileName: 'file.json',
    //   type: 'text' | 'binary',
    //   hint: 'usage hint'
    // }]
};

// ============================================
// LocalStorage Functions
// ============================================

const STORAGE_KEY = 'flutter_ios_wizard_state';
const STORAGE_WARNING_KEY = 'flutter_ios_wizard_security_warning_dismissed';

function loadState() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const savedState = JSON.parse(saved);
            // Keep the code's totalSteps (ignore cached values after a version upgrade)
            const currentTotalSteps = state.totalSteps;
            Object.assign(state, savedState);
            state.totalSteps = currentTotalSteps; // always set from the current code

            // Correct currentStep if it exceeds totalSteps
            if (state.currentStep > state.totalSteps) {
                state.currentStep = state.totalSteps;
            }

            restoreUIFromState();
            return true;
        }
    } catch (e) {
        console.warn('[testflight state] localStorage load failed:', e);
    }
    return false;
}

function restoreUIFromState() {
    // Restore input fields
    const inputs = {
        'projectPath': state.projectPath,
        'repoRoot': state.repoRoot,
        'bundleId': state.bundleId,
        'bundleId-confirm': state.bundleId,
        'teamId': state.teamId,
        'profileName': state.profileName,
        'profileName-confirm': state.profileName,
        'appName': state.appName,
        'p12-password': state.p12Password,
        'api-key-id': state.apiKeyId,
        'issuer-id': state.issuerId
    };

    Object.entries(inputs).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value) el.value = value;
    });

    // Update Step 5 display elements
    if (state.bundleId) {
        const displayBundleId = document.getElementById('display-bundle-id');
        if (displayBundleId) displayBundleId.textContent = state.bundleId;
    }
    if (state.profileName) {
        const displayProfileName = document.getElementById('display-profile-name');
        if (displayProfileName) displayProfileName.textContent = state.profileName;
    }

    // Restore the encryption setting
    if (state.encryptionType) {
        const radio = document.querySelector(`input[name="encryptionType"][value="${state.encryptionType}"]`);
        if (radio) radio.checked = true;
    }

    // Restore file upload state
    if (state.p12Base64) {
        document.getElementById('p12-upload').classList.add('has-file');
        const info = document.getElementById('p12-info');
        if (info) {
            info.style.display = 'block';
            info.textContent = translate('upload.certificateLoaded');
        }
    }

    if (state.provisionBase64) {
        document.getElementById('provision-upload').classList.add('has-file');
        const info = document.getElementById('provision-info');
        if (info) {
            info.style.display = 'block';
            info.textContent = translate('upload.profileLoaded');
        }
    }

    if (state.p8Base64) {
        document.getElementById('p8-upload').classList.add('has-file');
        const info = document.getElementById('p8-info');
        if (info) {
            info.style.display = 'block';
            info.textContent = translate('upload.apiKeyLoaded');
        }
    }

    // Restore custom Secrets
    if (state.customSecrets && state.customSecrets.length > 0) {
        renderCustomSecrets();
    }
}

// ============================================
// Security Warning
// ============================================

/**
 * Live Team ID validation.
 * A 9-character input missing its last character after copy-paste is common; stored in a Secret as is,
 * it fails only at build signing with a team mismatch that is hard to trace. Catch it at input time.
 */
function validateTeamId(input) {
    const warning = document.getElementById('teamId-warning');
    if (!warning) return;

    const value = (input.value || '').trim().toUpperCase();
    input.value = value;

    // Do not warn while empty (red text before any input is noise)
    if (value.length === 0) {
        warning.className = 'text-xs mt-1 hidden';
        return;
    }

    if (value.length < 10) {
        warning.textContent = translate('teamId.tooShort', { length: value.length });
        warning.className = 'text-xs mt-1 text-red-400';
    } else if (!/^[A-Z0-9]{10}$/.test(value)) {
        warning.textContent = translate('teamId.invalid');
        warning.className = 'text-xs mt-1 text-red-400';
    } else {
        warning.textContent = translate('teamId.valid');
        warning.className = 'text-xs mt-1 text-green-400';
    }
}

// ============================================
// File Upload & Base64 Conversion
// ============================================

// .p12 file upload
async function handleP12Upload(event) {
    const file = event.target.files[0];
    if (file) await handleP12File(file);
}

async function handleP12File(file) {
    if (!file.name.endsWith('.p12')) {
        showToast(translate('upload.p12Only'));
        return;
    }

    try {
        state.p12Base64 = await fileToBase64(file);
        document.getElementById('p12-upload').classList.add('has-file');
        const info = document.getElementById('p12-info');
        info.style.display = 'block';
        info.textContent = `✅ ${file.name} (${(file.size/1024).toFixed(1)}KB)`;
        saveState();
        showToast(translate('upload.certificateDone'));
    } catch (error) {
        showToast(translate('upload.readFailed', { message: error.message }));
    }
}

// .mobileprovision file upload
async function handleProvisionUpload(event) {
    const file = event.target.files[0];
    if (file) await handleProvisionFile(file);
}

async function handleProvisionFile(file) {
    if (!file.name.endsWith('.mobileprovision')) {
        showToast(translate('upload.provisionOnly'));
        return;
    }

    try {
        state.provisionBase64 = await fileToBase64(file);
        document.getElementById('provision-upload').classList.add('has-file');
        const info = document.getElementById('provision-info');
        info.style.display = 'block';
        info.textContent = `✅ ${file.name} (${(file.size/1024).toFixed(1)}KB)`;
        saveState();
        showToast(translate('upload.profileDone'));
    } catch (error) {
        showToast(translate('upload.readFailed', { message: error.message }));
    }
}

// .p8 file upload
async function handleP8Upload(event) {
    const file = event.target.files[0];
    if (file) await handleP8File(file);
}

async function handleP8File(file) {
    if (!file.name.endsWith('.p8')) {
        showToast(translate('upload.p8Only'));
        return;
    }

    try {
        state.p8Base64 = await fileToBase64(file);
        document.getElementById('p8-upload').classList.add('has-file');
        const info = document.getElementById('p8-info');
        info.style.display = 'block';
        info.textContent = `✅ ${file.name}`;

        // Extract the Key ID from the file name automatically
        const match = file.name.match(/AuthKey_(\w+)\.p8/);
        if (match) {
            state.apiKeyId = match[1];
            document.getElementById('api-key-id').value = match[1];
        }

        saveState();
        showToast(translate('upload.apiKeyDone'));
    } catch (error) {
        showToast(translate('upload.readFailed', { message: error.message }));
    }
}

// ============================================
// Folder Selection (File System Access API)
// ============================================

async function selectProjectFolder() {
    if ('showDirectoryPicker' in window) {
        try {
            const dirHandle = await window.showDirectoryPicker();
            const folderName = dirHandle.name;

            // Browsers never give absolute paths for security (only the folder name is available).
            // Writing a notice into the input would overwrite the real path and send the fallback (/path/to/project),
            // so the input is left alone and only the hint area shows the folder name.
            const hint = document.getElementById('projectPath-hint');
            if (hint) {
                hint.innerHTML = translate('folder.selectedHint', { folderName });
                hint.classList.remove('hidden');
            }

            const input = document.getElementById('projectPath');
            if (input) input.focus();

            showToast(translate('folder.selectedToast', { folderName }));
        } catch (err) {
            if (err.name !== 'AbortError') {
                console.error('[testflight folder] picker failed:', err);
                showToast(translate('folder.pickFailed'));
            }
        }
    } else {
        showToast(translate('folder.unsupported'));
        const input = document.getElementById('projectPath');
        if (input) input.focus();
    }
}

// ============================================
// Clipboard Functions
// ============================================

// ============================================
// Navigation Functions
// ============================================

function updateProgress() {
    $$('.step-indicator').forEach((indicator, index) => {
        const stepNum = index + 1;
        const circle = indicator.querySelector('.step-circle');
        const label = indicator.querySelector('span');

        if (stepNum < state.currentStep) {
            // Completed step
            circle.className = 'step-circle w-10 h-10 rounded-full bg-green-500 text-white flex items-center justify-center font-bold text-sm z-10 shadow-lg';
            circle.innerHTML = '✓';
            if (label) label.className = 'text-xs mt-2 text-green-400 text-center hidden md:block';
        } else if (stepNum === state.currentStep) {
            // Current step - blue-purple gradient
            circle.className = 'step-circle w-10 h-10 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 text-white flex items-center justify-center font-bold text-sm z-10 shadow-lg shadow-blue-500/30';
            circle.innerHTML = stepNum;
            if (label) label.className = 'text-xs mt-2 text-blue-400 text-center hidden md:block';
        } else {
            // Step not done yet
            circle.className = 'step-circle w-10 h-10 rounded-full bg-slate-700 text-slate-400 flex items-center justify-center font-bold text-sm z-10';
            circle.innerHTML = stepNum;
            if (label) label.className = 'text-xs mt-2 text-slate-500 text-center hidden md:block';
        }

        // Click to jump to that step
        indicator.style.cursor = 'pointer';
        indicator.onclick = () => goToStep(stepNum);
    });
}

function initializeStep(stepNumber) {
    switch (stepNumber) {
        case 2:
            // Step 2: Distribution certificate
            restoreInputValues();
            break;
        case 3:
            // Step 3: App ID (Bundle ID) - bundleId input
            restoreInputValues();
            break;
        case 4:
            // Step 4: Provisioning Profile - profileName input
            restoreInputValues();
            break;
        case 5:
            // Step 5: register the app in App Store Connect (new!)
            syncStep5ASCValues();
            break;
        case 6:
            // Step 6: check app info - show values entered in earlier steps
            syncStep6Values();
            restoreInputValues();
            break;
        case 7:
            // Step 7: API Key
            restoreInputValues();
            break;
        case 8:
            // Step 8: Fastlane setup
            generateInitCommand();
            break;
        case 9:
            // Step 9: done
            generateResults();
            break;
    }
}

function syncStep5ASCValues() {
    // Show the Bundle ID from Step 3 in the Step 5 App Store Connect guide
    const bundleIdValue = state.bundleId || getInputValue('bundleId');
    const displayBundleIdAsc = document.getElementById('display-bundle-id-asc');
    if (displayBundleIdAsc && bundleIdValue) {
        displayBundleIdAsc.textContent = bundleIdValue;
    }
}

function syncStep6Values() {
    // Show the Bundle ID from Step 3 in Step 6
    const bundleIdValue = state.bundleId || getInputValue('bundleId');
    const displayBundleId = document.getElementById('display-bundle-id');
    if (displayBundleId && bundleIdValue) {
        displayBundleId.textContent = bundleIdValue;
    }

    // Show the Profile Name from Step 4 in Step 6
    const profileNameValue = state.profileName || getInputValue('profileName');
    const displayProfileName = document.getElementById('display-profile-name');
    if (displayProfileName && profileNameValue) {
        displayProfileName.textContent = profileNameValue;
    }

    // Set the value in the confirmation input field too (readonly)
    const bundleIdConfirm = document.getElementById('bundleId-confirm');
    if (bundleIdConfirm && bundleIdValue) {
        bundleIdConfirm.value = bundleIdValue;
    }

    const profileNameConfirm = document.getElementById('profileName-confirm');
    if (profileNameConfirm && profileNameValue) {
        profileNameConfirm.value = profileNameValue;
    }
}

function restoreInputValues() {
    const inputs = {
        'bundleId': state.bundleId,
        'bundleId-confirm': state.bundleId,
        'teamId': state.teamId,
        'profileName': state.profileName,
        'profileName-confirm': state.profileName,
        'appName': state.appName,
        'p12-password': state.p12Password,
        'api-key-id': state.apiKeyId,
        'issuer-id': state.issuerId
    };

    Object.entries(inputs).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value) el.value = value;
    });
}

function nextStep() {
    saveCurrentStepData();

    if (state.currentStep < state.totalSteps) {
        state.currentStep++;
        showStep(state.currentStep);
        updateProgress();
        saveState();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function goToStep(stepNumber) {
    if (stepNumber === state.currentStep) return;
    if (stepNumber >= 1 && stepNumber <= state.totalSteps) {
        saveCurrentStepData();
        state.currentStep = stepNumber;
        showStep(state.currentStep);
        updateProgress();
        saveState();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function skipStep(stepNumber) {
    if (stepNumber < state.totalSteps) {
        saveCurrentStepData();
        state.currentStep = stepNumber + 1;
        showStep(state.currentStep);
        updateProgress();
        saveState();
        window.scrollTo({ top: 0, behavior: 'smooth' });
        showToast(translate('nav.skipped', { stepNumber }));
    }
}

function resetWizard() {
    if (confirm(translate('nav.resetConfirm'))) {
        state.currentStep = 1;
        state.projectPath = '';
        state.repoRoot = '';
        state.bundleId = '';
        state.teamId = '';
        state.profileName = '';
        state.appName = '';
        state.encryptionType = 'none';
        state.p12Base64 = '';
        state.p12Password = '';
        state.provisionBase64 = '';
        state.p8Base64 = '';
        state.apiKeyId = '';
        state.issuerId = '';

        clearState();

        // Reset the UI
        const inputs = ['projectPath', 'repoRoot', 'bundleId', 'bundleId-confirm', 'teamId', 'profileName', 'profileName-confirm', 'appName', 'p12-password', 'api-key-id', 'issuer-id'];
        inputs.forEach(id => {
            const input = document.getElementById(id);
            if (input) input.value = '';
        });

        // Reset display elements
        const displayBundleId = document.getElementById('display-bundle-id');
        if (displayBundleId) displayBundleId.textContent = translate('value.notEntered');
        const displayProfileName = document.getElementById('display-profile-name');
        if (displayProfileName) displayProfileName.textContent = translate('value.notEntered');

        // Reset file upload state
        document.querySelectorAll('.file-upload').forEach(el => {
            el.classList.remove('has-file');
        });
        document.querySelectorAll('.file-info').forEach(el => {
            el.style.display = 'none';
        });

        showStep(1);
        updateProgress();
        showToast(translate('nav.resetDone'));
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// ============================================
// Data Management Functions
// ============================================

function saveCurrentStepData() {
    switch (state.currentStep) {
        case 1:
            // Step 1: get started - project path
            state.projectPath = getInputValue('projectPath');
            // If a notice written into the input by an old version remains, do not use it as the path
            if (state.projectPath.startsWith('선택된 폴더:')) {
                state.projectPath = '';
            }
            // Relative paths lead to a failed cd in the Step 8 command, so filter them out early
            if (state.projectPath && !isAbsolutePath(state.projectPath)) {
                showToast(translate('step1.absolutePathRequired'));
                state.projectPath = '';
            }
            // Optional input filled only for monorepos — empty means the Flutter root is used as is
            state.repoRoot = getInputValue('repoRoot');
            if (state.repoRoot && !isAbsolutePath(state.repoRoot)) {
                showToast(translate('step1.repoRootAbsoluteRequired'));
                state.repoRoot = '';
            }
            break;
        case 2:
            // Step 2: Distribution certificate - .p12 file and password
            state.p12Password = getInputValue('p12-password');
            break;
        case 3:
            // Step 3: App ID (Bundle ID) - bundleId input
            state.bundleId = getInputValue('bundleId');
            break;
        case 4:
            // Step 4: Provisioning Profile - profileName input
            state.profileName = getInputValue('profileName');
            break;
        case 5:
            // Step 5: register the app in App Store Connect - nothing to save (confirmation step)
            break;
        case 6:
            // Step 6: check app info - Team ID, App Name, encryption setting
            state.teamId = getInputValue('teamId').toUpperCase();
            state.appName = getInputValue('appName');
            const encryptionRadio = document.querySelector('input[name="encryptionType"]:checked');
            state.encryptionType = encryptionRadio ? encryptionRadio.value : 'none';
            break;
        case 7:
            // Step 7: API Key - apiKeyId, issuerId
            state.apiKeyId = getInputValue('api-key-id');
            state.issuerId = getInputValue('issuer-id');
            break;
        case 8:
            // Step 8: Fastlane setup - nothing to save
            break;
        case 9:
            // Step 9: done - nothing to save
            break;
    }

    saveState();
}

// ============================================
// Command Generation Functions
// ============================================

function generateInitCommand() {
    // If the placeholder goes out without a path, cd fails.
    // Instead of hiding the command, a banner says what to fill in.
    const pathMissing = !state.projectPath;
    const projectPath = state.projectPath || translate('step8.projectPathPlaceholder');
    const bundleId = state.bundleId || 'com.example.app';
    const teamId = state.teamId || 'TEAM_ID';
    const profileName = state.profileName || 'Profile Name';
    const usesNonExemptEncryption = state.encryptionType === 'standard' ? 'true' : 'false';

    const warning = document.getElementById('initCmd-warning');
    if (warning) {
        warning.classList.toggle('hidden', !pathMissing);
    }

    // Scripts (.github/...) are relative to the repo root, but pubspec.yaml is relative to the Flutter root.
    // In a monorepo (e.g. repo/client/) the two differ, so cd goes to the repo root
    // and the Flutter root is passed separately as an argument to satisfy both.
    const repoRoot = state.repoRoot || projectPath;
    const isMonorepo = !!state.repoRoot && state.repoRoot !== state.projectPath;

    const monoNote = document.getElementById('initCmd-mono');
    if (monoNote) {
        monoNote.classList.toggle('hidden', !isMonorepo);
    }
    const isWindows = /^[A-Za-z]:[\\/]/.test(repoRoot);
    const python = isWindows ? 'python' : 'python3';
    const scriptPath = isWindows
        ? '.github\\util\\flutter\\testflight-wizard\\testflight-wizard.py'
        : '.github/util/flutter/testflight-wizard/testflight-wizard.py';

    // PowerShell 5.1, the default Windows terminal, cannot parse &&
    const separator = isWindows ? ';' : ' &&';
    const cmd = `cd "${repoRoot}"${separator} ${python} "${scriptPath}" setup "${projectPath}" "${bundleId}" "${teamId}" "${profileName}" "${usesNonExemptEncryption}"`;
    setElementText('initCmd', cmd);
}

function generateResults() {
    const secrets = [
        { key: 'APPLE_CERTIFICATE_BASE64', value: state.p12Base64, desc: translate('results.descCertificate') },
        { key: 'APPLE_CERTIFICATE_PASSWORD', value: state.p12Password, desc: translate('results.descCertificatePassword') },
        { key: 'APPLE_PROVISIONING_PROFILE_BASE64', value: state.provisionBase64, desc: 'Provisioning Profile' },
        { key: 'IOS_PROVISIONING_PROFILE_NAME', value: state.profileName, desc: translate('results.descProfileName') },
        { key: 'APP_STORE_CONNECT_API_KEY_BASE64', value: state.p8Base64, desc: 'API Key (.p8)' },
        { key: 'APP_STORE_CONNECT_API_KEY_ID', value: state.apiKeyId, desc: 'API Key ID' },
        { key: 'APP_STORE_CONNECT_ISSUER_ID', value: state.issuerId, desc: 'Issuer ID' },
        { key: 'APPLE_TEAM_ID', value: state.teamId, desc: 'Apple Team ID' },
        { key: 'IOS_BUNDLE_ID', value: state.bundleId, desc: 'Bundle ID' }
    ];

    const container = document.getElementById('results-container');
    container.innerHTML = secrets.map(s => `
        <div class="result-item">
            <div class="key">
                <span>${s.key} <small style="color:#71717a">(${s.desc})</small></span>
                <button class="copy-btn-small" onclick="copyValue(this, '${s.key}')">${translate('results.copy')}</button>
            </div>
            <div class="value" id="value-${s.key}">${s.value || translate('results.empty')}</div>
        </div>
    `).join('');
}

function copyValue(btn, key) {
    const value = document.getElementById(`value-${key}`).textContent;
    if (value === translate('results.empty')) {
        showToast(translate('results.valueEmpty'));
        return;
    }

    navigator.clipboard.writeText(value).then(() => {
        btn.textContent = translate('results.copied');
        btn.classList.add('copied');
        setTimeout(() => {
            btn.textContent = translate('results.copy');
            btn.classList.remove('copied');
        }, 2000);
    });
}

function downloadAsJson() {
    const secrets = {
        APPLE_CERTIFICATE_BASE64: state.p12Base64,
        APPLE_CERTIFICATE_PASSWORD: state.p12Password,
        APPLE_PROVISIONING_PROFILE_BASE64: state.provisionBase64,
        IOS_PROVISIONING_PROFILE_NAME: state.profileName,
        APP_STORE_CONNECT_API_KEY_BASE64: state.p8Base64,
        APP_STORE_CONNECT_API_KEY_ID: state.apiKeyId,
        APP_STORE_CONNECT_ISSUER_ID: state.issuerId,
        APPLE_TEAM_ID: state.teamId,
        IOS_BUNDLE_ID: state.bundleId
    };

    // Add custom Secrets
    if (state.customSecrets && state.customSecrets.length > 0) {
        state.customSecrets.forEach(cs => {
            if (cs.key && cs.value) {
                secrets[cs.key] = cs.value;
            }
        });
    }

    const jsonStr = JSON.stringify(secrets, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'github-secrets.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(translate('export.jsonDone'));
}

function downloadAsTxt() {
    const lines = [
        '# GitHub Secrets for iOS TestFlight Deployment',
        translate('export.txtGeneratedAt', { date: new Date().toLocaleString(getExportDateLocale()) }),
        '',
        '===== GitHub Repository Secrets =====',
        '',
        'APPLE_CERTIFICATE_BASE64:',
        state.p12Base64 || translate('value.notEntered'),
        '',
        'APPLE_CERTIFICATE_PASSWORD:',
        state.p12Password || translate('value.notEntered'),
        '',
        'APPLE_PROVISIONING_PROFILE_BASE64:',
        state.provisionBase64 || translate('value.notEntered'),
        '',
        'IOS_PROVISIONING_PROFILE_NAME:',
        state.profileName || translate('value.notEntered'),
        '',
        'APP_STORE_CONNECT_API_KEY_BASE64:',
        state.p8Base64 || translate('value.notEntered'),
        '',
        'APP_STORE_CONNECT_API_KEY_ID:',
        state.apiKeyId || translate('value.notEntered'),
        '',
        'APP_STORE_CONNECT_ISSUER_ID:',
        state.issuerId || translate('value.notEntered'),
        '',
        'APPLE_TEAM_ID:',
        state.teamId || translate('value.notEntered'),
        '',
        'IOS_BUNDLE_ID:',
        state.bundleId || translate('value.notEntered')
    ];

    // Add custom Secrets
    if (state.customSecrets && state.customSecrets.length > 0) {
        lines.push('');
        lines.push(translate('export.customSecretsHeader'));
        lines.push('');
        state.customSecrets.forEach(cs => {
            if (cs.key && cs.value) {
                const typeLabel = cs.type === 'text' ? translate('export.typeText') : '[Base64]';
                lines.push(`${cs.key}: ${typeLabel}`);
                lines.push(cs.value);
                lines.push('');
            }
        });
    }

    lines.push('=====================================');

    const txtStr = lines.join('\n');
    const blob = new Blob([txtStr], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'github-secrets.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(translate('export.txtDone'));
}

// ============================================
// Secret Guide Modal Functions
// ============================================

/** Guide text — assembled each time it opens to reflect language switches */
function getSecretGuides() {
    return {
        certificate: {
            title: translate('guide.certificateTitle'),
            steps: [
                translate('guide.certificateStep1'),
                translate('guide.certificateStep2'),
                translate('guide.certificateStep3'),
                translate('guide.certificateStep4'),
                translate('guide.certificateStep5'),
                translate('guide.certificateStep6')
            ],
            commands: [
                'base64 -i ~/Desktop/Certificates.p12 | pbcopy',
                translate('guide.copiedComment')
            ]
        },
        profile: {
            title: translate('guide.profileTitle'),
            steps: [
                translate('guide.profileStep1'),
                '2. Certificates, Identifiers & Profiles → Profiles',
                translate('guide.profileStep3'),
                translate('guide.profileStep4'),
                translate('guide.profileStep5'),
                translate('guide.profileStep6'),
                translate('guide.profileStep7')
            ],
            commands: [
                'base64 -i ~/Downloads/YourProfile.mobileprovision | pbcopy'
            ]
        },
        apikey: {
            title: translate('guide.apiKeyTitle'),
            steps: [
                translate('guide.apiKeyStep1'),
                translate('guide.apiKeyStep2'),
                translate('guide.apiKeyStep3'),
                translate('guide.apiKeyStep4'),
                translate('guide.apiKeyStep5'),
                translate('guide.apiKeyStep6'),
                translate('guide.apiKeyStep7'),
                translate('guide.apiKeyStep8')
            ],
            commands: [
                'base64 -i ~/Downloads/AuthKey_XXXXXX.p8 | pbcopy'
            ]
        }
    };
}

function showSecretGuide(type) {
    const guide = getSecretGuides()[type];
    if (!guide) return;

    const modal = document.getElementById('guideModal');
    const titleEl = document.getElementById('guideTitle');
    const content = document.getElementById('guideContent');

    if (!modal || !content) return;

    if (titleEl) {
        titleEl.textContent = guide.title;
    }

    let html = '<ol class="list-decimal list-inside space-y-2 mb-4">';
    guide.steps.forEach(step => {
        html += `<li class="text-slate-300 text-sm">${step}</li>`;
    });
    html += '</ol>';

    if (guide.commands && guide.commands.length > 0) {
        html += '<div class="space-y-2">';
        guide.commands.forEach(cmd => {
            html += `
                <div class="code-block">
                    <button class="copy-btn absolute top-2 right-2 px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs text-slate-300 transition" onclick="copyCode(this)">${translate('results.copy')}</button>
                    <pre>${cmd}</pre>
                </div>
            `;
        });
        html += '</div>';
    }

    content.innerHTML = html;
    modal.classList.remove('hidden');
}

function closeGuideModal(event) {
    if (event && event.target !== event.currentTarget) {
        return;
    }

    const modal = document.getElementById('guideModal');
    if (modal) {
        modal.classList.add('hidden');
    }
}

// ============================================
// Input Event Handlers
// ============================================

function setupInputHandlers() {
    // Uppercase the Team ID automatically
    const teamIdInput = document.getElementById('teamId');
    if (teamIdInput) {
        teamIdInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.toUpperCase();
        });
    }

    // Close the modal with the ESC key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeGuideModal();
        }
    });

    // Save on input field change
    const inputIds = ['projectPath', 'bundleId', 'bundleId-confirm', 'teamId', 'profileName', 'profileName-confirm', 'appName', 'p12-password', 'api-key-id', 'issuer-id'];
    inputIds.forEach(id => {
        const input = document.getElementById(id);
        if (input) {
            input.addEventListener('change', saveState);
            input.addEventListener('blur', saveState);
        }
    });

    // Live sync on Bundle ID input
    const bundleIdInput = document.getElementById('bundleId');
    if (bundleIdInput) {
        bundleIdInput.addEventListener('input', (e) => {
            state.bundleId = e.target.value.trim();
            const displayEl = document.getElementById('display-bundle-id');
            if (displayEl) displayEl.textContent = e.target.value.trim() || translate('value.notEntered');
        });
    }

    // Live sync on Profile Name input
    const profileNameInput = document.getElementById('profileName');
    if (profileNameInput) {
        profileNameInput.addEventListener('input', (e) => {
            state.profileName = e.target.value.trim();
            const displayEl = document.getElementById('display-profile-name');
            if (displayEl) displayEl.textContent = e.target.value.trim() || translate('value.notEntered');
        });
    }

    // Save on encryption setting change
    document.querySelectorAll('input[name="encryptionType"]').forEach(radio => {
        radio.addEventListener('change', saveState);
    });
}

// ============================================
// Initialization
// ============================================

function initialize() {
    // Load saved state
    const hasState = loadState();

    if (hasState) {
        showStep(state.currentStep);
        updateProgress();
        showToast(translate('nav.restored'));
    } else {
        showStep(1);
        updateProgress();
    }

    setupInputHandlers();
    setupDragAndDrop();
    showSecurityWarning();
}

// Initialize when the DOM is loaded
document.addEventListener('DOMContentLoaded', initialize);

/** Export date format — ko keeps the existing ko-KR output */
function getExportDateLocale() {
    return getWizardLanguage() === 'ko' ? 'ko-KR' : 'en-US';
}

/** "Not entered" cells — switch only cells already showing the not-entered text (en/ko) to the current language (example values stay) */
function refreshNotEnteredLabels() {
    const notEnteredTexts = ['(not entered)', '(미입력)'];
    ['display-bundle-id', 'display-profile-name'].forEach((id) => {
        const element = document.getElementById(id);
        if (element && notEnteredTexts.includes(element.textContent)) {
            element.textContent = translate('value.notEntered');
        }
    });
}

// Language switch: redraw JS-drawn areas (current step, custom Secrets, Team ID warning)
document.addEventListener('wizardlanguagechange', () => {
    showStep(state.currentStep);
    renderCustomSecrets();
    refreshNotEnteredLabels();
    const teamIdInput = document.getElementById('teamId');
    if (teamIdInput) validateTeamId(teamIdInput);
});

// Warn on page unload (prevents data loss)
window.addEventListener('beforeunload', (e) => {
    if (state.currentStep > 1 || state.bundleId || state.p12Base64) {
        e.preventDefault();
        e.returnValue = translate('nav.leaveWarning');
    }
});

// ============================================
// Changelog Modal Functions
// ============================================

// Close the changelog modal with ESC too
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeChangelogModal();
    }
});

// Update the version badge on page load
document.addEventListener('DOMContentLoaded', () => {
    const data = getVersionData();
    if (data && data.version) {
        const versionBadge = document.getElementById('versionBadge');
        if (versionBadge) {
            versionBadge.textContent = `v${data.version}`;
        }
    }
});
