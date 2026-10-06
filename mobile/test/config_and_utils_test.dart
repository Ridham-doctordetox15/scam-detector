import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:scamchecker/api/models.dart';
import 'package:scamchecker/config/api_config.dart';
import 'package:scamchecker/platform/screenshot_picker.dart';
import 'package:scamchecker/state/controllers.dart';
import 'package:scamchecker/util/image_check.dart';
import 'package:scamchecker/util/text_utils.dart';

import 'helpers.dart';

void main() {
  group('ApiConfig', () {
    test('debug builds default to the local API (adb reverse)', () {
      final c = ApiConfig.resolve(isRelease: false, target: '', urlOverride: '');
      expect(c.baseUrl, 'http://127.0.0.1:7860');
    });

    test('release builds use the deployed URL', () {
      final c = ApiConfig.resolve(isRelease: true, target: '', urlOverride: '', deployed: 'https://x.hf.space/');
      expect(c.baseUrl, 'https://x.hf.space'); // trailing slash removed
    });

    test('release with no deployed URL is "not configured"', () {
      final c = ApiConfig.resolve(isRelease: true, target: '', urlOverride: '', deployed: '');
      expect(c.isConfigured, isFalse);
      expect(c.problem, ApiConfigProblem.notConfigured);
    });

    test('release builds refuse plain HTTP, even as an override', () {
      expect(
        ApiConfig.resolve(isRelease: true, target: '', urlOverride: '', deployed: 'http://x.hf.space').problem,
        ApiConfigProblem.insecureInRelease,
      );
      expect(
        ApiConfig.resolve(isRelease: true, target: '', urlOverride: 'http://192.168.1.5:7860').problem,
        ApiConfigProblem.insecureInRelease,
      );
    });

    test('debug can use another address via API_URL, or the deployed one via API_TARGET', () {
      expect(
        ApiConfig.resolve(isRelease: false, target: '', urlOverride: 'http://192.168.1.5:7860').baseUrl,
        'http://192.168.1.5:7860',
      );
      expect(
        ApiConfig.resolve(isRelease: false, target: 'deployed', urlOverride: '', deployed: 'https://a.b').baseUrl,
        'https://a.b',
      );
    });

    test('garbage addresses are rejected', () {
      for (final bad in ['ftp://x', 'not a url', 'https://']) {
        expect(
          ApiConfig.resolve(isRelease: false, target: '', urlOverride: bad).isConfigured,
          isFalse,
          reason: bad,
        );
      }
    });

    test('the checked-in deployed URL is empty or HTTPS', () {
      expect(deployedApiUrl.isEmpty || deployedApiUrl.startsWith('https://'), isTrue);
    });
  });

  group('image checks (same rules as src/ocr/validate.py)', () {
    test('PNG, JPEG and WebP are recognised from magic bytes', () {
      expect(sniffImageFormat(pngBytes), ImageFormat.png);
      expect(sniffImageFormat(Uint8List.fromList([0xFF, 0xD8, 0xFF, 0xE0])), ImageFormat.jpeg);
      expect(
        sniffImageFormat(Uint8List.fromList([...'RIFF'.codeUnits, 0, 0, 0, 0, ...'WEBP'.codeUnits])),
        ImageFormat.webp,
      );
    });

    test('other files, empty files and files over 5 MB are refused', () {
      expect(validateImageBytes(Uint8List(0)), 'empty');
      expect(validateImageBytes(Uint8List.fromList('GIF89a'.codeUnits)), 'unsupported_type');
      // HEIC (ftyp box), the format of many phone photos
      expect(validateImageBytes(Uint8List.fromList([0, 0, 0, 24, ...'ftypheic'.codeUnits])), 'unsupported_type');
      final big = Uint8List(5 * 1024 * 1024 + 1)..setAll(0, pngBytes);
      expect(validateImageBytes(big), 'too_large');
      expect(validateImageBytes(pngBytes), isNull);
    });
  });

  group('input validation', () {
    test('empty and too-long text are caught before sending', () {
      expect(validateInput(const TextAnalysis('   ')), 'empty_text');
      expect(validateInput(TextAnalysis('a' * 5001)), 'text_too_long');
      expect(validateInput(TextAnalysis('a' * 5000)), isNull);
    });

    test('characters are counted like the API (code points, not UTF-16 units)', () {
      expect(charCount('😀😀'), 2);
      expect(validateInput(TextAnalysis('😀' * 5000)), isNull);
    });
  });

  group('typography', () {
    test('Hindi content gets line height 1.75, Hinglish and English 1.5', () {
      expect(contentStyle(null, ContentLanguage.hi).height, 1.75);
      expect(contentStyle(null, ContentLanguage.hinglish).height, 1.5);
      expect(contentStyle(null, ContentLanguage.en).height, 1.5);
    });

    test('text of unknown language gets 1.75 when it contains Devanagari', () {
      expect(guessedStyle(null, 'आपका खाता बंद').height, 1.75);
      expect(guessedStyle(null, 'Your account is blocked').height, 1.5);
    });
  });

  group('picker cleanup only ever deletes our own cache copy', () {
    test('cache paths of this app are recognised', () {
      expect(isOwnCacheCopy('/data/user/0/io.github.ridhamsd1.scamchecker/cache/abc/image.png'), isTrue);
      expect(isOwnCacheCopy('/data/data/io.github.ridhamsd1.scamchecker/cache/x.jpg'), isTrue);
    });

    test('anything else is never deleted', () {
      for (final path in [
        '/storage/emulated/0/DCIM/Screenshots/shot.png',
        '/data/user/0/com.whatsapp/cache/x.jpg',
        '/data/user/0/io.github.ridhamsd1.scamchecker/files/x.png',
        '/data/user/0/io.github.ridhamsd1.scamchecker/cache/../files/x.png',
      ]) {
        expect(isOwnCacheCopy(path), isFalse, reason: path);
      }
    });
  });

  group('models', () {
    test('only the displayed fields are parsed; numeric fields have nowhere to go', () {
      final json = analyzeJson()..addAll({'probability': 0.97, 'score': 97, 'confidence': 0.9});
      final r = AnalyzeResponse.fromJson(json);
      expect(r.verdict, Verdict.scam);
      expect(r.urlFindings.single.urlDefanged, 'hxxp://sbi-kyc-verify[.]tk/update');
    });

    test('missing language falls back to English; unknown verdict is rejected', () {
      expect(AnalyzeResponse.fromJson(analyzeJson()..remove('language')).language, ContentLanguage.en);
      expect(() => AnalyzeResponse.fromJson(analyzeJson(verdict: 'maybe')), throwsA(isA<FormatError>()));
    });
  });
}
