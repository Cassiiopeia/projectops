/**
 * Flutter iOS TestFlight 통합 마법사
 * 파일 업로드, Base64 변환, localStorage 진행률 저장 포함
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
    // 파일 데이터 (Base64)
    p12Base64: '',
    p12Password: '',
    provisionBase64: '',
    p8Base64: '',
    apiKeyId: '',
    issuerId: '',
    // Custom Secrets (사용자 추가)
    customSecrets: []
    // [{
    //   key: 'SECRET_NAME',
    //   value: '...',
    //   fileName: 'file.json',
    //   type: 'text' | 'binary',
    //   hint: '사용법 힌트'
    // }]
};

// ============================================
// LocalStorage Functions
// ============================================

const STORAGE_KEY = 'flutter_ios_wizard_state';
const STORAGE_WARNING_KEY = 'flutter_ios_wizard_security_warning_dismissed';

function saveState() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
        console.warn('localStorage 저장 실패:', e);
    }
}

function loadState() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const savedState = JSON.parse(saved);
            // 현재 코드의 totalSteps 보존 (버전 업그레이드 시 캐시된 값 무시)
            const currentTotalSteps = state.totalSteps;
            Object.assign(state, savedState);
            state.totalSteps = currentTotalSteps; // 항상 현재 코드 기준으로 설정

            // currentStep이 totalSteps를 초과하면 보정
            if (state.currentStep > state.totalSteps) {
                state.currentStep = state.totalSteps;
            }

            restoreUIFromState();
            return true;
        }
    } catch (e) {
        console.warn('localStorage 로드 실패:', e);
    }
    return false;
}

function clearState() {
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch (e) {
        console.warn('localStorage 삭제 실패:', e);
    }
}

function restoreUIFromState() {
    // 입력 필드 복원
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

    // Step 5 display 요소 업데이트
    if (state.bundleId) {
        const displayBundleId = document.getElementById('display-bundle-id');
        if (displayBundleId) displayBundleId.textContent = state.bundleId;
    }
    if (state.profileName) {
        const displayProfileName = document.getElementById('display-profile-name');
        if (displayProfileName) displayProfileName.textContent = state.profileName;
    }

    // 암호화 설정 복원
    if (state.encryptionType) {
        const radio = document.querySelector(`input[name="encryptionType"][value="${state.encryptionType}"]`);
        if (radio) radio.checked = true;
    }

    // 파일 업로드 상태 복원
    if (state.p12Base64) {
        document.getElementById('p12-upload').classList.add('has-file');
        const info = document.getElementById('p12-info');
        if (info) {
            info.style.display = 'block';
            info.textContent = '✅ 인증서 파일 로드됨';
        }
    }

    if (state.provisionBase64) {
        document.getElementById('provision-upload').classList.add('has-file');
        const info = document.getElementById('provision-info');
        if (info) {
            info.style.display = 'block';
            info.textContent = '✅ 프로비저닝 프로파일 로드됨';
        }
    }

    if (state.p8Base64) {
        document.getElementById('p8-upload').classList.add('has-file');
        const info = document.getElementById('p8-info');
        if (info) {
            info.style.display = 'block';
            info.textContent = '✅ API Key 파일 로드됨';
        }
    }

    // 커스텀 Secrets 복원
    if (state.customSecrets && state.customSecrets.length > 0) {
        renderCustomSecrets();
    }
}

// ============================================
// Security Warning
// ============================================

// ============================================
// DOM Utility Functions
// ============================================

function $(selector) {
    return document.querySelector(selector);
}

function $$(selector) {
    return document.querySelectorAll(selector);
}

/**
 * Team ID 실시간 검증.
 * 복붙 중 마지막 글자가 누락된 9자리 입력이 잦은데, 그대로 Secret에 들어가면
 * 빌드 서명 단계에서야 팀 불일치로 실패해 원인 추적이 어렵다. 입력 시점에 잡는다.
 */
function validateTeamId(input) {
    const warning = document.getElementById('teamId-warning');
    if (!warning) return;

    const value = (input.value || '').trim().toUpperCase();
    input.value = value;

    // 미입력 상태에서는 경고를 띄우지 않는다 (입력 전부터 빨간 글씨는 노이즈)
    if (value.length === 0) {
        warning.className = 'text-xs mt-1 hidden';
        return;
    }

    if (value.length < 10) {
        warning.textContent = `⚠️ ${value.length}자리 - Team ID는 10자리입니다. 마지막 글자가 빠지지 않았는지 확인하세요.`;
        warning.className = 'text-xs mt-1 text-red-400';
    } else if (!/^[A-Z0-9]{10}$/.test(value)) {
        warning.textContent = '⚠️ Team ID는 영문 대문자와 숫자 10자리입니다.';
        warning.className = 'text-xs mt-1 text-red-400';
    } else {
        warning.textContent = '✅ 형식이 올바릅니다';
        warning.className = 'text-xs mt-1 text-green-400';
    }
}

// ============================================
// File Upload & Base64 Conversion
// ============================================

