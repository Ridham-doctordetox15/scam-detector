/// Receives content shared from other apps (Android ACTION_SEND), via the native code in
/// android/app/src/main/kotlin/.../MainActivity.kt.
///
/// Protocol on channel [shareChannelName]:
///   Dart -> native  `getInitialShare`  returns the share that launched the app (once), or null.
///   native -> Dart  `onShare`          a new share while the app is already running.
/// Each share is a map: `{kind: text, text}`, `{kind: image, bytes}` or `{kind: error, code}`.
/// Shared content is kept in memory only; nothing is written to disk on either side.
library;

import 'dart:async';

import 'package:flutter/services.dart';

const String shareChannelName = 'io.github.ridhamsd1.scamchecker/share';

/// One item shared into the app.
sealed class SharedItem {
  const SharedItem();

  /// Decodes a map sent by the native side. Anything unexpected becomes an [SharedError].
  static SharedItem fromChannel(Object? raw) {
    if (raw is! Map) return const SharedError('mobile.shareReadFailed');
    switch (raw['kind']) {
      case 'text':
        final text = raw['text'];
        return text is String && text.trim().isNotEmpty
            ? SharedText(text)
            : const SharedError('mobile.shareUnsupported');
      case 'image':
        final bytes = raw['bytes'];
        return bytes is Uint8List && bytes.isNotEmpty
            ? SharedImage(bytes)
            : const SharedError('mobile.shareReadFailed');
      case 'error':
        return SharedError(switch (raw['code']) {
          'too_large' => 'too_large',
          'unsupported' => 'mobile.shareUnsupported',
          _ => 'mobile.shareReadFailed',
        });
      default:
        return const SharedError('mobile.shareReadFailed');
    }
  }
}

class SharedText extends SharedItem {
  const SharedText(this.text);
  final String text;
}

class SharedImage extends SharedItem {
  const SharedImage(this.bytes);
  final Uint8List bytes;
}

/// A share that can't be analysed. [code] is an error code or a `mobile.*` string key.
class SharedError extends SharedItem {
  const SharedError(this.code);
  final String code;
}

/// Source of shared items. The app uses [ChannelShareReceiver]; tests use a fake.
abstract class ShareReceiver {
  /// The share that launched the app, if any. Returns it only once.
  Future<SharedItem?> initialShare();

  /// Shares that arrive while the app is running.
  Stream<SharedItem> get shares;

  void dispose();
}

class ChannelShareReceiver implements ShareReceiver {
  ChannelShareReceiver({this.channel = const MethodChannel(shareChannelName)}) {
    channel.setMethodCallHandler((call) async {
      if (call.method == 'onShare') _controller.add(SharedItem.fromChannel(call.arguments));
      return null;
    });
  }

  final MethodChannel channel;
  final StreamController<SharedItem> _controller = StreamController<SharedItem>.broadcast();

  @override
  Future<SharedItem?> initialShare() async {
    try {
      final raw = await channel.invokeMethod<Object?>('getInitialShare');
      return raw == null ? null : SharedItem.fromChannel(raw);
    } on MissingPluginException {
      return null; // not running on Android (e.g. widget tests without a mock)
    } on PlatformException {
      return const SharedError('mobile.shareReadFailed');
    }
  }

  @override
  Stream<SharedItem> get shares => _controller.stream;

  @override
  void dispose() {
    channel.setMethodCallHandler(null);
    _controller.close();
  }
}
