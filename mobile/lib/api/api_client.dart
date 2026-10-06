/// The only network code in the app. It talks to the project's API and nothing else, sends no
/// credentials or identifiers, and stores nothing. Mirrors web/src/lib/api.ts.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../config/api_config.dart';
import '../config/limits.dart';
import '../util/image_check.dart';
import 'models.dart';

/// An error with a code from the API's vocabulary, or one of the client codes
/// (`network_error`, `client_timeout`, `not_configured`, `unknown_error`).
class ApiException implements Exception {
  const ApiException(this.code, {this.status = 0, this.requestId, this.retryAfterS});

  final String code;
  final int status;
  final String? requestId;
  final int? retryAfterS;

  @override
  String toString() => 'ApiException($code, status $status)';
}

/// The four endpoints the web app uses: /analyze/text, /analyze/image, /feedback and /health.
class ApiClient {
  ApiClient({required this.config, http.Client? httpClient}) : _http = httpClient ?? http.Client();

  final ApiConfig config;
  final http.Client _http;

  /// Called after every successful (2xx) response: proof that the server is reachable, even if
  /// an earlier /health check timed out (e.g. during a slow cold start or on a slow network).
  void Function()? onSuccess;

  Uri _uri(String path) {
    final base = config.baseUrl;
    if (base == null) throw const ApiException('not_configured');
    return Uri.parse('$base$path');
  }

  /// Sends [request] with a timeout and turns every failure into an [ApiException].
  Future<Map<String, Object?>> _send(http.BaseRequest request, Duration timeout) async {
    final http.Response response;
    try {
      final streamed = await _http.send(request).timeout(timeout);
      response = await http.Response.fromStream(streamed).timeout(timeout);
    } on TimeoutException {
      throw const ApiException('client_timeout');
    } on ApiException {
      rethrow;
    } catch (_) {
      // SocketException, ClientException, TLS errors... The message is not shown or logged.
      throw const ApiException('network_error');
    }

    Object? payload;
    try {
      payload = jsonDecode(utf8.decode(response.bodyBytes));
    } catch (_) {
      payload = null;
    }
    final ok = response.statusCode >= 200 && response.statusCode < 300;
    if (!ok) {
      final error = payload is Map<String, Object?> ? payload['error'] : null;
      final code = error is Map<String, Object?> && error['code'] is String ? error['code'] as String : 'unknown_error';
      final requestId = error is Map<String, Object?> && error['request_id'] is String
          ? error['request_id'] as String
          : response.headers['x-request-id'];
      throw ApiException(
        code,
        status: response.statusCode,
        requestId: requestId,
        retryAfterS: int.tryParse(response.headers['retry-after'] ?? ''),
      );
    }
    onSuccess?.call();
    if (payload is Map<String, Object?>) return payload;
    if (response.statusCode == 201 || payload == null) return const <String, Object?>{};
    throw ApiException('unknown_error', status: response.statusCode);
  }

  AnalyzeResponse _parse(Map<String, Object?> json) {
    try {
      return AnalyzeResponse.fromJson(json);
    } on FormatError {
      throw const ApiException('unknown_error');
    }
  }

  /// POST /analyze/text.
  Future<AnalyzeResponse> analyzeText(String text) async {
    final request = http.Request('POST', _uri('/analyze/text'))
      ..headers['Content-Type'] = 'application/json'
      ..body = jsonEncode(<String, String>{'text': text});
    return _parse(await _send(request, textTimeout));
  }

  /// POST /analyze/image as multipart, field `file`, exactly like the web app.
  Future<AnalyzeResponse> analyzeImage(Uint8List bytes) async {
    final format = sniffImageFormat(bytes) ?? ImageFormat.png;
    final request = http.MultipartRequest('POST', _uri('/analyze/image'))
      ..files.add(
        http.MultipartFile.fromBytes(
          'file',
          bytes,
          // The API never uses or logs the filename and sniffs the format from the bytes, so a
          // fixed name is sent and the content type is left to the server's own check.
          filename: 'screenshot.${format.extension}',
        ),
      );
    return _parse(await _send(request, imageTimeout));
  }

  /// POST /feedback. Only the result id and the answer are sent.
  Future<void> sendFeedback(String predictionId, UserVerdict verdict) async {
    final request = http.Request('POST', _uri('/feedback'))
      ..headers['Content-Type'] = 'application/json'
      ..body = jsonEncode(<String, String>{'prediction_id': predictionId, 'user_verdict': verdict.name});
    await _send(request, feedbackTimeout);
  }

  /// GET /health. Returns null when the server can't be reached at all (asleep, offline, timed out).
  Future<HealthStatus?> checkHealth() async {
    try {
      final json = await _send(http.Request('GET', _uri('/health')), healthTimeout);
      return switch (json['status']) {
        'ok' => HealthStatus.ok,
        'degraded' => HealthStatus.degraded,
        _ => HealthStatus.unavailable,
      };
    } on ApiException catch (e) {
      if (e.status == 503) return HealthStatus.unavailable;
      return null;
    }
  }

  void close() => _http.close();
}