// .p12 파일 업로드
async function handleP12Upload(event) {
    const file = event.target.files[0];
    if (file) await handleP12File(file);
}

async function handleP12File(file) {
    if (!file.name.endsWith('.p12')) {
        showToast('⚠️ .p12 파일만 업로드 가능합니다');
        return;
    }

    try {
        state.p12Base64 = await fileToBase64(file);
        document.getElementById('p12-upload').classList.add('has-file');
        const info = document.getElementById('p12-info');
        info.style.display = 'block';
        info.textContent = `✅ ${file.name} (${(file.size/1024).toFixed(1)}KB)`;
        saveState();
        showToast('✅ 인증서 파일 업로드 완료');
    } catch (error) {
        showToast('❌ 파일 읽기 실패: ' + error.message);
    }
}

// .mobileprovision 파일 업로드
async function handleProvisionUpload(event) {
    const file = event.target.files[0];
    if (file) await handleProvisionFile(file);
}

async function handleProvisionFile(file) {
    if (!file.name.endsWith('.mobileprovision')) {
        showToast('⚠️ .mobileprovision 파일만 업로드 가능합니다');
        return;
    }

    try {
        state.provisionBase64 = await fileToBase64(file);
        document.getElementById('provision-upload').classList.add('has-file');
        const info = document.getElementById('provision-info');
        info.style.display = 'block';
        info.textContent = `✅ ${file.name} (${(file.size/1024).toFixed(1)}KB)`;
        saveState();
        showToast('✅ 프로비저닝 프로파일 업로드 완료');
    } catch (error) {
        showToast('❌ 파일 읽기 실패: ' + error.message);
    }
}

// .p8 파일 업로드
async function handleP8Upload(event) {
    const file = event.target.files[0];
    if (file) await handleP8File(file);
}

async function handleP8File(file) {
    if (!file.name.endsWith('.p8')) {
        showToast('⚠️ .p8 파일만 업로드 가능합니다');
        return;
    }

    try {
        state.p8Base64 = await fileToBase64(file);
        document.getElementById('p8-upload').classList.add('has-file');
        const info = document.getElementById('p8-info');
        info.style.display = 'block';
        info.textContent = `✅ ${file.name}`;

        // 파일명에서 Key ID 자동 추출
        const match = file.name.match(/AuthKey_(\w+)\.p8/);
        if (match) {
            state.apiKeyId = match[1];
            document.getElementById('api-key-id').value = match[1];
        }

        saveState();
        showToast('✅ API Key 파일 업로드 완료');
    } catch (error) {
        showToast('❌ 파일 읽기 실패: ' + error.message);
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

            // 브라우저는 보안상 절대경로를 주지 않는다 (폴더명만 얻을 수 있음).
            // 입력칸에 안내문을 써넣으면 실제 경로를 덮어써 폴백(/path/to/project)이 나가므로,
            // 입력칸은 건드리지 않고 힌트 영역에만 폴더명을 표시한다.
            const hint = document.getElementById('projectPath-hint');
            if (hint) {
                hint.innerHTML = `선택한 폴더: <span class="text-yellow-400 font-mono">${folderName}</span> — 아래 칸에 이 폴더의 <span class="text-yellow-400">절대경로</span>를 입력하세요 (터미널에서 <code class="text-slate-300">pwd</code>)`;
                hint.classList.remove('hidden');
            }

            const input = document.getElementById('projectPath');
            if (input) input.focus();

            showToast(`폴더 "${folderName}" 선택됨 - 절대경로를 입력해주세요`);
        } catch (err) {
            if (err.name !== 'AbortError') {
                console.error('폴더 선택 오류:', err);
                showToast('폴더 선택에 실패했습니다. 경로를 직접 입력해주세요.');
            }
        }
    } else {
        showToast('이 브라우저는 폴더 선택을 지원하지 않습니다.');
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
            // 완료된 스텝
            circle.className = 'step-circle w-10 h-10 rounded-full bg-green-500 text-white flex items-center justify-center font-bold text-sm z-10 shadow-lg';
            circle.innerHTML = '✓';
            if (label) label.className = 'text-xs mt-2 text-green-400 text-center hidden md:block';
        } else if (stepNum === state.currentStep) {
            // 현재 스텝 - 파랑-보라 그라데이션
            circle.className = 'step-circle w-10 h-10 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 text-white flex items-center justify-center font-bold text-sm z-10 shadow-lg shadow-blue-500/30';
            circle.innerHTML = stepNum;
            if (label) label.className = 'text-xs mt-2 text-blue-400 text-center hidden md:block';
        } else {
            // 아직 안 한 스텝
            circle.className = 'step-circle w-10 h-10 rounded-full bg-slate-700 text-slate-400 flex items-center justify-center font-bold text-sm z-10';
            circle.innerHTML = stepNum;
            if (label) label.className = 'text-xs mt-2 text-slate-500 text-center hidden md:block';
        }

        // 클릭하여 해당 스텝으로 이동 가능
        indicator.style.cursor = 'pointer';
        indicator.onclick = () => goToStep(stepNum);
    });
}

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

