// Phase 11b redesign: the result hero, motion settings, accessibility, haptics and the new states.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:scamchecker/theme/app_theme.dart';
import 'package:scamchecker/util/text_utils.dart';
import 'package:scamchecker/widgets/ui.dart';

import 'helpers.dart';

Future<void> check(WidgetTester tester, [String text = 'Your account will be blocked']) async {
  await tester.enterText(find.byKey(const Key('message-input')), text);
  await tapOn(tester, find.byKey(const Key('submit-text')));
  await tester.pumpAndSettle();
}

FakeApi answering(Map<String, Object?> json) =>
    FakeApi(handler: (r) => r.url.path.startsWith('/analyze') ? FakeApi.json(json) : FakeApi.defaultHandler(r));

/// A result with every section: flags, several steps, pattern, two links and screenshot text.
Map<String, Object?> fullResult({String language = 'en'}) => analyzeJson(
  language: language,
  inputType: 'image',
  whatToDo: ['Do not open the link.', 'Call your bank on the number on your card.', 'Delete the message.'],
  urls: [
    {
      'url_defanged': 'hxxp://sbi-kyc-verify[.]tk/update',
      'risk_band': 'high',
      'reasons': ['Risky ending (.tk)'],
    },
    {
      'url_defanged': 'hxxps://bit[.]ly/x',
      'risk_band': 'medium',
      'reasons': ['URL shortener'],
    },
  ],
  ocr: {
    'extracted_text': 'Dear customer प्रिय ग्राहक, update KYC at http://sbi-kyc.top/verify today.',
    'quality': 'fair',
    'dark_mode': true,
  },
);

/// Records HapticFeedback calls.
List<String> recordHaptics(WidgetTester tester) {
  final calls = <String>[];
  tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, (call) async {
    if (call.method == 'HapticFeedback.vibrate') calls.add('${call.arguments}');
    return null;
  });
  addTearDown(() => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform, null));
  return calls;
}

/// Turns on Android's "Remove animations" for this test.
void removeAnimations(WidgetTester tester) {
  tester.platformDispatcher.accessibilityFeaturesTestValue = const FakeAccessibilityFeatures(disableAnimations: true);
  addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
}

