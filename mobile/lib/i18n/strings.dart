/// Interface text lookup for English and Hindi.
///
/// Keys are the web app's dotted keys (e.g. `result.verdict.scam`), so the wording is shared
/// verbatim with web/src/i18n. Keys starting with `mobile.` are app-only strings
/// (lib/i18n/mobile_strings.dart). A missing key is a programming error and throws, and a test
/// checks that every key used in lib/ exists in both languages.
library;

import 'package:flutter/widgets.dart';

import '../config/limits.dart';
import '../generated/web_data.g.dart';
import 'mobile_strings.dart';

/// Interface languages, matching the web app's EN | हिंदी switch.
enum UiLanguage { en, hi }

class Strings {
  const Strings(this.language);

  final UiLanguage language;

  /// The strings for the current locale (Hindi when the locale's language is `hi`).
  static Strings of(BuildContext context) => Strings(languageFor(Localizations.localeOf(context)));

  static UiLanguage languageFor(Locale locale) => locale.languageCode == 'hi' ? UiLanguage.hi : UiLanguage.en;

  bool get isHindi => language == UiLanguage.hi;

  Object _raw(String key) {
    final map = key.startsWith('mobile.') ? (isHindi ? mobileHi : mobileEn) : (isHindi ? webHi : webEn);
    final value = map[key];
    if (value == null) throw ArgumentError.value(key, 'key', 'Unknown interface-text key');
    return value;
  }

  /// A single string, with `{name}` placeholders filled from [values].
  String t(String key, [Map<String, Object> values = const {}]) {
    final value = _raw(key);
    if (value is! String) throw ArgumentError.value(key, 'key', 'Not a single string');
    return fmt(value, values);
  }

  /// A list of strings (bullet lists such as `about.steps`).
  List<String> list(String key) {
    final value = _raw(key);
    if (value is! List<String>) throw ArgumentError.value(key, 'key', 'Not a list');
    return value;
  }

  /// Friendly message for an API or client error code. Mirrors web/src/lib/errors.ts.
  String errorMessage(String code, {int? retryAfterS}) {
    if (code == 'rate_limited') {
      return retryAfterS != null && retryAfterS > 0
          ? t('errors.rate_limited', {'seconds': retryAfterS})
          : t('errors.rate_limited_generic');
    }
    if (code == 'text_too_long') return t('errors.text_too_long', {'max': maxTextChars});
    // Web wording that talks about "this site" or "your browser" has an app version.
    if (code == 'not_configured' || code == 'length_required') return t('mobile.errors.$code');
    if (code.startsWith('mobile.')) return t(code);
    return knownErrorCodes.contains(code) ? t('errors.$code') : t('errors.unknown_error');
  }
}

/// Every error code the API documents (api/main.py, src/ocr/validate.py) plus client codes.
/// Unknown codes fall back to a generic message instead of showing raw server text.
const Set<String> knownErrorCodes = {
  'empty_text', 'text_too_long', 'too_large', 'body_too_large', 'unsupported_type', 'corrupt',
  'too_small', 'too_many_pixels', 'empty', 'no_text_found', 'invalid_request', 'length_required',
  'rate_limited', 'busy', 'timeout', 'classifier_unavailable', 'ocr_unavailable',
  'feedback_not_configured', 'feedback_storage_error', 'unknown_prediction', 'internal_error',
  // client-side
  'network_error', 'client_timeout', 'not_configured', 'unknown_error',
};

/// Errors where trying the same request again later can succeed.
bool isRetryable(String code) => const {
  'rate_limited',
  'busy',
  'timeout',
  'client_timeout',
  'network_error',
  'internal_error',
  'feedback_storage_error',
}.contains(code);

/// Replace `{name}` placeholders. Unknown placeholders are left as they are.
String fmt(String template, Map<String, Object> values) =>
    template.replaceAllMapped(RegExp(r'\{(\w+)\}'), (m) => values.containsKey(m[1]) ? '${values[m[1]]}' : m[0]!);
