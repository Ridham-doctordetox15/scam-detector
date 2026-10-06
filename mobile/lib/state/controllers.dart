/// App state with plain ChangeNotifiers (no state-management package). Nothing here is ever
/// persisted: results, inputs and settings live in memory and are gone when the app closes.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../api/api_client.dart';
import '../api/models.dart';
import '../config/api_config.dart';
import '../config/limits.dart';
import '../util/image_check.dart';
import '../util/text_utils.dart';

/// Theme and interface-language choice. Not saved: the app starts with the system theme and
/// the device language every time (owner decision: nothing is stored on the phone).
class AppSettings extends ChangeNotifier {
  ThemeMode _themeMode = ThemeMode.system;

  /// null = follow the device language.
  Locale? _locale;

  ThemeMode get themeMode => _themeMode;
  Locale? get locale => _locale;

  set themeMode(ThemeMode value) {
    if (value == _themeMode) return;
    _themeMode = value;
    notifyListeners();
  }

  set locale(Locale? value) {
    if (value == _locale) return;
    _locale = value;
    notifyListeners();
  }
}

/// Server reachability, from GET /health. Mirrors web/src/lib/useBackendMode.ts without the
/// demo mode: the app never pretends to analyse.
enum BackendState { checking, live, unreachable, notConfigured, insecure }

class BackendStatus extends ChangeNotifier {
  BackendStatus(this._api)
    : _state = switch (_api.config.problem) {
        null => BackendState.checking,
        ApiConfigProblem.notConfigured => BackendState.notConfigured,
        ApiConfigProblem.insecureInRelease => BackendState.insecure,
      } {
    _api.onSuccess = markReachable;
  }

  final ApiClient _api;
  BackendState _state;
  bool _retrying = false;

  /// Any successful API call proves the server is reachable: clear a stale "unreachable" banner.
  void markReachable() {
    if (_state == BackendState.unreachable || _state == BackendState.checking) {
      _state = BackendState.live;
      _notify();
    }
  }

  bool _disposed = false;

  BackendState get state => _state;
  bool get retrying => _retrying;

  /// Checks the server. Returns the new state so the caller can announce it.
  Future<BackendState> check() async {
    if (!_api.config.isConfigured) return _state;
    _retrying = _state != BackendState.checking;
    _notify();
    final health = await _api.checkHealth();
    _state = health == null || health == HealthStatus.unavailable ? BackendState.unreachable : BackendState.live;
    _retrying = false;
    _notify();
    return _state;
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    if (_api.onSuccess == markReachable) _api.onSuccess = null;
    super.dispose();
  }
}

/// What to analyse, and where it came from.
sealed class AnalysisInput {
  const AnalysisInput({this.fromShare = false});
  final bool fromShare;
}

class TextAnalysis extends AnalysisInput {
  const TextAnalysis(this.text, {super.fromShare});
  final String text;
}

class ImageAnalysis extends AnalysisInput {
  const ImageAnalysis(this.bytes, {super.fromShare});
  final Uint8List bytes;
}

/// Input that is already known to be unusable (e.g. an unsupported share).
class InvalidAnalysis extends AnalysisInput {
  const InvalidAnalysis(this.code, {super.fromShare});
  final String code;
}

/// An error to show: a code from the API's vocabulary (or a `mobile.*` key) plus details.
@immutable
class ErrorInfo {
  const ErrorInfo(this.code, {this.requestId, this.retryAfterS});

  factory ErrorInfo.from(Object error) => error is ApiException
      ? ErrorInfo(error.code, requestId: error.requestId, retryAfterS: error.retryAfterS)
      : const ErrorInfo('unknown_error');

  final String code;
  final String? requestId;
  final int? retryAfterS;
}

/// Client-side checks done before anything is sent (the API repeats them).
String? validateInput(AnalysisInput input) => switch (input) {
  TextAnalysis(:final text) when text.trim().isEmpty => 'empty_text',
  TextAnalysis(:final text) when charCount(text) > maxTextChars => 'text_too_long',
  TextAnalysis() => null,
  ImageAnalysis(:final bytes) => validateImageBytes(bytes),
  InvalidAnalysis(:final code) => code,
};

sealed class AnalysisState {
  const AnalysisState();
}

class AnalysisLoading extends AnalysisState {
  const AnalysisLoading();
}

class AnalysisDone extends AnalysisState {
  const AnalysisDone(this.result);
  final AnalyzeResponse result;
}

class AnalysisFailed extends AnalysisState {
  const AnalysisFailed(this.error);
  final ErrorInfo error;
}

/// Runs one analysis (and its retries) for the results screen.
class AnalysisController extends ChangeNotifier {
  AnalysisController(this._api, this.input);

  final ApiClient _api;
  final AnalysisInput input;
  AnalysisState _state = const AnalysisLoading();
  bool _running = false;
  bool _disposed = false;

  AnalysisState get state => _state;

  Future<void> run() async {
    if (_running) return; // no double submits
    final problem = validateInput(input);
    if (problem != null) {
      _set(AnalysisFailed(ErrorInfo(problem)));
      return;
    }
    _running = true;
    _set(const AnalysisLoading());
    try {
      final result = switch (input) {
        TextAnalysis(:final text) => await _api.analyzeText(text),
        ImageAnalysis(:final bytes) => await _api.analyzeImage(bytes),
        InvalidAnalysis() => throw StateError('unreachable'),
      };
      _set(AnalysisDone(result));
    } catch (e) {
      _set(AnalysisFailed(ErrorInfo.from(e)));
    } finally {
      _running = false;
    }
  }

  void _set(AnalysisState next) {
    _state = next;
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}

sealed class FeedbackState {
  const FeedbackState();
}

class FeedbackIdle extends FeedbackState {
  const FeedbackIdle();
}

class FeedbackSending extends FeedbackState {
  const FeedbackSending(this.verdict);
  final UserVerdict verdict;
}

class FeedbackSaved extends FeedbackState {
  const FeedbackSaved(this.verdict);
  final UserVerdict verdict;
}

class FeedbackFailed extends FeedbackState {
  const FeedbackFailed(this.error, {required this.isFinal});
  final ErrorInfo error;

  /// The server said no for good (too old, not configured): no retry is offered.
  final bool isFinal;
}

/// "Was this correct?" One answer per result; retry only for transient errors.
/// Mirrors web/src/components/FeedbackBox.tsx.
class FeedbackController extends ChangeNotifier {
  FeedbackController(this._api, this.predictionId);

  static const Set<String> _finalCodes = {'unknown_prediction', 'feedback_not_configured', 'invalid_request'};

  final ApiClient _api;
  final String predictionId;
  FeedbackState _state = const FeedbackIdle();
  bool _disposed = false;

  FeedbackState get state => _state;

  bool get buttonsEnabled => switch (_state) {
    FeedbackIdle() => true,
    FeedbackFailed(:final isFinal) => !isFinal,
    _ => false,
  };

  Future<void> answer(UserVerdict verdict) async {
    if (!buttonsEnabled) return;
    _set(FeedbackSending(verdict));
    try {
      await _api.sendFeedback(predictionId, verdict);
      _set(FeedbackSaved(verdict));
    } catch (e) {
      final info = ErrorInfo.from(e);
      _set(FeedbackFailed(info, isFinal: _finalCodes.contains(info.code)));
    }
  }

  void _set(FeedbackState next) {
    _state = next;
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
