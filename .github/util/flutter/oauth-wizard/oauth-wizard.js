/**
 * OAuth login wizard (Kakao, Google) — state, step flow, screen rendering (#156)
 * Static HTML/JS: no network calls; Secret values stay only in this browser (localStorage).
 *
 * Steps are dynamic, depending on the chosen providers.
 *   Only active steps among .step-content[data-step-id] get data-step="order"
 *   so the shared showStep/prevStep (_shared/wizard-common.js) work as is.
 * Step rendering is in oauth-wizard-steps.js, output generation in oauth-wizard-snippets.js, downloads in oauth-wizard-export.js
 */

// ============================================
// Constants
// ============================================
const STORAGE_KEY = 'oauth_wizard_state';
// Full step order — kakao/google are active only when chosen
const STEP_IDS_IN_ORDER = ['providers', 'identity', 'fingerprints', 'kakao', 'google', 'secrets', 'cicd', 'gitignore', 'apply', 'summary'];
// googleSetup: firebase-sdk (config files included) | firebase-ids (client IDs only) | cloud (Cloud console)
const GOOGLE_SETUP_WITH_FILES = 'firebase-sdk';

// Output placeholders and paths (used by oauth-wizard-snippets.js)
const PLACEHOLDER_KAKAO_NATIVE_APP_KEY = 'YOUR_NATIVE_APP_KEY';
const PLACEHOLDER_GOOGLE_IOS_CLIENT_ID = 'YOUR_IOS_CLIENT_ID.apps.googleusercontent.com';
const PLACEHOLDER_GOOGLE_SERVER_CLIENT_ID = 'YOUR_WEB_CLIENT_ID.apps.googleusercontent.com';
const OAUTH_WIZARD_CLI_PATH = '.github/util/flutter/oauth-wizard/oauth-wizard.py';
// Wizard export file name — change together with oauth-wizard.py GITIGNORE_EXPORT_PATTERNS
const OAUTH_EXPORT_FILE_PREFIX_SECRETS = 'oauth-secrets-';
const OAUTH_EXPORT_FILE_PREFIX_SETUP = 'oauth-setup-';
// Secret names — same as PLATFORMS in .github/scripts/firebase_config_files.py (#785)
const SECRET_NAME_GOOGLE_SERVICES_JSON = 'GOOGLE_SERVICES_JSON';
const SECRET_NAME_GOOGLE_SERVICE_INFO_PLIST = 'GOOGLE_SERVICE_INFO_PLIST';
// Template workflows that restore the Firebase config files with the script above (Flutter CI restores both)
const ANDROID_WORKFLOWS = ['PROJECT-FLUTTER-ANDROID-TEST-APK', 'PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD', 'PROJECT-FLUTTER-ANDROID-FIREBASE-CICD', 'PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD'];
const IOS_WORKFLOWS = ['PROJECT-FLUTTER-IOS-TESTFLIGHT', 'PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT'];

// ============================================
// State
// ============================================
function createInitialState() {
    return {
        currentStep: 1,
        currentStepId: 'providers',
        totalSteps: STEP_IDS_IN_ORDER.length,
        operatingSystem: detectOS() === 'windows' ? 'windows' : 'mac',
        providers: { kakao: false, google: false },
        applicationId: '',
        bundleId: '',
        projectPath: '.',
        debugSha1: '',
        uploadSha1: '',
        playSigningSha1: '',
        kakaoNativeAppKey: '',
        googleSetup: 'firebase-ids',
        googleIosClientId: '',
        googleServerClientId: '',
        googleServicesJson: '',
        googleServicesFileName: '',
        googleServiceInfoPlist: '',
        googleServiceInfoFileName: '',
        repoOwner: '',
        repoName: '',
        updateGitignore: true,
        checklist: {},
        customSecrets: []
    };
}

const state = createInitialState();

function loadState() {
    const saved = readWizardState(STORAGE_KEY);
    if (!saved) return false;
    Object.assign(state, createInitialState(), saved);
    state.providers = Object.assign({ kakao: false, google: false }, saved.providers || {});
    state.checklist = saved.checklist || {};
    state.customSecrets = Array.isArray(saved.customSecrets) ? saved.customSecrets : [];
    return true;
}

