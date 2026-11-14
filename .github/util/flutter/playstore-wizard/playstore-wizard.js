/**
 * Flutter Android Play Store all-in-one wizard
 * Includes file upload, Base64 conversion and localStorage progress saving
 */

// ============================================
// OS Detection
// ============================================

let detectedOS = 'mac'; // default: Mac

// ============================================
// State Management
// ============================================

/**
 * Wizard scripts (.github/util/...) are relative to the repo root,
 * but pubspec.yaml is relative to the Flutter root. In monorepos (repo/client, etc.)
 * the two differ, so the cd target and arguments must be separated.
 */
function getRepoRoot() {
    return state.repoRoot || state.projectPath || '/path/to/your/project';
}


/** Apply the repo root input to state + refresh commands (filled only for monorepos) */
function onRepoRootInput(el) {
    const v = (el.value || '').trim();
    state.repoRoot = v;
    saveState();
    if (typeof updateCommandsForOS === 'function') updateCommandsForOS();
}

const state = {
    currentStep: 1,
    maxReachedStep: 1, // highest step reached (kept when going back)
    totalSteps: 7, // Step 1~7 (project, Keystore, AAB build, app creation, AAB upload, Service Account, done)
    projectPath: '',
    repoRoot: '',      // monorepo: the repo root containing .github (empty = same as projectPath)
    detectedOS: 'mac', // OS detection result
    // Project Info
    applicationId: '',
    versionName: '',
    versionCode: '',
    gradleType: 'kts',
    // Keystore
    keyAlias: '',
    storePassword: '',
    keyPassword: '',
    keystoreBase64: '',
    validityDays: '99999', // default: unlimited
    // Certificate Info
    certCN: '',
    certO: '',
    certL: '',
    certC: 'KR',
    // Service Account
    serviceAccountBase64: '',
    // Optional
    googleServicesJson: '',
    envFileContent: '',
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

const STORAGE_KEY = 'flutter_playstore_wizard_state';
const STORAGE_WARNING_KEY = 'flutter_playstore_wizard_security_warning_dismissed';

function loadState() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            const savedState = JSON.parse(saved);
            // Keep the code's totalSteps (ignore cached values after a version upgrade)
            const currentTotalSteps = state.totalSteps;
            Object.assign(state, savedState);
            state.totalSteps = currentTotalSteps;
            
            // Always use the latest OS value (ignore the saved one)
            state.detectedOS = detectOS();

            // Correct currentStep if it exceeds totalSteps
            if (state.currentStep > state.totalSteps) {
                state.currentStep = state.totalSteps;
            }

            // Correct maxReachedStep if missing or invalid (compatibility with older versions)
            if (!state.maxReachedStep || state.maxReachedStep < state.currentStep) {
                state.maxReachedStep = state.currentStep;
            }
            if (state.maxReachedStep > state.totalSteps) {
                state.maxReachedStep = state.totalSteps;
            }

            restoreUIFromState();
            return true;
        }
    } catch (e) {
        console.warn('[playstore wizard] localStorage load failed:', e);
    }
    return false;
}

function restoreUIFromState() {
    // Restore input fields
    const inputs = {
        'projectPath': state.projectPath,
        'repoRoot': state.repoRoot,
        'applicationId': state.applicationId,
        'keyAlias': state.keyAlias,
        'storePassword': state.storePassword,
        'keyPassword': state.keyPassword,
        'certCN': state.certCN,
        'certO': state.certO,
        'certL': state.certL,
        'certC': state.certC,
        'envFileContent': state.envFileContent
    };

    Object.entries(inputs).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value) {
            el.value = value;
            // For projectPath, update the validation UI
            if (id === 'projectPath') {
                updatePathValidation(value);
            }
        }
    });
    
    // Restore the Application ID (show the detected value)
    if (state.applicationId) {
        const detectedContainer = document.getElementById('detectedApplicationIdContainer');
        const detectedValue = document.getElementById('detectedAppIdValue');
        if (detectedContainer && detectedValue) {
            detectedValue.textContent = state.applicationId;
            detectedContainer.classList.remove('hidden');
        }
    }
    
    // Restore the validity period
    if (state.validityDays) {
        const validitySelect = document.getElementById('validityDays');
        const validityCustom = document.getElementById('validityDaysCustom');
        if (validitySelect) {
            // Check whether the saved value is among the options
            const optionExists = Array.from(validitySelect.options).some(opt => opt.value === state.validityDays);
            if (optionExists) {
                validitySelect.value = state.validityDays;
            } else {
                // Custom value
                validitySelect.value = 'custom';
                if (validityCustom) {
                    validityCustom.classList.remove('hidden');
                    validityCustom.value = state.validityDays;
                }
            }
        }
    }

    // Restore file upload state
    if (state.keystoreBase64) {
        const upload = document.getElementById('keystoreUpload');
        if (upload) {
            upload.classList.add('has-file');
            const p = upload.querySelector('p');
            if (p) p.textContent = translate('step2.keystoreLoaded');
        }
        const result = document.getElementById('keystoreBase64Result');
        if (result) {
            result.classList.remove('hidden');
            const pre = document.getElementById('keystoreBase64');
            if (pre) pre.textContent = state.keystoreBase64;
        }
    }

    if (state.serviceAccountBase64) {
        const upload = document.getElementById('serviceAccountUpload');
        if (upload) {
            upload.classList.add('has-file');
            const p = upload.querySelector('p');
            if (p) p.textContent = translate('step6.serviceAccountLoaded');
        }
    }

    // Restore Project Info
    if (state.applicationId) {
        const detected = document.getElementById('detectedInfo');
        if (detected) detected.classList.remove('hidden');
        setElementText('detectedAppId', state.applicationId);
        setElementText('detectedVersion', state.versionName);
        setElementText('detectedVersionCode', state.versionCode);
        setElementText('detectedGradleType', state.gradleType);
    }

    // Restore custom Secrets (reset if not an array)
    if (!Array.isArray(state.customSecrets)) {
        state.customSecrets = [];
    }
    renderCustomSecrets();
}

// ============================================
// Security Warning
// ============================================

// ============================================
// File Upload & Base64 Conversion
// ============================================

// Keystore file upload
async function handleKeystoreUpload(input) {
    const file = input.files[0];
    if (!file) return;

    if (!file.name.endsWith('.jks') && !file.name.endsWith('.keystore')) {
        showToast(translate('step2.keystoreFileTypeOnly'));
        return;
    }

    try {
        state.keystoreBase64 = await fileToBase64(file);

        document.getElementById('keystoreBase64Result').classList.remove('hidden');
        document.getElementById('keystoreUpload').classList.add('has-file');
        document.getElementById('keystoreUpload').querySelector('p').textContent = `✅ ${file.name} (${(file.size/1024).toFixed(1)}KB)`;

        saveState();
        showToast(translate('step2.keystoreUploaded'));
    } catch (error) {
        showToast(translate('common.uploadFailed', { message: error.message }));
    }
}

