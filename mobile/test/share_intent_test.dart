import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scamchecker/platform/share_receiver.dart';

import 'helpers.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('channel decoding (what MainActivity.kt sends)', () {
    test('text, image and error maps', () {
      expect(SharedItem.fromChannel({'kind': 'text', 'text': 'Hi'}), isA<SharedText>());
      final img = SharedItem.fromChannel({'kind': 'image', 'bytes': pngBytes});
      expect(img, isA<SharedImage>().having((i) => i.bytes, 'bytes', pngBytes));
      expect(
        SharedItem.fromChannel({'kind': 'error', 'code': 'too_large'}),
        isA<SharedError>().having((e) => e.code, 'code', 'too_large'),
      );
      expect(
        SharedItem.fromChannel({'kind': 'error', 'code': 'unsupported'}),
        isA<SharedError>().having((e) => e.code, 'code', 'mobile.shareUnsupported'),
      );
    });

    test('blank text, empty image and junk become errors', () {
      expect(SharedItem.fromChannel({'kind': 'text', 'text': '  '}), isA<SharedError>());
      expect(SharedItem.fromChannel({'kind': 'image', 'bytes': Uint8List(0)}), isA<SharedError>());
      expect(SharedItem.fromChannel('nonsense'), isA<SharedError>());
      expect(SharedItem.fromChannel({'kind': 'video'}), isA<SharedError>());
    });

    test('ChannelShareReceiver: initial share once, then pushed shares', () async {
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      const channel = MethodChannel(shareChannelName);
      var calls = 0;
      messenger.setMockMethodCallHandler(channel, (call) async {
        expect(call.method, 'getInitialShare');
        calls++;
        return {'kind': 'text', 'text': 'Launched with this'};
      });
      final receiver = ChannelShareReceiver();
      addTearDown(() {
        receiver.dispose();
        messenger.setMockMethodCallHandler(channel, null);
      });

      final initial = await receiver.initialShare();
      expect(initial, isA<SharedText>().having((t) => t.text, 'text', 'Launched with this'));
      expect(calls, 1);

      final next = receiver.shares.first;
      await messenger.handlePlatformMessage(
        shareChannelName,
        const StandardMethodCodec().encodeMethodCall(const MethodCall('onShare', {'kind': 'text', 'text': 'Later'})),
        (_) {},
      );
      expect(await next, isA<SharedText>().having((t) => t.text, 'text', 'Later'));
    });

    test('no native side (not Android) means no initial share', () async {
      final receiver = ChannelShareReceiver(channel: const MethodChannel('nobody/listens/here'));
      addTearDown(receiver.dispose);
      expect(await receiver.initialShare(), isNull);
    });
  });

  group('app behaviour', () {
    testWidgets('text shared at launch is analysed straight away', (tester) async {
      final share = FakeShareReceiver(initial: const SharedText('Your parcel is held, pay Rs 25 here'));
      final api = await pumpApp(tester, share: share);
      expect(find.text('Shared from another app: text'), findsOneWidget);
      expect(find.byKey(const Key('result-card')), findsOneWidget);
      expect(jsonDecode(api.to('/analyze/text').single.body), {'text': 'Your parcel is held, pay Rs 25 here'});
    });

    testWidgets('screenshot shared at launch is uploaded and analysed', (tester) async {
      final share = FakeShareReceiver(initial: SharedImage(pngBytes));
      final api = await pumpApp(tester, share: share);
      expect(find.text('Shared from another app: screenshot'), findsOneWidget);
      expect(api.to('/analyze/image'), hasLength(1));
      expect(find.byKey(const Key('result-card')), findsOneWidget);
    });

    testWidgets('a share while the app is open replaces the screen; Back goes Home', (tester) async {
      final share = FakeShareReceiver();
      final api = await pumpApp(tester, share: share);
      // Open an older result first.
      await tester.enterText(find.byKey(const Key('message-input')), 'old message');
      await tapOn(tester, find.byKey(const Key('submit-text')));
      await tester.pumpAndSettle();

      share.controller.add(const SharedText('new shared message'));
      await tester.pumpAndSettle();
      expect(find.text('Shared from another app: text'), findsOneWidget);
      expect(api.to('/analyze/text').map((r) => jsonDecode(r.body)['text']), ['old message', 'new shared message']);

      await tester.pageBack();
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('message-input')), findsOneWidget, reason: 'one Back returns to Home');
    });

    testWidgets('unsupported share shows a message and sends nothing', (tester) async {
      final share = FakeShareReceiver(initial: const SharedError('mobile.shareUnsupported'));
      final api = await pumpApp(tester, share: share);
      expect(find.textContaining("That can't be checked."), findsOneWidget);
      // A failed share must not be labelled as "text" (the item's kind isn't known).
      expect(find.text('Shared from another app: text'), findsNothing);
      expect(api.to('/analyze/text'), isEmpty);
      expect(api.to('/analyze/image'), isEmpty);
    });

    testWidgets('a shared image over 5 MB gets the size message', (tester) async {
      final share = FakeShareReceiver(initial: const SharedError('too_large'));
      await pumpApp(tester, share: share);
      expect(find.text('That screenshot is larger than 5 MB. Try cropping it or saving it as JPEG.'), findsOneWidget);
    });

    testWidgets('shared text over 5000 characters is refused before sending', (tester) async {
      final share = FakeShareReceiver(initial: SharedText('x' * 5001));
      final api = await pumpApp(tester, share: share);
      expect(find.textContaining('keep it under 5000 characters'), findsOneWidget);
      expect(api.to('/analyze/text'), isEmpty);
    });
  });
}
