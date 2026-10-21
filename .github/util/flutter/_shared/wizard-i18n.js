/* ===================================================================
 * projectops HTML 마법사 언어 전환 (정본, #769)
 * ===================================================================
 *
 * 로드하는 쪽: Flutter 마법사 3종 + common 마법사(projects-sync, secrets-converter)
 *   Flutter: wizard.css > wizard-i18n.js > wizard-common.js > <name>-wizard-i18n.js > <name>-wizard.js
 *   common : ../../flutter/_shared/wizard-i18n.js > <name>-i18n.js > <name>.js
 *
 * 문구 원본 2곳
 *   - 정적 마크업: HTML 본문의 영문이 en 원본. data-i18n 요소의 처음 내용을 en으로 기억
 *   - 그 외(토스트·동적 렌더): registerWizardMessages 사전의 en/ko
 *   ko 문구는 전부 사전에 둔다. 키 누락은 check-consistency.py 가 잡는다.
 *
 * 마크업 계약
 *   data-i18n="key"             내용(innerHTML) 교체
 *   data-i18n-placeholder="key" placeholder 교체
 *   data-i18n-title="key"       title 교체
 *   data-lang-toggle            언어 전환 버튼 (엔진이 라벨 채우고 hidden 해제)
 *
 * 언어 결정 순서: 주소 ?lang=en|ko > 저장된 선택 > navigator.language 가 ko* 면 ko > en
 * 변경 시 document 에 'wizardlanguagechange' 이벤트 — 동적 영역은 각 마법사가 다시 그린다
 *
 * common 마법사가 wizard-common.js 대신 이 파일만 로드하는 이유:
 *   common 쪽에 같은 이름·다른 시그니처 함수(showToast·processFile·setupDragAndDrop 등)가 있어
 *   공통 유틸까지 끌어오면 덮어쓰기 관계가 꼬인다. 언어 전환만 떼어 둔다.
 * =================================================================== */

/* eslint-disable no-unused-vars */

const WIZARD_LANGUAGES = ['en', 'ko'];
const WIZARD_DEFAULT_LANGUAGE = 'en';
// localStorage: 마법사 공통 언어 선택 (en | ko)
const WIZARD_LANGUAGE_STORAGE_KEY = 'projectops.wizard.language';
// 버튼 라벨은 "바꿀 언어" 이름을 보여준다
const WIZARD_LANGUAGE_TOGGLE_LABELS = { en: '한국어', ko: 'English' };

const wizardMessagesByLanguage = { en: {}, ko: {} };
// data-i18n 요소 > 처음 영문 내용·속성 (en 복원용)
const wizardOriginalContentByElement = new WeakMap();
let wizardCurrentLanguage = null;

/** 사전 등록 (같은 키는 나중 등록이 이긴다) */
function registerWizardMessages(messages) {
    WIZARD_LANGUAGES.forEach((language) => {
        Object.assign(wizardMessagesByLanguage[language], (messages && messages[language]) || {});
    });
}

function isSupportedWizardLanguage(language) {
    return WIZARD_LANGUAGES.includes(language);
}

/** 저장 읽기 실패(사생활 모드·file:// 차단)는 선택 없음으로 처리 */
function readSavedWizardLanguage() {
    try {
        const saved = localStorage.getItem(WIZARD_LANGUAGE_STORAGE_KEY);
        return isSupportedWizardLanguage(saved) ? saved : null;
    } catch (err) {
        return null;
    }
}

function saveWizardLanguage(language) {
    try {
        localStorage.setItem(WIZARD_LANGUAGE_STORAGE_KEY, language);
    } catch (err) {
        /* 저장 실패해도 이번 화면 전환은 유지 */
    }
}

/** 주소 ?lang= 값 (링크 공유·헤드리스 검증용, 저장하지 않음) */
function readWizardLanguageFromUrl() {
    try {
        const requested = new URLSearchParams(window.location.search).get('lang');
        return isSupportedWizardLanguage(requested) ? requested : null;
    } catch (err) {
        return null;
    }
}

/** 주소 ?lang= > 저장된 선택 > 브라우저 언어(ko*) > en */
function detectInitialWizardLanguage() {
    const requested = readWizardLanguageFromUrl();
    if (requested) return requested;
    const saved = readSavedWizardLanguage();
    if (saved) return saved;
    const browserLanguage = String(navigator.language || (navigator.languages && navigator.languages[0]) || '');
    return browserLanguage.toLowerCase().startsWith('ko') ? 'ko' : WIZARD_DEFAULT_LANGUAGE;
}

function getWizardLanguage() {
    if (!wizardCurrentLanguage) wizardCurrentLanguage = detectInitialWizardLanguage();
    return wizardCurrentLanguage;
}

/**
 * 키 > 현재 언어 문구 (없으면 en > 키 그대로)
 * {name} 자리표시자를 params 값으로 치환
 */
function translate(key, params) {
    const language = getWizardLanguage();
    let message = wizardMessagesByLanguage[language][key];
    if (message == null) message = wizardMessagesByLanguage[WIZARD_DEFAULT_LANGUAGE][key];
    if (message == null) message = key;
    if (!params) return message;
    return message.replace(/\{(\w+)\}/g, (placeholder, name) => (
        Object.prototype.hasOwnProperty.call(params, name) ? String(params[name]) : placeholder
    ));
}

