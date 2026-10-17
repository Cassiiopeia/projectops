/* ===================================================================
 * playstore 마법사 — 내보내기·가져오기 (Secret 일괄 복사, JSON·TXT·ZIP 다운로드, JSON 가져오기)
 * 로드 순서: ../_shared/wizard-common.js > playstore-wizard.js > 이 파일
 * 함수 선언만 둔다 (상태·초기화 코드는 본 파일)
 * =================================================================== */

// ============================================
// Copy All Secrets to Clipboard
// ============================================

function copyAllSecrets() {
    const secrets = [
        { key: 'RELEASE_KEYSTORE_BASE64', value: state.keystoreBase64 },
        { key: 'RELEASE_KEYSTORE_PASSWORD', value: state.storePassword },
        { key: 'RELEASE_KEY_ALIAS', value: state.keyAlias },
        { key: 'RELEASE_KEY_PASSWORD', value: state.keyPassword },
        { key: 'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64', value: state.serviceAccountBase64 },
        { key: 'GOOGLE_SERVICES_JSON', value: state.googleServicesJson },
        { key: 'ENV_FILE', value: state.envFileContent }
    ];

    // 커스텀 Secrets 추가
    const customSecrets = getCustomSecretsForExport();
    customSecrets.forEach(cs => {
        secrets.push({ key: cs.key, value: cs.value });
    });

    // 설정된 값만 필터링
    const configuredSecrets = secrets.filter(s => s.value);

    if (configuredSecrets.length === 0) {
        showToast('⚠️ 복사할 설정값이 없습니다');
        return;
    }

    const lines = [
        '===== GitHub Secrets for Play Store =====',
        `생성일: ${new Date().toLocaleString('ko-KR')}`,
        `Application ID: ${state.applicationId || '(미설정)'}`,
        '',
        ...configuredSecrets.map(s => `${s.key}=${s.value}`),
        '',
        '========================================='
    ];

    const text = lines.join('\n');

    navigator.clipboard.writeText(text).then(() => {
        showToast(`✅ ${configuredSecrets.length}개 Secret 전체 복사 완료!`);
    }).catch(() => {
        showToast('❌ 클립보드 복사 실패');
    });
}

// ============================================
// Download Functions
// ============================================

