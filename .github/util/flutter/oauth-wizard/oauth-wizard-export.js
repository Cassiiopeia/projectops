/**
 * OAuth wizard export (split file — function declarations only)
 * JSON/TXT: Secret values only / ZIP: Secrets + all outputs + README
 * The file name prefix matches the .gitignore pattern (oauth-wizard.py) — so it is not committed by mistake
 */

/* eslint-disable no-unused-vars */

function downloadAsJson() {
    const secrets = buildSecretsList().filter((secret) => secret.value);
    if (secrets.length === 0) {
        showToast(translate('toast.noSecrets'));
        return;
    }
    const output = {};
    secrets.forEach((secret) => { output[secret.key] = secret.value; });
    triggerDownload(new Blob([JSON.stringify(output, null, 2)], { type: 'application/json' }),
        `${OAUTH_EXPORT_FILE_PREFIX_SECRETS}${getDateStamp()}.json`);
    showToast(translate('toast.downloaded'));
}

function downloadAsTxt() {
    const secrets = buildSecretsList().filter((secret) => secret.value);
    if (secrets.length === 0) {
        showToast(translate('toast.noSecrets'));
        return;
    }
    const text = secrets.map((secret) => `=== ${secret.key} ===\n${secret.value}\n`).join('\n');
    triggerDownload(new Blob([text], { type: 'text/plain' }), `${OAUTH_EXPORT_FILE_PREFIX_SECRETS}${getDateStamp()}.txt`);
    showToast(translate('toast.downloaded'));
}

/** Outputs for the selection > {path inside ZIP: content} (same content in both languages) */
function collectSnippetFiles() {
    const files = {};
    if (state.providers.kakao) {
        files['native/AndroidManifest-kakao.xml'] = buildKakaoManifestSnippet(state.kakaoNativeAppKey);
        files['native/Info-plist-kakao.xml'] = buildKakaoPlistSnippet(state.kakaoNativeAppKey);
        files['dart/kakao_login.dart'] = buildKakaoDartSnippet(state.kakaoNativeAppKey);
    }
    if (state.providers.google) {
        files['native/Info-plist-google.xml'] = buildGooglePlistSnippet(state.googleIosClientId, state.googleServerClientId);
        files['dart/google_login.dart'] = buildGoogleDartSnippet(state.googleServerClientId);
    }
    if (isUsingFirebaseFiles()) {
        files['ci/fallback-ios-create-google-service-info-plist.yml'] = buildFallbackIosRestoreStep();
    }
    files['gitignore-lines.txt'] = buildGitignoreSnippet(isUsingFirebaseFiles());
    files['commands.txt'] = [
        buildSetupCommand('mac', buildSetupOptions(true)),
        buildSetupCommand('mac', buildSetupOptions(false)),
        '',
        buildSetupCommand('windows', buildSetupOptions(true)),
        buildSetupCommand('windows', buildSetupOptions(false)),
        '',
        buildPubAddCommand(),
    ].join('\n');
    return files;
}

function buildZipReadme(secrets) {
    const lines = [
        `# ${translate('zip.title')}`,
        '',
        translate('zip.generatedAt', { value: new Date().toISOString() }),
        '',
        `## ${translate('zip.secretsTitle')}`,
        '',
    ];
    if (secrets.length === 0) lines.push(translate('secrets.noneNeeded'));
    secrets.forEach((secret) => lines.push(`- github-secrets/${secret.key}.txt → ${secret.key}`));
    lines.push('', `## ${translate('zip.filesTitle')}`, '',
        translate('zip.native'), translate('zip.dart'), translate('zip.ci'), translate('zip.commands'),
        '', `## ${translate('zip.warningTitle')}`, '', translate('zip.warning'), '');
    return lines.join('\n');
}

async function downloadAsZip() {
    if (typeof JSZip === 'undefined') {
        showToast(translate('toast.jszipFailed'));
        return;
    }
    const secrets = buildSecretsList().filter((secret) => secret.value);
    const zip = new JSZip();
    secrets.forEach((secret) => zip.file(`github-secrets/${secret.key}.txt`, secret.value));
    Object.entries(collectSnippetFiles()).forEach(([path, content]) => zip.file(path, `${content}\n`));
    zip.file('README.md', buildZipReadme(secrets));
    const blob = await zip.generateAsync({ type: 'blob' });
    triggerDownload(blob, `${OAUTH_EXPORT_FILE_PREFIX_SETUP}${getDateStamp()}.zip`);
    showToast(translate('toast.downloaded'));
}
