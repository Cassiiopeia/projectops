/* ===================================================================
 * projectops Flutter 마법사 공통 유틸 (정본)
 * ===================================================================
 *
 * testflight / playstore / firebase 마법사가 공유한다.
 * 각 마법사 JS보다 **먼저** 로드된다:
 *
 *   <script src="../_shared/wizard-common.js"></script>
 *   <script src="testflight-wizard.js"></script>
 *
 * ⚠️ 규칙
 * -------------------------------------------------------------------
 * 1. 여기에는 "마법사 흐름과 무관한 순수 유틸"만 둔다.
 *    단계 이동(showStep/goToStep), 상태 스키마(saveState/loadState),
 *    산출물 생성(generateXxx)은 마법사마다 다르므로 각자 파일에 둔다.
 * 2. 마법사 JS에서 같은 이름을 다시 정의하면 이 정본이 덮어써진다.
 *    의도적 오버라이드가 아니라면 중복 정의하지 말 것.
 *    (_shared/check-consistency.py가 중복 정의를 잡아낸다)
 * 3. 함수 시그니처를 바꾸면 3종 전부 영향을 받는다. 반드시 3종을 함께 확인한다.
 *
 * 구현 선택 근거 — 3종에 갈라져 있던 구현 중 가장 안전한 것을 채택했다:
 *   escapeHtml   : firebase판 (null 안전 + 따옴표까지 이스케이프)
 *   getInputValue: testflight/playstore판 (trim 수행)
 *   showToast    : testflight/playstore판 (DOM에 #toast가 없어도 동작)
 *   getDateString: YYYY-MM-DD 로 통일하고, 파일명용 YYYYMMDD는 getDateStamp로 분리
 * =================================================================== */

/* eslint-disable no-unused-vars */

// ============================================
// 문자열 / 이스케이프
// ============================================

