/**
 * OAuth 마법사 단계 화면 렌더 + Firebase 설정 파일 읽기 (분할 파일 — 함수 선언만)
 * 상태·흐름은 oauth-wizard.js, 산출물 문자열은 oauth-wizard-snippets.js
 */

/* eslint-disable no-unused-vars */

// ============================================
// 단계별 렌더
// ============================================

/** 공통 showStep 이 단계 표시 직후 부른다 */
function initializeStep(stepNumber) {
    state.currentStepId = getStepIdByNumber(stepNumber);
    renderStepContent(state.currentStepId);
}

function renderStepContent(stepId) {
    applyConditionalVisibility();
    renderOperatingSystemTabs();
    switch (stepId) {
        case 'providers': renderProvidersStep(); break;
        case 'identity': renderIdentityStep(); break;
        case 'fingerprints': renderFingerprintsStep(); break;
        case 'kakao': renderKakaoStep(); break;
        case 'google': renderGoogleStep(); break;
        case 'secrets': renderSecretsStep(); break;
        case 'cicd': renderCicdStep(); break;
        case 'gitignore': renderGitignoreStep(); break;
        case 'apply': renderApplyStep(); break;
        default: renderSummaryStep();
    }
}

function renderProvidersStep() {
    ['kakao', 'google'].forEach((provider) => {
        const suffix = provider === 'kakao' ? 'Kakao' : 'Google';
        const input = document.getElementById(`provider${suffix}`);
        if (input) input.checked = state.providers[provider];
        const card = document.getElementById(`providerCard${suffix}`);
        if (card) card.classList.toggle('selected', state.providers[provider]);
    });
}

function renderIdentityStep() {
    setInputValue('applicationIdInput', state.applicationId);
    setInputValue('bundleIdInput', state.bundleId);
    setInputValue('projectPathInput', state.projectPath === '.' ? '' : state.projectPath);
    setPreText('detectCommand', buildDetectCommand(state.operatingSystem, state.projectPath));
}

function renderFingerprintsStep() {
    const commands = buildKeytoolCommands(state.operatingSystem);
    setPreText('keytoolDebugCommand', commands.debug);
    setPreText('keytoolUploadCommand', commands.upload);
    setPreText('fingerprintCliCommand', `${commands.cliDebug}\n${commands.cliUpload}`);
    ['debugSha1', 'uploadSha1', 'playSigningSha1'].forEach((field) => {
        setInputValue(`${field}Input`, state[field]);
        const value = state[field];
        let message = '';
        if (value && !isValidSha1(value)) message = translate('fingerprints.invalid');
        else if (value) message = translate('fingerprints.keyHash', { keyHash: sha1ToKakaoKeyHash(value) });
        setElementText(`${field}Hash`, message);
    });
}

function renderKakaoStep() {
    setInputValue('kakaoNativeAppKeyInput', state.kakaoNativeAppKey);
    const status = document.getElementById('kakaoKeyStatus');
    if (status) {
        const isValid = isValidKakaoNativeAppKey(state.kakaoNativeAppKey);
        status.textContent = state.kakaoNativeAppKey ? (isValid ? translate('kakao.keyValid') : translate('kakao.keyInvalid')) : '';
        status.className = `text-xs mt-1 ${isValid ? 'text-green-400' : 'text-red-400'}`;
    }
    setElementText('kakaoPackageName', state.applicationId || translate('value.notEntered'));
    setElementText('kakaoBundleId', state.bundleId || translate('value.notEntered'));
    const entries = collectFingerprintEntries();
    setPreText('kakaoKeyHashList', entries.length ? entries.map((entry) => entry.keyHash).join('\n') : translate('value.noFingerprints'));
    setPreText('kakaoManifestSnippet', buildKakaoManifestSnippet(state.kakaoNativeAppKey));
    setPreText('kakaoPlistSnippet', buildKakaoPlistSnippet(state.kakaoNativeAppKey));
    setPreText('kakaoDartSnippet', buildKakaoDartSnippet(state.kakaoNativeAppKey));
}

