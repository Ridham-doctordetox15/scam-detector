/// Design tokens: the one set of spacing, radius, type and motion values used everywhere.
///
/// Kept in line with the web app (web/src/app/globals.css): the same colours (app_theme.dart),
/// the web's `--radius: 12px` scale and its easing curve. Widgets use these names instead of raw
/// numbers, so the whole app changes together.
library;

import 'package:flutter/widgets.dart';

/// Spacing on a 4 dp grid.
abstract final class Space {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;

  /// Side margin of every screen.
  static const double gutter = 16;

  /// Gap between cards on a screen.
  static const double cardGap = 16;

  /// Minimum size of anything tappable (Material / WCAG target size).
  static const double minTouch = 48;
}

/// Corner radii (web: --radius 12px, -sm 8, -xl 16).
abstract final class Radii {
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 28;

  static const BorderRadius smAll = BorderRadius.all(Radius.circular(sm));
  static const BorderRadius mdAll = BorderRadius.all(Radius.circular(md));
  static const BorderRadius lgAll = BorderRadius.all(Radius.circular(lg));
  static const BorderRadius xlAll = BorderRadius.all(Radius.circular(xl));
  static const BorderRadius pill = BorderRadius.all(Radius.circular(999));
}

/// Type scale (logical px). Line heights are set per language in app_theme.dart.
abstract final class TypeScale {
  /// Verdict on the results screen.
  static const double display = 30;

  /// Screen hero ("Is this message a scam?").
  static const double headline = 24;

  /// Card and section titles.
  static const double title = 18;

  /// Everything readable, including the API's content.
  static const double body = 16;

  /// Buttons, chips, segment labels.
  static const double label = 14;

  /// Hints, disclaimers, small notes.
  static const double caption = 13;
}

/// Motion durations and curves. Always read through `Motion.of(context)` (motion.dart), which
/// turns them off when the phone's "Remove animations" setting is on.
abstract final class MotionTokens {
  static const Duration short = Duration(milliseconds: 150);
  static const Duration medium = Duration(milliseconds: 250);
  static const Duration long = Duration(milliseconds: 400);

  /// The gauge needle settling into its band.
  static const Duration gauge = Duration(milliseconds: 700);

  /// Delay between consecutive result cards appearing.
  static const Duration stagger = Duration(milliseconds: 60);

  /// The web app's easing: cubic-bezier(0.22, 1, 0.36, 1).
  static const Curve emphasized = Cubic(0.22, 1, 0.36, 1);
}
