// 워크플로우 댓글 문구 런타임 (#769): github-script 스텝이 require 해서 쓴다.
// messages.py js 가 이 파일 앞에 `const DATA = {lang, messages}` 를 붙여 $RUNNER_TEMP 에 쓴다.
// 치환 문법은 messages.py 와 같다: {name}, 값이 없으면 자리표시자를 그대로 둔다.
const PLACEHOLDER = /\{([A-Za-z_][A-Za-z0-9_]*)\}/g;

// 키 > 문구 (없는 키는 키 문자열 — 문구 하나 때문에 빌드가 죽으면 안 된다)
function t(key, values = {}) {
  const text = Object.prototype.hasOwnProperty.call(DATA.messages, key) ? DATA.messages[key] : key;
  return text.replace(PLACEHOLDER, (m, name) => (name in values ? String(values[name]) : m));
}

// 분·초 > "1분 2초" / "1m 2s" (분이 0 이면 초만). 계산은 호출부가 기존 방식 그대로 한다
function elapsed(minutes, seconds) {
  return minutes > 0
    ? t('comment.elapsed.min_sec', { minutes, seconds })
    : t('comment.elapsed.sec', { seconds });
}

module.exports = { t, elapsed, lang: DATA.lang };