function initializeStep(stepNumber) {
    switch (stepNumber) {
        case 2:
            // Step 2: Distribution 인증서
            restoreInputValues();
            break;
        case 3:
            // Step 3: App ID (Bundle ID) - bundleId 입력
            restoreInputValues();
            break;
        case 4:
            // Step 4: Provisioning Profile - profileName 입력
            restoreInputValues();
            break;
        case 5:
            // Step 5: App Store Connect 앱 등록 (신규!)
            syncStep5ASCValues();
            break;
        case 6:
            // Step 6: 앱 정보 확인 - 이전 단계에서 입력한 값 표시
            syncStep6Values();
            restoreInputValues();
            break;
        case 7:
            // Step 7: API Key
            restoreInputValues();
            break;
        case 8:
            // Step 8: Fastlane 설정
            generateInitCommand();
            break;
        case 9:
            // Step 9: 완료
            generateResults();
            break;
    }
}

function syncStep5ASCValues() {
    // Step 3에서 입력한 Bundle ID를 Step 5 App Store Connect 가이드에 표시
    const bundleIdValue = state.bundleId || getInputValue('bundleId');
    const displayBundleIdAsc = document.getElementById('display-bundle-id-asc');
    if (displayBundleIdAsc && bundleIdValue) {
        displayBundleIdAsc.textContent = bundleIdValue;
    }
}

function syncStep6Values() {
    // Step 3에서 입력한 Bundle ID를 Step 6에 표시
    const bundleIdValue = state.bundleId || getInputValue('bundleId');
    const displayBundleId = document.getElementById('display-bundle-id');
    if (displayBundleId && bundleIdValue) {
        displayBundleId.textContent = bundleIdValue;
    }

    // Step 4에서 입력한 Profile Name을 Step 6에 표시
    const profileNameValue = state.profileName || getInputValue('profileName');
    const displayProfileName = document.getElementById('display-profile-name');
    if (displayProfileName && profileNameValue) {
        displayProfileName.textContent = profileNameValue;
    }

    // 확인용 입력 필드에도 값 설정 (readonly)
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
        showToast(`Step ${stepNumber} 건너뛰기`);
    }
}

