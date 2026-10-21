// ============================================
// GitHub Secrets Converter
// 파일을 업로드하면 자동으로 최적의 형식으로 변환
// ============================================

// 상태 관리
const STORAGE_KEY = 'secrets-converter-state';
let state = {
    files: []
    // [{
    //   key: 'SECRET_NAME',
    //   value: '...',
    //   fileName: 'original.p12',
    //   type: 'text' | 'binary',
    //   hint: '사용법'
    // }]
};

// ============================================
// 파일 타입 감지 및 처리
// ============================================

// 텍스트 파일 확장자 (원본 그대로 저장)
const TEXT_EXTENSIONS = [
    '.json', '.yml', '.yaml', '.env', '.txt', '.xml',
    '.plist', '.properties', '.toml', '.ini', '.cfg', '.conf'
];

// 바이너리 파일 확장자 (Base64 인코딩)
const BINARY_EXTENSIONS = [
    '.jks', '.keystore', '.p12', '.mobileprovision', '.p8',
    '.cer', '.pfx', '.pem', '.der', '.key', '.crt'
];

function getFileType(fileName) {
    const lowerName = fileName.toLowerCase();
    // .env로 시작하는 파일은 텍스트로 처리 (.env.production, .env.local 등)
    if (lowerName === '.env' || lowerName.startsWith('.env.')) return 'text';

    const ext = '.' + fileName.split('.').pop().toLowerCase();
    if (TEXT_EXTENSIONS.includes(ext)) return 'text';
    if (BINARY_EXTENSIONS.includes(ext)) return 'binary';
    // 알 수 없는 확장자는 바이너리로 처리 (안전)
    return 'binary';
}

function generateKeyName(fileName, fileType) {
    // 파일명에서 확장자 제거 후 대문자+언더스코어로 변환
    const baseName = fileName
        .replace(/\.[^/.]+$/, '')  // 확장자 제거
        .toUpperCase()
        .replace(/[^A-Z0-9]/g, '_')
        .replace(/_+/g, '_')
        .replace(/^_|_$/g, '');  // 시작/끝 언더스코어 제거

    // 바이너리 파일만 _BASE64 접미사 추가
    if (fileType === 'binary') {
        return baseName + '_BASE64';
    }
    return baseName;
}

async function processFile(file) {
    const fileType = getFileType(file.name);

    if (fileType === 'text') {
        // 텍스트 파일: 원본 내용 그대로
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve({
                value: reader.result,
                type: 'text',
                hint: translate('hint.text')
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
                hint: 'echo $SECRET | base64 -d > file'
            });
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }
}

// ============================================
// UI 렌더링
// ============================================