/** innerHTML 보간용 이스케이프. null/undefined도 빈 문자열로 안전 처리한다. */
function escapeHtml(value) {
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

/** onclick="fn('...')" 처럼 JS 문자열 리터럴 안에 넣을 값 이스케이프 */
function escapeJsString(value) {
    return String(value == null ? '' : value)
        .replace(/\\/g, '\\\\')
        .replace(/'/g, "\\'")
        .replace(/"/g, '\\"')
        .replace(/\n/g, '\\n')
        .replace(/\r/g, '');
}

/** 셸 명령에 값을 끼워 넣을 때 사용 (작은따옴표 감싸기) */
function shellEscape(value) {
    const s = String(value == null ? '' : value);
    return `'${s.replace(/'/g, `'\\''`)}'`;
}

// ============================================
// 날짜
// ============================================

/** 화면 표시용 날짜 (2026-07-27) */
function getDateString() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

/** 파일명용 날짜 (20260727) — 공백·하이픈 없이 정렬 가능한 형태 */
function getDateStamp() {
    return getDateString().replace(/-/g, '');
}

// ============================================
// DOM 접근
// ============================================

/** input/textarea 값을 trim해서 반환. 요소가 없으면 빈 문자열. */
function getInputValue(id) {
    const element = document.getElementById(id);
    return element?.value?.trim() || '';
}

function setElementText(id, text) {
    const element = document.getElementById(id);
    if (element) element.textContent = text;
}

function setElementHtml(id, html) {
    const element = document.getElementById(id);
    if (element) element.innerHTML = html;
}

// ============================================
// 알림 / 클립보드
// ============================================

/**
 * 우하단 토스트. DOM에 미리 #toast가 없어도 동작하도록 매번 생성한다.
 * (firebase가 쓰던 "고정 #toast 참조" 방식은 요소 누락 시 예외로 죽었다)
 */
function showToast(message) {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

/**
 * 클립보드 복사. navigator.clipboard가 없거나(구형 브라우저·비보안 컨텍스트)
 * 실패하면 execCommand로 폴백한다. file://로 열어도 동작해야 하므로 폴백이 필수다.
 */
async function copyToClipboard(text, successMessage = '복사되었습니다') {
    const value = String(text == null ? '' : text);
    try {
        if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(value);
            showToast(successMessage);
            return true;
        }
        throw new Error('clipboard API unavailable');
    } catch (err) {
        try {
            const ta = document.createElement('textarea');
            ta.value = value;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            const ok = document.execCommand('copy');
            document.body.removeChild(ta);
            showToast(ok ? successMessage : '복사에 실패했습니다. 직접 선택해 복사해주세요.');
            return ok;
        } catch (fallbackErr) {
            showToast('복사에 실패했습니다. 직접 선택해 복사해주세요.');
            return false;
        }
    }
}

/** 코드 블록 복사 — 버튼에 일시적으로 완료 표시를 남긴다 */
async function copyCode(elementId, buttonEl) {
    const el = document.getElementById(elementId);
    if (!el) return false;
    const ok = await copyToClipboard(el.textContent, '명령어가 복사되었습니다');
    if (ok && buttonEl) {
        const original = buttonEl.textContent;
        buttonEl.textContent = '✅ 복사됨';
        buttonEl.classList.add('copied');
        setTimeout(() => {
            buttonEl.textContent = original;
            buttonEl.classList.remove('copied');
        }, 1500);
    }
    return ok;
}

// ============================================
// 파일 처리
// ============================================

/** 확장자·MIME으로 텍스트/바이너리 판정. Secret 값 변환 방식을 가른다. */
function getFileType(file) {
    const textExtensions = ['.json', '.txt', '.yml', '.yaml', '.xml', '.plist', '.env', '.properties', '.pem', '.cer', '.crt', '.key', '.md', '.conf', '.config', '.xcconfig'];
    const name = (file.name || '').toLowerCase();
    if (textExtensions.some((ext) => name.endsWith(ext))) return 'text';
    if (file.type && file.type.startsWith('text/')) return 'text';
    if (file.type === 'application/json') return 'text';
    return 'binary';
}

/** 파일 → base64 문자열 (data URL 접두사 제거) */
function fileToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
            const result = String(reader.result || '');
            resolve(result.includes(',') ? result.split(',')[1] : result);
        };
        reader.onerror = () => reject(reader.error || new Error('파일을 읽지 못했습니다'));
        reader.readAsDataURL(file);
    });
}

/** 파일 → 원문 텍스트 */
function fileToText(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(reader.error || new Error('파일을 읽지 못했습니다'));
        reader.readAsText(file);
    });
}

/** 파일명 → GitHub Secret 키 후보 (바이너리는 _BASE64 접미사) */
function generateKeyName(fileName, fileType) {
    const base = fileName
        .replace(/\.[^.]+$/, '')
        .replace(/[^a-zA-Z0-9]/g, '_')
        .replace(/_+/g, '_')
        .replace(/^_|_$/g, '')
        .toUpperCase();
    return fileType === 'binary' ? `${base}_BASE64` : base;
}

/** 드래그&드롭 영역 배선 — 3종이 동일하게 쓰던 패턴 */
function setupDragAndDrop(dropZoneId, onFile) {
    const zone = document.getElementById(dropZoneId);
    if (!zone) return;
    ['dragenter', 'dragover'].forEach((evt) => {
        zone.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.add('dragover');
        });
    });
    ['dragleave', 'drop'].forEach((evt) => {
        zone.addEventListener(evt, (e) => {
            e.preventDefault();
            e.stopPropagation();
            zone.classList.remove('dragover');
        });
    });
    zone.addEventListener('drop', (e) => {
        const file = e.dataTransfer?.files?.[0];
        if (file) onFile(file);
    });
}

// ============================================
// OS 감지
// ============================================

/** 'windows' | 'mac' | 'linux' — 판별 불가 시 mac (마법사 주 사용 환경) */
function detectOS() {
    const ua = navigator.userAgent || navigator.appVersion || navigator.platform || '';
    if (/Win/i.test(ua)) return 'windows';
    if (/Mac/i.test(ua)) return 'mac';
    if (/Linux|X11|Android/i.test(ua)) return 'linux';
    return 'mac';
}

/** POSIX 경로 → Windows 경로 (명령어 생성용) */
function toWinPath(p) {
    return String(p || '').replace(/\//g, '\\');
}

/** POSIX(/...)와 Windows(C:\...) 절대경로를 모두 허용한다 */
function isAbsolutePath(p) {
    const v = String(p || '').trim();
    return v.startsWith('/') || /^[A-Za-z]:[\\/]/.test(v);
}

// ============================================
// 진행 상태 저장 (localStorage)
// ============================================

/**
 * 상태 읽기. legacyKeys를 함께 넘기면 구 키에 저장된 진행 상황을 자동 이관한다.
 * (키 이름을 통일하면서 기존 사용자의 저장 데이터가 날아가지 않게 하기 위함)
 */
function readWizardState(key, legacyKeys = []) {
    try {
        let raw = localStorage.getItem(key);
        if (!raw) {
            for (const legacy of legacyKeys) {
                const old = localStorage.getItem(legacy);
                if (old) {
                    localStorage.setItem(key, old);
                    localStorage.removeItem(legacy);
                    raw = old;
                    break;
                }
            }
        }
        return raw ? JSON.parse(raw) : null;
    } catch (err) {
        console.warn('저장된 진행 상황을 읽지 못했습니다:', err);
        return null;
    }
}

function writeWizardState(key, state) {
    try {
        localStorage.setItem(key, JSON.stringify(state));
        return true;
    } catch (err) {
        // 용량 초과(대용량 인증서를 여러 개 올린 경우)에도 마법사가 죽지 않게 한다
        console.warn('진행 상황 저장 실패:', err);
        showToast('진행 상황을 저장하지 못했습니다 (브라우저 저장 공간 부족)');
        return false;
    }
}

function clearWizardState(key, legacyKeys = []) {
    try {
        localStorage.removeItem(key);
        legacyKeys.forEach((k) => localStorage.removeItem(k));
    } catch (err) {
        console.warn('진행 상황 삭제 실패:', err);
    }
}

// ============================================
// 버전 / 변경 이력
// ============================================

/** HTML에 인라인된 versionJson 블록을 파싱 (version-sync.sh가 주입한다) */
function getVersionData() {
    try {
        const el = document.getElementById('versionJson');
        return el ? JSON.parse(el.textContent) : null;
    } catch (err) {
        console.warn('버전 정보를 읽지 못했습니다:', err);
        return null;
    }
}

/**
 * 변경 이력 모달 — 3종 공통.
 *
 * ⚠️ 마크업 계약 (마법사 HTML이 반드시 갖춰야 하는 구조):
 *   <div id="changelogModal" class="modal-backdrop hidden" onclick="closeChangelogModal(event)">
 *     <div class="modal-content" onclick="event.stopPropagation()">
 *       ... <div id="changelogContent"></div>
 *           <p id="changelogLastUpdated"></p>
 *     </div>
 *   </div>
 *
 * 껍데기(닫기 버튼·배경 클릭 영역)는 HTML이 소유하고, 이 함수는 내용만 채운다.
 * 모달 전체를 innerHTML로 갈아끼우면 배경 클릭 닫기가 사라지므로 하지 않는다.
 */
function openChangelogModal() {
    const modal = document.getElementById('changelogModal');
    const content = document.getElementById('changelogContent');
    const lastUpdated = document.getElementById('changelogLastUpdated');
    if (!modal || !content) return;

    const data = getVersionData();
    if (!data) {
        content.innerHTML = '<div class="text-center text-red-400 py-4">버전 정보를 불러올 수 없습니다.</div>';
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        return;
    }

    const releases = data.changelog || [];
    content.innerHTML = releases.map((release, index) => {
        const isLatest = index === 0;
        const divider = index < releases.length - 1 ? 'border-b border-slate-700 mb-4' : '';
        const items = (release.changes || []).map((change) => `
                        <li class="text-sm text-slate-400 flex items-start gap-2">
                            <span class="text-slate-600 mt-1">•</span>
                            <span>${escapeHtml(change)}</span>
                        </li>`).join('');
        return `
            <div class="pb-4 ${divider}">
                <div class="flex items-center gap-2 mb-2">
                    <span class="text-white font-semibold">v${escapeHtml(release.version)}</span>
                    ${isLatest ? '<span class="px-2 py-0.5 text-xs bg-blue-500/20 text-blue-400 rounded-full">Latest</span>' : ''}
                    <span class="text-slate-500 text-xs">${escapeHtml(release.date)}</span>
                </div>
                <ul class="space-y-1.5 pl-2">${items}</ul>
            </div>`;
    }).join('');

    if (lastUpdated) lastUpdated.textContent = `Last updated: ${data.lastUpdated || '-'}`;

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
}

/** 배경(backdrop)을 눌렀을 때만 닫는다 — 내용 영역 클릭으로 닫히면 안 된다 */
function closeChangelogModal(event) {
    if (event && event.target !== event.currentTarget) return;
    const modal = document.getElementById('changelogModal');
    if (modal) modal.classList.add('hidden');
    document.body.style.overflow = '';
}

/** 헤더의 버전 배지를 version.json 값으로 채운다 (HTML 하드코딩 방지) */
function syncVersionBadge() {
    const badge = document.getElementById('versionBadge');
    const data = getVersionData();
    if (badge && data?.version) badge.textContent = `v${data.version}`;
}

// ============================================
// 보안 경고 배너
// ============================================

/** 입력값이 브라우저에만 남는다는 점을 알린다. 닫으면 세션 동안 다시 뜨지 않는다. */
function showSecurityWarning() {
    if (sessionStorage.getItem('wizardSecurityWarningClosed') === '1') return;
    const el = document.getElementById('securityWarning');
    if (el) el.classList.remove('hidden');
}

function closeSecurityWarning() {
    const el = document.getElementById('securityWarning');
    if (el) el.classList.add('hidden');
    try {
        sessionStorage.setItem('wizardSecurityWarningClosed', '1');
    } catch (err) {
        /* 세션 저장 실패는 무시 — 배너만 닫히면 된다 */
    }
}

// ============================================
// 다운로드
// ============================================

/** Blob을 파일로 저장 (3종 공통 다운로드 진입점) */
function triggerDownload(blob, fileName) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
}