function resetWizard() {
    if (confirm('모든 데이터를 초기화하시겠습니까?')) {
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

        // UI 초기화
        const inputs = ['projectPath', 'repoRoot', 'bundleId', 'bundleId-confirm', 'teamId', 'profileName', 'profileName-confirm', 'appName', 'p12-password', 'api-key-id', 'issuer-id'];
        inputs.forEach(id => {
            const input = document.getElementById(id);
            if (input) input.value = '';
        });

        // Display 요소 초기화
        const displayBundleId = document.getElementById('display-bundle-id');
        if (displayBundleId) displayBundleId.textContent = '(미입력)';
        const displayProfileName = document.getElementById('display-profile-name');
        if (displayProfileName) displayProfileName.textContent = '(미입력)';

        // 파일 업로드 상태 초기화
        document.querySelectorAll('.file-upload').forEach(el => {
            el.classList.remove('has-file');
        });
        document.querySelectorAll('.file-info').forEach(el => {
            el.style.display = 'none';
        });

        showStep(1);
        updateProgress();
        showToast('마법사가 초기화되었습니다.');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// ============================================
// Data Management Functions
// ============================================

function saveCurrentStepData() {
    switch (state.currentStep) {
        case 1:
            // Step 1: 시작하기 - 프로젝트 경로
            state.projectPath = getInputValue('projectPath');
            // 구버전이 입력칸에 써넣던 안내문이 남아 있으면 경로로 쓰지 않는다
            if (state.projectPath.startsWith('선택된 폴더:')) {
                state.projectPath = '';
            }
            // 상대경로는 Step 8 명령어에서 cd 실패로 이어지므로 미리 걸러낸다
            if (state.projectPath && !isAbsolutePath(state.projectPath)) {
                showToast('절대경로를 입력해주세요 (예: /Users/이름/projects/myapp)');
                state.projectPath = '';
            }
            // 모노레포에서만 채우는 선택 입력 — 비어 있으면 Flutter 루트를 그대로 쓴다
            state.repoRoot = getInputValue('repoRoot');
            if (state.repoRoot && !isAbsolutePath(state.repoRoot)) {
                showToast('레포 루트도 절대경로로 입력해주세요');
                state.repoRoot = '';
            }
            break;
        case 2:
            // Step 2: Distribution 인증서 - .p12 파일 및 비밀번호
            state.p12Password = getInputValue('p12-password');
            break;
        case 3:
            // Step 3: App ID (Bundle ID) - bundleId 입력
            state.bundleId = getInputValue('bundleId');
            break;
        case 4:
            // Step 4: Provisioning Profile - profileName 입력
            state.profileName = getInputValue('profileName');
            break;
        case 5:
            // Step 5: App Store Connect 앱 등록 - 별도 저장 없음 (확인 단계)
            break;
        case 6:
            // Step 6: 앱 정보 확인 - Team ID, App Name, 암호화 설정
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
            // Step 8: Fastlane 설정 - 별도 저장 없음
            break;
        case 9:
            // Step 9: 완료 - 별도 저장 없음
            break;
    }

    saveState();
}

// ============================================
// Command Generation Functions
// ============================================

function generateInitCommand() {
    // 경로 미입력 시 placeholder가 그대로 나가면 cd 실패로 이어진다.
    // 명령어를 감추는 대신 배너로 무엇을 채워야 하는지 알린다.
    const pathMissing = !state.projectPath;
    const projectPath = state.projectPath || '<<Step 1에서 프로젝트 절대경로를 입력하세요>>';
    const bundleId = state.bundleId || 'com.example.app';
    const teamId = state.teamId || 'TEAM_ID';
    const profileName = state.profileName || 'Profile Name';
    const usesNonExemptEncryption = state.encryptionType === 'standard' ? 'true' : 'false';

    const warning = document.getElementById('initCmd-warning');
    if (warning) {
        warning.classList.toggle('hidden', !pathMissing);
    }

    // 스크립트(.github/...)는 레포 루트 기준인데 pubspec.yaml은 Flutter 루트 기준이다.
    // 모노레포(예: repo/client/)에서는 두 위치가 달라, cd 지점을 레포 루트로 잡고
    // Flutter 루트는 인자로 따로 넘겨야 양쪽 다 해결된다.
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

    const cmd = `cd "${repoRoot}" && ${python} "${scriptPath}" setup "${projectPath}" "${bundleId}" "${teamId}" "${profileName}" "${usesNonExemptEncryption}"`;
    setElementText('initCmd', cmd);
}

function generateResults() {
    const secrets = [
        { key: 'APPLE_CERTIFICATE_BASE64', value: state.p12Base64, desc: 'Distribution 인증서 (.p12)' },
        { key: 'APPLE_CERTIFICATE_PASSWORD', value: state.p12Password, desc: '인증서 비밀번호' },
        { key: 'APPLE_PROVISIONING_PROFILE_BASE64', value: state.provisionBase64, desc: 'Provisioning Profile' },
        { key: 'IOS_PROVISIONING_PROFILE_NAME', value: state.profileName, desc: '프로파일 이름' },
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
                <button class="copy-btn-small" onclick="copyValue(this, '${s.key}')">복사</button>
            </div>
            <div class="value" id="value-${s.key}">${s.value || '(비어있음)'}</div>
        </div>
    `).join('');
}

function copyValue(btn, key) {
    const value = document.getElementById(`value-${key}`).textContent;
    if (value === '(비어있음)') {
        showToast('⚠️ 값이 비어있습니다');
        return;
    }

    navigator.clipboard.writeText(value).then(() => {
        btn.textContent = '복사됨!';
        btn.classList.add('copied');
        setTimeout(() => {
            btn.textContent = '복사';
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

    // 커스텀 Secrets 추가
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
    showToast('✅ JSON 파일 다운로드 완료!');
}

function downloadAsTxt() {
    const lines = [
        '# GitHub Secrets for iOS TestFlight Deployment',
        '# 생성일: ' + new Date().toLocaleString('ko-KR'),
        '',
        '===== GitHub Repository Secrets =====',
        '',
        'APPLE_CERTIFICATE_BASE64:',
        state.p12Base64 || '(미입력)',
        '',
        'APPLE_CERTIFICATE_PASSWORD:',
        state.p12Password || '(미입력)',
        '',
        'APPLE_PROVISIONING_PROFILE_BASE64:',
        state.provisionBase64 || '(미입력)',
        '',
        'IOS_PROVISIONING_PROFILE_NAME:',
        state.profileName || '(미입력)',
        '',
        'APP_STORE_CONNECT_API_KEY_BASE64:',
        state.p8Base64 || '(미입력)',
        '',
        'APP_STORE_CONNECT_API_KEY_ID:',
        state.apiKeyId || '(미입력)',
        '',
        'APP_STORE_CONNECT_ISSUER_ID:',
        state.issuerId || '(미입력)',
        '',
        'APPLE_TEAM_ID:',
        state.teamId || '(미입력)',
        '',
        'IOS_BUNDLE_ID:',
        state.bundleId || '(미입력)'
    ];

    // 커스텀 Secrets 추가
    if (state.customSecrets && state.customSecrets.length > 0) {
        lines.push('');
        lines.push('===== 사용자 추가 Secrets =====');
        lines.push('');
        state.customSecrets.forEach(cs => {
            if (cs.key && cs.value) {
                const typeLabel = cs.type === 'text' ? '[텍스트]' : '[Base64]';
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
    showToast('✅ TXT 파일 다운로드 완료!');
}

// ============================================
// Copy All Secrets to Clipboard
// ============================================

function copyAllSecrets() {
    const secrets = [
        { key: 'APPLE_CERTIFICATE_BASE64', value: state.p12Base64 },
        { key: 'APPLE_CERTIFICATE_PASSWORD', value: state.p12Password },
        { key: 'APPLE_PROVISIONING_PROFILE_BASE64', value: state.provisionBase64 },
        { key: 'IOS_PROVISIONING_PROFILE_NAME', value: state.profileName },
        { key: 'APP_STORE_CONNECT_API_KEY_BASE64', value: state.p8Base64 },
        { key: 'APP_STORE_CONNECT_API_KEY_ID', value: state.apiKeyId },
        { key: 'APP_STORE_CONNECT_ISSUER_ID', value: state.issuerId },
        { key: 'APPLE_TEAM_ID', value: state.teamId },
        { key: 'IOS_BUNDLE_ID', value: state.bundleId }
    ];

    // 커스텀 Secrets 추가
    if (state.customSecrets && state.customSecrets.length > 0) {
        state.customSecrets.forEach(cs => {
            if (cs.key && cs.value) {
                secrets.push({ key: cs.key, value: cs.value, type: cs.type });
            }
        });
    }

    // 설정된 값만 필터링
    const configuredSecrets = secrets.filter(s => s.value);

    if (configuredSecrets.length === 0) {
        showToast('⚠️ 복사할 설정값이 없습니다');
        return;
    }

    const lines = [
        '===== GitHub Secrets for iOS TestFlight =====',
        `생성일: ${new Date().toLocaleString('ko-KR')}`,
        `Bundle ID: ${state.bundleId || '(미설정)'}`,
        '',
        ...configuredSecrets.map(s => `${s.key}=${s.value}`),
        '',
        '============================================='
    ];

    const text = lines.join('\n');

    navigator.clipboard.writeText(text).then(() => {
        showToast(`✅ ${configuredSecrets.length}개 Secret 전체 복사 완료!`);
    }).catch(() => {
        showToast('❌ 클립보드 복사 실패');
    });
}

// ============================================
// ZIP Export Functions
// ============================================

function generateReadme() {
    return `# iOS TestFlight 배포 설정 백업

생성일: ${new Date().toLocaleString('ko-KR')}
Bundle ID: ${state.bundleId || '(미설정)'}
Team ID: ${state.teamId || '(미설정)'}

## 📁 파일 구조

\`\`\`
├── certificate.p12              # 배포 인증서 (Base64 디코딩됨)
├── provisioning.mobileprovision # 프로비저닝 프로파일 (Base64 디코딩됨)
├── api-key.p8                   # App Store Connect API Key (Base64 디코딩됨)
├── github-secrets/              # GitHub Secrets용 값들
│   ├── APPLE_CERTIFICATE_BASE64.txt
│   ├── APPLE_CERTIFICATE_PASSWORD.txt
│   ├── APPLE_PROVISIONING_PROFILE_BASE64.txt
│   ├── IOS_PROVISIONING_PROFILE_NAME.txt
│   ├── APP_STORE_CONNECT_API_KEY_BASE64.txt
│   ├── APP_STORE_CONNECT_API_KEY_ID.txt
│   ├── APP_STORE_CONNECT_ISSUER_ID.txt
│   ├── APPLE_TEAM_ID.txt
│   └── IOS_BUNDLE_ID.txt
└── README.md
\`\`\`

## 🔐 GitHub Secrets 등록 방법

1. GitHub 저장소 → Settings → Secrets and variables → Actions
2. \`github-secrets/\` 폴더 내 각 파일의 내용을 Secret으로 등록
3. Secret 이름은 파일명에서 .txt를 제외한 이름 사용

## ⚠️ 주의사항

- 이 파일들에는 민감한 정보가 포함되어 있습니다
- 안전한 장소에 보관하고, Git에 커밋하지 마세요
- 필요한 경우 암호화하여 보관하세요
`;
}

async function downloadAsZip() {
    // JSZip 로드 확인
    if (typeof JSZip === 'undefined') {
        showToast('❌ ZIP 라이브러리 로드 실패. 페이지를 새로고침해주세요.');
        return;
    }

    const zip = new JSZip();

    // 1. 실제 파일들 (Base64 디코딩)
    if (state.p12Base64) {
        try {
            const binaryString = atob(state.p12Base64);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            zip.file("certificate.p12", bytes);
        } catch (e) {
            console.error('P12 디코딩 실패:', e);
        }
    }

    if (state.provisionBase64) {
        try {
            const binaryString = atob(state.provisionBase64);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            zip.file("provisioning.mobileprovision", bytes);
        } catch (e) {
            console.error('Provisioning Profile 디코딩 실패:', e);
        }
    }

    if (state.p8Base64) {
        try {
            const p8Content = atob(state.p8Base64);
            zip.file("api-key.p8", p8Content);
        } catch (e) {
            console.error('P8 디코딩 실패:', e);
        }
    }

    // 2. 개별 Secret TXT 파일들 (github-secrets 폴더에)
    const secrets = [
        { name: 'APPLE_CERTIFICATE_BASE64.txt', value: state.p12Base64 },
        { name: 'APPLE_CERTIFICATE_PASSWORD.txt', value: state.p12Password },
        { name: 'APPLE_PROVISIONING_PROFILE_BASE64.txt', value: state.provisionBase64 },
        { name: 'IOS_PROVISIONING_PROFILE_NAME.txt', value: state.profileName },
        { name: 'APP_STORE_CONNECT_API_KEY_BASE64.txt', value: state.p8Base64 },
        { name: 'APP_STORE_CONNECT_API_KEY_ID.txt', value: state.apiKeyId },
        { name: 'APP_STORE_CONNECT_ISSUER_ID.txt', value: state.issuerId },
        { name: 'APPLE_TEAM_ID.txt', value: state.teamId },
        { name: 'IOS_BUNDLE_ID.txt', value: state.bundleId }
    ];

    // 커스텀 Secrets 추가
    if (state.customSecrets && state.customSecrets.length > 0) {
        state.customSecrets.forEach(cs => {
            if (cs.key && cs.value) {
                secrets.push({ name: `${cs.key}.txt`, value: cs.value });
            }
        });
    }

    const secretsFolder = zip.folder("github-secrets");
    let fileCount = 0;
    secrets.forEach(s => {
        if (s.value) {
            secretsFolder.file(s.name, s.value);
            fileCount++;
        }
    });

    // 파일이 하나도 없으면 경고
    if (fileCount === 0) {
        showToast('⚠️ 내보낼 설정값이 없습니다');
        return;
    }

    // 3. README.md 생성
    const readme = generateReadme();
    zip.file("README.md", readme);

    // 4. ZIP 다운로드
    try {
        const content = await zip.generateAsync({ type: "blob" });
        const url = URL.createObjectURL(content);
        const a = document.createElement('a');
        a.href = url;
        const bundleId = state.bundleId ? state.bundleId.replace(/\./g, '-') : 'ios-app';
        a.download = `testflight-secrets-${bundleId}-${getDateString()}.zip`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        showToast(`✅ ZIP 파일 다운로드 완료! (${fileCount}개 설정 포함)`);
    } catch (e) {
        console.error('ZIP 생성 실패:', e);
        showToast('❌ ZIP 파일 생성 실패');
    }
}

// ============================================
// Import from JSON
// ============================================

function importFromJson(event) {
    const file = event.target.files[0];
    if (!file) return;

    // 파일 확장자 확인
    if (!file.name.endsWith('.json')) {
        showToast('❌ JSON 파일만 업로드 가능합니다');
        event.target.value = '';
        return;
    }

    const reader = new FileReader();

    reader.onload = function(e) {
        try {
            const data = JSON.parse(e.target.result);

            // 유효성 검사 - 적어도 하나의 알려진 키가 있어야 함
            const knownKeys = [
                'APPLE_CERTIFICATE_BASE64',
                'APPLE_CERTIFICATE_PASSWORD',
                'APPLE_PROVISIONING_PROFILE_BASE64',
                'IOS_PROVISIONING_PROFILE_NAME',
                'APP_STORE_CONNECT_API_KEY_BASE64',
                'APP_STORE_CONNECT_API_KEY_ID',
                'APP_STORE_CONNECT_ISSUER_ID',
                'APPLE_TEAM_ID',
                'IOS_BUNDLE_ID'
            ];

            const hasValidKey = knownKeys.some(key => key in data);
            if (!hasValidKey) {
                showToast('❌ 올바른 iOS Secrets JSON 파일이 아닙니다');
                event.target.value = '';
                return;
            }

            // State에 값 매핑
            let importedCount = 0;

            if (data.APPLE_CERTIFICATE_BASE64) {
                state.p12Base64 = data.APPLE_CERTIFICATE_BASE64;
                importedCount++;
            }
            if (data.APPLE_CERTIFICATE_PASSWORD) {
                state.p12Password = data.APPLE_CERTIFICATE_PASSWORD;
                importedCount++;
            }
            if (data.APPLE_PROVISIONING_PROFILE_BASE64) {
                state.provisionBase64 = data.APPLE_PROVISIONING_PROFILE_BASE64;
                importedCount++;
            }
            if (data.IOS_PROVISIONING_PROFILE_NAME) {
                state.profileName = data.IOS_PROVISIONING_PROFILE_NAME;
                importedCount++;
            }
            if (data.APP_STORE_CONNECT_API_KEY_BASE64) {
                state.p8Base64 = data.APP_STORE_CONNECT_API_KEY_BASE64;
                importedCount++;
            }
            if (data.APP_STORE_CONNECT_API_KEY_ID) {
                state.apiKeyId = data.APP_STORE_CONNECT_API_KEY_ID;
                importedCount++;
            }
            if (data.APP_STORE_CONNECT_ISSUER_ID) {
                state.issuerId = data.APP_STORE_CONNECT_ISSUER_ID;
                importedCount++;
            }
            if (data.APPLE_TEAM_ID) {
                state.teamId = data.APPLE_TEAM_ID;
                importedCount++;
            }
            if (data.IOS_BUNDLE_ID) {
                state.bundleId = data.IOS_BUNDLE_ID;
                importedCount++;
            }

            // LocalStorage에 저장
            saveState();

            // 결과 테이블 갱신
            generateFinalResult();

            showToast(`✅ ${importedCount}개 설정값 가져오기 완료!`);

        } catch (error) {
            console.error('JSON 파싱 오류:', error);
            showToast('❌ JSON 파일 읽기 실패: 형식이 올바르지 않습니다');
        }

        // 파일 입력 초기화 (같은 파일 다시 선택 가능하도록)
        event.target.value = '';
    };

    reader.onerror = function() {
        showToast('❌ 파일 읽기 오류');
        event.target.value = '';
    };

    reader.readAsText(file);
}

// ============================================
// Secret Guide Modal Functions
// ============================================

const secretGuides = {
    certificate: {
        title: '📜 배포 인증서 (.p12) 생성 가이드',
        steps: [
            '1. Mac에서 "키체인 접근" 앱을 엽니다.',
            '2. "로그인" 키체인에서 "Apple Distribution" 인증서를 찾습니다.',
            '3. 인증서를 우클릭 → "내보내기"를 선택합니다.',
            '4. 파일 형식을 ".p12"로 선택합니다.',
            '5. 안전한 비밀번호를 설정합니다.',
            '6. 아래 명령어로 Base64 인코딩합니다:'
        ],
        commands: [
            'base64 -i ~/Desktop/Certificates.p12 | pbcopy',
            '# 클립보드에 복사됨'
        ]
    },
    profile: {
        title: '📋 프로비저닝 프로파일 생성 가이드',
        steps: [
            '1. Apple Developer Console 접속',
            '2. Certificates, Identifiers & Profiles → Profiles',
            '3. "App Store" Distribution 타입 선택',
            '4. 앱의 Bundle ID 선택',
            '5. Distribution Certificate 선택',
            '6. 프로파일 다운로드',
            '7. 아래 명령어로 Base64 인코딩:'
        ],
        commands: [
            'base64 -i ~/Downloads/YourProfile.mobileprovision | pbcopy'
        ]
    },
    apikey: {
        title: '🔑 App Store Connect API Key 생성 가이드',
        steps: [
            '1. App Store Connect 접속',
            '2. Users and Access → Keys 탭',
            '3. "+" 버튼으로 새 API Key 생성',
            '4. Access: "App Manager" 또는 "Admin" 선택',
            '5. Key ID 복사',
            '6. Issuer ID 복사 (상단에 표시됨)',
            '7. API Key 다운로드 (.p8 파일)',
            '8. 아래 명령어로 Base64 인코딩:'
        ],
        commands: [
            'base64 -i ~/Downloads/AuthKey_XXXXXX.p8 | pbcopy'
        ]
    }
};

function showSecretGuide(type) {
    const guide = secretGuides[type];
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
                    <button class="copy-btn absolute top-2 right-2 px-3 py-1 bg-slate-700 hover:bg-slate-600 rounded text-xs text-slate-300 transition" onclick="copyCode(this)">복사</button>
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
    // Team ID 대문자 자동 변환
    const teamIdInput = document.getElementById('teamId');
    if (teamIdInput) {
        teamIdInput.addEventListener('input', (e) => {
            e.target.value = e.target.value.toUpperCase();
        });
    }

    // ESC 키로 모달 닫기
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeGuideModal();
        }
    });

    // 입력 필드 변경 시 저장
    const inputIds = ['projectPath', 'bundleId', 'bundleId-confirm', 'teamId', 'profileName', 'profileName-confirm', 'appName', 'p12-password', 'api-key-id', 'issuer-id'];
    inputIds.forEach(id => {
        const input = document.getElementById(id);
        if (input) {
            input.addEventListener('change', saveState);
            input.addEventListener('blur', saveState);
        }
    });

    // Bundle ID 입력 시 실시간 동기화
    const bundleIdInput = document.getElementById('bundleId');
    if (bundleIdInput) {
        bundleIdInput.addEventListener('input', (e) => {
            state.bundleId = e.target.value.trim();
            const displayEl = document.getElementById('display-bundle-id');
            if (displayEl) displayEl.textContent = e.target.value.trim() || '(미입력)';
        });
    }

    // Profile Name 입력 시 실시간 동기화
    const profileNameInput = document.getElementById('profileName');
    if (profileNameInput) {
        profileNameInput.addEventListener('input', (e) => {
            state.profileName = e.target.value.trim();
            const displayEl = document.getElementById('display-profile-name');
            if (displayEl) displayEl.textContent = e.target.value.trim() || '(미입력)';
        });
    }

    // 암호화 설정 변경 시 저장
    document.querySelectorAll('input[name="encryptionType"]').forEach(radio => {
        radio.addEventListener('change', saveState);
    });
}