function renderFileList() {
    const container = document.getElementById('fileList');
    if (!container) return;

    if (state.files.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <div class="empty-icon">📁</div>
                <p>${translate('empty.title')}</p>
                <p class="hint">${translate('empty.hint')}</p>
            </div>
        `;
        return;
    }

    container.innerHTML = state.files.map((file, index) => {
        const typeIcon = file.type === 'text' ? '📄' : '🔐';
        const typeBadge = file.type === 'text' ? 'Raw Text' : 'Base64';
        const typeClass = file.type === 'text' ? 'text' : 'binary';
        const valuePreview = file.value ?
            (file.value.length > 100 ? file.value.substring(0, 100) + '...' : file.value) :
            '';

        return `
            <div class="file-slot" data-index="${index}">
                <div class="slot-header">
                    <span class="type-badge ${typeClass}">${typeIcon} ${typeBadge}</span>
                    <button class="remove-btn" onclick="removeFile(${index})" title="${translate('slot.remove')}">×</button>
                </div>
                <div class="key-input-wrapper">
                    <label>${translate('slot.keyName')}</label>
                    <input type="text"
                           class="key-input"
                           value="${file.key || ''}"
                           onchange="updateKey(${index}, this.value)"
                           placeholder="SECRET_NAME">
                </div>
                <div class="file-info">
                    <span class="file-name">${file.fileName || translate('slot.noFile')}</span>
                    ${file.value ? `<span class="file-size">(${formatSize(file.value.length)})</span>` : ''}
                </div>
                ${file.hint ? `<div class="usage-hint">💡 ${file.hint}</div>` : ''}
                ${file.value ? `
                    <div class="value-preview">
                        <code>${escapeHtml(valuePreview)}</code>
                    </div>
                    <button class="copy-btn" onclick="copyValue(${index})">${translate('slot.copyValue')}</button>
                ` : ''}
            </div>
        `;
    }).join('');
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatSize(length) {
    if (length < 1024) return `${length}B`;
    if (length < 1024 * 1024) return `${(length / 1024).toFixed(1)}KB`;
    return `${(length / (1024 * 1024)).toFixed(1)}MB`;
}

// ============================================
// 파일 슬롯 관리
// ============================================

function addFileSlot() {
    state.files.push({
        key: '',
        value: '',
        fileName: '',
        type: 'binary',
        hint: ''
    });
    renderFileList();
    saveState();

    // 새로 추가된 슬롯의 파일 선택 다이얼로그 열기
    setTimeout(() => {
        const slots = document.querySelectorAll('.file-slot');
        const lastSlot = slots[slots.length - 1];
        if (lastSlot) {
            const input = document.createElement('input');
            input.type = 'file';
            input.onchange = (e) => handleFileSelect(state.files.length - 1, e.target.files[0]);
            input.click();
        }
    }, 100);
}

function removeFile(index) {
    state.files.splice(index, 1);
    renderFileList();
    saveState();
    showToast(translate('toast.fileRemoved'));
}

function updateKey(index, newKey) {
    if (state.files[index]) {
        state.files[index].key = newKey.toUpperCase().replace(/[^A-Z0-9_]/g, '_');
        saveState();
    }
}

async function handleFileSelect(index, file) {
    if (!file) return;

    try {
        const result = await processFile(file);
        const suggestedKey = generateKeyName(file.name, result.type);

        state.files[index] = {
            key: suggestedKey,
            value: result.value,
            fileName: file.name,
            type: result.type,
            hint: result.hint
        };

        renderFileList();
        saveState();
        showToast(translate('toast.fileProcessed', {
            fileName: file.name,
            fileType: result.type === 'text' ? translate('fileType.text') : 'Base64'
        }));
    } catch (error) {
        console.error('[secrets converter] file processing failed:', error);
        showToast(translate('toast.fileFailed'));
    }
}

// 여러 파일 한번에 처리
async function handleMultipleFiles(files) {
    for (const file of files) {
        try {
            const result = await processFile(file);
            const suggestedKey = generateKeyName(file.name, result.type);

            state.files.push({
                key: suggestedKey,
                value: result.value,
                fileName: file.name,
                type: result.type,
                hint: result.hint
            });
        } catch (error) {
            console.error('[secrets converter] file processing failed:', file.name, error);
        }
    }
    renderFileList();
    saveState();
    if (files.length > 0) {
        showToast(translate('toast.filesProcessed', { count: files.length }));
    }
    // input 초기화
    document.getElementById('fileInput').value = '';
}

// ============================================
// Drag & Drop
// ============================================

function setupDragAndDrop() {
    const dropZone = document.getElementById('dropZone');
    if (!dropZone) return;

    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, () => {
            dropZone.classList.remove('drag-over');
        });
    });

    dropZone.addEventListener('drop', async (e) => {
        const files = e.dataTransfer.files;
        for (const file of files) {
            try {
                const result = await processFile(file);
                const suggestedKey = generateKeyName(file.name, result.type);

                state.files.push({
                    key: suggestedKey,
                    value: result.value,
                    fileName: file.name,
                    type: result.type,
                    hint: result.hint
                });
            } catch (error) {
                console.error('[secrets converter] file processing failed:', file.name, error);
            }
        }
        renderFileList();
        saveState();
        showToast(translate('toast.filesProcessed', { count: files.length }));
    });
}

// ============================================
// 복사 및 내보내기
// ============================================

function copyValue(index) {
    const file = state.files[index];
    if (!file || !file.value) {
        showToast(translate('toast.noValue'));
        return;
    }

    navigator.clipboard.writeText(file.value).then(() => {
        showToast(translate('toast.valueCopied', { key: file.key }));
    }).catch(() => {
        showToast(translate('toast.clipboardFailed'));
    });
}

function copyAllAsJson() {
    const validFiles = state.files.filter(f => f.key && f.value);
    if (validFiles.length === 0) {
        showToast(translate('toast.noDataToCopy'));
        return;
    }

    const result = {};
    validFiles.forEach(f => {
        result[f.key] = f.value;
    });

    navigator.clipboard.writeText(JSON.stringify(result, null, 2)).then(() => {
        showToast(translate('toast.jsonCopied', { count: validFiles.length }));
    }).catch(() => {
        showToast(translate('toast.clipboardFailed'));
    });
}

function downloadAsJson() {
    const validFiles = state.files.filter(f => f.key && f.value);
    if (validFiles.length === 0) {
        showToast(translate('toast.noDataToExport'));
        return;
    }

    const result = {};
    validFiles.forEach(f => {
        result[f.key] = f.value;
    });

    const jsonStr = JSON.stringify(result, null, 2);
    const blob = new Blob([jsonStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `github-secrets-${getDateString()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(translate('toast.jsonDownloaded'));
}

function downloadAsTxt() {
    const validFiles = state.files.filter(f => f.key && f.value);
    if (validFiles.length === 0) {
        showToast(translate('toast.noDataToExport'));
        return;
    }

    const lines = [
        '# GitHub Secrets',
        translate('txt.createdAt') + new Date().toLocaleString(getWizardLanguage() === 'ko' ? 'ko-KR' : 'en-US'),
        ''
    ];

    validFiles.forEach(f => {
        const typeLabel = f.type === 'text' ? translate('txt.textLabel') : '[Base64]';
        lines.push(`===== ${f.key} ${typeLabel} =====`);
        lines.push(translate('txt.sourceFile', { fileName: f.fileName }));
        lines.push(translate('txt.usage', { hint: f.hint }));
        lines.push('');
        lines.push(f.value);
        lines.push('');
    });

    const txtStr = lines.join('\n');
    const blob = new Blob([txtStr], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `github-secrets-${getDateString()}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast(translate('toast.txtDownloaded'));
}

function getDateString() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

// ============================================
// 상태 저장/복원
// ============================================

function saveState() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
        console.error('[secrets converter] state save failed:', e);
    }
}

function loadState() {
    try {
        const saved = localStorage.getItem(STORAGE_KEY);
        if (saved) {
            state = JSON.parse(saved);
        }
    } catch (e) {
        console.error('[secrets converter] state restore failed:', e);
        state = { files: [] };
    }
}

function clearAll() {
    if (confirm(translate('confirm.clearAll'))) {
        state = { files: [] };
        saveState();
        renderFileList();
        showToast(translate('toast.allCleared'));
    }
}

// ============================================
// 토스트 메시지
// ============================================

function showToast(message) {
    // 기존 토스트 제거
    const existingToast = document.querySelector('.toast');
    if (existingToast) {
        existingToast.remove();
    }

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.classList.add('show');
    }, 10);

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}

// ============================================
// 초기화
// ============================================

document.addEventListener('DOMContentLoaded', () => {
    loadState();
    renderFileList();
    setupDragAndDrop();
});

// 언어 전환 시 파일 목록 다시 그리기 (빈 상태 안내·버튼 문구)
document.addEventListener('wizardlanguagechange', () => renderFileList());