// Service Account JSON upload
async function handleServiceAccountUpload(input) {
    const file = input.files[0];
    if (!file) return;

    if (!file.name.endsWith('.json')) {
        showToast(translate('step6.jsonFileOnly'));
        return;
    }

    try {
        const reader = new FileReader();
        reader.onload = function(e) {
            state.serviceAccountBase64 = btoa(e.target.result);

            document.getElementById('serviceAccountUpload').classList.add('has-file');
            document.getElementById('serviceAccountUpload').querySelector('p').textContent = `✅ ${file.name}`;

            saveState();
            showToast(translate('step6.serviceAccountUploaded'));
        };
        reader.readAsText(file);
    } catch (error) {
        showToast(translate('common.uploadFailed', { message: error.message }));
    }
}

// Copy the service account email
function copyServiceAccountEmail() {
    const emailInput = document.getElementById('serviceAccountEmail');
    const email = emailInput ? emailInput.value : '';

    if (email) {
        navigator.clipboard.writeText(email).then(() => {
            showToast(translate('step6.emailCopied'));
        }).catch(() => {
            // Fallback for older browsers
            emailInput.select();
            document.execCommand('copy');
            showToast(translate('step6.emailCopied'));
        });
    } else {
        showToast(translate('step6.enterEmailFirst'));
    }
}

// Step 3 email input → reflected in the Step 6 confirm popup automatically
function updateStep6Email() {
    const emailInput = document.getElementById('serviceAccountEmail');
    const step6Display = document.getElementById('step6EmailDisplay');

    if (emailInput && step6Display) {
        const email = emailInput.value;
        if (email && email.length > 0) {
            // Shorten an email that is too long
            const displayEmail = email.length > 25 ? email.substring(0, 22) + '...' : email;
            step6Display.textContent = displayEmail;
        } else {
            step6Display.textContent = 'your-bot@project.iam...';
        }
    }
}

// Google Services JSON upload
function handleGoogleServicesUpload(input) {
    const file = input.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = function(e) {
        state.googleServicesJson = e.target.result;
        document.getElementById('googleServicesResult').classList.remove('hidden');
        saveState();
        showToast(translate('step7.googleServicesUploaded'));
    };
    reader.readAsText(file);
}

// ============================================
// Path Input & Validation
// ============================================

function copyPathCommand() {
    const os = state.detectedOS;
    let command = '';
    
    if (os === 'windows') {
        command = '(pwd).Path';
    } else {
        command = 'pwd';
    }
    
    navigator.clipboard.writeText(command).then(() => {
        showToast(translate('step1.commandCopied', { command }));
    }).catch(() => {
        // Fallback
        const textarea = document.createElement('textarea');
        textarea.value = command;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        showToast(translate('step1.commandCopied', { command }));
    });
}

function validateProjectPath(path) {
    if (!path || path.trim() === '') {
        return { valid: false, message: '' };
    }
    
    // Ignore values starting with "선택된 폴더:" (folder picker placeholder)
    if (path.startsWith('선택된 폴더:')) {
        return { valid: false, message: translate('step1.enterRealAbsolutePath') };
    }
    
    // Validate the path format
    const isWindowsPath = /^[A-Za-z]:[\\/]/.test(path) || (path.includes('\\') && !path.startsWith('/'));
    const isUnixPath = path.startsWith('/');
    
    if (!isWindowsPath && !isUnixPath) {
        return { valid: false, message: translate('step1.invalidAbsolutePath') };
    }
    
    return { valid: true, message: '' };
}

function updatePathValidation(path) {
    const validationDiv = document.getElementById('pathValidation');
    const validationMessage = document.getElementById('pathValidationMessage');
    
    if (!validationDiv || !validationMessage) return;
    
    const validation = validateProjectPath(path);
    
    if (!path || path.trim() === '') {
        validationDiv.classList.add('hidden');
        return;
    }
    
    validationDiv.classList.remove('hidden');
    
    if (validation.valid) {
        validationMessage.textContent = translate('step1.validPathFormat');
        validationMessage.className = 'text-xs text-green-400';
    } else {
        validationMessage.textContent = `⚠️ ${validation.message}`;
        validationMessage.className = 'text-xs text-yellow-400';
    }
}

function updateProjectCommands(path) {
    // Save the path (valid paths only)
    if (path && !path.startsWith('선택된 폴더:')) {
        const validation = validateProjectPath(path);
        if (validation.valid) {
            state.projectPath = path;

            // ✅ Generate the Application ID auto-detect command
            generateApplicationIdDetectionCommand(path);
        }
    }

    // Update the path validation UI
    updatePathValidation(path);

    // Update commands for the OS
    updateCommandsForOS();
}

// ============================================
// Update OS-specific commands
// ============================================

