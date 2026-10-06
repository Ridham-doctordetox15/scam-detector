/// Small text helpers shared by several screens.
library;

import 'package:flutter/painting.dart';

import '../api/models.dart';

/// Line height for Devanagari text, same as the web app (globals.css, `:lang(hi)`).
const double devanagariLineHeight = 1.75;

/// Line height for Latin text.
const double latinLineHeight = 1.5;

final RegExp _devanagari = RegExp('[ऀ-ॿ]');

/// True when [text] contains any Devanagari character.
bool hasDevanagari(String text) => _devanagari.hasMatch(text);

/// Length the way the API counts it (Python `len`: Unicode code points), so emoji are not
/// double-counted against the 5000 limit.
int charCount(String text) => text.runes.length;

/// Style for API content (red flags, explanation, advice): Devanagari typography only when the
/// content is Hindi. Hinglish is Hindi in Latin script, so it keeps the Latin line height.
TextStyle contentStyle(TextStyle? base, ContentLanguage language) => (base ?? const TextStyle()).copyWith(
  height: language == ContentLanguage.hi ? devanagariLineHeight : latinLineHeight,
);

/// `http://sbi-kyc.tk/x` -> `hxxp://sbi-kyc[.]tk/x`. Same rule as the API's `defang_url`
/// (api/schemas.py): the scheme becomes hxxp(s) and the dots of the host become `[.]`.
String defangUrl(String url) {
  final sep = url.indexOf('://');
  var scheme = '', rest = url, mark = '';
  if (sep >= 0) {
    scheme = url.substring(0, sep);
    mark = '://';
    rest = url.substring(sep + 3);
    scheme = const {'http': 'hxxp', 'https': 'hxxps'}[scheme.toLowerCase()] ?? scheme;
  }
  final slash = rest.indexOf('/');
  final host = slash < 0 ? rest : rest.substring(0, slash);
  final path = slash < 0 ? '' : rest.substring(slash);
  // Dots already written as "[.]" stay as they are, so defanging twice changes nothing.
  return '$scheme$mark${host.replaceAll(RegExp(r'(?<!\[)\.(?!\])'), '[.]')}$path';
}

/// Links written in free text: anything with a scheme or `www.`, plus bare domains on common
/// endings (`sbi-update.top/pay`). Sentence dots such as "e.g." are not matched.
final RegExp _linkInText = RegExp(
  r'(?:\b[a-z][a-z0-9+.-]*://|\bwww\.)[^\s<>"]+'
  r'|\b(?:[a-z0-9-]+\.)+(?:com|in|net|org|co|io|info|biz|xyz|top|tk|ml|ga|cf|gq|ly|me|link|click|online|site|live|app|cc|ru|cn|shop|store|club|vip|win|icu|buzz|gov|edu|bank)\b(?:/[^\s<>"]*)?',
  caseSensitive: false,
);

/// Trailing characters that end a sentence rather than a link.
final RegExp _linkTail = RegExp(r'[.,;:!?)\]]+$');

/// [text] with every link in it defanged (used for text read from a screenshot, so no link in
/// the app is ever shown in a form that can be copied into a browser as-is).
String defangLinksInText(String text) => text.replaceAllMapped(_linkInText, (m) {
  final link = m[0]!;
  final tail = _linkTail.firstMatch(link)?.group(0) ?? '';
  return defangUrl(link.substring(0, link.length - tail.length)) + tail;
});

/// Style for text whose language we don't know (e.g. text read from a screenshot).
TextStyle guessedStyle(TextStyle? base, String text) =>
    (base ?? const TextStyle()).copyWith(height: hasDevanagari(text) ? devanagariLineHeight : latinLineHeight);
