/* ===================================================================
 * testflight 마법사 — 내보내기·가져오기 (Secret 일괄 복사, ZIP 다운로드, JSON 가져오기)
 * 로드 순서: ../_shared/wizard-common.js > testflight-wizard.js > 이 파일
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
4. Secret 등록이 끝나면 다운로드한 github-secrets 파일과 폴더를 반드시 삭제하세요. 인증서와 키가 그대로 들어 있습니다

## ⚠️ 주의사항

- 이 파일들에는 민감한 정보가 포함되어 있습니다
- Secret 등록이 끝나면 github-secrets 파일을 삭제하세요. 인증서와 키가 그대로 들어 있습니다
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
