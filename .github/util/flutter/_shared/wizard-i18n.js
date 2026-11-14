/* ===================================================================
 * projectops HTML wizard language switch (source of truth, #769)
 * ===================================================================
 *
 * Loaded by: the Flutter wizards + common wizards (projects-sync, secrets-converter)
 *   Flutter: wizard.css > wizard-i18n.js > wizard-common.js > <name>-wizard-i18n.js > <name>-wizard.js
 *   common : ../../flutter/_shared/wizard-i18n.js > <name>-i18n.js > <name>.js
 *
 * 2 text sources
 *   - Static markup: the English in the HTML body is the en source. The initial content of data-i18n elements is remembered as en
 *   - Everything else (toasts, dynamic rendering): en/ko in the registerWizardMessages dictionary
 *   All ko text lives in dictionaries. check-consistency.py catches missing keys.
 *
 * Markup contract
 *   data-i18n="key"             replaces content (innerHTML)
 *   data-i18n-placeholder="key" replaces placeholder
 *   data-i18n-title="key"       replaces title
 *   data-lang-toggle            language toggle button (the engine fills the label and removes hidden)
 *
 * Language order: address ?lang=en|ko > saved choice > ko if navigator.language is ko* > en
 * On change, a 'wizardlanguagechange' event on document — each wizard redraws its dynamic areas
 *
 * Why common wizards load only this file instead of wizard-common.js:
 *   the common side has functions with the same names but different signatures (showToast, processFile, setupDragAndDrop, etc.),
 *   so pulling in the shared utils too would tangle overrides. Only the language switch is split out.
 * =================================================================== */

/* eslint-disable no-unused-vars */

const WIZARD_LANGUAGES = ['en', 'ko'];
const WIZARD_DEFAULT_LANGUAGE = 'en';
// localStorage: shared wizard language choice (en | ko)
const WIZARD_LANGUAGE_STORAGE_KEY = 'projectops.wizard.language';
// The button label shows the name of the language to switch to
const WIZARD_LANGUAGE_TOGGLE_LABELS = { en: '한국어', ko: 'English' };

const wizardMessagesByLanguage = { en: {}, ko: {} };
// data-i18n element > initial English content/attributes (for restoring en)
const wizardOriginalContentByElement = new WeakMap();
let wizardCurrentLanguage = null;

/** Register a dictionary (for the same key, the later registration wins) */
function registerWizardMessages(messages) {
    WIZARD_LANGUAGES.forEach((language) => {
        Object.assign(wizardMessagesByLanguage[language], (messages && messages[language]) || {});
    });
}

function isSupportedWizardLanguage(language) {
    return WIZARD_LANGUAGES.includes(language);
}

/** Treat a failed storage read (private mode, file:// blocked) as no choice */
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
        /* Keep this screen's switch even if saving fails */
    }
}

/** Address ?lang= value (for sharing links and headless checks; not saved) */
function readWizardLanguageFromUrl() {
    try {
        const requested = new URLSearchParams(window.location.search).get('lang');
        return isSupportedWizardLanguage(requested) ? requested : null;
    } catch (err) {
        return null;
    }
}

/** Address ?lang= > saved choice > browser language (ko*) > en */
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
 * key > text in the current language (else en > the key itself)
 * Replace {name} placeholders with params values
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

/** Remember an element's English content/attributes the first time (once before replacing) */
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

/** ko uses the dictionary value, en the HTML source (keeps the source if not in the dictionary) */
function resolveWizardText(key, originalText, language) {
    if (language === WIZARD_DEFAULT_LANGUAGE) return originalText;
    const message = wizardMessagesByLanguage[language][key];
    return message == null ? originalText : message;
}

/** data-i18n* Apply the current language to every data-i18n* element */
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

/** Toggle button: show the name of the language to switch to > unhide */
function updateWizardLanguageToggles() {
    const language = getWizardLanguage();
    document.querySelectorAll('[data-lang-toggle]').forEach((button) => {
        button.textContent = WIZARD_LANGUAGE_TOGGLE_LABELS[language];
        button.setAttribute('aria-label', language === 'ko' ? 'Switch to English' : '한국어로 전환');
        button.classList.remove('hidden');
    });
}

/** Language change: save > apply static text > notify to redraw dynamic areas */
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

// First application: after the dictionary files and wizard JS have loaded (DOMContentLoaded for scripts at the end of body)
document.addEventListener('DOMContentLoaded', () => applyWizardTranslations());

// Shared util (wizard-common.js) text — toasts and custom Secret UI used by all wizards
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