function downloadAsJson() {
    const secrets = {
        RELEASE_KEYSTORE_BASE64: state.keystoreBase64,
        RELEASE_KEYSTORE_PASSWORD: state.storePassword,
        RELEASE_KEY_ALIAS: state.keyAlias,
        RELEASE_KEY_PASSWORD: state.keyPassword,
        GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64: state.serviceAccountBase64,
        GOOGLE_SERVICES_JSON: state.googleServicesJson,
        ENV_FILE: state.envFileContent
    };

    // 커스텀 Secrets 추가
    const customSecrets = getCustomSecretsForExport();
    customSecrets.forEach(cs => {
        secrets[cs.key] = cs.value;
    });

    const jsonStr = JSON.stringify(secrets, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'github-secrets-playstore.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('✅ JSON 파일 다운로드 완료!');
}

function downloadAsTxt() {
    const lines = [
        '# GitHub Secrets for Play Store Deployment',
        '# 생성일: ' + new Date().toLocaleString('ko-KR'),
        '',
        '===== GitHub Repository Secrets =====',
        '',
        'RELEASE_KEYSTORE_BASE64:',
        state.keystoreBase64 || '(미입력)',
        '',
        'RELEASE_KEYSTORE_PASSWORD:',
        state.storePassword || '(미입력)',
        '',
        'RELEASE_KEY_ALIAS:',
        state.keyAlias || '(미입력)',
        '',
        'RELEASE_KEY_PASSWORD:',
        state.keyPassword || '(미입력)',
        '',
        'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64:',
        state.serviceAccountBase64 || '(미입력)',
        '',
        'GOOGLE_SERVICES_JSON:',
        state.googleServicesJson ? '[설정됨]' : '(미입력)',
        '',
        'ENV_FILE:',
        state.envFileContent || '(미입력)',
        ''
    ];

    // 커스텀 Secrets 추가
    const customSecrets = getCustomSecretsForExport();
    if (customSecrets.length > 0) {
        lines.push('===== 사용자 추가 Secrets =====');
        lines.push('');
        customSecrets.forEach(cs => {
            const typeLabel = cs.type === 'text' ? '[텍스트]' : '[Base64]';
            lines.push(`${cs.key}: ${typeLabel}`);
            lines.push(cs.value.substring(0, 100) + (cs.value.length > 100 ? '...' : ''));
            lines.push('');
        });
    }

    lines.push('=====================================');

    const txtStr = lines.join('\n');
    const blob = new Blob([txtStr], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'github-secrets-playstore.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast('✅ TXT 파일 다운로드 완료!');
}

function downloadConfig() {
    const config = {
        projectInfo: {
            applicationId: state.applicationId,
            versionName: state.versionName,
            versionCode: state.versionCode,
            gradleType: state.gradleType
        },
        generatedAt: new Date().toISOString(),
        secrets: {
            RELEASE_KEYSTORE_BASE64: state.keystoreBase64 ? '[설정됨]' : null,
            RELEASE_KEYSTORE_PASSWORD: state.storePassword ? '[설정됨]' : null,
            RELEASE_KEY_ALIAS: state.keyAlias || null,
            RELEASE_KEY_PASSWORD: state.keyPassword ? '[설정됨]' : null,
            GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64: state.serviceAccountBase64 ? '[설정됨]' : null
        }
    };

    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'playstore-cicd-config.json';
    a.click();
    URL.revokeObjectURL(url);
    showToast('✅ 설정 JSON 다운로드 완료!');
}

// ============================================
// ZIP Export Functions
// ============================================

function generateReadme() {
    return `# Play Store 배포 설정 백업

생성일: ${new Date().toLocaleString('ko-KR')}
Application ID: ${state.applicationId || '(미설정)'}

## 📁 파일 구조

\`\`\`
├── release-key.jks          # Android 서명 키스토어 (Base64 디코딩됨)
├── service-account.json     # Google Play Service Account (Base64 디코딩됨)
├── github-secrets/          # GitHub Secrets용 값들
│   ├── RELEASE_KEYSTORE_BASE64.txt
│   ├── RELEASE_KEYSTORE_PASSWORD.txt
│   ├── RELEASE_KEY_ALIAS.txt
│   ├── RELEASE_KEY_PASSWORD.txt
│   └── GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64.txt
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
    if (state.keystoreBase64) {
        try {
            const binaryString = atob(state.keystoreBase64);
            const bytes = new Uint8Array(binaryString.length);
            for (let i = 0; i < binaryString.length; i++) {
                bytes[i] = binaryString.charCodeAt(i);
            }
            zip.file("release-key.jks", bytes);
        } catch (e) {
            console.error('Keystore 디코딩 실패:', e);
        }
    }

    if (state.serviceAccountBase64) {
        try {
            const jsonContent = atob(state.serviceAccountBase64);
            zip.file("service-account.json", jsonContent);
        } catch (e) {
            console.error('Service Account 디코딩 실패:', e);
        }
    }

    // 2. 개별 Secret TXT 파일들 (github-secrets 폴더에)
    const secrets = [
        { name: 'RELEASE_KEYSTORE_BASE64.txt', value: state.keystoreBase64 },
        { name: 'RELEASE_KEYSTORE_PASSWORD.txt', value: state.storePassword },
        { name: 'RELEASE_KEY_ALIAS.txt', value: state.keyAlias },
        { name: 'RELEASE_KEY_PASSWORD.txt', value: state.keyPassword },
        { name: 'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64.txt', value: state.serviceAccountBase64 },
        { name: 'GOOGLE_SERVICES_JSON.txt', value: state.googleServicesJson },
        { name: 'ENV_FILE.txt', value: state.envFileContent }
    ];

    // 커스텀 Secrets 추가
    const customSecrets = getCustomSecretsForExport();
    customSecrets.forEach(cs => {
        secrets.push({ name: `${cs.key}.txt`, value: cs.value });

        // 바이너리 파일은 실제 파일로도 복원
        if (cs.type === 'binary') {
            try {
                const binaryString = atob(cs.value);
                const bytes = new Uint8Array(binaryString.length);
                for (let i = 0; i < binaryString.length; i++) {
                    bytes[i] = binaryString.charCodeAt(i);
                }
                // 파일명에서 확장자 추출
                const ext = cs.fileName.split('.').pop() || 'bin';
                zip.file(`custom-files/${cs.fileName}`, bytes);
            } catch (e) {
                console.error(`커스텀 파일 디코딩 실패 (${cs.key}):`, e);
            }
        } else {
            // 텍스트 파일은 그대로 저장
            zip.file(`custom-files/${cs.fileName}`, cs.value);
        }
    });

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
        const appId = state.applicationId ? state.applicationId.replace(/\./g, '-') : 'app';
        a.download = `playstore-secrets-${appId}-${getDateString()}.zip`;
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
                'RELEASE_KEYSTORE_BASE64',
                'RELEASE_KEYSTORE_PASSWORD',
                'RELEASE_KEY_ALIAS',
                'RELEASE_KEY_PASSWORD',
                'GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64',
                'GOOGLE_SERVICES_JSON',
                'ENV_FILE'
            ];

            const hasValidKey = knownKeys.some(key => key in data);
            if (!hasValidKey) {
                showToast('❌ 올바른 PlayStore Secrets JSON 파일이 아닙니다');
                event.target.value = '';
                return;
            }

            // State에 값 매핑
            let importedCount = 0;

            if (data.RELEASE_KEYSTORE_BASE64) {
                state.keystoreBase64 = data.RELEASE_KEYSTORE_BASE64;
                importedCount++;
            }
            if (data.RELEASE_KEYSTORE_PASSWORD) {
                state.storePassword = data.RELEASE_KEYSTORE_PASSWORD;
                importedCount++;
            }
            if (data.RELEASE_KEY_ALIAS) {
                state.keyAlias = data.RELEASE_KEY_ALIAS;
                importedCount++;
            }
            if (data.RELEASE_KEY_PASSWORD) {
                state.keyPassword = data.RELEASE_KEY_PASSWORD;
                importedCount++;
            }
            if (data.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64) {
                state.serviceAccountBase64 = data.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON_BASE64;
                importedCount++;
            }
            if (data.GOOGLE_SERVICES_JSON) {
                state.googleServicesJson = data.GOOGLE_SERVICES_JSON;
                importedCount++;
            }
            if (data.ENV_FILE) {
                state.envFileContent = data.ENV_FILE;
                importedCount++;
            }

            // LocalStorage에 저장
            saveState();

            // 테이블 갱신
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
