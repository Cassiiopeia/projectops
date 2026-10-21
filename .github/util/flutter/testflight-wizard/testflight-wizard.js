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
        console.warn('[testflight state] localStorage load failed:', e);
    }
    return false;
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

    // 커스텀 Secrets 복원
    if (state.customSecrets && state.customSecrets.length > 0) {
        renderCustomSecrets();
    }
}

// ============================================
// Security Warning
// ============================================

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

// .p12 파일 업로드
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

// .mobileprovision 파일 업로드
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

// .p8 파일 업로드
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

        // 파일명에서 Key ID 자동 추출
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

            // 브라우저는 보안상 절대경로를 주지 않는다 (폴더명만 얻을 수 있음).
            // 입력칸에 안내문을 써넣으면 실제 경로를 덮어써 폴백(/path/to/project)이 나가므로,
            // 입력칸은 건드리지 않고 힌트 영역에만 폴더명을 표시한다.
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

        // UI 초기화
        const inputs = ['projectPath', 'repoRoot', 'bundleId', 'bundleId-confirm', 'teamId', 'profileName', 'profileName-confirm', 'appName', 'p12-password', 'api-key-id', 'issuer-id'];
        inputs.forEach(id => {
            const input = document.getElementById(id);
            if (input) input.value = '';
        });

        // Display 요소 초기화
        const displayBundleId = document.getElementById('display-bundle-id');
        if (displayBundleId) displayBundleId.textContent = translate('value.notEntered');
        const displayProfileName = document.getElementById('display-profile-name');
        if (displayProfileName) displayProfileName.textContent = translate('value.notEntered');

        // 파일 업로드 상태 초기화
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
            // Step 1: 시작하기 - 프로젝트 경로
            state.projectPath = getInputValue('projectPath');
            // 구버전이 입력칸에 써넣던 안내문이 남아 있으면 경로로 쓰지 않는다
            if (state.projectPath.startsWith('선택된 폴더:')) {
                state.projectPath = '';
            }
            // 상대경로는 Step 8 명령어에서 cd 실패로 이어지므로 미리 걸러낸다
            if (state.projectPath && !isAbsolutePath(state.projectPath)) {
                showToast(translate('step1.absolutePathRequired'));
                state.projectPath = '';
            }
            // 모노레포에서만 채우는 선택 입력 — 비어 있으면 Flutter 루트를 그대로 쓴다
            state.repoRoot = getInputValue('repoRoot');
            if (state.repoRoot && !isAbsolutePath(state.repoRoot)) {
                showToast(translate('step1.repoRootAbsoluteRequired'));
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
    const projectPath = state.projectPath || translate('step8.projectPathPlaceholder');
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

    // 커스텀 Secrets 추가
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

/** 가이드 문구 — 언어 전환 반영 위해 열 때마다 조립 */
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
            if (displayEl) displayEl.textContent = e.target.value.trim() || translate('value.notEntered');
        });
    }

    // Profile Name 입력 시 실시간 동기화
    const profileNameInput = document.getElementById('profileName');
    if (profileNameInput) {
        profileNameInput.addEventListener('input', (e) => {
            state.profileName = e.target.value.trim();
            const displayEl = document.getElementById('display-profile-name');
            if (displayEl) displayEl.textContent = e.target.value.trim() || translate('value.notEntered');
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
        showToast(translate('nav.restored'));
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

/** 내보내기 날짜 표기 — ko 는 기존 출력과 같게 ko-KR */
function getExportDateLocale() {
    return getWizardLanguage() === 'ko' ? 'ko-KR' : 'en-US';
}

/** 미입력 표시칸 — 이미 미입력 문구(en·ko)를 보이는 칸만 현재 언어로 (예시 값은 유지) */
function refreshNotEnteredLabels() {
    const notEnteredTexts = ['(not entered)', '(미입력)'];
    ['display-bundle-id', 'display-profile-name'].forEach((id) => {
        const element = document.getElementById(id);
        if (element && notEnteredTexts.includes(element.textContent)) {
            element.textContent = translate('value.notEntered');
        }
    });
}

// 언어 전환: JS 가 그린 영역(현재 단계·커스텀 Secret·Team ID 경고) 다시 그리기
document.addEventListener('wizardlanguagechange', () => {
    showStep(state.currentStep);
    renderCustomSecrets();
    refreshNotEnteredLabels();
    const teamIdInput = document.getElementById('teamId');
    if (teamIdInput) validateTeamId(teamIdInput);
});

// 페이지 언로드 시 경고 (데이터 손실 방지)
window.addEventListener('beforeunload', (e) => {
    if (state.currentStep > 1 || state.bundleId || state.p12Base64) {
        e.preventDefault();
        e.returnValue = translate('nav.leaveWarning');
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
