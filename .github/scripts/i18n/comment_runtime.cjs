// Workflow comment text runtime (#769): required by github-script steps.
// messages.py js prepends `const DATA = {lang, messages}` to this file and writes it to $RUNNER_TEMP.
// Same substitution syntax as messages.py: {name}; missing values leave the placeholder as is.
const PLACEHOLDER = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

// key > text (missing keys give the key string — one text must never kill a build)
function t(key, values = {}) {
  const text = Object.prototype.hasOwnProperty.call(DATA.messages, key) ? DATA.messages[key] : key;
  return text.replace(PLACEHOLDER, (m, name) => (name in values ? String(values[name]) : m));
}

// min/sec > "1분 2초" / "1m 2s" (seconds only when minutes are 0). The caller does the math as before
function elapsed(minutes, seconds) {
  return minutes > 0
    ? t('comment.elapsed.min_sec', { minutes, seconds })
    : t('comment.elapsed.sec', { seconds });
}

module.exports = { t, elapsed, lang: DATA.lang };