// ============================================
// Initialization
// ============================================

function initialize() {
    // 저장된 상태 로드
    const hasState = loadState();

    if (hasState) {
        showStep(state.currentStep);
        updateProgress();
        showToast('이전 진행 상태를 복원했습니다');
    } else {
        showStep(1);
        updateProgress();
    }

    setupInputHandlers();
    setupDragAndDrop();
    showSecurityWarning();
}

// DOM 로드 완료 시 초기화
document.addEventListener('DOMContentLoaded', initialize);

// 페이지 언로드 시 경고 (데이터 손실 방지)
window.addEventListener('beforeunload', (e) => {
    if (state.currentStep > 1 || state.bundleId || state.p12Base64) {
        e.preventDefault();
        e.returnValue = '입력한 데이터가 사라질 수 있습니다. 정말 나가시겠습니까?';
    }
});

// ============================================
// Changelog Modal Functions
// ============================================

// ESC 키로 changelog 모달도 닫기
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
        closeChangelogModal();
    }
});

// 페이지 로드 시 버전 배지 업데이트
document.addEventListener('DOMContentLoaded', () => {
    const data = getVersionData();
    if (data && data.version) {
        const versionBadge = document.getElementById('versionBadge');
        if (versionBadge) {
            versionBadge.textContent = `v${data.version}`;
        }
    }
});

