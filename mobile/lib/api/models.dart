/// Response models. They mirror api/schemas.py and web/src/lib/types.ts.
///
/// There is deliberately no probability, score or timing field here: the API returns none that
/// the app may show, and `timings_ms` is not parsed so it can never reach the screen.
library;

import 'package:flutter/foundation.dart';

enum Verdict { safe, suspicious, scam }

enum RiskLevel { low, medium, high }

/// Language of the API's content (red flags, explanation, advice).
enum ContentLanguage { en, hi, hinglish }

enum ExplainerPath { groq, gemini, template }

enum OcrQuality { good, fair, poor }

enum UserVerdict { correct, incorrect }

/// Thrown when a response body doesn't match the documented schema.
class FormatError implements Exception {
  const FormatError(this.message);
  final String message;
  @override
  String toString() => 'FormatError: $message';
}

T _enum<T extends Enum>(List<T> values, Object? raw, String field) {
  for (final v in values) {
    if (v.name == raw) return v;
  }
  throw FormatError('Unexpected value for $field');
}

String _string(Map<String, Object?> json, String field) {
  final v = json[field];
  if (v is String) return v;
  throw FormatError('Missing or invalid $field');
}

List<String> _strings(Map<String, Object?> json, String field) {
  final v = json[field];
  if (v is List && v.every((e) => e is String)) return List<String>.unmodifiable(v.cast<String>());
  throw FormatError('Missing or invalid $field');
}

Map<String, Object?> _object(Object? v, String field) {
  if (v is Map<String, Object?>) return v;
  throw FormatError('Missing or invalid $field');
}

@immutable
class UrlFinding {
  const UrlFinding({required this.urlDefanged, required this.riskBand, required this.reasons});

  factory UrlFinding.fromJson(Map<String, Object?> json) => UrlFinding(
    urlDefanged: _string(json, 'url_defanged'),
    riskBand: _enum(RiskLevel.values, json['risk_band'], 'risk_band'),
    reasons: _strings(json, 'reasons'),
  );

  /// Already defanged by the API (`hxxp://x[.]tk`); shown as plain text, never as a link.
  final String urlDefanged;
  final RiskLevel riskBand;
  final List<String> reasons;
}

@immutable
class OcrInfo {
  const OcrInfo({required this.extractedText, required this.quality, required this.darkMode});

  factory OcrInfo.fromJson(Map<String, Object?> json) => OcrInfo(
    extractedText: _string(json, 'extracted_text'),
    quality: _enum(OcrQuality.values, json['quality'], 'quality'),
    darkMode: json['dark_mode'] == true,
  );

  final String extractedText;
  final OcrQuality quality;
  final bool darkMode;
}

@immutable
class AnalyzeResponse {
  const AnalyzeResponse({
    required this.predictionId,
    required this.verdict,
    required this.riskLevel,
    required this.redFlags,
    required this.explanation,
    required this.whatToDo,
    required this.matchedPattern,
    required this.urlFindings,
    required this.explainerPath,
    required this.language,
    required this.ocr,
  });

  /// Parses only the fields the app shows. Unknown fields are ignored on purpose.
  factory AnalyzeResponse.fromJson(Map<String, Object?> json) {
    final urls = json['url_findings'];
    if (urls is! List) throw const FormatError('Missing or invalid url_findings');
    final pattern = json['matched_pattern'];
    final ocr = json['ocr'];
    return AnalyzeResponse(
      predictionId: _string(json, 'prediction_id'),
      verdict: _enum(Verdict.values, json['verdict'], 'verdict'),
      riskLevel: _enum(RiskLevel.values, json['risk_level'], 'risk_level'),
      redFlags: _strings(json, 'red_flags'),
      explanation: _string(json, 'explanation'),
      whatToDo: _strings(json, 'what_to_do'),
      matchedPattern: pattern is String && pattern.isNotEmpty ? pattern : null,
      urlFindings: List<UrlFinding>.unmodifiable(urls.map((u) => UrlFinding.fromJson(_object(u, 'url_findings')))),
      explainerPath: _enum(ExplainerPath.values, json['explainer_path'], 'explainer_path'),
      // Older servers may not send `language`; English is the safe default for typography.
      language: json['language'] == null
          ? ContentLanguage.en
          : _enum(ContentLanguage.values, json['language'], 'language'),
      ocr: ocr == null ? null : OcrInfo.fromJson(_object(ocr, 'ocr')),
    );
  }

  final String predictionId;
  final Verdict verdict;
  final RiskLevel riskLevel;
  final List<String> redFlags;
  final String explanation;
  final List<String> whatToDo;
  final String? matchedPattern;
  final List<UrlFinding> urlFindings;
  final ExplainerPath explainerPath;
  final ContentLanguage language;
  final OcrInfo? ocr;
}

/// Server status from GET /health.
enum HealthStatus { ok, degraded, unavailable }
