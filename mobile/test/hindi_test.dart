import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:scamchecker/i18n/strings.dart';
import 'package:scamchecker/util/text_utils.dart';

import 'helpers.dart';

/// The effective line height of the RichText showing [text].
double? lineHeightOf(WidgetTester tester, String text) {
  final rich = tester.widget<RichText>(find.byWidgetPredicate((w) => w is RichText && w.text.toPlainText() == text));
  final span = rich.text as TextSpan;
  return span.style?.height ?? span.children?.whereType<TextSpan>().first.style?.height;
}

void main() {
  testWidgets('Hindi interface uses the web app\'s Hindi wording', (tester) async {
    await pumpApp(tester, locale: const Locale('hi'));
    expect(find.text('क्या यह मैसेज स्कैम है?'), findsOneWidget);
    expect(find.text('मैसेज जाँचें'), findsWidgets);
    expect(find.text('स्कैम मैसेज जाँच'), findsOneWidget); // app bar title
  });

  testWidgets('Hindi interface text gets line height 1.75', (tester) async {
    await pumpApp(tester, locale: const Locale('hi'));
    expect(lineHeightOf(tester, 'क्या यह मैसेज स्कैम है?'), 1.75);
  });

  testWidgets('English interface text does not get the Devanagari line height', (tester) async {
    await pumpApp(tester);
    expect(lineHeightOf(tester, 'Is this message a scam?'), isNot(1.75));
  });

  testWidgets('Hindi result in the Hindi interface: labels and content in Hindi, height 1.75', (tester) async {
    final api = FakeApi(
      handler: (r) => r.url.path.startsWith('/analyze')
          ? FakeApi.json(
              analyzeJson(
                language: 'hi',
                redFlags: ['खाता बंद करने की धमकी'],
                explanation: 'यह मैसेज आपको डराकर लिंक खोलने को कहता है।',
                whatToDo: ['लिंक न खोलें।'],
              ),
            )
          : FakeApi.defaultHandler(r),
    );
    await pumpApp(tester, api: api, locale: const Locale('hi'));
    await tester.enterText(find.byKey(const Key('message-input')), 'प्रिय ग्राहक, आपका खाता बंद हो जाएगा');
    await tapOn(tester, find.byKey(const Key('submit-text')));
    await tester.pumpAndSettle();

    expect(find.text('संभवतः स्कैम'), findsOneWidget); // result.verdict.scam (hi)
    expect(find.text('यह मैसेज आपको डराकर लिंक खोलने को कहता है।'), findsOneWidget);
    expect(lineHeightOf(tester, 'यह मैसेज आपको डराकर लिंक खोलने को कहता है।'), 1.75);
    expect(lineHeightOf(tester, 'खाता बंद करने की धमकी'), 1.75);
  });

  testWidgets('Hindi content in the English interface still gets 1.75; Hinglish gets 1.5', (tester) async {
    var language = 'hi';
    final api = FakeApi(
      handler: (r) => r.url.path.startsWith('/analyze')
          ? FakeApi.json(
              analyzeJson(
                language: language,
                explanation: language == 'hi' ? 'लिंक न खोलें।' : 'Is link ko mat kholiye.',
              ),
            )
          : FakeApi.defaultHandler(r),
    );
    await pumpApp(tester, api: api);
    await tester.enterText(find.byKey(const Key('message-input')), 'x');
    await tapOn(tester, find.byKey(const Key('submit-text')));
    await tester.pumpAndSettle();
    expect(lineHeightOf(tester, 'लिंक न खोलें।'), 1.75);

    await tester.pageBack();
    await tester.pumpAndSettle();
    language = 'hinglish';
    await tapOn(tester, find.byKey(const Key('submit-text')));
    await tester.pumpAndSettle();
    expect(lineHeightOf(tester, 'Is link ko mat kholiye.'), 1.5);
  });

  testWidgets('switching EN -> हिंदी changes the interface immediately', (tester) async {
    await pumpApp(tester);
    await tapOn(tester, find.byKey(const Key('display-options')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('हिंदी'));
    await tester.pumpAndSettle();
    await tester.tapAt(const Offset(10, 10)); // close the sheet
    await tester.pumpAndSettle();
    expect(find.text('क्या यह मैसेज स्कैम है?'), findsOneWidget);
  });

  testWidgets('Hindi error message when the server is busy', (tester) async {
    final api = FakeApi(
      handler: (r) => r.url.path.startsWith('/analyze')
          ? FakeApi.json({
              'error': {'code': 'busy'},
            }, status: 503)
          : FakeApi.defaultHandler(r),
    );
    await pumpApp(tester, api: api, locale: const Locale('hi'));
    await tester.enterText(find.byKey(const Key('message-input')), 'x');
    await tapOn(tester, find.byKey(const Key('submit-text')));
    await tester.pumpAndSettle();
    const hi = Strings(UiLanguage.hi);
    expect(find.byKey(const ValueKey('error-busy')), findsOneWidget);
    expect(find.text(hi.t('errors.heading')), findsOneWidget);
    expect(find.text(hi.t('errors.busy')), findsOneWidget);
    expect(hasDevanagari(hi.t('errors.busy')), isTrue);
  });
}