// ============================================
// Custom Secrets Functions (파일 타입별 자동 처리)
// ============================================

// 텍스트 파일 확장자 (원본 그대로 저장 - cat <<EOF 로 사용)
const TEXT_EXTENSIONS = ['.json', '.yml', '.yaml', '.env', '.txt', '.xml', '.plist', '.properties', '.toml', '.ini', '.cfg', '.conf'];

// 바이너리 파일 확장자 (Base64 인코딩 - echo $SECRET | base64 -d 로 사용)
const BINARY_EXTENSIONS = ['.jks', '.keystore', '.p12', '.mobileprovision', '.p8', '.cer', '.pfx', '.pem', '.der', '.key', '.crt'];

/**
 * 파일을 타입에 따라 처리
 * @param {File} file 파일 객체
 * @returns {Promise<{value: string, type: 'text' | 'binary', hint: string}>}
 */
async function processFile(file) {
    const fileType = getFileType(file.name);

    if (fileType === 'text') {
        // 텍스트 파일: 원본 내용 그대로
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve({
                value: reader.result,
                type: 'text',
                hint: 'cat <<EOF > file 로 사용'
            });
            reader.onerror = reject;
            reader.readAsText(file);
        });
    } else {
        // 바이너리 파일: Base64 인코딩
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve({
                value: reader.result.split(',')[1],  // data URL에서 base64만 추출
                type: 'binary',
                hint: 'echo $SECRET | base64 -d > file 로 사용'
            });
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }
}

