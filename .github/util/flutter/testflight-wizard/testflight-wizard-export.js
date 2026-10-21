/* ===================================================================
 * testflight 마법사 — 내보내기·가져오기 (Secret 일괄 복사, ZIP 다운로드, JSON 가져오기)
 * 로드 순서: ../_shared/wizard-i18n.js > ../_shared/wizard-common.js > testflight-wizard-i18n.js > testflight-wizard.js > 이 파일
 * 함수 선언만 둔다 (상태·초기화 코드는 본 파일)
 * =================================================================== */

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
        showToast(translate('export.nothingToCopy'));
        return;
    }

    const lines = [
        '===== GitHub Secrets for iOS TestFlight =====',
        translate('export.generatedAt', { date: new Date().toLocaleString(getExportDateLocale()) }),
        `Bundle ID: ${state.bundleId || translate('export.notSet')}`,
        '',
        ...configuredSecrets.map(s => `${s.key}=${s.value}`),
        '',
        '============================================='
    ];

    const text = lines.join('\n');

    navigator.clipboard.writeText(text).then(() => {
        showToast(translate('export.copyAllDone', { count: configuredSecrets.length }));
    }).catch(() => {
        showToast(translate('export.clipboardFailed'));
    });
}

// ============================================
// ZIP Export Functions
// ============================================

function generateReadme() {
    // 템플릿 전체를 사전에 둔다 (ko 출력은 기존과 같은 바이트)
    return translate('export.readme', {
        date: new Date().toLocaleString(getExportDateLocale()),
        bundleId: state.bundleId || translate('export.notSet'),
        teamId: state.teamId || translate('export.notSet')
    });
}

async function downloadAsZip() {
    // JSZip 로드 확인
    if (typeof JSZip === 'undefined') {
        showToast(translate('export.zipLibraryMissing'));
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
            console.error('[testflight export] p12 decode failed:', e);
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
            console.error('[testflight export] provisioning profile decode failed:', e);
        }
    }

    if (state.p8Base64) {
        try {
            const p8Content = atob(state.p8Base64);
            zip.file("api-key.p8", p8Content);
        } catch (e) {
            console.error('[testflight export] p8 decode failed:', e);
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
        showToast(translate('export.nothingToExport'));
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
        showToast(translate('export.zipDone', { count: fileCount }));
    } catch (e) {
        console.error('[testflight export] zip generation failed:', e);
        showToast(translate('export.zipFailed'));
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
        showToast(translate('import.jsonOnly'));
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
                showToast(translate('import.invalidFile'));
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

            showToast(translate('import.done', { count: importedCount }));

        } catch (error) {
            console.error('[testflight import] json parse failed:', error);
            showToast(translate('import.parseFailed'));
        }

        // 파일 입력 초기화 (같은 파일 다시 선택 가능하도록)
        event.target.value = '';
    };

    reader.onerror = function() {
        showToast(translate('import.readError'));
        event.target.value = '';
    };

    reader.readAsText(file);
}