// ============================================
// Dynamic steps
// ============================================

function isStepActive(stepId) {
    if (stepId === 'kakao') return state.providers.kakao;
    if (stepId === 'google') return state.providers.google;
    return true;
}

function getActiveStepIds() {
    return STEP_IDS_IN_ORDER.filter(isStepActive);
}

function getStepIdByNumber(stepNumber) {
    return getActiveStepIds()[stepNumber - 1] || 'providers';
}

/** Step labels (keys must be written as literal strings so check_i18n.py knows they are used) */
function getStepLabel(stepId) {
    switch (stepId) {
        case 'providers': return translate('steps.providers');
        case 'identity': return translate('steps.identity');
        case 'fingerprints': return translate('steps.fingerprints');
        case 'kakao': return 'Kakao';
        case 'google': return 'Google';
        case 'secrets': return 'Secrets';
        case 'cicd': return 'CI/CD';
        case 'gitignore': return '.gitignore';
        case 'apply': return translate('steps.apply');
        default: return translate('steps.summary');
    }
}

/** Number only active steps with data-step > update the step count and current position */
function assignStepNumbers() {
    const activeStepIds = getActiveStepIds();
    $$('.step-content[data-step-id]').forEach((element) => {
        const index = activeStepIds.indexOf(element.dataset.stepId);
        const badge = element.querySelector('.step-number-badge');
        if (index === -1) {
            element.removeAttribute('data-step');
            element.classList.add('hidden');
            if (badge) badge.textContent = '';
        } else {
            element.setAttribute('data-step', String(index + 1));
            if (badge) badge.textContent = String(index + 1);
        }
    });
    state.totalSteps = activeStepIds.length;
    const currentIndex = activeStepIds.indexOf(state.currentStepId);
    state.currentStep = currentIndex === -1 ? Math.min(state.currentStep, state.totalSteps) : currentIndex + 1;
    state.currentStepId = getStepIdByNumber(state.currentStep);
}

function renderStepIndicators() {
    const container = document.getElementById('stepIndicatorList');
    if (!container) return;
    container.innerHTML = getActiveStepIds().map((stepId, index) => `
        <div class="step-indicator flex flex-col items-center flex-1 relative min-w-[40px]" data-step="${index + 1}">
            <div class="step-circle w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs z-10"></div>
            <span class="text-[10px] mt-1 text-center hidden md:block">${escapeHtml(getStepLabel(stepId))}</span>
        </div>`).join('');
}

/** Step indicator: done ✓ / current / remaining — any step can be clicked (shared behavior across wizards) */
function updateProgress() {
    renderStepIndicators();
    $$('.step-indicator').forEach((indicator, index) => {
        const stepNumber = index + 1;
        const circle = indicator.querySelector('.step-circle');
        const label = indicator.querySelector('span');
        const base = 'step-circle w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs z-10';
        if (stepNumber < state.currentStep) {
            circle.className = `${base} bg-green-500 text-slate-900 shadow-lg`;
            circle.textContent = '✓';
            label.classList.add('text-green-400');
        } else if (stepNumber === state.currentStep) {
            circle.className = `${base} bg-oauth-primary text-white shadow-lg`;
            circle.textContent = String(stepNumber);
            label.classList.add('text-oauth-accent');
        } else {
            circle.className = `${base} bg-slate-700 text-slate-400`;
            circle.textContent = String(stepNumber);
            label.classList.add('text-slate-500');
        }
        indicator.style.cursor = 'pointer';
        indicator.onclick = () => goToStep(stepNumber);
    });
}