function renderGoogleStep() {
    $$('input[name="googleSetup"]').forEach((radio) => { radio.checked = radio.value === state.googleSetup; });
    setElementText('googlePackageName', state.applicationId || translate('value.notEntered'));
    setElementText('googleBundleId', state.bundleId || translate('value.notEntered'));
    const entries = collectFingerprintEntries();
    setPreText('googleSha1List', entries.length ? entries.map((entry) => entry.sha1).join('\n') : translate('value.noFingerprints'));
    setElementText('googleServicesStatus', state.googleServicesFileName ? `✅ ${state.googleServicesFileName}` : translate('upload.dropHint'));
    setElementText('googleServiceInfoStatus', state.googleServiceInfoFileName ? `✅ ${state.googleServiceInfoFileName}` : translate('upload.dropHint'));
    renderGoogleFileChecks();
    setInputValue('googleIosClientIdInput', state.googleIosClientId);
    setInputValue('googleServerClientIdInput', state.googleServerClientId);
    setPreText('googlePlistSnippet', buildGooglePlistSnippet(state.googleIosClientId, state.googleServerClientId));
    setPreText('googleDartSnippet', buildGoogleDartSnippet(state.googleServerClientId));
}

function renderSecretsStep() {
    setInputValue('repoOwnerInput', state.repoOwner);
    setInputValue('repoNameInput', state.repoName);
    const link = document.getElementById('secretsPageLink');
    if (link) {
        link.href = state.repoOwner && state.repoName
            ? `https://github.com/${encodeURIComponent(state.repoOwner)}/${encodeURIComponent(state.repoName)}/settings/secrets/actions`
            : 'https://github.com';
    }
    renderSecretsTable();
    renderCustomSecrets();
}

