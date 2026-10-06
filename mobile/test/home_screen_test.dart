import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:scamchecker/config/api_config.dart';
import 'package:scamchecker/generated/web_data.g.dart';

import 'helpers.dart';

void main() {
  testWidgets('home shows the form, samples and no server banner when the server is live', (tester) async {
    await pumpApp(tester);
    expect(find.text('Is this message a scam?'), findsOneWidget);
    expect(find.byKey(const Key('message-input')), findsOneWidget);
    expect(find.text('0 / 5000 characters'), findsOneWidget);
    expect(find.byKey(const ValueKey('server-checking')), findsNothing);
    expect(find.byKey(const ValueKey('server-unreachable')), findsNothing);
    await scrollTo(tester, find.byKey(ValueKey('sample-${textSamples.last.id}')));
    expect(find.text('English - friend asking about lunch'), findsOneWidget);
  });

  testWidgets('shows "checking" while /health is pending', (tester) async {
    final health = Completer<http.Response>();
    final api = FakeApi(handler: (r) => r.url.path == '/health' ? health.future : FakeApi.defaultHandler(r));
    await pumpApp(tester, api: api, settle: false);
    expect(find.text('Connecting to the analysis server…'), findsOneWidget);
    health.complete(FakeApi.json({'status': 'ok', 'components': {}}));
    await tester.pumpAndSettle();
    expect(find.text('Connecting to the analysis server…'), findsNothing);
  });

  testWidgets('server unreachable: banner, then Retry brings it back', (tester) async {
    var up = false;
    final api = FakeApi(
      handler: (r) {
        if (r.url.path == '/health' && !up) throw const SocketException('down');
        return FakeApi.defaultHandler(r);
      },
    );
    await pumpApp(tester, api: api);
    expect(find.text("Can't reach the analysis server"), findsOneWidget);

    up = true;
    await tapOn(tester, find.text('Try the live server again'));
    await tester.pumpAndSettle();
    expect(find.text("Can't reach the analysis server"), findsNothing);
    expect(find.text('The live server is back. You can check your own messages now.'), findsOneWidget);
  });

  testWidgets('no server configured (release without a deployed URL)', (tester) async {
    final api = await pumpApp(tester, config: ApiConfig.resolve(isRelease: true, deployed: ''));
    expect(find.text('No analysis server is set up for this app yet'), findsOneWidget);
    expect(api.requests, isEmpty, reason: 'nothing may be sent without a configured server');
  });

  testWidgets('empty text shows an error and sends nothing', (tester) async {
    final api = await pumpApp(tester);
    await tapOn(tester, find.byKey(const Key('submit-text')));
    await tester.pumpAndSettle();
    expect(find.text('Please paste a message first.'), findsOneWidget);
    expect(api.to('/analyze/text'), isEmpty);
  });

  testWidgets('text over 5000 characters is refused before sending', (tester) async {
    final api = await pumpApp(tester);
    await tester.enterText(find.byKey(const Key('message-input')), 'a' * 5001);
    await tester.pump();
    expect(find.text('5001 / 5000 characters'), findsOneWidget);
    await tapOn(tester, find.byKey(const Key('submit-text')));
    await tester.pumpAndSettle();
    expect(find.textContaining('keep it under 5000 characters'), findsOneWidget);
    expect(api.to('/analyze/text'), isEmpty);
  });

  testWidgets('submitting text opens results and sends exactly that text', (tester) async {
    final api = await pumpApp(tester);
    await tester.enterText(find.byKey(const Key('message-input')), 'Your KYC is pending, click here');
    await tapOn(tester, find.byKey(const Key('submit-text')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('result-card')), findsOneWidget);
    expect(jsonDecode(api.to('/analyze/text').single.body), {'text': 'Your KYC is pending, click here'});
  });

  testWidgets('tapping a sample checks it straight away', (tester) async {
    final api = await pumpApp(tester);
    final sample = textSamples.first;
    await scrollTo(tester, find.byKey(ValueKey('sample-${sample.id}')));
    await tapOn(tester, find.byKey(ValueKey('sample-${sample.id}')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('result-card')), findsOneWidget);
    expect(jsonDecode(api.to('/analyze/text').single.body)['text'], sample.text);
  });

  testWidgets('screenshot: pick, preview, check (multipart upload)', (tester) async {
    final picker = FakePicker(pngBytes);
    final api = await pumpApp(tester, picker: picker);
    await tapOn(tester, find.text('Screenshot'));
    await tester.pumpAndSettle();
    await tapOn(tester, find.byKey(const Key('pick-image')));
    await tester.pumpAndSettle();
    expect(picker.calls, 1);
    expect(find.byKey(const Key('submit-image')), findsOneWidget);
    await tapOn(tester, find.byKey(const Key('submit-image')));
    await tester.pumpAndSettle();
    expect(api.to('/analyze/image'), hasLength(1));
    expect(find.byKey(const Key('result-card')), findsOneWidget);
  });

  testWidgets('screenshot: unsupported file is refused with the web message', (tester) async {
    final picker = FakePicker(Uint8List.fromList('GIF89a....'.codeUnits));
    final api = await pumpApp(tester, picker: picker);
    await tapOn(tester, find.text('Screenshot'));
    await tester.pumpAndSettle();
    await tapOn(tester, find.byKey(const Key('pick-image')));
    await tester.pumpAndSettle();
    expect(find.text('Please upload a PNG, JPEG or WebP image.'), findsOneWidget);
    expect(find.byKey(const Key('submit-image')), findsNothing);
    expect(api.to('/analyze/image'), isEmpty);
  });

  testWidgets('screenshot: cancelling the picker changes nothing', (tester) async {
    await pumpApp(tester, picker: FakePicker());
    await tapOn(tester, find.text('Screenshot'));
    await tester.pumpAndSettle();
    await tapOn(tester, find.byKey(const Key('pick-image')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pick-image')), findsOneWidget);
    expect(find.text("Couldn't check that"), findsNothing);
  });

  testWidgets('About opens and shows the Gmail / WhatsApp note', (tester) async {
    await pumpApp(tester);
    await tapOn(tester, find.byKey(const Key('open-about')));
    await tester.pumpAndSettle();
    expect(find.text('How it works'), findsWidgets);
    await tester.scrollUntilVisible(
      find.textContaining('Gmail has no option'),
      300,
      scrollable: find.descendant(of: find.byKey(const Key('about-list')), matching: find.byType(Scrollable)),
    );
    expect(find.textContaining('WhatsApp'), findsWidgets);
    // The website-only items are not shown in the app.
    expect(find.textContaining('this website'), findsNothing);
  });

  testWidgets('dark theme can be chosen and the app still renders', (tester) async {
    await pumpApp(tester);
    await tapOn(tester, find.byKey(const Key('display-options')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Dark'));
    await tester.pumpAndSettle();
    final context = tester.element(find.byKey(const Key('message-input')));
    expect(Theme.of(context).brightness, Brightness.dark);
  });

  testWidgets('a successful check clears a stale "unreachable" banner (found on the phone)', (tester) async {
    // /health timed out during a slow cold start, but the server was fine.
    final api = FakeApi(
      handler: (r) {
        if (r.url.path == '/health') throw const SocketException('timed out');
        return FakeApi.defaultHandler(r);
      },
    );
    await pumpApp(tester, api: api);
    expect(find.text("Can't reach the analysis server"), findsOneWidget);

    await tester.enterText(find.byKey(const Key('message-input')), 'hello');
    await tapOn(tester, find.byKey(const Key('submit-text')));
    await tester.pumpAndSettle();
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text("Can't reach the analysis server"), findsNothing);
  });
}