/**
 * 새 커스텀 Secret 슬롯 추가
 */
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

/**
 * 커스텀 Secret 삭제
 * @param {number} index 인덱스
 */
function removeCustomSecret(index) {
    state.customSecrets.splice(index, 1);
    renderCustomSecrets();
    saveState();
}

/**
 * 커스텀 Secret 키 이름 업데이트
 * @param {number} index 인덱스
 * @param {string} key 새 키 이름
 */
function updateCustomSecretKey(index, key) {
    if (state.customSecrets[index]) {
        state.customSecrets[index].key = key.toUpperCase().replace(/[^A-Z0-9_]/g, '_');
        saveState();
    }
}

/**
 * 커스텀 Secret 파일 업로드 처리
 * @param {number} index 인덱스
 * @param {File} file 파일 객체
 */
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

        // 키가 비어있으면 자동 생성된 키 사용
        if (!state.customSecrets[index].key) {
            state.customSecrets[index].key = suggestedKey;
        }

        renderCustomSecrets();
        saveState();
        showToast(`✅ ${file.name} 업로드 완료 (${result.type === 'text' ? '텍스트' : 'Base64'})`);
    } catch (error) {
        showToast('❌ 파일 읽기 실패: ' + error.message);
    }
}

/**
 * 커스텀 Secret 값 복사
 * @param {number} index 인덱스
 */
