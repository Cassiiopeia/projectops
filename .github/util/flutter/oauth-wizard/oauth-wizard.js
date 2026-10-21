/**
 * OAuth 로그인 마법사 (Kakao · Google) — 상태·단계 흐름·화면 렌더 (#156)
 * 정적 HTML/JS: 네트워크 호출 없음, Secret 값은 이 브라우저(localStorage)에만 남는다.
 *
 * 단계는 선택한 제공자에 따라 동적이다.
 *   .step-content[data-step-id] 중 활성 단계에만 data-step="순번"을 매겨
 *   공통 showStep·prevStep(_shared/wizard-common.js)이 그대로 동작하게 한다.
 * 단계 화면 렌더는 oauth-wizard-steps.js, 산출물 생성은 oauth-wizard-snippets.js, 내려받기는 oauth-wizard-export.js
 */

// ============================================
// 상수
// ============================================
const STORAGE_KEY = 'oauth_wizard_state';
// 단계 전체 순서 — kakao·google 은 선택했을 때만 활성
const STEP_IDS_IN_ORDER = ['providers', 'identity', 'fingerprints', 'kakao', 'google', 'secrets', 'cicd', 'gitignore', 'apply', 'summary'];
// googleSetup: firebase-sdk(설정 파일 동봉) | firebase-ids(클라이언트 ID만) | cloud(Cloud 콘솔)
const GOOGLE_SETUP_WITH_FILES = 'firebase-sdk';

// 산출물 자리표시자·경로 (oauth-wizard-snippets.js 가 쓴다)
const PLACEHOLDER_KAKAO_NATIVE_APP_KEY = 'YOUR_NATIVE_APP_KEY';
const PLACEHOLDER_GOOGLE_IOS_CLIENT_ID = 'YOUR_IOS_CLIENT_ID.apps.googleusercontent.com';
const PLACEHOLDER_GOOGLE_SERVER_CLIENT_ID = 'YOUR_WEB_CLIENT_ID.apps.googleusercontent.com';
const OAUTH_WIZARD_CLI_PATH = '.github/util/flutter/oauth-wizard/oauth-wizard.py';
// 마법사 내보내기 파일 이름 — oauth-wizard.py GITIGNORE_EXPORT_PATTERNS 와 함께 바꾼다
const OAUTH_EXPORT_FILE_PREFIX_SECRETS = 'oauth-secrets-';
const OAUTH_EXPORT_FILE_PREFIX_SETUP = 'oauth-setup-';
// Secret 이름 — .github/scripts/firebase_config_files.py PLATFORMS 와 같다 (#785)
const SECRET_NAME_GOOGLE_SERVICES_JSON = 'GOOGLE_SERVICES_JSON';
const SECRET_NAME_GOOGLE_SERVICE_INFO_PLIST = 'GOOGLE_SERVICE_INFO_PLIST';
// 위 스크립트로 Firebase 설정 파일을 복원하는 템플릿 워크플로우 (Flutter CI 는 두 파일 모두)
const ANDROID_WORKFLOWS = ['PROJECT-FLUTTER-ANDROID-TEST-APK', 'PROJECT-FLUTTER-ANDROID-PLAYSTORE-CICD', 'PROJECT-FLUTTER-ANDROID-FIREBASE-CICD', 'PROJECT-FLUTTER-ANDROID-SELFHOSTED-CICD'];
const IOS_WORKFLOWS = ['PROJECT-FLUTTER-IOS-TESTFLIGHT', 'PROJECT-FLUTTER-IOS-TEST-TESTFLIGHT'];

// ============================================
// 상태
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
// 동적 단계
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

/** 단계 라벨 (키를 문자열 그대로 써야 check_i18n.py 가 사용 여부를 안다) */
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

/** 활성 단계에만 data-step 순번 부여 > 단계 수·현재 순번 갱신 */
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

/** 단계 표시: 완료 ✓ / 현재 / 남음 — 어느 단계로든 클릭 이동 가능 (3종 공통 동작) */
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

/** 현재 단계 검증 통과 시에만 다음으로 (단계 표시 클릭 이동은 자유) */
function nextStep() {
    const problem = findCurrentStepProblem();
    if (problem) {
        showToast(problem);
        return;
    }
    if (state.currentStep < state.totalSteps) moveToStep(state.currentStep + 1);
}

/** 공통 prevStep·nextStep 이 단계 이동 전에 부른다 — 입력은 oninput 으로 이미 저장됨 */
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
// 단계별 검증
// ============================================

/** 현재 단계 > 막는 사유 문구 (통과면 빈 문자열) */
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
// 선택 상태 판단
// ============================================

/** Google + Firebase SDK 사용 = 설정 파일 2개를 Secret 으로 CI 에 복원 */
function isUsingFirebaseFiles() {
    return state.providers.google && state.googleSetup === GOOGLE_SETUP_WITH_FILES;
}

/** 입력한 SHA-1 > [{label, sha1, keyHash}] (형식이 맞는 것만) */
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

/** data-show-if 영역 표시: google-firebase · google-cloud · firebase-files · no-firebase-files */
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
// 입력 핸들러
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
    // 입력 중인 칸은 다시 쓰지 않는다 (커서가 끝으로 튀는 문제)
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
            // 선택 탭만 강조 (bg-slate-900 과 함께 두면 CSS 순서에 따라 강조가 묻힌다)
            const isSelected = state.operatingSystem === operatingSystem;
            tab.classList.toggle('bg-oauth-primary', isSelected);
            tab.classList.toggle('bg-slate-900', !isSelected);
        });
}

// ============================================
// Secret 목록
// ============================================

/** 등록할 Secret > [{key, value, source, usedBy, type}] */
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
// 초기화
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

// 언어 전환: JS 가 그린 영역(단계 표시·현재 단계·커스텀 Secret) 다시 그리기
document.addEventListener('wizardlanguagechange', () => {
    updateProgress();
    renderStepContent(getStepIdByNumber(state.currentStep));
    renderCustomSecrets();
});

document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') closeChangelogModal();
});