function moveToStep(stepNumber) {
    saveCurrentStepData();
    state.currentStep = stepNumber;
    state.currentStepId = getStepIdByNumber(stepNumber);
    showStep(state.currentStep);
    updateProgress();
    saveState();
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function goToStep(stepNumber) {
    if (stepNumber === state.currentStep) return;
    if (stepNumber >= 1 && stepNumber <= state.totalSteps) moveToStep(stepNumber);
}

/** Move on only when the current step validates (clicking the step indicator is free) */
function nextStep() {
    const problem = findCurrentStepProblem();
    if (problem) {
        showToast(problem);
        return;
    }
    if (state.currentStep < state.totalSteps) moveToStep(state.currentStep + 1);
}

/** Called by the shared prevStep/nextStep before moving — input was already saved via oninput */
function saveCurrentStepData() {
    state.currentStepId = getStepIdByNumber(state.currentStep);
}

function resetWizard() {
    if (!confirm(translate('confirm.reset'))) return;
    clearState();
    Object.assign(state, createInitialState());
    assignStepNumbers();
    showStep(1);
    updateProgress();
    showToast(translate('toast.reset'));
}

// ============================================
// Per-step validation
// ============================================

/** Current step > blocking reason text (empty string when it passes) */
function findCurrentStepProblem() {
    switch (getStepIdByNumber(state.currentStep)) {
        case 'providers':
            return state.providers.kakao || state.providers.google ? '' : translate('toast.pickProvider');
        case 'identity':
            if (!isValidApplicationId(state.applicationId)) return translate('toast.invalidApplicationId');
            if (!isValidBundleId(state.bundleId)) return translate('toast.invalidBundleId');
            return '';
        case 'fingerprints':
            return findFingerprintProblem();
        case 'kakao':
            return isValidKakaoNativeAppKey(state.kakaoNativeAppKey) ? '' : translate('toast.invalidKakaoKey');
        case 'google':
            return findGoogleProblem();
        default:
            return '';
    }
}

function findFingerprintProblem() {
    const values = [state.debugSha1, state.uploadSha1, state.playSigningSha1];
    if (values.some((value) => value && !isValidSha1(value))) return translate('toast.invalidSha1');
    return values.some(isValidSha1) ? '' : translate('toast.needOneSha1');
}

function findGoogleProblem() {
    if (isUsingFirebaseFiles() && (!state.googleServicesJson || !state.googleServiceInfoPlist)) {
        return translate('toast.needFirebaseFiles');
    }
    if (!isValidGoogleClientId(state.googleIosClientId)) return translate('toast.invalidIosClientId');
    if (state.googleServerClientId && !isValidGoogleClientId(state.googleServerClientId)) return translate('toast.invalidServerClientId');
    if (!state.googleServerClientId && !isUsingFirebaseFiles()) return translate('toast.needServerClientId');
    return '';
}

// ============================================
// Selection state
// ============================================

/** Google + Firebase SDK = the 2 config files restored in CI from Secrets */
function isUsingFirebaseFiles() {
    return state.providers.google && state.googleSetup === GOOGLE_SETUP_WITH_FILES;
}

/** Entered SHA-1 > [{label, sha1, keyHash}] (only well-formed ones) */
function collectFingerprintEntries() {
    return [
        { label: translate('keys.debug'), value: state.debugSha1 },
        { label: translate('keys.upload'), value: state.uploadSha1 },
        { label: translate('keys.playSigning'), value: state.playSigningSha1 },
    ].filter((entry) => isValidSha1(entry.value)).map((entry) => ({
        label: entry.label,
        sha1: normalizeSha1(entry.value),
        keyHash: sha1ToKakaoKeyHash(entry.value),
    }));
}

/** Show data-show-if areas: google-firebase / google-cloud / firebase-files / no-firebase-files */
function applyConditionalVisibility() {
    const isFirebaseConsole = state.googleSetup === 'firebase-sdk' || state.googleSetup === 'firebase-ids';
    const visibilityByCondition = {
        'google-firebase': state.providers.google && isFirebaseConsole,
        'google-cloud': state.providers.google && state.googleSetup === 'cloud',
        'firebase-files': isUsingFirebaseFiles(),
        'no-firebase-files': !isUsingFirebaseFiles(),
    };
    $$('[data-show-if]').forEach((element) => {
        element.classList.toggle('hidden', !visibilityByCondition[element.dataset.showIf]);
    });
}

// ============================================
// Input handlers
// ============================================

function onTextInput(field, value) {
    state[field] = String(value || '').trim();
    saveState();
    renderStepContent(getStepIdByNumber(state.currentStep));
}

function onFingerprintInput(field, value) {
    onTextInput(field, value);
}

function onProviderToggle(provider, isChecked) {
    state.providers[provider] = isChecked;
    assignStepNumbers();
    updateProgress();
    saveState();
    renderProvidersStep();
}

function onGoogleSetupChange(value) {
    state.googleSetup = value;
    saveState();
    renderStepContent('google');
}

function onUpdateGitignoreToggle(isChecked) {
    state.updateGitignore = isChecked;
    saveState();
}

function onChecklistToggle(itemId, isChecked) {
    state.checklist[itemId] = isChecked;
    saveState();
}

function selectOperatingSystem(operatingSystem) {
    state.operatingSystem = operatingSystem;
    saveState();
    renderStepContent(getStepIdByNumber(state.currentStep));
}

function setInputValue(id, value) {
    const element = document.getElementById(id);
    // Do not rewrite the field being typed in (the cursor jumps to the end)
    if (element && document.activeElement !== element) element.value = value || '';
}

function setPreText(id, text) {
    const element = document.getElementById(id);
    if (element) element.textContent = text;
}

function renderOperatingSystemTabs() {
    [['fingerprintOsTabMac', 'mac'], ['fingerprintOsTabWindows', 'windows'], ['applyOsTabMac', 'mac'], ['applyOsTabWindows', 'windows']]
        .forEach(([id, operatingSystem]) => {
            const tab = document.getElementById(id);
            if (!tab) return;
            // Highlight only the selected tab (together with bg-slate-900 the highlight gets lost depending on CSS order)
            const isSelected = state.operatingSystem === operatingSystem;
            tab.classList.toggle('bg-oauth-primary', isSelected);
            tab.classList.toggle('bg-slate-900', !isSelected);
        });
}

// ============================================
// Secret list
// ============================================

/** Secrets to register > [{key, value, source, usedBy, type}] */
function buildSecretsList() {
    const secrets = [];
    if (isUsingFirebaseFiles()) {
        secrets.push({
            key: SECRET_NAME_GOOGLE_SERVICES_JSON, value: state.googleServicesJson, type: 'text',
            source: state.googleServicesFileName || 'google-services.json', usedBy: 'Android workflows + Flutter CI',
        });
        secrets.push({
            key: SECRET_NAME_GOOGLE_SERVICE_INFO_PLIST, value: state.googleServiceInfoPlist, type: 'text',
            source: state.googleServiceInfoFileName || 'GoogleService-Info.plist', usedBy: 'iOS TestFlight workflows + Flutter CI',
        });
    }
    getCustomSecretsForExport().forEach((secret) => {
        secrets.push({ key: secret.key, value: secret.value, type: secret.type, source: secret.desc, usedBy: secret.hint });
    });
    return secrets;
}

function copySecretValue(key) {
    const secret = buildSecretsList().find((item) => item.key === key);
    if (!secret || !secret.value) {
        showToast(translate('toast.secretEmpty', { key }));
        return;
    }
    copyToClipboard(secret.value, translate('toast.secretCopied', { key }));
}

// ============================================
// Initialization
// ============================================

function initialize() {
    const hasSavedState = loadState();
    assignStepNumbers();
    showStep(state.currentStep);
    updateProgress();
    if (hasSavedState) showToast(translate('toast.restored'));
    setupDragAndDrop('googleServicesDropZone', handleGoogleServicesFile);
    setupDragAndDrop('googleServiceInfoDropZone', handleGoogleServiceInfoFile);
    syncVersionBadge();
    showSecurityWarning();
}

document.addEventListener('DOMContentLoaded', initialize);

// Language switch: redraw JS-drawn areas (step indicator, current step, custom Secrets)
document.addEventListener('wizardlanguagechange', () => {
    updateProgress();
    renderStepContent(getStepIdByNumber(state.currentStep));
    renderCustomSecrets();
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeChangelogModal();
});
