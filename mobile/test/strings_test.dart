import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:scamchecker/generated/web_data.g.dart';
import 'package:scamchecker/i18n/mobile_strings.dart';
import 'package:scamchecker/i18n/strings.dart';

const en = Strings(UiLanguage.en);
const hi = Strings(UiLanguage.hi);

/// Every `t('key')` / `list('key')` / `'mobile.x'` literal in lib/, so a typo fails here, not on a phone.
Set<String> keysUsedInLib() {
  final keys = <String>{};
  final pattern = RegExp(r'''\.(?:t|list)\(\s*'([a-zA-Z0-9_.]+)'|'((?:mobile|about\.findings)\.[a-zA-Z0-9_.]+)''');
  for (final file in Directory('lib').listSync(recursive: true).whereType<File>()) {
    if (!file.path.endsWith('.dart') || file.path.contains('generated') || file.path.endsWith('mobile_strings.dart')) {
      continue;
    }
    for (final m in pattern.allMatches(file.readAsStringSync())) {
      final key = m[1] ?? m[2]!;
      if (!key.endsWith('.')) keys.add(key); // a prefix such as 'mobile.errors.' + code
    }
  }
  return keys;
}

void main() {
  test('every interface-text key used in lib/ exists in English and Hindi', () {
    final keys = keysUsedInLib();
    expect(keys.length, greaterThan(60), reason: 'the key scan found too few keys; is the regex broken?');
    for (final key in keys) {
      expect(en._has(key), isTrue, reason: 'missing in English: $key');
      expect(hi._has(key), isTrue, reason: 'missing in Hindi: $key');
    }
  });

  test('keys built at runtime (verdict, risk, errors, samples) all exist', () {
    for (final s in [en, hi]) {
      for (final v in ['safe', 'suspicious', 'scam']) {
        s.t('result.verdict.$v');
      }
      for (final r in ['low', 'medium', 'high']) {
        s.t('result.risk.$r');
        s.t('result.gaugeBand.$r');
      }
      for (final p in ['groq', 'gemini', 'template']) {
        s.t('result.explainer.$p');
      }
      for (final q in ['good', 'fair', 'poor']) {
        s.t('result.ocrQualityValue.$q');
      }
      for (final code in knownErrorCodes.difference({'unknown_error'})) {
        expect(s.errorMessage(code), isNot(s.t('errors.unknown_error')), reason: code);
      }
      for (final sample in textSamples) {
        s.t(sample.titleKey);
      }
    }
  });

  test('mobile-only strings have the same keys in English and Hindi', () {
    expect(mobileHi.keys.toSet(), mobileEn.keys.toSet());
    for (final key in mobileEn.keys) {
      expect(mobileHi[key].runtimeType, mobileEn[key].runtimeType, reason: key);
    }
  });

  test('wording is the web app\'s: generated file matches web/src/i18n (node tool/sync_web_data.mjs)', () async {
    final ProcessResult result;
    try {
      result = await Process.run('node', ['tool/sync_web_data.mjs', '--check']);
    } on ProcessException {
      markTestSkipped('Node.js is not installed; cannot compare with web/src/i18n.');
      return;
    }
    expect(result.exitCode, 0, reason: '${result.stdout}${result.stderr}');
  });

  test('error messages follow the web rules', () {
    expect(en.errorMessage('rate_limited', retryAfterS: 30), contains('30 seconds'));
    expect(en.errorMessage('rate_limited'), en.t('errors.rate_limited_generic'));
    expect(en.errorMessage('text_too_long'), contains('5000'));
    expect(en.errorMessage('something_new_from_server'), en.t('errors.unknown_error'));
    expect(en.errorMessage('network_error'), "Couldn't reach the server. Check your connection and try again.");
    // Web wording about "this site" / "your browser" is replaced in the app.
    expect(en.errorMessage('not_configured'), isNot(contains('site')));
    expect(en.errorMessage('length_required'), isNot(contains('browser')));
  });

  test('About drops exactly the website-only items', () {
    // about_screen.dart keeps the first 4 privacy points and first 3 limitations.
    expect(en.list('about.privacy').length, 5);
    expect(en.list('about.privacy').last, contains('website'));
    expect(en.list('about.privacy').take(4).any((p) => p.contains('website')), isFalse);
    expect(en.list('about.limits').length, 4);
    expect(en.list('about.limits').last, contains('website'));
    expect(en.list('about.limits').take(3).any((p) => p.contains('website')), isFalse);
  });

  test('fmt fills placeholders and leaves unknown ones', () {
    expect(fmt('{n} / {max}', {'n': 3, 'max': 5000}), '3 / 5000');
    expect(fmt('{a} {b}', {'a': 1}), '1 {b}');
  });
}

extension on Strings {
  bool _has(String key) {
    try {
      t(key);
      return true;
    } on ArgumentError {
      try {
        list(key);
        return true;
      } on ArgumentError {
        return false;
      }
    }
  }
}