function renderSecretsTable() {
    const tbody = document.getElementById('secretsTableBody');
    if (!tbody) return;
    const secrets = buildSecretsList();
    if (secrets.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="py-3 px-2 text-green-400">${translate('secrets.noneNeeded')}</td></tr>`;
        return;
    }
    tbody.innerHTML = secrets.map((secret) => `
        <tr class="border-b border-slate-700/50">
            <td class="py-2 px-2 font-mono text-yellow-400">${escapeHtml(secret.key)}</td>
            <td class="py-2 px-2 text-slate-400">${secret.value ? escapeHtml(secret.source) : `<span class="text-red-400">${translate('secrets.notUploaded')}</span>`}</td>
            <td class="py-2 px-2 text-slate-400">${escapeHtml(secret.usedBy)}</td>
            <td class="py-2 px-2 text-right">${secret.value ? `<button class="copy-btn-small" onclick="copySecretValue('${escapeJsString(secret.key)}')">${translate('secrets.copyValue')}</button>` : ''}</td>
        </tr>`).join('');
}

function renderCicdStep() {
    const isWithFiles = isUsingFirebaseFiles();
    const rows = [
        ...ANDROID_WORKFLOWS.map((name) => [name, isWithFiles ? translate('cicd.rowAndroidSecret') : translate('cicd.rowNoChange')]),
        ...IOS_WORKFLOWS.map((name) => [name, isWithFiles ? translate('cicd.rowIosSecret') : translate('cicd.rowNoChange')]),
        ['PROJECT-FLUTTER-CI', isWithFiles ? translate('cicd.rowFlutterCiSecret') : translate('cicd.rowNoChange')],
        ['PROJECT-FLUTTER-PROJECTOPS-APP-BUILD-TRIGGER', translate('cicd.rowTrigger')],
    ];
    setElementHtml('cicdTableBody', rows.map(([name, change]) => `
        <tr class="border-b border-slate-700/50">
            <td class="py-2 px-2 font-mono">${escapeHtml(name)}.yaml</td>
            <td class="py-2 px-2">${change}</td>
        </tr>`).join(''));
    setPreText('builtInRestoreSteps', buildBuiltInRestoreStepsReference());
    setPreText('templateCheckCommand', buildTemplateCheckCommand(state.operatingSystem));
    setPreText('fallbackIosRestoreStep', buildFallbackIosRestoreStep());
}

function renderGitignoreStep() {
    setPreText('gitignoreSnippet', buildGitignoreSnippet(isUsingFirebaseFiles()));
    setPreText('untrackCommand', buildUntrackCommand());
    const checkbox = document.getElementById('updateGitignoreInput');
    if (checkbox) checkbox.checked = state.updateGitignore;
}

function buildSetupOptions(isDryRun) {
    return {
        projectPath: state.projectPath,
        useKakao: state.providers.kakao,
        kakaoNativeAppKey: state.kakaoNativeAppKey,
        useGoogle: state.providers.google,
        googleIosClientId: state.googleIosClientId,
        googleServerClientId: state.googleServerClientId,
        updateGitignore: state.updateGitignore,
        includeFirebaseFiles: isUsingFirebaseFiles(),
        isDryRun,
    };
}

function buildPubAddCommand() {
    const packages = [];
    if (state.providers.kakao) packages.push('kakao_flutter_sdk_user');
    if (state.providers.google) packages.push('google_sign_in');
    return `flutter pub add ${packages.join(' ')}`;
}

function renderApplyStep() {
    setPreText('setupDryRunCommand', buildSetupCommand(state.operatingSystem, buildSetupOptions(true)));
    setPreText('setupCommand', buildSetupCommand(state.operatingSystem, buildSetupOptions(false)));
    setPreText('pubAddCommand', buildPubAddCommand());
}

/** 최종 점검 항목 — 선택에 따라 달라진다 (문구 키는 문자열 그대로) */
function buildChecklistItems() {
    const items = [];
    if (state.providers.kakao) {
        items.push(['kakaoConsole', translate('checklist.kakaoConsole')]);
        items.push(['kakaoKeyHashes', translate('checklist.kakaoKeyHashes')]);
    }
    if (state.providers.google) {
        items.push(['googleClients', translate('checklist.googleClients')]);
    }
    if (isUsingFirebaseFiles()) {
        items.push(['secretsRegistered', translate('checklist.secretsRegistered')]);
        items.push(['templateUpToDate', translate('checklist.templateUpToDate')]);
        items.push(['xcodeTarget', translate('checklist.xcodeTarget')]);
    }
    items.push(['setupApplied', translate('checklist.setupApplied')]);
    items.push(['dartCode', translate('checklist.dartCode')]);
    items.push(['gitignore', translate('checklist.gitignore')]);
    items.push(['mergedToMain', translate('checklist.mergedToMain')]);
    items.push(['playSigning', translate('checklist.playSigning')]);
    items.push(['testBuildLogin', translate('checklist.testBuildLogin')]);
    return items;
}

function renderSummaryStep() {
    setElementHtml('summaryChecklist', buildChecklistItems().map(([itemId, text]) => `
        <label class="flex items-start gap-2">
            <input type="checkbox" class="mt-1" ${state.checklist[itemId] ? 'checked' : ''} onchange="onChecklistToggle('${itemId}', this.checked)">
            <span>${text}</span>
        </label>`).join(''));

    const yes = translate('summary.inGit');
    const no = translate('summary.notInGit');
    const rows = [];
    if (state.providers.kakao) rows.push(['android/app/src/main/AndroidManifest.xml', yes, translate('summary.builtAsIs')]);
    rows.push(['ios/Runner/Info.plist', yes, translate('summary.builtAsIs')]);
    rows.push(['lib/ (Dart)', yes, translate('summary.builtAsIs')]);
    if (isUsingFirebaseFiles()) {
        rows.push(['android/app/google-services.json', no, `${SECRET_NAME_GOOGLE_SERVICES_JSON} → ${translate('summary.existingStep')}`]);
        rows.push(['ios/Runner/GoogleService-Info.plist', no, `${SECRET_NAME_GOOGLE_SERVICE_INFO_PLIST} → ${translate('summary.existingStep')}`]);
    }
    rows.push([`${OAUTH_EXPORT_FILE_PREFIX_SECRETS}* / ${OAUTH_EXPORT_FILE_PREFIX_SETUP}*`, no, translate('summary.never')]);
    setElementHtml('summaryFilesBody', rows.map(([file, inGit, inCi]) => `
        <tr class="border-b border-slate-700/50">
            <td class="py-2 px-2 font-mono">${escapeHtml(file)}</td>
            <td class="py-2 px-2">${inGit}</td>
            <td class="py-2 px-2">${escapeHtml(inCi)}</td>
        </tr>`).join(''));
}

// ============================================
// Firebase 설정 파일 (브라우저 안에서만 읽는다)
// ============================================

async function handleGoogleServicesFile(file) {
    if (!file) return;
    try {
        const text = await fileToText(file);
        const parsed = JSON.parse(text);
        state.googleServicesJson = text;
        state.googleServicesFileName = file.name;
        const webClientId = findWebClientId(parsed);
        if (!state.googleServerClientId && webClientId) state.googleServerClientId = webClientId;
        saveState();
        renderGoogleStep();
        showToast(translate('toast.fileLoaded', { fileName: file.name }));
    } catch (error) {
        showToast(translate('toast.fileInvalid', { fileName: file.name, message: error.message }));
    }
}

async function handleGoogleServiceInfoFile(file) {
    if (!file) return;
    try {
        const text = await fileToText(file);
        const values = readPlistStrings(text);
        if (!values.CLIENT_ID) throw new Error('CLIENT_ID not found');
        state.googleServiceInfoPlist = text;
        state.googleServiceInfoFileName = file.name;
        if (!state.googleIosClientId) state.googleIosClientId = values.CLIENT_ID;
        saveState();
        renderGoogleStep();
        showToast(translate('toast.fileLoaded', { fileName: file.name }));
    } catch (error) {
        showToast(translate('toast.fileInvalid', { fileName: file.name, message: error.message }));
    }
}

/** plist 최상위 dict 의 <key> > <string> 값 */
function readPlistStrings(text) {
    const documentNode = new DOMParser().parseFromString(text, 'application/xml');
    if (documentNode.querySelector('parsererror')) throw new Error('not a valid plist');
    const values = {};
    const dict = documentNode.querySelector('plist > dict');
    if (!dict) return values;
    const children = Array.from(dict.children);
    children.forEach((child, index) => {
        const next = children[index + 1];
        if (child.tagName === 'key' && next && next.tagName === 'string') values[child.textContent] = next.textContent;
    });
    return values;
}

/** google-services.json > 웹 클라이언트 ID (client_type 3) */
function findWebClientId(googleServices) {
    for (const client of googleServices.client || []) {
        for (const oauthClient of client.oauth_client || []) {
            if (oauthClient.client_type === 3) return oauthClient.client_id;
        }
    }
    return '';
}

/** google-services.json > {패키지명들, 등록된 SHA-1 해시들(소문자 16진)} */
function readGoogleServicesSummary(googleServices) {
    const packageNames = [];
    const certificateHashes = [];
    for (const client of googleServices.client || []) {
        const packageName = client.client_info?.android_client_info?.package_name;
        if (packageName) packageNames.push(packageName);
        for (const oauthClient of client.oauth_client || []) {
            const hash = oauthClient.android_info?.certificate_hash;
            if (hash) certificateHashes.push(String(hash).toLowerCase());
        }
    }
    return { packageNames, certificateHashes };
}

/** 올린 파일 <-> 입력값 대조 결과 표시 (패키지명·번들 ID·SHA-1 등록·웹 클라이언트) */
function renderGoogleFileChecks() {
    const lines = [];
    if (state.googleServicesJson) {
        try {
            const parsed = JSON.parse(state.googleServicesJson);
            const summary = readGoogleServicesSummary(parsed);
            const hasPackage = summary.packageNames.includes(state.applicationId);
            lines.push([hasPackage, (hasPackage ? translate('check.packageMatch', { value: state.applicationId || '-' }) : translate('check.packageMismatch', { value: state.applicationId || '-' }))]);
            collectFingerprintEntries().forEach((entry) => {
                const isRegistered = summary.certificateHashes.includes(entry.sha1.replace(/:/g, '').toLowerCase());
                lines.push([isRegistered, (isRegistered ? translate('check.sha1Registered', { label: entry.label }) : translate('check.sha1Missing', { label: entry.label }))]);
            });
            const hasWebClient = Boolean(findWebClientId(parsed));
            lines.push([hasWebClient, (hasWebClient ? translate('check.webClientFound') : translate('check.webClientMissing'))]);
        } catch (error) {
            lines.push([false, translate('check.jsonBroken')]);
        }
    }
    if (state.googleServiceInfoPlist) {
        const values = readPlistStrings(state.googleServiceInfoPlist);
        const isBundleMatch = values.BUNDLE_ID === state.bundleId;
        lines.push([isBundleMatch, (isBundleMatch ? translate('check.bundleMatch', { value: values.BUNDLE_ID || '-' }) : translate('check.bundleMismatch', { value: values.BUNDLE_ID || '-' }))]);
    }
    setElementHtml('googleFileChecks', lines.map(([isOk, text]) => `<div class="${isOk ? 'text-green-400' : 'text-yellow-300'}">${isOk ? '✅' : '⚠️'} ${escapeHtml(text)}</div>`).join(''));
}