void main() {
  group('result hero', () {
    testWidgets('verdict, risk and the first step come first; the step is not repeated', (tester) async {
      await pumpApp(tester, api: answering(fullResult()));
      await check(tester);
      final hero = find.byKey(const Key('result-hero'));
      expect(find.descendant(of: hero, matching: find.byKey(const Key('risk-gauge'))), findsOneWidget);
      expect(find.descendant(of: hero, matching: find.text('Likely scam')), findsOneWidget);
      expect(find.descendant(of: hero, matching: find.text('Do this first')), findsOneWidget);
      expect(find.descendant(of: hero, matching: find.text('Do not open the link.')), findsOneWidget);
      expect(find.text('Do not open the link.'), findsOneWidget, reason: 'step 1 is shown once, in the hero');
      // The remaining steps follow, numbered from 2.
      final steps = find.byKey(const Key('what-to-do'));
      expect(
        find.descendant(of: steps, matching: find.text('Call your bank on the number on your card.')),
        findsOneWidget,
      );
      expect(find.descendant(of: steps, matching: find.text('2')), findsOneWidget);
      expect(find.descendant(of: steps, matching: find.text('1')), findsNothing);
      // The hero is above everything else.
      expect(tester.getTopLeft(hero).dy, lessThan(tester.getTopLeft(find.byKey(const Key('red-flags'))).dy));
      expect(find.text('More details'), findsOneWidget);
    });

    testWidgets('with a single step there is no separate "What to do" card', (tester) async {
      await pumpApp(tester, api: answering(analyzeJson(whatToDo: ['Do not open the link.'])));
      await check(tester);
      expect(find.byKey(const Key('first-step')), findsOneWidget);
      expect(find.byKey(const Key('what-to-do')), findsNothing);
    });

    testWidgets('a safe result says "No warning signs" calmly', (tester) async {
      await pumpApp(
        tester,
        api: answering(analyzeJson(verdict: 'safe', risk: 'low', redFlags: [])),
      );
      await check(tester);
      expect(find.text('No warning signs'), findsOneWidget);
      expect(find.text('No specific warning signs found.'), findsOneWidget);
      expect(find.text('Warning signs'), findsNothing);
    });

    for (final (risk, band) in [('low', 'Low'), ('medium', 'Medium'), ('high', 'High')]) {
      testWidgets('$risk: the gauge emphasises exactly the "$band" label, under the arc', (tester) async {
        await pumpApp(
          tester,
          api: answering(analyzeJson(verdict: risk == 'low' ? 'safe' : 'scam', risk: risk)),
        );
        await check(tester);
        final gauge = find.byKey(const Key('risk-gauge'));
        final arc = find.descendant(of: gauge, matching: find.byType(CustomPaint)).first;
        final arcBottom = tester.getBottomLeft(arc).dy;
        for (final name in ['Low', 'Medium', 'High']) {
          final label = find.descendant(of: gauge, matching: find.text(name));
          expect(label, findsOneWidget);
          // Nothing is printed above the arc, where it could be read as the answer.
          expect(tester.getTopLeft(label).dy, greaterThanOrEqualTo(arcBottom), reason: '$name label position');
          final weight = tester.widget<Text>(label).style?.fontWeight;
          expect(weight == FontWeight.w700, name == band, reason: '$name emphasised?');
        }
        expect(find.bySemanticsLabel('Risk level: $band'), findsOneWidget);
      });
    }
  });

  group('screen readers (TalkBack)', () {
    testWidgets('the result is read in order: verdict, first step, gauge, then the cards', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpApp(tester, api: answering(fullResult()));
      await check(tester);
      final order = tester.semantics
          .simulatedAccessibilityTraversal()
          .map((n) => n.label.replaceAll('\n', ' '))
          .where((l) => l.isNotEmpty)
          .toList();
      int at(String part) => order.indexWhere((l) => l.contains(part));
      expect(at('Likely scam'), isNonNegative);
      expect(at('Likely scam'), lessThan(at('Do this first')));
      expect(at('Do this first'), lessThan(at('Risk level: High')));
      expect(at('Risk level: High'), lessThan(at('Warning signs')));
      // "Result" is said once (the app bar), not again as a heading inside the card.
      expect(order.where((l) => l == 'Result'), hasLength(1));
      handle.dispose();
    });

    for (final screen in ['home', 'result', 'about', 'error']) {
      testWidgets('$screen: controls are labelled, at least 48 dp, and text contrast passes', (tester) async {
        final handle = tester.ensureSemantics();
        final api = screen == 'error'
            ? FakeApi(
                handler: (r) => r.url.path.startsWith('/analyze')
                    ? FakeApi.json({
                        'error': {'code': 'busy'},
                      }, status: 503)
                    : FakeApi.defaultHandler(r),
              )
            : answering(fullResult());
        await pumpApp(tester, api: api, width: 360);
        if (screen == 'result' || screen == 'error') await check(tester);
        if (screen == 'about') {
          await tester.tap(find.byKey(const Key('open-about')));
          await tester.pumpAndSettle();
        }
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        await expectLater(tester, meetsGuideline(textContrastGuideline));
        handle.dispose();
      });
    }

    testWidgets('home: icon buttons and the screenshot picker have clear labels', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpApp(tester);
      // Icon buttons: TalkBack reads their tooltip.
      expect(find.byTooltip('How it works'), findsOneWidget);
      expect(find.byTooltip('Display options'), findsOneWidget);
      await tapOn(tester, find.text('Screenshot'));
      await tester.pumpAndSettle();
      expect(find.bySemanticsLabel('Choose a screenshot'), findsOneWidget);
      handle.dispose();
    });

    testWidgets('decorative icons are hidden: the gauge is one image with no children', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpApp(tester, api: answering(fullResult()));
      await check(tester);
      final node = tester.getSemantics(find.byKey(const Key('risk-gauge')));
      expect(node, isSemantics(label: 'Risk level: High', isImage: true));
      expect(node.childrenCount, 0, reason: 'band names and icons inside are not read separately');
      handle.dispose();
    });
  });

  group('large text and narrow phones', () {
    for (final lang in ['hi', 'en']) {
      testWidgets('$lang at font scale 2.0, 360 dp: every screen renders without overflow', (tester) async {
        tester.platformDispatcher.textScaleFactorTestValue = 2.0;
        addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
        await pumpApp(
          tester,
          api: answering(fullResult(language: lang)),
          locale: Locale(lang),
          width: 360,
        );
        // Display options sheet.
        await tester.tap(find.byKey(const Key('display-options')));
        await tester.pumpAndSettle();
        await tester.tapAt(const Offset(10, 10));
        await tester.pumpAndSettle();
        // Screenshot mode empty state.
        await tester.tap(find.text(lang == 'hi' ? 'स्क्रीनशॉट' : 'Screenshot').first);
        await tester.pumpAndSettle();
        await tester.tap(find.text(lang == 'hi' ? 'टेक्स्ट' : 'Text').first);
        await tester.pumpAndSettle();
        // Full result, with everything expanded. (Settle first: a list that is still coasting
        // from the previous scroll swallows taps.)
        await tester.enterText(find.byKey(const Key('message-input')), 'Your account will be blocked');
        await scrollTo(tester, find.byKey(const Key('submit-text')));
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const Key('submit-text')));
        await tester.pumpAndSettle();
        await tapOn(tester, find.byKey(const Key('extracted-text-toggle')));
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('result-hero')), findsOneWidget);
        // Not pageBack(): it looks for the English "Back" tooltip.
        await tester.tap(find.byType(BackButton));
        await tester.pumpAndSettle();
        await tester.tap(find.byKey(const Key('open-about')));
        await tester.pumpAndSettle();
        // Any RenderFlex overflow fails the test automatically.
        expect(tester.takeException(), isNull);
      });
    }

    testWidgets('Hindi keeps line height 1.75 and no letter spacing on the new headings', (tester) async {
      await pumpApp(
        tester,
        api: answering(fullResult(language: 'hi')),
        locale: const Locale('hi'),
      );
      await check(tester);
      for (final heading in ['सबसे पहले यह करें', 'और जानकारी']) {
        final style = tester.widget<Text>(find.text(heading)).style;
        expect(style?.letterSpacing ?? 0, 0, reason: heading);
        expect(style?.height, devanagariLineHeight, reason: heading);
      }
    });
  });

  group('"Remove animations" setting', () {
    testWidgets('the result appears complete in one frame: no fades, needle already in its band', (tester) async {
      removeAnimations(tester);
      final answer = Completer<http.Response>();
      await pumpApp(
        tester,
        api: FakeApi(handler: (r) => r.url.path.startsWith('/analyze') ? answer.future : FakeApi.defaultHandler(r)),
      );
      await tester.enterText(find.byKey(const Key('message-input')), 'hello');
      await tapOn(tester, find.byKey(const Key('submit-text')));
      await tester.pump();
      // Loading: no moving progress bar.
      expect(find.byKey(const Key('result-skeleton')), findsOneWidget);
      expect(find.byType(LinearProgressIndicator), findsNothing);

      answer.complete(FakeApi.json(fullResult()));
      await tester.pump();
      await tester.pump();
      expect(find.byKey(const Key('result-hero')), findsOneWidget);
      for (final fade in tester.widgetList<FadeTransition>(
        find.descendant(of: find.byKey(const Key('result-card')), matching: find.byType(FadeTransition)),
      )) {
        expect(fade.opacity.value, 1, reason: 'content must not fade in with animations off');
      }
      // The needle is already in the middle of its band.
      final gauge = tester.widget<CustomPaint>(
        find.descendant(of: find.byKey(const Key('risk-gauge')), matching: find.byType(CustomPaint)).first,
      );
      expect((gauge.painter as dynamic).progress, 1.0);
    });

    testWidgets('with animations on, the result does animate in (and settles)', (tester) async {
      await pumpApp(tester);
      await tester.enterText(find.byKey(const Key('message-input')), 'hello');
      await tapOn(tester, find.byKey(const Key('submit-text')));
      await tester.pump();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(tester.binding.transientCallbackCount, greaterThan(0));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('result-hero')), findsOneWidget);
    });
  });

  group('haptics', () {
    for (final (risk, expected) in [
      ('high', 'HapticFeedbackType.heavyImpact'),
      ('medium', 'HapticFeedbackType.mediumImpact'),
      ('low', 'HapticFeedbackType.lightImpact'),
    ]) {
      testWidgets('$risk result arrives: $expected', (tester) async {
        final haptics = recordHaptics(tester);
        await pumpApp(
          tester,
          api: answering(analyzeJson(verdict: risk == 'low' ? 'safe' : 'scam', risk: risk)),
        );
        await check(tester);
        expect(haptics, [expected]);
      });
    }

    testWidgets('feedback saved: a light tap; a failed send: none', (tester) async {
      final haptics = recordHaptics(tester);
      var fail = true;
      final api = FakeApi(
        handler: (r) => r.url.path == '/feedback' && fail
            ? FakeApi.json({
                'error': {'code': 'feedback_storage_error'},
              }, status: 502)
            : FakeApi.defaultHandler(r),
      );
      await pumpApp(tester, api: api);
      await check(tester);
      haptics.clear();
      await tapOn(tester, find.text('Yes'));
      await tester.pumpAndSettle();
      expect(haptics, isEmpty);
      fail = false;
      await tapOn(tester, find.text('Yes'));
      await tester.pumpAndSettle();
      expect(haptics, ['HapticFeedbackType.lightImpact']);
    });
  });

  group('states', () {
    testWidgets('the input error sits under the field, is not the scam red, and clears when typing', (tester) async {
      await pumpApp(tester);
      await tapOn(tester, find.byKey(const Key('submit-text')));
      await tester.pumpAndSettle();
      final notice = find.byType(InlineNotice);
      expect(notice, findsOneWidget);
      expect(find.descendant(of: notice, matching: find.text('Please paste a message first.')), findsOneWidget);
      // Directly between the field and the button.
      expect(
        tester.getTopLeft(notice).dy,
        greaterThan(tester.getBottomLeft(find.byKey(const Key('message-input'))).dy),
      );
      expect(tester.getTopLeft(notice).dy, lessThan(tester.getTopLeft(find.byKey(const Key('submit-text'))).dy));

      await tester.enterText(find.byKey(const Key('message-input')), 'h');
      await tester.pumpAndSettle();
      expect(find.byType(InlineNotice), findsNothing, reason: 'found on the phone: the error stayed after typing');
    });

    testWidgets('error panels use neutral colours, not the high-risk red', (tester) async {
      final api = FakeApi(
        handler: (r) => r.url.path.startsWith('/analyze')
            ? FakeApi.json({
                'error': {'code': 'busy'},
              }, status: 503)
            : FakeApi.defaultHandler(r),
      );
      await pumpApp(tester, api: api);
      await check(tester);
      final badge = tester.widget<IconBadge>(
        find.descendant(of: find.byKey(const ValueKey('error-busy')), matching: find.byType(IconBadge)),
      );
      final context = tester.element(find.byKey(const ValueKey('error-busy')));
      expect(badge.background, Theme.of(context).colorScheme.primaryContainer);
      expect(badge.background, isNot(AppColors.of(context).high.bg));
    });

    testWidgets('429: the retry button counts down from Retry-After, and stays usable', (tester) async {
      var limited = true;
      final api = FakeApi(
        handler: (r) => r.url.path.startsWith('/analyze') && limited
            ? FakeApi.json(
                {
                  'error': {'code': 'rate_limited'},
                },
                status: 429,
                headers: {'retry-after': '3'},
              )
            : FakeApi.defaultHandler(r),
      );
      await pumpApp(tester, api: api);
      await check(tester);
      expect(find.text('Try again in 3 s'), findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
      expect(find.text('Try again in 2 s'), findsOneWidget);
      await tester.pump(const Duration(seconds: 2));
      expect(find.text('Try again'), findsOneWidget);
      limited = false;
      await tapOn(tester, find.byKey(const Key('retry')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('result-hero')), findsOneWidget);
    });

    testWidgets('a slow screenshot check adds a reassuring line after 8 seconds', (tester) async {
      final answer = Completer<http.Response>();
      final api = FakeApi(
        handler: (r) => r.url.path.startsWith('/analyze') ? answer.future : FakeApi.defaultHandler(r),
      );
      await pumpApp(tester, api: api, picker: FakePicker(pngBytes));
      await tapOn(tester, find.text('Screenshot'));
      await tester.pumpAndSettle();
      await tapOn(tester, find.byKey(const Key('pick-image')));
      await tester.pumpAndSettle();
      await tapOn(tester, find.byKey(const Key('submit-image')));
      await tester.pump(const Duration(seconds: 1));
      expect(find.text('Still working. Screenshots can take up to 30 seconds.'), findsNothing);
      await tester.pump(const Duration(seconds: 8));
      expect(find.text('Still working. Screenshots can take up to 30 seconds.'), findsOneWidget);
      answer.complete(FakeApi.json(fullResult()));
      await tester.pumpAndSettle();
    });

    testWidgets('feedback: the chosen answer stays visibly selected after it is saved', (tester) async {
      final handle = tester.ensureSemantics();
      await pumpApp(tester);
      await check(tester);
      await tapOn(tester, find.text('No'));
      await tester.pumpAndSettle();
      final box = find.byKey(const Key('feedback-box'));
      expect(find.descendant(of: box, matching: find.byIcon(Icons.check_rounded)), findsOneWidget);
      final chosen = tester.widget<FilledButton>(
        find.ancestor(of: find.text('No'), matching: find.byWidgetPredicate((w) => w is FilledButton)),
      );
      final context = tester.element(box);
      expect(chosen.onPressed, isNull, reason: 'one answer per result');
      expect(
        chosen.style?.backgroundColor?.resolve({WidgetState.disabled}),
        Theme.of(context).colorScheme.primaryContainer,
        reason: 'still looks selected while locked',
      );
      expect(tester.getSemantics(find.text('No')), isSemantics(isSelected: true, isButton: true));
      handle.dispose();
    });
  });

  group('links stay defanged', () {
    test('defangUrl follows the API rule', () {
      expect(defangUrl('http://sbi-kyc.tk/x'), 'hxxp://sbi-kyc[.]tk/x');
      expect(defangUrl('HTTPS://a.b.c/d.e'), 'hxxps://a[.]b[.]c/d.e');
      expect(defangUrl('www.bit.ly/abc'), 'www[.]bit[.]ly/abc');
      expect(defangUrl('hxxp://x[.]tk/y'), 'hxxp://x[.]tk/y', reason: 'defanging twice changes nothing');
    });

    test('links inside free text are defanged; ordinary sentences are not touched', () {
      expect(
        defangLinksInText('Update KYC at http://sbi-kyc.top/verify. Or call us.'),
        'Update KYC at hxxp://sbi-kyc[.]top/verify. Or call us.',
      );
      expect(defangLinksInText('Pay at sbi-update.xyz/pay now'), 'Pay at sbi-update[.]xyz/pay now');
      expect(defangLinksInText('visit www.example.com'), 'visit www[.]example[.]com');
      expect(defangLinksInText('Meet at 5. See you, e.g. at the cafe.'), 'Meet at 5. See you, e.g. at the cafe.');
      expect(defangLinksInText('आपका खाता बंद होगा'), 'आपका खाता बंद होगा');
    });

    testWidgets('text read from a screenshot shows its links defanged (a difference from the web app)', (tester) async {
      await pumpApp(tester, api: answering(fullResult()));
      await check(tester);
      await tapOn(tester, find.byKey(const Key('extracted-text-toggle')));
      await tester.pumpAndSettle();
      final shown = tester.widget<SelectableText>(find.byKey(const Key('extracted-text'))).data!;
      expect(shown, contains('hxxp://sbi-kyc[.]top/verify'));
      expect(shown, isNot(contains('http://')));
      expect(shown, contains('प्रिय ग्राहक'));
    });

    testWidgets('the defanged link is at least 48 dp tall (found by the audit: 42 dp)', (tester) async {
      await pumpApp(tester, api: answering(fullResult()), width: 360);
      await check(tester);
      final link = find.byKey(const Key('defanged-url')).first;
      await scrollTo(tester, link);
      final box = find.ancestor(of: link, matching: find.byType(ConstrainedBox)).first;
      expect(tester.getSize(box).height, greaterThanOrEqualTo(48));
    });
  });
}
