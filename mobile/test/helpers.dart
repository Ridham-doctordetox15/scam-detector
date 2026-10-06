/// Shared test fakes: a scripted HTTP client, picker and share receiver, plus sample responses.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:scamchecker/api/api_client.dart';
import 'package:scamchecker/app.dart';
import 'package:scamchecker/config/api_config.dart';
import 'package:scamchecker/platform/screenshot_picker.dart';
import 'package:scamchecker/platform/share_receiver.dart';
import 'package:scamchecker/state/controllers.dart';

/// A full /analyze response, as the real API returns it (api/schemas.py).
Map<String, Object?> analyzeJson({
  String verdict = 'scam',
  String risk = 'high',
  String language = 'en',
  List<String>? redFlags,
  String explanation = 'This message threatens to block your account and asks you to open a link.',
  List<String>? whatToDo,
  String? pattern = 'fake_kyc_update',
  List<Map<String, Object?>>? urls,
  Map<String, Object?>? ocr,
  String inputType = 'text',
  String explainer = 'groq',
}) => {
  'prediction_id': '7d3c1a52-1111-4a5b-9c9d-000000000001',
  'input_type': inputType,
  'verdict': verdict,
  'risk_level': risk,
  'red_flags': redFlags ?? ['Threatens to block your account', 'Link to an unknown website'],
  'explanation': explanation,
  'what_to_do': whatToDo ?? ['Do not open the link.', 'Call your bank on the number on your card.'],
  'matched_pattern': pattern,
  'url_findings':
      urls ??
      [
        {
          'url_defanged': 'hxxp://sbi-kyc-verify[.]tk/update',
          'risk_band': 'high',
          'reasons': ['Risky domain ending (.tk)', 'Brand name in an unrelated domain'],
        },
      ],
  'explainer_path': explainer,
  'language': language,
  'classifier_model': 'tfidf_svm',
  'timings_ms': {'total': 4321.5, 'classifier': 12.25},
  'ocr': ocr,
  'disclaimer': 'Automated assessment.',
};

/// Records requests and answers them from [handler].
class FakeApi {
  FakeApi({FutureOr<http.Response> Function(http.Request request)? handler})
    : _handler = handler ?? ((r) => defaultHandler(r));

  final FutureOr<http.Response> Function(http.Request request) _handler;
  final List<http.Request> requests = [];

  static http.Response json(Object body, {int status = 200, Map<String, String> headers = const {}}) =>
      http.Response.bytes(
        utf8.encode(jsonEncode(body)),
        status,
        headers: {'content-type': 'application/json', ...headers},
      );

  /// Healthy server that says "scam / high" to every analysis and accepts feedback.
  static http.Response defaultHandler(http.Request r) {
    if (r.url.path == '/health') return json({'status': 'ok', 'components': <String, Object>{}});
    if (r.url.path == '/feedback') return json({'prediction_id': 'x', 'status': 'saved'}, status: 201);
    return json(analyzeJson());
  }

  ApiClient client({ApiConfig config = const ApiConfig.forUrl('http://test.local')}) => ApiClient(
    config: config,
    httpClient: MockClient((request) async {
      requests.add(request);
      return _handler(request);
    }),
  );

  List<http.Request> to(String path) => requests.where((r) => r.url.path == path).toList();
}

/// Returns pre-set bytes (or null = cancelled).
class FakePicker implements ScreenshotPicker {
  FakePicker([this.result]);
  Uint8List? result;
  int calls = 0;

  @override
  Future<Uint8List?> pick() async {
    calls++;
    return result;
  }
}

/// A share receiver driven by the test.
class FakeShareReceiver implements ShareReceiver {
  FakeShareReceiver({this.initial});

  SharedItem? initial;
  final StreamController<SharedItem> controller = StreamController<SharedItem>.broadcast();

  @override
  Future<SharedItem?> initialShare() async {
    final item = initial;
    initial = null;
    return item;
  }

  @override
  Stream<SharedItem> get shares => controller.stream;

  @override
  void dispose() => controller.close();
}

/// A tiny valid PNG header (the app only sniffs magic bytes; the API decodes the image).
final Uint8List pngBytes = Uint8List.fromList([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13]);

/// Pumps the whole app with fakes. Use [locale] to start in Hindi.
Future<FakeApi> pumpApp(
  WidgetTester tester, {
  FakeApi? api,
  FakePicker? picker,
  FakeShareReceiver? share,
  Locale? locale,
  ThemeMode themeMode = ThemeMode.light,
  ApiConfig config = const ApiConfig.forUrl('http://test.local'),
  bool settle = true,
  double width = 393,
}) async {
  // Phone width (1080 px at 2.75x = 393 logical pixels, so overflow at phone width is caught),
  // but very tall, so taps never depend on scrolling a lazily built list.
  tester.view.physicalSize = Size(width * 2.75, 8250);
  tester.view.devicePixelRatio = 2.75;
  addTearDown(tester.view.reset);
  final fake = api ?? FakeApi();
  final settings = AppSettings()
    ..locale = locale
    ..themeMode = themeMode;
  addTearDown(settings.dispose);
  await tester.pumpWidget(
    ScamCheckerApp(
      api: fake.client(config: config),
      picker: picker ?? FakePicker(),
      shareReceiver: share ?? FakeShareReceiver(),
      settings: settings,
    ),
  );
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    await tester.pump();
  }
  return fake;
}

/// Every string shown by Text / RichText / SelectableText under [root] (or the whole tree).
List<String> visibleTexts(WidgetTester tester, {Finder? root}) {
  final texts = <String>[];
  final finder = root == null
      ? find.byWidgetPredicate((w) => w is RichText || w is EditableText)
      : find.descendant(of: root, matching: find.byWidgetPredicate((w) => w is RichText || w is EditableText));
  for (final widget in tester.widgetList(finder)) {
    if (widget is RichText) texts.add(widget.text.toPlainText());
    if (widget is EditableText) texts.add(widget.controller.text);
  }
  return texts;
}

/// The page's own scroll view (a TextField has a Scrollable inside it too, so take the outermost).
Finder get pageScrollable => find.byType(Scrollable).first;

/// Scrolls the page until [finder] can be tapped (and lays out the new scroll position).
Future<void> scrollTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 150, scrollable: pageScrollable);
  await tester.pump();
}

/// Scrolls to [finder], taps it and pumps one frame (callers settle when nothing is pending).
Future<void> tapOn(WidgetTester tester, Finder finder) async {
  await scrollTo(tester, finder);
  await tester.tap(finder);
  await tester.pump();
}