function updateCommandsForOS() {
    const os = state.detectedOS;
    let projectPath = state.projectPath || '/path/to/your/project';
    
    // Normalize the path (invalid paths use the default)
    if (!projectPath || projectPath.startsWith('선택된 폴더:')) {
        projectPath = '/path/to/your/project';
    }
    
    // Validate the path
    const validation = validateProjectPath(projectPath);
    if (!validation.valid && projectPath !== '/path/to/your/project') {
        // Invalid paths use the default
        projectPath = '/path/to/your/project';
    }
    
    const macCommandEl = document.getElementById('macCommand');
    const windowsCommandEl = document.getElementById('windowsCommand');
    const macSection = macCommandEl?.closest('.mb-4');
    const windowsSection = windowsCommandEl?.closest('div:not(.mb-4)');
    
    if (os === 'windows') {
        // Windows only
        if (macSection) macSection.style.display = 'none';
        if (windowsSection) windowsSection.style.display = 'block';
        
        // Convert to a Windows path
        let winPath = projectPath;
        if (!winPath.includes('\\') && !/^[A-Za-z]:/.test(winPath)) {
            // Convert a Unix path to a Windows path
            winPath = winPath.replace(/\//g, '\\');
            if (winPath.startsWith('\\')) {
                // /Users/... -> C:\Users\...
                winPath = 'C:' + winPath;
            }
        } else {
            // Normalize an existing Windows path
            winPath = winPath.replace(/\//g, '\\');
        }
        
        if (windowsCommandEl) {
            windowsCommandEl.textContent = `cd "${toWinPath(getRepoRoot())}"; python .github\\util\\flutter\\playstore-wizard\\playstore-wizard.py setup`;
        }
        
        // Show the admin rights notice to Windows users
        const adminWarningEl = document.getElementById('adminWarningWindows');
        if (adminWarningEl) {
            adminWarningEl.classList.remove('hidden');
        }
    } else {
        // Hide the admin rights notice on Mac/Linux
        const adminWarningEl = document.getElementById('adminWarningWindows');
        if (adminWarningEl) {
            adminWarningEl.classList.add('hidden');
        }
        // Show for Mac/Linux
        if (macSection) macSection.style.display = 'block';
        if (windowsSection) windowsSection.style.display = 'none';
        
        // Convert to a Unix path (when a Windows path was entered)
        let unixPath = projectPath;
        if (unixPath.includes('\\') || /^[A-Za-z]:/.test(unixPath)) {
            // Convert a Windows path to a Unix path
            unixPath = unixPath.replace(/\\/g, '/').replace(/^([A-Za-z]):/, (_, drive) => '/' + drive.toLowerCase());
        }
        
        if (macCommandEl) {
            macCommandEl.textContent = `cd "${getRepoRoot()}" && python3 .github/util/flutter/playstore-wizard/playstore-wizard.py setup`;
        }
    }
}

function updateOSBadge() {
    const osBadge = document.getElementById('osBadge');
    const osName = document.getElementById('osName');
    
    if (osBadge && osName) {
        const os = state.detectedOS;
        const osNames = {
            'windows': 'Windows',
            'mac': 'macOS',
            'linux': 'Linux'
        };
        const osColors = {
            'windows': 'text-blue-400',
            'mac': 'text-green-400',
            'linux': 'text-purple-400'
        };
        osName.textContent = osNames[os] || 'Unknown';
        osName.className = `font-bold ${osColors[os] || 'text-slate-400'}`;
    }
}

// ============================================
// Clipboard Functions
// ============================================

function copySecret(name) {
    const value = state[name] || '';
    if (!value) {
        showToast(translate('secrets.valueEmpty'));
        return;
    }

    navigator.clipboard.writeText(value).then(() => {
        showToast(translate('secrets.copiedName', { name }));
    });
}

// ============================================
// Navigation Functions
// ============================================

function updateProgress() {
    $$('.step-indicator').forEach((indicator, index) => {
        const stepNum = index + 1;
        const circle = indicator.querySelector('.step-circle');
        const label = indicator.querySelector('span:last-child');

        if (stepNum === state.currentStep) {
            // Current step - blue-purple gradient
            circle.className = 'step-circle w-8 h-8 rounded-full bg-gradient-to-r from-blue-500 to-purple-500 text-white flex items-center justify-center font-bold text-xs z-10 shadow-lg shadow-blue-500/30';
            circle.innerHTML = stepNum;
            if (label) label.className = 'text-[9px] mt-1 text-blue-400 text-center hidden md:block';
        } else if (stepNum <= state.maxReachedStep) {
            // Visited step - green check
            circle.className = 'step-circle w-8 h-8 rounded-full bg-green-500 text-white flex items-center justify-center font-bold text-xs z-10 shadow-lg';
            circle.innerHTML = '✓';
            if (label) label.className = 'text-[9px] mt-1 text-green-400 text-center hidden md:block';
        } else {
            // Not yet visited step - gray
            circle.className = 'step-circle w-8 h-8 rounded-full bg-slate-700 text-slate-400 flex items-center justify-center font-bold text-xs z-10';
            circle.innerHTML = stepNum;
            if (label) label.className = 'text-[9px] mt-1 text-slate-500 text-center hidden md:block';
        }

        // Click to jump to that step
        indicator.style.cursor = 'pointer';
        indicator.onclick = () => goToStep(stepNum);
    });
}

function initializeStep(stepNumber) {
    switch (stepNumber) {
        case 1:
            // Step 1: project setup (path + Application ID)
            // Update the project path validation UI
            if (state.projectPath) {
                updatePathValidation(state.projectPath);
                // With a project path, generate the Application ID detect command automatically
                autoDetectApplicationIdOnPathInput();
            }

            // Restore the Application ID
            if (state.applicationId) {
                const detectedContainer = document.getElementById('detectedApplicationIdContainer');
                const detectedValue = document.getElementById('detectedAppIdValue');
                if (detectedContainer && detectedValue) {
                    detectedValue.textContent = state.applicationId;
                    detectedContainer.classList.remove('hidden');
                }
                // Fill the manual input field too (if present)
                const applicationIdInput = document.getElementById('applicationId');
                if (applicationIdInput) {
                    applicationIdInput.value = state.applicationId;
                }
            }
            break;
        case 2:
            // Step 2: Keystore creation
            restoreInputValues();
            // Generate the Key Alias automatically from the Application ID
            if (state.applicationId && !state.keyAlias) {
                const suggestedAlias = state.applicationId.split('.').pop() + '-release-key';
                const aliasInput = document.getElementById('keyAlias');
                if (aliasInput && !aliasInput.value) {
                    aliasInput.value = suggestedAlias;
                    state.keyAlias = suggestedAlias;
                }
            }
            // Make sure the validity dropdown is initialized
            const validitySelect = document.getElementById('validityDays');
            const validityCustom = document.getElementById('validityDaysCustom');
            if (validitySelect && !validitySelect.value) {
                validitySelect.value = '99999'; // default: unlimited
            }
            if (validityCustom && validitySelect.value !== 'custom') {
                validityCustom.classList.add('hidden');
            }
            // Generate the Keystore creation command automatically (always runs)
            setTimeout(() => {
                generateKeystoreCreationCommand();
            }, 100);
            break;
        case 3:
            // Step 3: AAB build
            // Show the file lock notice to Windows users
            if (state.detectedOS === 'windows') {
                const fileLockErrorEl = document.getElementById('fileLockErrorWindows');
                if (fileLockErrorEl) {
                    fileLockErrorEl.classList.remove('hidden');
                }
            } else {
                const fileLockErrorEl = document.getElementById('fileLockErrorWindows');
                if (fileLockErrorEl) {
                    fileLockErrorEl.classList.add('hidden');
                }
            }
            
            // Generate the AAB build command from the project path
            if (state.projectPath) {
                const aabBuildCommand = document.getElementById('aabBuildCommandStep3');
                const aabOutputPath = document.getElementById('aabOutputPathStep3');
                const aabCheckCommand = document.getElementById('aabCheckCommand');
                const projectPath = state.projectPath;
                const os = state.detectedOS || 'mac';

                if (aabBuildCommand) {
                    if (os === 'windows') {
                        const winPath = projectPath.replace(/\//g, '\\');
                        // Split each command onto its own line for sequential execution
                        // Multiple lines can be selected and run in PowerShell (Shift+Enter, or select and Enter)
                        // cd before each command to guarantee the working directory
                        aabBuildCommand.textContent = `cd "${winPath}"
cd "${winPath}"; flutter clean
cd "${winPath}"; flutter pub get
cd "${winPath}"; flutter build appbundle --release`;
                    } else {
                        aabBuildCommand.textContent = `cd "${projectPath}" && flutter clean && flutter pub get && flutter build appbundle --release`;
                    }
                }
                if (aabOutputPath) {
                    if (os === 'windows') {
                        const winPath = projectPath.replace(/\//g, '\\');
                        aabOutputPath.textContent = `${winPath}\\build\\app\\outputs\\bundle\\release\\app-release.aab`;
                    } else {
                        aabOutputPath.textContent = `${projectPath}/build/app/outputs/bundle/release/app-release.aab`;
                    }
                }
                if (aabCheckCommand) {
                    if (os === 'windows') {
                        const winPath = projectPath.replace(/\//g, '\\');
                        aabCheckCommand.textContent = `dir "${winPath}\\build\\app\\outputs\\bundle\\release\\"`;
                    } else {
                        aabCheckCommand.textContent = `ls -lah "${projectPath}/build/app/outputs/bundle/release/"`;
                    }
                }
            }
            break;
        case 4:
            // Step 4: create the app in Play Console
            // Extract the app name from the Application ID and show it
            if (state.applicationId) {
                const appName = state.applicationId.split('.').pop() || state.applicationId;
                // Convert camelCase/snake_case to a readable form (suh_devops_template -> SuhDevopsTemplate)
                const formattedName = appName
                    .split(/[_-]/)
                    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
                    .join('');
                const appNameDisplay = document.getElementById('appNameDisplay');
                if (appNameDisplay) {
                    appNameDisplay.textContent = formattedName;
                }
            }
            break;
        case 5:
            // Step 5: manual AAB upload
            // Show the AAB file path
            if (state.projectPath) {
                const aabUploadPath = document.getElementById('aabUploadPath');
                const projectPath = state.projectPath;
                if (aabUploadPath) {
                    const os = state.detectedOS || 'mac';
                    if (os === 'windows') {
                        const winPath = projectPath.replace(/\//g, '\\');
                        aabUploadPath.textContent = `${winPath}\\build\\app\\outputs\\bundle\\release\\app-release.aab`;
                    } else {
                        aabUploadPath.textContent = `${projectPath}/build/app/outputs/bundle/release/app-release.aab`;
                    }
                }
            }
            break;
        case 6:
            // Step 6: Service Account
            restoreInputValues();
            break;
        case 7:
            // Step 7: done
            generateFinalResult();
            break;
    }
}

function restoreInputValues() {
    const inputs = {
        'projectPath': state.projectPath,
        'repoRoot': state.repoRoot,
        'keyAlias': state.keyAlias,
        'storePassword': state.storePassword,
        'keyPassword': state.keyPassword,
        'certCN': state.certCN,
        'certO': state.certO,
        'certL': state.certL,
        'certC': state.certC,
        'envFileContent': state.envFileContent
    };

    Object.entries(inputs).forEach(([id, value]) => {
        const el = document.getElementById(id);
        if (el && value) el.value = value;
    });
    
    // Restore the validity period
    if (state.validityDays) {
        const validitySelect = document.getElementById('validityDays');
        const validityCustom = document.getElementById('validityDaysCustom');
        if (validitySelect) {
            // Check whether the saved value is among the options
            const optionExists = Array.from(validitySelect.options).some(opt => opt.value === state.validityDays);
            if (optionExists) {
                validitySelect.value = state.validityDays;
                if (validityCustom) {
                    validityCustom.classList.add('hidden');
                }
            } else {
                // Custom value
                validitySelect.value = 'custom';
                if (validityCustom) {
                    validityCustom.classList.remove('hidden');
                    validityCustom.value = state.validityDays;
                }
            }
        }
    }
}

function nextStep() {
    saveCurrentStepData();

    // Validate the Application ID when moving from Step 1 to Step 2
    if (state.currentStep === 1) {
        const applicationId = state.applicationId;
        if (!applicationId || applicationId.trim() === '') {
            showToast(translate('step1.detectApplicationIdFirst'));
            return;
        }

        // Validate the project path
        const projectPath = state.projectPath;
        if (!projectPath || projectPath.trim() === '') {
            showToast(translate('step1.enterProjectPathFirst'));
            return;
        }
    }

    if (state.currentStep < state.totalSteps) {
        state.currentStep++;
        // Update the highest step reached
        if (state.currentStep > state.maxReachedStep) {
            state.maxReachedStep = state.currentStep;
        }
        showStep(state.currentStep);
        updateProgress();
        saveState();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function goToStep(stepNumber) {
    // Ignore if it is the current step
    if (stepNumber === state.currentStep) return;

    // Range check
    if (stepNumber >= 1 && stepNumber <= state.totalSteps) {
        saveCurrentStepData();
        state.currentStep = stepNumber;
        showStep(state.currentStep);
        updateProgress();
        saveState();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

function resetWizard() {
    if (confirm(translate('reset.confirm'))) {
        // Reset state
        Object.keys(state).forEach(key => {
            if (key === 'currentStep') state[key] = 1;
            else if (key === 'maxReachedStep') state[key] = 1;
            else if (key === 'totalSteps') state[key] = 7;
            else if (key === 'certC') state[key] = 'KR';
            else if (key === 'gradleType') state[key] = 'kts';
            else if (key === 'validityDays') state[key] = '99999'; // unlimited by default
            else if (key === 'detectedOS') state[key] = detectOS(); // detect the OS again
            else state[key] = '';
        });

        // Clear localStorage completely
        try {
            localStorage.removeItem(STORAGE_KEY);
            localStorage.removeItem(STORAGE_WARNING_KEY);
            // Delete all related keys (just in case)
            Object.keys(localStorage).forEach(key => {
                if (key.startsWith('flutter_playstore_wizard')) {
                    localStorage.removeItem(key);
                }
            });
        } catch (e) {
            console.warn('[playstore wizard] localStorage clear failed:', e);
        }

        // Reset the UI
        const inputs = ['projectPath', 'repoRoot', 'applicationId', 'keyAlias', 'storePassword', 'keyPassword', 'certCN', 'certO', 'certL', 'certC', 'envFileContent', 'scriptOutput'];
        inputs.forEach(id => {
            const input = document.getElementById(id);
            if (input) {
                if (id === 'certC') {
                    input.value = 'KR';
                } else {
                    input.value = '';
                }
            }
        });
        
        // Restore the Application ID input placeholder
        const applicationIdInput = document.getElementById('applicationId');
        if (applicationIdInput) {
            applicationIdInput.placeholder = translate('step1.applicationIdPlaceholder');
        }
        
        // Reset the validity period
        const validitySelect = document.getElementById('validityDays');
        const validityCustom = document.getElementById('validityDaysCustom');
        if (validitySelect) {
            validitySelect.value = '99999'; // unlimited by default
        }
        if (validityCustom) {
            validityCustom.classList.add('hidden');
            validityCustom.value = '';
        }

        // Reset checkboxes
        document.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
            checkbox.checked = false;
        });

        // Reset file upload state
        document.querySelectorAll('.file-upload').forEach(el => {
            el.classList.remove('has-file');
        });
        renderUploadLabels();

        // Hide result areas
        document.querySelectorAll('[id$="Result"]').forEach(el => {
            el.classList.add('hidden');
        });
        
        // Hide detected info
        const detectedInfo = document.getElementById('detectedInfo');
        if (detectedInfo) {
            detectedInfo.classList.add('hidden');
        }

        // Update the OS badge
        updateOSBadge();
        updateCommandsForOS();

        showStep(1);
        updateProgress();
        showToast(translate('reset.done'));
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
}

// ============================================
// Data Management Functions
// ============================================

function saveCurrentStepData() {
    switch (state.currentStep) {
        case 1:
            const path = getInputValue('projectPath');
            const validation = validateProjectPath(path);
            if (validation.valid) {
                state.projectPath = path;
            } else {
                state.projectPath = '';
            }
            // Save the Application ID (detected or manually entered)
            const detectedAppId = document.getElementById('detectedAppIdValue')?.textContent?.trim();
            const manualAppId = getInputValue('applicationId');
            if (detectedAppId) {
                state.applicationId = detectedAppId;
            } else if (manualAppId && manualAppId.trim() !== '') {
                state.applicationId = manualAppId.trim();
            }
            break;
        case 2:
            state.keyAlias = getInputValue('keyAlias');
            state.storePassword = getInputValue('storePassword');
            state.keyPassword = getInputValue('keyPassword');
            state.certCN = getInputValue('certCN');
            state.certO = getInputValue('certO');
            state.certL = getInputValue('certL');
            state.certC = getInputValue('certC') || 'KR';
            // Save the validity period
            const validitySelect = document.getElementById('validityDays');
            if (validitySelect) {
                const validityValue = validitySelect.value;
                if (validityValue === 'custom') {
                    const customValue = getInputValue('validityDaysCustom');
                    state.validityDays = customValue || '99999';
                } else {
                    state.validityDays = validityValue;
                }
            }
            break;
        case 5:
            state.envFileContent = getInputValue('envFileContent');
            break;
    }

    saveState();
}

// ============================================
// Command Generation Functions
// ============================================

function generateSetupCommand() {
    const projectPath = state.projectPath || '/path/to/project';
    const applicationId = state.applicationId || 'com.example.app';
    const keyAlias = state.keyAlias || 'release-key';
    const storePassword = state.storePassword || 'changeit';
    const keyPassword = state.keyPassword || storePassword;
    const validityDays = state.validityDays || '99999';
    const certCN = state.certCN || 'Unknown';
    const certO = state.certO || 'Unknown';
    const certL = state.certL || 'Unknown';
    const certC = state.certC || 'KR';

    const os = state.detectedOS;
    let cmd = '';

    if (os === 'windows') {
        // Windows PowerShell command
        let winPath = projectPath;
        // Convert a Unix path to a Windows path
        if (!winPath.includes('\\') && !/^[A-Za-z]:/.test(winPath)) {
            winPath = winPath.replace(/\//g, '\\');
            if (winPath.startsWith('\\')) {
                winPath = 'C:' + winPath;
            }
        } else {
            winPath = winPath.replace(/\//g, '\\');
        }
        
        // Escape special characters for PowerShell
        const escapePowerShell = (str) => {
            return str.replace(/"/g, '`"').replace(/\$/g, '`$');
        };
        
        cmd = `cd "${toWinPath(getRepoRoot())}"; python .github\\util\\flutter\\playstore-wizard\\playstore-wizard.py setup "${escapePowerShell(winPath)}" "${escapePowerShell(applicationId)}" "${escapePowerShell(keyAlias)}" "${escapePowerShell(storePassword)}" "${escapePowerShell(keyPassword)}" "${validityDays}" "${escapePowerShell(certCN)}" "${escapePowerShell(certO)}" "${escapePowerShell(certL)}" "${certC}"`;
    } else {
        // Mac/Linux Bash command
        // Escape special characters
        const escapeBash = (str) => {
            return str.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\$/g, '\\$');
        };
        
        cmd = `cd "${getRepoRoot()}" && python3 .github/util/flutter/playstore-wizard/playstore-wizard.py setup "${escapeBash(projectPath)}" "${escapeBash(applicationId)}" "${escapeBash(keyAlias)}" "${escapeBash(storePassword)}" "${escapeBash(keyPassword)}" "${validityDays}" "${escapeBash(certCN)}" "${escapeBash(certO)}" "${escapeBash(certL)}" "${certC}"`;
    }

    const setupCmdEl = document.getElementById('setupCmd');
    if (setupCmdEl) {
        setupCmdEl.textContent = cmd;
    }
}

// ============================================
// Step 1: Application ID auto-detection (runs automatically on project path input)
// ============================================

function autoDetectApplicationIdOnPathInput() {
    const projectPath = getInputValue('projectPath');
    
    if (!projectPath || projectPath.trim() === '') {
        // Hide the command area when the path is empty
        const commandContainer = document.getElementById('detectAppIdCommandContainer');
        if (commandContainer) {
            const cmdEl = document.getElementById('detectAppIdCommand');
            if (cmdEl) {
                cmdEl.textContent = translate('step1.commandShownHere');
            }
        }
        return;
    }
    
    // Validate the path
    const validation = validateProjectPath(projectPath);
    if (!validation.valid) {
        return;
    }
    
    // Generate and show the command automatically
    generateApplicationIdDetectionCommand(projectPath);
}

function generateApplicationIdDetectionCommand(projectPath) {
    // Detect the OS
    const os = state.detectedOS || detectOS();
    const isWindows = os === 'windows';
    
    // Generate the command
    let cmd = '';
    if (isWindows) {
        const winPath = projectPath.replace(/\//g, '\\');
        const escapePowerShell = (str) => {
            return str.replace(/"/g, '`"').replace(/\$/g, '`$');
        };
        cmd = `cd "${toWinPath(getRepoRoot())}"; python .github\\util\\flutter\\playstore-wizard\\playstore-wizard.py detect-app-id "${escapePowerShell(winPath)}"`;
    } else {
        const escapeBash = (str) => {
            return str.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\$/g, '\\$');
        };
        cmd = `cd "${getRepoRoot()}" && python3 .github/util/flutter/playstore-wizard/playstore-wizard.py detect-app-id "${escapeBash(projectPath)}"`;
    }
    
    // Show the command
    const commandDisplay = document.getElementById('detectAppIdCommand');
    if (commandDisplay) {
        commandDisplay.textContent = cmd;
    }
    
    // Show the command container
    const commandContainer = document.getElementById('detectAppIdCommandContainer');
    if (commandContainer) {
        commandContainer.classList.remove('hidden');
    }
}

// Legacy function (kept for compatibility)
function detectApplicationId() {
    const projectPath = state.projectPath || getInputValue('projectPath');
    
    if (!projectPath || projectPath.trim() === '') {
        showToast(translate('step1.enterProjectPathFirst'));
        return;
    }
    
    // Validate the path
    const validation = validateProjectPath(projectPath);
    if (!validation.valid) {
        showToast(translate('step1.enterValidProjectPath'));
        return;
    }
    
    // Generate and show the command
    generateApplicationIdDetectionCommand(projectPath);
    showToast(translate('step1.copyAndRunCommand'));
}

function parseDetectedApplicationId() {
    const resultText = getInputValue('detectAppIdResult');
    
    if (!resultText || resultText.trim() === '') {
        showToast(translate('step1.pasteCommandOutput'));
        return;
    }
    
    try {
        // Try parsing JSON
        let jsonData;
        try {
            jsonData = JSON.parse(resultText.trim());
        } catch (e) {
            // Not JSON: try extracting only applicationId
            const match = resultText.match(/["']?applicationId["']?\s*:\s*["']([^"']+)["']/i);
            if (match) {
                jsonData = { applicationId: match[1] };
            } else {
                throw new Error('detect-app-id output is not JSON');
            }
        }
        
        if (jsonData.applicationId) {
            // Save to state
            state.applicationId = jsonData.applicationId;
            saveCurrentStepData();
            
            // Show the detected Application ID
            const detectedContainer = document.getElementById('detectedApplicationIdContainer');
            const detectedValue = document.getElementById('detectedAppIdValue');
            if (detectedContainer && detectedValue) {
                detectedValue.textContent = jsonData.applicationId;
                detectedContainer.classList.remove('hidden');
            }
            
            // Fill the manual input field too (if present)
            const applicationIdInput = document.getElementById('applicationId');
            if (applicationIdInput) {
                applicationIdInput.value = jsonData.applicationId;
            }
            
            // Reset the result input area
            const resultArea = document.getElementById('detectAppIdResult');
            if (resultArea) {
                resultArea.value = '';
            }
            
            showToast(translate('step1.applicationIdDetectedToast', { applicationId: jsonData.applicationId }));
        } else {
            showToast(translate('step1.applicationIdNotFound'));
            // Show the manual input option
            const manualContainer = document.getElementById('manualApplicationIdContainer');
            if (manualContainer) {
                manualContainer.classList.remove('hidden');
            }
        }
    } catch (e) {
        showToast(translate('step1.parseFailed'));
        console.error('Parse error:', e);
        // Show the manual input option
        const manualContainer = document.getElementById('manualApplicationIdContainer');
        if (manualContainer) {
            manualContainer.classList.remove('hidden');
        }
    }
}

// ============================================
// Step 1: Parse Project Info (legacy - kept for compatibility)
// ============================================

function parseProjectInfo() {
    const output = getInputValue('scriptOutput');

    if (!output) {
        // Manual entry fallback
        state.applicationId = 'com.example.app';
        state.versionName = '1.0.0';
        state.versionCode = '1';
        state.gradleType = 'kts';
    } else {
        try {
            const info = JSON.parse(output);
            state.applicationId = info.applicationId || 'com.example.app';
            state.versionName = info.versionName || '1.0.0';
            state.versionCode = info.versionCode?.toString() || '1';
            state.gradleType = info.gradleType || 'kts';
        } catch (e) {
            showToast(translate('step1.jsonParseFailed'));
            return;
        }
    }

    setElementText('detectedAppId', state.applicationId);
    setElementText('detectedVersion', state.versionName);
    setElementText('detectedVersionCode', state.versionCode);
    setElementText('detectedGradleType', state.gradleType);
    document.getElementById('detectedInfo').classList.remove('hidden');

    // Auto-generate key alias
    if (state.applicationId) {
        const suggestedAlias = state.applicationId.split('.').pop() + '-release-key';
        const aliasInput = document.getElementById('keyAlias');
        if (aliasInput && !aliasInput.value) {
            aliasInput.value = suggestedAlias;
            state.keyAlias = suggestedAlias;
        }
    }

    saveState();
    showToast(translate('step1.projectInfoParsed'));
}

// ============================================
// Step 2: generate the Keystore creation command (fully automatic)
// ============================================

function generateKeystoreCreationCommand() {
    const projectPath = state.projectPath || getInputValue('projectPath');
    const applicationId = state.applicationId || getInputValue('applicationId');
    const commandTextEl = document.getElementById('keystoreCreationCommandText');

    // Show a placeholder without a project path or Application ID
    if (!projectPath || projectPath.trim() === '') {
        if (commandTextEl) {
            commandTextEl.textContent = translate('step2.enterPathInStep1');
        }
        return;
    }

    if (!applicationId || applicationId.trim() === '') {
        if (commandTextEl) {
            commandTextEl.textContent = translate('step2.detectIdInStep1');
        }
        return;
    }
    
    // Get Keystore info
    let keyAlias = getInputValue('keyAlias') || applicationId.split('.').pop() + '-release-key';
    let storePassword = getInputValue('storePassword') || 'changeit';
    let keyPassword = getInputValue('keyPassword') || storePassword;
    let validityDays = getInputValue('validityDays') || '99999';
    
    // Handle a custom validity period
    if (validityDays === 'custom') {
        const customValidity = getInputValue('validityDaysCustom');
        if (customValidity && parseInt(customValidity) > 0) {
            validityDays = customValidity;
        } else {
            validityDays = '99999';
        }
    }
    
    const certCN = getInputValue('certCN') || 'Unknown';
    const certO = getInputValue('certO') || 'Unknown';
    const certL = getInputValue('certL') || 'Unknown';
    const certC = getInputValue('certC') || 'KR';
    
    // Detect the OS
    const os = state.detectedOS || detectOS();
    const isWindows = os === 'windows';
    
    // Generate the command
    let cmd = '';
    if (isWindows) {
        let winPath = projectPath.replace(/\//g, '\\');
        if (!winPath.match(/^[A-Z]:/)) {
            winPath = 'C:' + winPath;
        }
        
        const escapePowerShell = (str) => {
            return str.replace(/"/g, '`"').replace(/\$/g, '`$');
        };
        
        cmd = `cd "${toWinPath(getRepoRoot())}"; python .github\\util\\flutter\\playstore-wizard\\playstore-wizard.py setup "${escapePowerShell(winPath)}" "${escapePowerShell(applicationId)}" "${escapePowerShell(keyAlias)}" "${escapePowerShell(storePassword)}" "${escapePowerShell(keyPassword)}" "${validityDays}" "${escapePowerShell(certCN)}" "${escapePowerShell(certO)}" "${escapePowerShell(certL)}" "${certC}"`;
    } else {
        const escapeBash = (str) => {
            return str.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\$/g, '\\$');
        };
        
        cmd = `cd "${getRepoRoot()}" && python3 .github/util/flutter/playstore-wizard/playstore-wizard.py setup "${escapeBash(projectPath)}" "${escapeBash(applicationId)}" "${escapeBash(keyAlias)}" "${escapeBash(storePassword)}" "${escapeBash(keyPassword)}" "${validityDays}" "${escapeBash(certCN)}" "${escapeBash(certO)}" "${escapeBash(certL)}" "${certC}"`;
    }
    
    // Show the command (always visible, so no need to toggle hidden)
    if (commandTextEl) {
        commandTextEl.textContent = cmd;
    }
    
    // Fill the Key Alias automatically
    const keyAliasInput = document.getElementById('keyAlias');
    if (keyAliasInput && !keyAliasInput.value) {
        keyAliasInput.value = keyAlias;
        state.keyAlias = keyAlias;
    }
    
    // Save input values
    state.storePassword = storePassword;
    state.keyPassword = keyPassword;
    state.validityDays = validityDays;
    state.certCN = certCN;
    state.certO = certO;
    state.certL = certL;
    state.certC = certC;
    saveCurrentStepData();
    
    // Show only the command, without a toast
}

// ============================================
// Step 2: Keytool Command Generation (legacy - kept for compatibility)
// ============================================

function generateKeytoolCommand() {
    // Legacy function - no longer used but kept for compatibility
    // generateKeystoreCreationCommand() is what is actually used
    showToast(translate('step2.useGenerateButton'));
    generateKeystoreCreationCommand();
    return;
    
    // The code below is unused (kept for compatibility)
    const alias = getInputValue('keyAlias') || 'release-key';
    const storePass = getInputValue('storePassword') || 'changeit';
    const keyPass = getInputValue('keyPassword') || storePass;
    
    // Handle the validity period (from state or from the input field)
    let validity = state.validityDays || getInputValue('validityDays') || '99999';
    if (validity === 'custom') {
        // Use the custom value
        const customValidity = getInputValue('validityDaysCustom');
        if (customValidity && parseInt(customValidity) > 0) {
            validity = customValidity;
        } else {
            validity = '99999'; // fall back to the default
        }
    }

    const cn = getInputValue('certCN') || 'Unknown';
    const o = getInputValue('certO') || 'Unknown';
    const l = getInputValue('certL') || 'Unknown';
    const c = getInputValue('certC') || 'KR';

    state.keyAlias = alias;
    state.storePassword = storePass;
    state.keyPassword = keyPass;
    state.certCN = cn;
    state.certO = o;
    state.certL = l;
    state.certC = c;

    const dname = `CN=${cn}, O=${o}, L=${l}, C=${c}`;

    const command = `keytool -genkey -v \\
  -keystore release-key.jks \\
  -keyalg RSA \\
  -keysize 2048 \\
  -validity ${validity} \\
  -alias ${alias} \\
  -storepass "${storePass}" \\
  -keypass "${keyPass}" \\
  -dname "${dname}"`;

    setElementText('keytoolCommandText', command);
    document.getElementById('keytoolCommand').classList.remove('hidden');
    saveState();
}

// ============================================
// Step 4: Fastlane Content Generation
// ============================================

function generateFastfileContent() {
    const appId = state.applicationId || 'com.example.app';

    const fastfile = `# Play Store 내부 테스트 배포용 Fastfile
# 경로: android/fastlane/Fastfile.playstore

default_platform(:android)

platform :android do
  desc "Play Store 내부 테스트로 배포"
  lane :deploy_internal do
    # 환경 변수
    aab_path = ENV["AAB_PATH"] || "../build/app/outputs/bundle/release/app-release.aab"
    json_key = ENV["GOOGLE_PLAY_JSON_KEY"] || "~/.config/gcloud/service-account.json"

    puts "========================================="
    puts "Play Store 내부 테스트 배포 시작"
    puts "========================================="
    puts "AAB 경로: #{aab_path}"
    puts "Service Account: #{json_key}"

    # AAB 파일 확인
    unless File.exist?(aab_path)
      UI.user_error!("AAB 파일을 찾을 수 없습니다: #{aab_path}")
    end

    # Service Account 확인
    unless File.exist?(json_key)
      UI.user_error!("Service Account JSON을 찾을 수 없습니다: #{json_key}")
    end

    # Play Store 업로드
    upload_to_play_store(
      package_name: "${appId}",
      track: "internal",
      aab: aab_path,
      json_key: json_key,
      skip_upload_metadata: true,
      skip_upload_images: true,
      skip_upload_screenshots: true,
      release_status: "completed"
    )

    puts ""
    puts "========================================="
    puts "내부 테스트 배포 성공!"
    puts "========================================="
  end

  desc "Service Account JSON 검증"
  lane :validate do
    json_key = ENV["GOOGLE_PLAY_JSON_KEY"] || "~/.config/gcloud/service-account.json"

    validate_play_store_json_key(
      json_key: json_key
    )

    puts "Service Account 검증 성공!"
  end
end`;

    setElementText('fastfileContent', fastfile);
}

// ============================================
// Step 7: done and generate the GitHub Secrets list
// ============================================

function generateFinalResult() {
    const secrets = [
        { key: 'RELEASE_KEYSTORE_BASE64', value: state.keystoreBase64, desc: translate('secrets.keystoreDescription') },
        { key: 'RELEASE_KEYSTORE_PASSWORD', value: state.storePassword, desc: translate('secrets.keystorePasswordDescription') },
        { key: 'RELEASE_KEY_ALIAS', value: state.keyAlias, desc: translate('secrets.keyAliasDescription') },
        { key: 'RELEASE_KEY_PASSWORD', value: state.keyPassword, desc: translate('secrets.keyPasswordDescription') },
        { key: 'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64', value: state.serviceAccountBase64, desc: 'Service Account (Base64)' },
        { key: 'GOOGLE_SERVICES_JSON', value: state.googleServicesJson, desc: translate('secrets.googleServicesDescription') },
        { key: 'ENV_FILE', value: state.envFileContent, desc: translate('secrets.envFileDescription') }
    ];

    const tbody = document.getElementById('secretsTableBody');
    if (!tbody) return;

    tbody.innerHTML = secrets.map(s => {
        const hasValue = !!s.value;
        return `
            <tr>
                <td class="px-4 py-3">
                    <code class="text-blue-400">${s.key}</code>
                    <p class="text-xs text-slate-500 mt-1">${s.desc}</p>
                </td>
                <td class="px-4 py-3">
                    <span class="${hasValue ? 'text-green-400' : 'text-red-400'}">
                        ${hasValue ? translate('secrets.statusSet') : translate('secrets.statusNotSet')}
                    </span>
                </td>
                <td class="px-4 py-3 text-right">
                    <button
                        class="px-3 py-1 ${hasValue ? 'bg-blue-600 hover:bg-blue-700' : 'bg-slate-700 cursor-not-allowed'} rounded text-xs transition"
                        onclick="copySecretValue('${s.key}')"
                        ${!hasValue ? 'disabled' : ''}>
                        ${translate('shared.copy')}
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    // Generate .env file content
    generateEnvFileContent();
}

function generateEnvFileContent() {
    const envContent = `# ============================================
# Android Play Store 배포 설정
# ============================================

# Application ID
ANDROID_APPLICATION_ID=${state.applicationId || 'com.example.app'}

# Keystore 정보 (로컬 개발용)
ANDROID_KEY_ALIAS=${state.keyAlias || 'release-key'}
ANDROID_STORE_PASSWORD=${state.storePassword || 'YOUR_STORE_PASSWORD'}
ANDROID_KEY_PASSWORD=${state.keyPassword || 'YOUR_KEY_PASSWORD'}
ANDROID_KEYSTORE_PATH=android/app/keystore/key.jks

# 인증서 정보
ANDROID_CERT_CN=${state.certCN || 'Your Name'}
ANDROID_CERT_O=${state.certO || 'Your Organization'}
ANDROID_CERT_L=${state.certL || 'Your City'}
ANDROID_CERT_C=${state.certC || 'KR'}

# GitHub Secrets 정보 (참고용 - 실제로는 GitHub에 직접 등록)
# RELEASE_KEYSTORE_BASE64=<keystore file을 base64로 인코딩한 값>
# RELEASE_KEYSTORE_PASSWORD=${state.storePassword || 'YOUR_STORE_PASSWORD'}
# RELEASE_KEY_ALIAS=${state.keyAlias || 'release-key'}
# RELEASE_KEY_PASSWORD=${state.keyPassword || 'YOUR_KEY_PASSWORD'}
# GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64=<service account JSON을 base64로 인코딩한 값>
`;

    setElementText('envFileContent', envContent);
}

function copySecretValue(key) {
    const mapping = {
        'RELEASE_KEYSTORE_BASE64': state.keystoreBase64,
        'RELEASE_KEYSTORE_PASSWORD': state.storePassword,
        'RELEASE_KEY_ALIAS': state.keyAlias,
        'RELEASE_KEY_PASSWORD': state.keyPassword,
        'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64': state.serviceAccountBase64,
        'GOOGLE_SERVICES_JSON': state.googleServicesJson,
        'ENV_FILE': state.envFileContent
    };

    const value = mapping[key];
    if (!value) {
        showToast(translate('secrets.valueEmpty'));
        return;
    }

    navigator.clipboard.writeText(value).then(() => {
        showToast(translate('secrets.copiedName', { name: key }));
    });
}

// ============================================
// Changelog Modal Functions
// ============================================

// ============================================
// Input Event Handlers
// ============================================

function setupInputHandlers() {
    // Close the modal with the ESC key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            closeChangelogModal();
        }
    });

    // Save on input field change
    const inputIds = ['projectPath', 'repoRoot', 'keyAlias', 'storePassword', 'keyPassword', 'certCN', 'certO', 'certL', 'certC', 'envFileContent', 'scriptOutput'];
    inputIds.forEach(id => {
        const input = document.getElementById(id);
        if (input) {
            input.addEventListener('change', saveCurrentStepData);
            input.addEventListener('blur', saveCurrentStepData);
        }
    });
    
    // Validity dropdown handling
    const validitySelect = document.getElementById('validityDays');
    const validityCustom = document.getElementById('validityDaysCustom');
    if (validitySelect && validityCustom) {
        validitySelect.addEventListener('change', function() {
            if (this.value === 'custom') {
                validityCustom.classList.remove('hidden');
                validityCustom.focus();
            } else {
                validityCustom.classList.add('hidden');
            }
            saveCurrentStepData();
        });
        
        validityCustom.addEventListener('input', saveCurrentStepData);
        validityCustom.addEventListener('blur', saveCurrentStepData);
    }

    // Live validation on projectPath input and automatic Application ID detect command generation
    const projectPathInput = document.getElementById('projectPath');
    if (projectPathInput) {
        projectPathInput.addEventListener('input', function() {
            const path = this.value.trim();
            updateProjectCommands(path);
            // Generate the Application ID auto-detect command
            autoDetectApplicationIdOnPathInput();
            saveCurrentStepData();
        });

        projectPathInput.addEventListener('blur', function() {
            const path = this.value.trim();
            updateProjectCommands(path);
            // Generate the Application ID auto-detect command
            autoDetectApplicationIdOnPathInput();
            saveCurrentStepData();
        });

        projectPathInput.addEventListener('paste', function(e) {
            // Validate after paste
            setTimeout(() => {
                const path = this.value.trim();
                updateProjectCommands(path);
                // Generate the Application ID auto-detect command
                autoDetectApplicationIdOnPathInput();
                saveCurrentStepData();
            }, 10);
        });
    }
    
    // Save on applicationId input and update the auto-detect command
    const applicationIdInput = document.getElementById('applicationId');
    if (applicationIdInput) {
        applicationIdInput.addEventListener('input', () => {
            saveCurrentStepData();
            // Update the command if the auto-detect command container is visible
            const detectContainer = document.getElementById('detectAppIdCommandContainer');
            if (detectContainer && !detectContainer.classList.contains('hidden')) {
                detectApplicationId();
            }
        });
        applicationIdInput.addEventListener('blur', saveCurrentStepData);
    }
    
    // Step 2: generate the command automatically when Keystore info is entered
    const keystoreInputs = ['keyAlias', 'storePassword', 'keyPassword', 'validityDays', 'certCN', 'certO', 'certL', 'certC'];
    keystoreInputs.forEach(inputId => {
        const input = document.getElementById(inputId);
        if (input) {
            input.addEventListener('input', () => {
                saveCurrentStepData();
                // Update the command automatically while on Step 2
                if (state.currentStep === 2) {
                    generateKeystoreCreationCommand();
                }
            });
            input.addEventListener('change', () => {
                saveCurrentStepData();
                if (state.currentStep === 2) {
                    generateKeystoreCreationCommand();
                }
            });
        }
    });
    
    // Custom validity input field
    const validityCustomInput = document.getElementById('validityDaysCustom');
    if (validityCustomInput) {
        validityCustomInput.addEventListener('input', () => {
            saveCurrentStepData();
            if (state.currentStep === 2) {
                generateKeystoreCreationCommand();
            }
        });
    }
}

// ============================================
// Initialization
// ============================================

function initialize() {
    // Detect the OS
    state.detectedOS = detectOS();
    
    // Load saved state
    const hasState = loadState();
    
    // Always use the latest OS value
    state.detectedOS = detectOS();

    if (hasState) {
        showStep(state.currentStep);
        updateProgress();
        showToast(translate('page.stateRestored'));
    } else {
        showStep(1);
        updateProgress();
    }

    // Update the OS badge and commands
    updateOSBadge();
    updateCommandsForOS();
    
    // Update the validation UI if a path is saved
    if (state.projectPath) {
        updatePathValidation(state.projectPath);
    }

    setupInputHandlers();
    setupDragAndDrop();
    showSecurityWarning();
    renderLanguageDependentText();

    // Update the version badge
    const data = getVersionData();
    if (data && data.version) {
        const versionBadge = document.getElementById('versionBadge');
        if (versionBadge) {
            versionBadge.textContent = `v${data.version}`;
        }
    }
}

// Initialize when the DOM is loaded
document.addEventListener('DOMContentLoaded', initialize);

// ============================================
// Language switch (#769)
// ============================================

/** Upload area text: loaded if a file exists, otherwise a prompt to select */
function renderUploadLabels() {
    const keystoreLabel = document.getElementById('keystoreUpload')?.querySelector('p');
    if (keystoreLabel) {
        keystoreLabel.textContent = state.keystoreBase64 ? translate('step2.keystoreLoaded') : translate('step2.keystoreDropPrompt');
    }
    const serviceAccountLabel = document.getElementById('serviceAccountUpload')?.querySelector('p');
    if (serviceAccountLabel) {
        serviceAccountLabel.textContent = state.serviceAccountBase64
            ? translate('step6.serviceAccountLoaded')
            : translate('step6.serviceAccountDropPrompt');
    }
}

/** Text filled by JS (upload prompt, command placeholder before a path is entered) */
function renderLanguageDependentText() {
    renderUploadLabels();
    // With a path, step initialization fills it with the real command
    if (!state.projectPath) {
        setElementText('detectAppIdCommand', translate('step1.commandPlaceholder'));
        setElementText('aabBuildCommandStep3', translate('step3.commandPlaceholder'));
        setElementText('aabCheckCommand', translate('step3.commandPlaceholder'));
        setElementText('aabOutputPathStep3', translate('step3.outputPathPlaceholder'));
        setElementText('aabUploadPath', translate('step3.outputPathPlaceholder'));
    }
}

// The engine swaps static text; dynamic areas (current step, custom Secrets, path validation) are redrawn here
document.addEventListener('wizardlanguagechange', () => {
    renderLanguageDependentText();
    showStep(state.currentStep);
    updateProgress();
    renderCustomSecrets();
    if (state.projectPath) updatePathValidation(state.projectPath);
});

// Warn on page unload (prevents data loss)
window.addEventListener('beforeunload', (e) => {
    if (state.currentStep > 1 || state.keystoreBase64 || state.serviceAccountBase64) {
        e.preventDefault();
        e.returnValue = translate('page.leaveWarning');
    }
});