/** 처음 본 요소의 영문 내용·속성 기억 (교체 전 1회) */
function rememberOriginalWizardContent(element) {
    if (wizardOriginalContentByElement.has(element)) return wizardOriginalContentByElement.get(element);
    const original = {
        html: element.innerHTML,
        placeholder: element.getAttribute('placeholder'),
        title: element.getAttribute('title'),
    };
    wizardOriginalContentByElement.set(element, original);
    return original;
}

/** ko 는 사전 값, en 은 HTML 원문 (사전에 없으면 원문 유지) */
function resolveWizardText(key, originalText, language) {
    if (language === WIZARD_DEFAULT_LANGUAGE) return originalText;
    const message = wizardMessagesByLanguage[language][key];
    return message == null ? originalText : message;
}

/** data-i18n* 요소 전부에 현재 언어 적용 */
function applyWizardTranslations(rootElement) {
    const root = rootElement || document;
    const language = getWizardLanguage();
    const selector = '[data-i18n], [data-i18n-placeholder], [data-i18n-title]';
    root.querySelectorAll(selector).forEach((element) => {
        const original = rememberOriginalWizardContent(element);
        const contentKey = element.getAttribute('data-i18n');
        const placeholderKey = element.getAttribute('data-i18n-placeholder');
        const titleKey = element.getAttribute('data-i18n-title');
        if (contentKey) element.innerHTML = resolveWizardText(contentKey, original.html, language);
        if (placeholderKey) element.setAttribute('placeholder', resolveWizardText(placeholderKey, original.placeholder || '', language));
        if (titleKey) element.setAttribute('title', resolveWizardText(titleKey, original.title || '', language));
    });
    document.documentElement.lang = language;
    updateWizardLanguageToggles();
}

/** 전환 버튼: 바꿀 언어 이름 표시 > 숨김 해제 */
function updateWizardLanguageToggles() {
    const language = getWizardLanguage();
    document.querySelectorAll('[data-lang-toggle]').forEach((button) => {
        button.textContent = WIZARD_LANGUAGE_TOGGLE_LABELS[language];
        button.setAttribute('aria-label', language === 'ko' ? 'Switch to English' : '한국어로 전환');
        button.classList.remove('hidden');
    });
}

/** 언어 변경: 저장 > 정적 문구 적용 > 동적 영역 다시 그리기 알림 */
function setWizardLanguage(language) {
    if (!isSupportedWizardLanguage(language)) return;
    wizardCurrentLanguage = language;
    saveWizardLanguage(language);
    applyWizardTranslations();
    document.dispatchEvent(new CustomEvent('wizardlanguagechange', { detail: { language } }));
}

function toggleWizardLanguage() {
    setWizardLanguage(getWizardLanguage() === 'ko' ? 'en' : 'ko');
}

// 최초 적용: 사전 파일·마법사 JS 가 모두 로드된 뒤 (본문 끝 script 기준 DOMContentLoaded)
document.addEventListener('DOMContentLoaded', () => applyWizardTranslations());

// 공통 유틸(wizard-common.js) 문구 — 3종이 함께 쓰는 토스트·커스텀 Secret UI
registerWizardMessages(
{
  "en": {
    "common.copied": "Copied",
    "common.commandCopied": "Command copied",
    "common.copiedButton": "✅ Copied",
    "common.copyFailed": "Copy failed. Please select the text and copy it manually.",
    "common.fileReadFailed": "Could not read the file",
    "common.stateSaveFailed": "Could not save your progress (browser storage is full)",
    "common.versionLoadFailed": "Could not load version information.",
    "common.textHint": "Use with cat <<EOF > file",
    "common.binaryHint": "Use with echo $SECRET | base64 -d > file",
    "common.uploadDone": "✅ {fileName} uploaded ({fileType})",
    "common.fileTypeText": "text",
    "common.uploadFailed": "❌ Could not read the file: {message}",
    "common.secretValueCopied": "✅ Copied the value of {key}",
    "common.clipboardFailed": "❌ Could not copy to the clipboard",
    "common.remove": "✕ Remove",
    "common.secretName": "Secret name",
    "common.chooseFile": "📁 Choose a file or click",
    "common.copyValue": "Copy value",
    "common.customSecretDescription": "Added by you ({fileName})"
  },
  "ko": {
    "common.copied": "복사되었습니다",
    "common.commandCopied": "명령어가 복사되었습니다",
    "common.copiedButton": "✅ 복사됨",
    "common.copyFailed": "복사에 실패했습니다. 직접 선택해 복사해주세요.",
    "common.fileReadFailed": "파일을 읽지 못했습니다",
    "common.stateSaveFailed": "진행 상황을 저장하지 못했습니다 (브라우저 저장 공간 부족)",
    "common.versionLoadFailed": "버전 정보를 불러올 수 없습니다.",
    "common.textHint": "cat <<EOF > file 로 사용",
    "common.binaryHint": "echo $SECRET | base64 -d > file 로 사용",
    "common.uploadDone": "✅ {fileName} 업로드 완료 ({fileType})",
    "common.fileTypeText": "텍스트",
    "common.uploadFailed": "❌ 파일 읽기 실패: {message}",
    "common.secretValueCopied": "✅ {key} 값 복사됨",
    "common.clipboardFailed": "❌ 클립보드 복사 실패",
    "common.remove": "✕ 삭제",
    "common.secretName": "Secret 이름",
    "common.chooseFile": "📁 파일 선택 또는 클릭",
    "common.copyValue": "값 복사",
    "common.customSecretDescription": "사용자 추가 ({fileName})"
  }
}
);
