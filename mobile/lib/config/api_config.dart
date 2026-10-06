/// Where the app sends requests. This is the ONE place to change the API address.
///
/// Pick a target at build time with `--dart-define`:
///
///   flutter run --dart-define=API_TARGET=local        (default for debug builds)
///   flutter build apk --release                       (always uses [deployedApiUrl])
///   flutter run --dart-define=API_URL=http://192.168.1.20:7860   (any other address, debug only)
///
/// `local` means http://127.0.0.1:7860 on the phone, forwarded over USB to the API on your
/// computer with `adb reverse tcp:7860 tcp:7860`. No firewall or Wi-Fi setup is needed.
///
/// Release builds only accept an https:// address. Anything else is treated as "no server
/// configured", so a release APK can never talk to a server in plain text.
library;

import 'package:flutter/foundation.dart';

/// The hosted API. Empty until the backend is deployed (then: `https://<space>.hf.space`).
/// Put the deployed URL here and rebuild the release APK. No trailing slash needed.
const String deployedApiUrl = '';

/// The API on your computer, reached from the phone through `adb reverse`.
const String localApiUrl = 'http://127.0.0.1:7860';

/// Build-time choices. Both are optional; see the library comment.
const String _targetDefine = String.fromEnvironment('API_TARGET');
const String _urlDefine = String.fromEnvironment('API_URL');

/// Why no usable API address is available.
enum ApiConfigProblem {
  /// No address was configured (the backend is not hosted yet).
  notConfigured,

  /// A release build was given a non-HTTPS address, which is refused.
  insecureInRelease,
}

/// The resolved API address, or the reason there is none.
@immutable
class ApiConfig {
  const ApiConfig._(this.baseUrl, this.problem);

  /// A usable configuration pointing at [url] (trailing slashes removed).
  const ApiConfig.forUrl(String url) : this._(url, null);

  /// Base URL without a trailing slash, or null when [problem] is set.
  final String? baseUrl;
  final ApiConfigProblem? problem;

  bool get isConfigured => baseUrl != null;

  /// Resolves the address for this build. Parameters exist for tests.
  static ApiConfig resolve({
    bool isRelease = kReleaseMode,
    String target = _targetDefine,
    String urlOverride = _urlDefine,
    String deployed = deployedApiUrl,
  }) {
    final String raw;
    if (urlOverride.isNotEmpty) {
      raw = urlOverride;
    } else if (isRelease || target == 'deployed') {
      raw = deployed;
    } else {
      // Debug and profile builds default to the local API.
      raw = localApiUrl;
    }
    final url = raw.trim().replaceAll(RegExp(r'/+$'), '');
    if (url.isEmpty) return const ApiConfig._(null, ApiConfigProblem.notConfigured);
    final uri = Uri.tryParse(url);
    final scheme = uri?.scheme.toLowerCase();
    if (uri == null || (scheme != 'http' && scheme != 'https') || uri.host.isEmpty) {
      return const ApiConfig._(null, ApiConfigProblem.notConfigured);
    }
    if (isRelease && scheme != 'https') {
      return const ApiConfig._(null, ApiConfigProblem.insecureInRelease);
    }
    return ApiConfig._(url, null);
  }
}
