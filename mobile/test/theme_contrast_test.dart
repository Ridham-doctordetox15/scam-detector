import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:scamchecker/api/models.dart';
import 'package:scamchecker/theme/app_theme.dart';

/// WCAG 2.x relative luminance and contrast ratio.
double _luminance(Color c) {
  double ch(double v) => v <= 0.04045 ? v / 12.92 : math.pow((v + 0.055) / 1.055, 2.4).toDouble();
  return 0.2126 * ch(c.r) + 0.7152 * ch(c.g) + 0.0722 * ch(c.b);
}

double contrast(Color a, Color b) {
  final la = _luminance(a), lb = _luminance(b);
  return (math.max(la, lb) + 0.05) / (math.min(la, lb) + 0.05);
}

void main() {
  test('contrast helper matches known values', () {
    expect(contrast(Colors.black, Colors.white), closeTo(21, 0.01));
    expect(contrast(Colors.white, Colors.white), closeTo(1, 0.001));
  });

  for (final (name, colors, scheme) in [
    ('light', AppColors.light, lightScheme),
    ('dark', AppColors.dark, darkScheme),
  ]) {
    group('$name theme meets WCAG AA', () {
      for (final level in RiskLevel.values) {
        final c = colors.risk(level);
        test('${level.name}: risk text on its tint and on the card is >= 4.5:1', () {
          expect(contrast(c.fg, c.bg), greaterThanOrEqualTo(4.5));
          expect(contrast(c.fg, scheme.surface), greaterThanOrEqualTo(4.5));
          expect(contrast(c.fg, colors.subtle), greaterThanOrEqualTo(4.5));
        });
        test('${level.name}: gauge colour is >= 3:1 against its tint (non-text graphic)', () {
          expect(contrast(c.solid, c.bg), greaterThanOrEqualTo(3));
        });
      }

      test('body, muted and primary text are >= 4.5:1', () {
        expect(contrast(scheme.onSurface, scheme.surface), greaterThanOrEqualTo(4.5));
        expect(contrast(colors.mutedForeground, scheme.surface), greaterThanOrEqualTo(4.5));
        expect(contrast(colors.mutedForeground, colors.subtle), greaterThanOrEqualTo(4.5));
        expect(contrast(scheme.primary, scheme.surface), greaterThanOrEqualTo(4.5));
        expect(contrast(scheme.onPrimary, scheme.primary), greaterThanOrEqualTo(4.5));
        expect(contrast(scheme.onPrimaryContainer, scheme.primaryContainer), greaterThanOrEqualTo(4.5));
      });

      // Phase 11b pairs.
      final page = buildTheme(dark: name == 'dark', hindiUi: false).scaffoldBackgroundColor;

      test('text directly on the page background is >= 4.5:1', () {
        expect(contrast(scheme.onSurface, page), greaterThanOrEqualTo(4.5));
        expect(contrast(colors.mutedForeground, page), greaterThanOrEqualTo(4.5));
        expect(contrast(scheme.primary, page), greaterThanOrEqualTo(4.5));
      });

      for (final level in RiskLevel.values) {
        final c = colors.risk(level);
        test('${level.name}: inactive gauge labels (muted) on the hero tint are >= 4.5:1', () {
          expect(contrast(colors.mutedForeground, c.bg), greaterThanOrEqualTo(4.5));
        });
      }

      test('server banner text on the warning tint, picker title on the subtle panel', () {
        expect(contrast(scheme.onSurface, colors.medium.bg), greaterThanOrEqualTo(4.5));
        expect(contrast(scheme.primary, colors.subtle), greaterThanOrEqualTo(4.5));
      });

      test('snackbar: inverted text is >= 4.5:1', () {
        expect(contrast(scheme.surface, scheme.onSurface), greaterThanOrEqualTo(4.5));
      });

      test('input and button outlines are >= 3:1 against the card (WCAG 1.4.11, non-text)', () {
        expect(contrast(scheme.outline, scheme.surface), greaterThanOrEqualTo(3));
        expect(contrast(scheme.outline, page), greaterThanOrEqualTo(3));
      });

      test('the three risk levels look different (not colour alone: icons differ too)', () {
        final solids = RiskLevel.values.map((l) => colors.risk(l).solid).toSet();
        expect(solids.length, 3);
      });
    });
  }

  test('launcher icon and splash logo: white artwork on indigo, logo against both splash colours', () {
    const indigo = Color(0xFF3B54D6);
    expect(contrast(Colors.white, indigo), greaterThanOrEqualTo(4.5));
    // The logo is an indigo circle on the light or dark launch background (graphic: >= 3:1).
    expect(contrast(indigo, const Color(0xFFFAFAFA)), greaterThanOrEqualTo(3));
    expect(contrast(indigo, const Color(0xFF0B0D10)), greaterThanOrEqualTo(3));
  });
}
