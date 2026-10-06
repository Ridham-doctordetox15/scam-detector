import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:scamchecker/api/api_client.dart';
import 'package:scamchecker/api/models.dart';
import 'package:scamchecker/config/api_config.dart';

import 'helpers.dart';

void main() {
  group('requests match the web app', () {
    test('analyzeText posts JSON {text} to /analyze/text', () async {
      final api = FakeApi();
      final result = await api.client().analyzeText('Hello there');
      final req = api.requests.single;
      expect(req.method, 'POST');
      expect(req.url.toString(), 'http://test.local/analyze/text');
      expect(req.headers['content-type'], startsWith('application/json'));
      expect(jsonDecode(req.body), {'text': 'Hello there'});
      expect(result.verdict, Verdict.scam);
      expect(result.riskLevel, RiskLevel.high);
    });

    test('analyzeImage sends multipart field "file" with a neutral filename', () async {
      final api = FakeApi();
      await api.client().analyzeImage(pngBytes);
      final req = api.requests.single;
      expect(req.url.path, '/analyze/image');
      expect(req.headers['content-type'], startsWith('multipart/form-data'));
      final body = latin1.decode(req.bodyBytes);
      expect(body, contains('name="file"'));
      expect(body, contains('filename="screenshot.png"'));
    });

    test('sendFeedback posts only the prediction id and the answer', () async {
      final api = FakeApi();
      await api.client().sendFeedback('abc', UserVerdict.incorrect);
      final req = api.requests.single;
      expect(req.url.path, '/feedback');
      expect(jsonDecode(req.body), {'prediction_id': 'abc', 'user_verdict': 'incorrect'});
    });

    test('no cookies, auth or tracking headers are sent', () async {
      final api = FakeApi();
      await api.client().analyzeText('x');
      final headers = api.requests.single.headers.keys.map((k) => k.toLowerCase());
      expect(headers, isNot(contains('authorization')));
      expect(headers, isNot(contains('cookie')));
    });
  });

  group('errors', () {
    Future<ApiException> errorFor(http.Response response) async {
      final client = ApiClient(
        config: const ApiConfig.forUrl('http://test.local'),
        httpClient: MockClient((_) async => response),
      );
      try {
        await client.analyzeText('x');
      } on ApiException catch (e) {
        return e;
      }
      fail('expected ApiException');
    }

    test('API error body gives code, request id and Retry-After', () async {
      final e = await errorFor(
        FakeApi.json(
          {
            'error': {'code': 'rate_limited', 'message': 'slow down', 'request_id': 'req-1'},
          },
          status: 429,
          headers: {'retry-after': '17'},
        ),
      );
      expect(e.code, 'rate_limited');
      expect(e.status, 429);
      expect(e.requestId, 'req-1');
      expect(e.retryAfterS, 17);
    });

    test('non-JSON error body becomes unknown_error', () async {
      final e = await errorFor(http.Response('<html>Bad gateway</html>', 502));
      expect(e.code, 'unknown_error');
      expect(e.status, 502);
    });

    test('malformed success body becomes unknown_error', () async {
      final e = await errorFor(FakeApi.json({'verdict': 'scam'}));
      expect(e.code, 'unknown_error');
    });

    test('connection failure is network_error (server unreachable)', () async {
      final client = ApiClient(
        config: const ApiConfig.forUrl('http://test.local'),
        httpClient: MockClient((_) async => throw const SocketException('refused')),
      );
      expect(
        () => client.analyzeText('x'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', 'network_error')),
      );
    });

    test('no server configured is not_configured, and nothing is sent', () async {
      final api = FakeApi();
      final client = api.client(config: ApiConfig.resolve(isRelease: true, deployed: ''));
      expect(
        () => client.analyzeText('x'),
        throwsA(isA<ApiException>().having((e) => e.code, 'code', 'not_configured')),
      );
      expect(api.requests, isEmpty);
    });

    testWidgets('a request that never answers is client_timeout', (tester) async {
      final client = ApiClient(
        config: const ApiConfig.forUrl('http://test.local'),
        httpClient: MockClient((_) => Completer<http.Response>().future),
      );
      Object? error;
      unawaited(client.analyzeText('x').then((_) {}, onError: (Object e) => error = e));
      await tester.pump(const Duration(seconds: 29));
      expect(error, isNull);
      await tester.pump(const Duration(seconds: 2)); // past the 30 s text timeout
      expect(error, isA<ApiException>().having((e) => e.code, 'code', 'client_timeout'));
    });
  });

  group('health', () {
    test('ok, degraded and 503 map to statuses; unreachable is null', () async {
      Future<HealthStatus?> health(http.Response r) => ApiClient(
        config: const ApiConfig.forUrl('http://t.local'),
        httpClient: MockClient((_) async => r),
      ).checkHealth();
      expect(await health(FakeApi.json({'status': 'ok', 'components': {}})), HealthStatus.ok);
      expect(await health(FakeApi.json({'status': 'degraded', 'components': {}})), HealthStatus.degraded);
      expect(await health(FakeApi.json({'status': 'unavailable'}, status: 503)), HealthStatus.unavailable);
      final down = ApiClient(
        config: const ApiConfig.forUrl('http://t.local'),
        httpClient: MockClient((_) async => throw const SocketException('down')),
      );
      expect(await down.checkHealth(), isNull);
    });
  });
}