function copyCustomSecretValue(index) {
    const secret = state.customSecrets[index];
    if (secret && secret.value) {
        navigator.clipboard.writeText(secret.value).then(() => {
            showToast(`✅ ${secret.key} 값 복사됨`);
        }).catch(() => {
            showToast('❌ 클립보드 복사 실패');
        });
    }
}

/**
 * 커스텀 Secrets 목록 렌더링
 */
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
                    <button class="remove-secret-btn" onclick="removeCustomSecret(${index})">✕ 삭제</button>
                </div>

                <div class="mb-3">
                    <label class="block text-xs text-slate-400 mb-1">Secret 이름</label>
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
                        : `<div class="text-slate-400 text-sm">📁 파일 선택 또는 클릭</div>`
                    }
                </div>

                ${hasFile ? `
                    <div class="usage-hint">💡 ${escapeHtml(secret.hint)}</div>
                    <div class="flex justify-end mt-2">
                        <button class="copy-btn-small" onclick="copyCustomSecretValue(${index})">값 복사</button>
                    </div>
                ` : ''}
            </div>
        `;
    }).join('');
}

/**
 * 커스텀 Secrets를 기존 Secrets와 통합하여 반환
 * @returns {Array} 통합된 Secrets 배열
 */
function getCustomSecretsForExport() {
    return state.customSecrets
        .filter(cs => cs.key && cs.value)
        .map(cs => ({
            key: cs.key,
            value: cs.value,
            desc: `사용자 추가 (${cs.fileName})`,
            type: cs.type,
            hint: cs.hint
        }));
}
