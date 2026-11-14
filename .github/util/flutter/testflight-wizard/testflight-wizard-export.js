/* ===================================================================
 * testflight wizard — export/import (copy all Secrets, ZIP download, JSON import)
 * Load order: ../_shared/wizard-i18n.js > ../_shared/wizard-common.js > testflight-wizard-i18n.js > testflight-wizard.js > this file
 * Function declarations only (state and init code live in the main file)
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

    // Add custom Secrets
    if (state.customSecrets && state.customSecrets.length > 0) {
        state.customSecrets.forEach(cs => {
            if (cs.key && cs.value) {
                secrets.push({ key: cs.key, value: cs.value, type: cs.type });
            }
        });
    }

    // Keep only values that are set
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
    // The whole template lives in the dictionary (ko output is byte-identical to before)
    return translate('export.readme', {
        date: new Date().toLocaleString(getExportDateLocale()),
        bundleId: state.bundleId || translate('export.notSet'),
        teamId: state.teamId || translate('export.notSet')
    });
}

async function downloadAsZip() {
    // Check that JSZip is loaded
    if (typeof JSZip === 'undefined') {
        showToast(translate('export.zipLibraryMissing'));
        return;
    }

    const zip = new JSZip();

    // 1. Actual files (Base64 decoded)
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

    // 2. Individual Secret TXT files (in the github-secrets folder)
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

    // Add custom Secrets
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

    // Warn if there are no files at all
    if (fileCount === 0) {
        showToast(translate('export.nothingToExport'));
        return;
    }

    // 3. Generate README.md
    const readme = generateReadme();
    zip.file("README.md", readme);

    // 4. Download the ZIP
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

    // Check the file extension
    if (!file.name.endsWith('.json')) {
        showToast(translate('import.jsonOnly'));
        event.target.value = '';
        return;
    }

    const reader = new FileReader();

    reader.onload = function(e) {
        try {
            const data = JSON.parse(e.target.result);

            // Validation - at least one known key must exist
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

            // Map values into State
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

            // Save to LocalStorage
            saveState();

            // Refresh the result table
            generateFinalResult();

            showToast(translate('import.done', { count: importedCount }));

        } catch (error) {
            console.error('[testflight import] json parse failed:', error);
            showToast(translate('import.parseFailed'));
        }

        // Reset the file input (so the same file can be chosen again)
        event.target.value = '';
    };

    reader.onerror = function() {
        showToast(translate('import.readError'));
        event.target.value = '';
    };

    reader.readAsText(file);
}
