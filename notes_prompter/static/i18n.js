/* Only explicit source-code messages are translated. User text is never inspected. */
window.NPI18n = Object.freeze({
  language: window.NP_LANGUAGE || 'en',
  t(message, ...values) {
    const translated = Object.prototype.hasOwnProperty.call(window.NP_MESSAGES || {}, message) ? window.NP_MESSAGES[message] : message;
    return translated.replace(/\{(\d+)\}/g, (match, index) => index < values.length ? String(values[index]) : match);
  },
});
