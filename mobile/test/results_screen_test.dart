import 'dart:async';
import 'dart:io';

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'helpers.dart';

/// Submits [text] from Home and waits for the results screen to finish.
Future<void> check(WidgetTester tester, [String text = 'Your account will be blocked']) async {
  await tester.enterText(find.byKey(const Key('message-input')), text);
  await tapOn(tester, find.byKey(const Key('submit-text')));
  await tester.pumpAndSettle();
}

FakeApi apiAnswering(FutureOr<http.Response> Function(http.Request) analyze) =>
    FakeApi(handler: (r) => r.url.path.startsWith('/analyze') ? analyze(r) : FakeApi.defaultHandler(r));

void main() {
  group('band-only risk display', () {
    for (final (risk, verdict, verdictText, riskText, band) in [
      ('low', 'safe', 'Looks safe', 'Low risk', 'Low'),
      ('medium', 'suspicious', 'Suspicious', 'Medium risk', 'Medium'),
      ('high', 'scam', 'Likely scam', 'High risk', 'High'),
    ]) {
      testWidgets('$risk: shows the band in words and no number', (tester) async {
        final api = apiAnswering((_) => FakeApi.json(analyzeJson(verdict: verdict, risk: risk)));
        await pumpApp(tester, api: api);
        await check(tester);

        expect(find.text(verdictText), findsOneWidget);
        expect(find.text(riskText), findsOneWidget);
        // The gauge is one labelled image: "Risk level: High", not a meter with a value.
        expect(find.bySemanticsLabel('Risk level: $band'), findsOneWidget);

        // Nothing in the gauge or the verdict contains a digit or a percent sign.
        for (final key in const [Key('risk-gauge'), Key('risk-band')]) {
          for (final t in visibleTexts(tester, root: find.byKey(key))) {
            expect(t, isNot(matches(RegExp(r'[0-9%]'))), reason: 'gauge/band text "$t"');
          }
        }
      });
    }

    testWidgets('a score or probability sent by the server is never shown, nor are timings', (tester) async {
      final api = apiAnswering(
        (_) => FakeApi.json(analyzeJson()..addAll({'probability': 0.9731, 'scam_probability': 97.31, 'score': 0.88})),
      );
      await pumpApp(tester, api: api);
      await check(tester);
      final all = visibleTexts(tester).join('\n');
      for (final forbidden in ['0.9731', '97.31', '97%', '0.88', '4321', '12.25']) {
        expect(all, isNot(contains(forbidden)), reason: forbidden);
      }
    });
  });

  testWidgets('loading state shows the skeleton and message until the result arrives', (tester) async {
    final answer = Completer<http.Response>();
    final api = apiAnswering((_) => answer.future);
    await pumpApp(tester, api: api);
    await tester.enterText(find.byKey(const Key('message-input')), 'hello');
    await tapOn(tester, find.byKey(const Key('submit-text')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.byKey(const Key('result-skeleton')), findsOneWidget);
    expect(find.text('Checking the message…'), findsOneWidget);
    expect(find.byKey(const Key('check-another')), findsNothing);

    answer.complete(FakeApi.json(analyzeJson()));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('result-skeleton')), findsNothing);
    expect(find.byKey(const Key('result-card')), findsOneWidget);
  });

  testWidgets('result shows red flags, explanation, steps, pattern and who wrote it', (tester) async {
    await pumpApp(tester);
    await check(tester);
    expect(find.text('Threatens to block your account'), findsOneWidget);
    expect(find.byKey(const Key('explanation')), findsOneWidget);
    expect(find.text('Do not open the link.'), findsOneWidget);
    expect(find.textContaining('Fake KYC Update / Account Block Threat', findRichText: true), findsOneWidget);
    expect(find.textContaining('(a known scam type)', findRichText: true), findsOneWidget);
    expect(find.textContaining('Explanation written by an AI model (Groq).'), findsOneWidget);
    expect(
      find.text('The verdict and risk level come from the classifier and link checks, never from the AI.'),
      findsOneWidget,
    );
  });

  testWidgets('links are shown defanged and are not tappable links', (tester) async {
    await pumpApp(tester);
    await check(tester);
    final url = find.byKey(const Key('defanged-url'));
    await scrollTo(tester, url);
    expect(url, findsOneWidget);
    expect(tester.widget<SelectableText>(url).data, 'hxxp://sbi-kyc-verify[.]tk/update');
    // No text span anywhere carries a tap recogniser (i.e. no hyperlinks).
    for (final rich in tester.widgetList<RichText>(find.byType(RichText))) {
      rich.text.visitChildren((span) {
        expect(span is TextSpan && span.recognizer is TapGestureRecognizer, isFalse);
        return true;
      });
    }
    expect(find.text('Link risk: High risk'), findsOneWidget);
  });

  testWidgets('screenshot result shows reading quality and the extracted text on demand', (tester) async {
    final api = apiAnswering(
      (_) => FakeApi.json(
        analyzeJson(
          inputType: 'image',
          ocr: {'extracted_text': 'Dear customer your KYC', 'quality': 'fair', 'dark_mode': true},
        ),
      ),
    );
    await pumpApp(tester, api: api);
    await check(tester);
    await scrollTo(tester, find.byKey(const Key('extracted-text-toggle')));
    expect(find.textContaining('Fair - some words may be misread', findRichText: true), findsOneWidget);
    expect(find.text('Dark-mode screenshot detected'), findsOneWidget);
    await tapOn(tester, find.byKey(const Key('extracted-text-toggle')));
    await tester.pumpAndSettle();
    expect(find.text('Dear customer your KYC'), findsOneWidget);
  });

  group('error states', () {
    testWidgets('server unreachable during a check: friendly message and Try again', (tester) async {
      var fail = true;
      final api = apiAnswering((_) {
        if (fail) throw const SocketException('connection refused');
        return FakeApi.json(analyzeJson());
      });
      await pumpApp(tester, api: api);
      await check(tester);
      expect(find.text("Couldn't check that"), findsOneWidget);
      expect(find.text("Couldn't reach the server. Check your connection and try again."), findsOneWidget);

      fail = false;
      await tapOn(tester, find.byKey(const Key('retry')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('result-card')), findsOneWidget);
    });

    testWidgets('429 shows the wait time from Retry-After', (tester) async {
      final api = apiAnswering(
        (_) => FakeApi.json(
          {
            'error': {'code': 'rate_limited', 'message': '', 'request_id': 'req-42'},
          },
          status: 429,
          headers: {'retry-after': '20'},
        ),
      );
      await pumpApp(tester, api: api);
      await check(tester);
      expect(find.text('Too many checks in a short time. Please wait 20 seconds and try again.'), findsOneWidget);
      expect(find.textContaining('req-42'), findsOneWidget);
      expect(find.byKey(const Key('retry')), findsOneWidget);
    });

    testWidgets('503 classifier_unavailable: message, no retry button', (tester) async {
      final api = apiAnswering(
        (_) => FakeApi.json({
          'error': {'code': 'classifier_unavailable', 'message': ''},
        }, status: 503),
      );
      await pumpApp(tester, api: api);
      await check(tester);
      expect(find.text("The analysis model isn't available right now. Please try again later."), findsOneWidget);
      expect(find.byKey(const Key('retry')), findsNothing);
    });

    testWidgets('server text is never shown for unknown codes', (tester) async {
      final api = apiAnswering(
        (_) => FakeApi.json({
          'error': {'code': 'brand_new_code', 'message': 'Traceback (most recent call last)'},
        }, status: 500),
      );
      await pumpApp(tester, api: api);
      await check(tester);
      expect(find.text('Something went wrong. Please try again.'), findsOneWidget);
      expect(find.textContaining('Traceback'), findsNothing);
    });

    testWidgets('"Check another message" returns to Home', (tester) async {
      await pumpApp(tester);
      await check(tester);
      await scrollTo(tester, find.byKey(const Key('check-another')));
      await tapOn(tester, find.byKey(const Key('check-another')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('message-input')), findsOneWidget);
    });
  });

  group('feedback', () {
    Future<void> openFeedback(WidgetTester tester) async {
      await check(tester);
      await scrollTo(tester, find.byKey(const Key('feedback-box')));
    }

    testWidgets('Yes is sent once and thanked; buttons lock', (tester) async {
      final api = await pumpApp(tester);
      await openFeedback(tester);
      await tapOn(tester, find.text('Yes'));
      await tester.pumpAndSettle();
      expect(find.text('Thanks - your answer was saved. No message text is stored.'), findsOneWidget);
      expect(api.to('/feedback'), hasLength(1));
      await tapOn(tester, find.text('No'));
      await tester.pumpAndSettle();
      expect(api.to('/feedback'), hasLength(1), reason: 'only one answer per result');
    });

    testWidgets('a transient failure can be retried', (tester) async {
      var fail = true;
      final api = FakeApi(
        handler: (r) {
          if (r.url.path == '/feedback' && fail) {
            return FakeApi.json({
              'error': {'code': 'feedback_storage_error'},
            }, status: 502);
          }
          return FakeApi.defaultHandler(r);
        },
      );
      await pumpApp(tester, api: api);
      await openFeedback(tester);
      await tapOn(tester, find.text('No'));
      await tester.pumpAndSettle();
      expect(find.textContaining('You can try again.'), findsOneWidget);
      fail = false;
      await tapOn(tester, find.text('No'));
      await tester.pumpAndSettle();
      expect(find.text('Thanks - your answer was saved. No message text is stored.'), findsOneWidget);
    });

    testWidgets('a final failure (server restarted) offers no retry', (tester) async {
      final api = FakeApi(
        handler: (r) => r.url.path == '/feedback'
            ? FakeApi.json({
                'error': {'code': 'unknown_prediction'},
              }, status: 404)
            : FakeApi.defaultHandler(r),
      );
      await pumpApp(tester, api: api);
      await openFeedback(tester);
      await tapOn(tester, find.text('Yes'));
      await tester.pumpAndSettle();
      expect(find.text('This result is too old to rate, because the server restarted.'), findsOneWidget);
      await tapOn(tester, find.text('Yes'));
      await tester.pumpAndSettle();
      expect(api.to('/feedback'), hasLength(1));
    });
  });

  testWidgets('small phone (360 dp), Hindi, dark theme, 1.3x text: home and result render without overflow', (
    tester,
  ) async {
    tester.platformDispatcher.textScaleFactorTestValue = 1.3;
    addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
    final api = apiAnswering(
      (_) => FakeApi.json(
        analyzeJson(
          language: 'hi',
          inputType: 'image',
          explanation: 'यह मैसेज आपको डराकर लिंक खोलने को कहता है।',
          ocr: {'extracted_text': 'प्रिय ग्राहक', 'quality': 'poor', 'dark_mode': true},
        ),
      ),
    );
    await pumpApp(tester, api: api, locale: const Locale('hi'), themeMode: ThemeMode.dark, width: 360);
    await check(tester);
    expect(find.byKey(const Key('result-card')), findsOneWidget);
    // Any RenderFlex overflow fails the test automatically (with the widget's location).
  });

  group('found on a real phone (OPPO CPH2269, 360 dp)', () {
    testWidgets('the "Explanation written by..." note wraps instead of being cut off', (tester) async {
      await pumpApp(tester, locale: const Locale('hi'), width: 360);
      await check(tester);
      final note = find.descendant(of: find.byKey(const Key('explained-by')), matching: find.textContaining('Groq'));
      expect(tester.renderObject<RenderParagraph>(note).didExceedMaxLines, isFalse);
      expect(find.byType(Chip), findsNothing);
    });

    testWidgets('Hindi headings get no letter spacing (it splits Devanagari conjuncts)', (tester) async {
      await pumpApp(tester, locale: const Locale('hi'));
      await check(tester);
      final heading = tester.widget<Text>(find.text('चेतावनी के संकेत'));
      expect(heading.style?.letterSpacing, 0);
    });

    testWidgets('the app name fits in the app bar at 360 dp', (tester) async {
      await pumpApp(tester, width: 360);
      expect(tester.renderObject<RenderParagraph>(find.text('Scam Message Checker')).didExceedMaxLines, isFalse);
      expect(find.ancestor(of: find.text('Scam Message Checker'), matching: find.byType(FittedBox)), findsOneWidget);
    });
  });
}
