/// Material 3 light and dark themes using the web app's design tokens (web/src/app/globals.css),
/// including its exact risk colours. WCAG AA contrast is checked by test/theme_contrast_test.dart.
library;

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../util/text_utils.dart';
import 'tokens.dart';

/// The four colours used for one risk level.
@immutable
class RiskColors {
  const RiskColors({required this.fg, required this.bg, required this.border, required this.solid});

  /// Text and icons on [bg] or on the card surface (>= 4.5:1).
  final Color fg;

  /// Tinted background behind the verdict.
  final Color bg;

  /// Borders of risk chips (decorative).
  final Color border;

  /// Graphic colour for the gauge (>= 3:1 against the card surface).
  final Color solid;
}

/// Risk colours plus the few web tokens Material's ColorScheme doesn't have.
@immutable
class AppColors extends ThemeExtension<AppColors> {
  const AppColors({
    required this.low,
    required this.medium,
    required this.high,
    required this.mutedForeground,
    required this.subtle,
    required this.border,
  });

  final RiskColors low;
  final RiskColors medium;
  final RiskColors high;
  final Color mutedForeground;
  final Color subtle;
  final Color border;

  RiskColors risk(RiskLevel level) => switch (level) {
    RiskLevel.low => low,
    RiskLevel.medium => medium,
    RiskLevel.high => high,
  };

  static AppColors of(BuildContext context) => Theme.of(context).extension<AppColors>()!;

  static const AppColors light = AppColors(
    low: RiskColors(fg: Color(0xFF0B6B3A), bg: Color(0xFFE8F6EE), border: Color(0xFFA6DDBE), solid: Color(0xFF15924F)),
    medium: RiskColors(
      fg: Color(0xFF8A4B00),
      bg: Color(0xFFFFF4E0),
      border: Color(0xFFF2CE8A),
      solid: Color(0xFFC27803),
    ),
    high: RiskColors(fg: Color(0xFFB4232C), bg: Color(0xFFFDECEC), border: Color(0xFFF4B4B7), solid: Color(0xFFD8323B)),
    mutedForeground: Color(0xFF565C69),
    subtle: Color(0xFFF6F7F9),
    border: Color(0xFFE3E5EA),
  );

  static const AppColors dark = AppColors(
    low: RiskColors(fg: Color(0xFF6EE7A8), bg: Color(0xFF0E2A1C), border: Color(0xFF1F5A3B), solid: Color(0xFF34C77B)),
    medium: RiskColors(
      fg: Color(0xFFFFC66B),
      bg: Color(0xFF2E2108),
      border: Color(0xFF6B4A12),
      solid: Color(0xFFF0A43A),
    ),
    high: RiskColors(fg: Color(0xFFFF9A9F), bg: Color(0xFF36141A), border: Color(0xFF7A2830), solid: Color(0xFFF2555E)),
    mutedForeground: Color(0xFFA3A9B6),
    subtle: Color(0xFF111418),
    border: Color(0xFF262B33),
  );

  @override
  AppColors copyWith() => this;

  @override
  AppColors lerp(covariant AppColors? other, double t) => t < 0.5 || other == null ? this : other;
}

/// Light colour scheme from the web tokens (primary #3B54D6).
const ColorScheme lightScheme = ColorScheme(
  brightness: Brightness.light,
  primary: Color(0xFF3B54D6),
  onPrimary: Color(0xFFFFFFFF),
  primaryContainer: Color(0xFFEEF1FD),
  onPrimaryContainer: Color(0xFF2A3FB0),
  secondary: Color(0xFF565C69),
  onSecondary: Color(0xFFFFFFFF),
  secondaryContainer: Color(0xFFF1F2F5),
  onSecondaryContainer: Color(0xFF1A1D24),
  error: Color(0xFFB4232C),
  onError: Color(0xFFFFFFFF),
  surface: Color(0xFFFFFFFF),
  onSurface: Color(0xFF0F1115),
  onSurfaceVariant: Color(0xFF565C69),
  surfaceContainerLowest: Color(0xFFFFFFFF),
  surfaceContainerLow: Color(0xFFFAFAFA),
  surfaceContainer: Color(0xFFF6F7F9),
  surfaceContainerHigh: Color(0xFFF1F2F5),
  surfaceContainerHighest: Color(0xFFE9EBEF),
  outline: Color(0xFF8D9096),
  outlineVariant: Color(0xFFE3E5EA),
);

/// Dark colour scheme from the web tokens (primary #93A5FF).
const ColorScheme darkScheme = ColorScheme(
  brightness: Brightness.dark,
  primary: Color(0xFF93A5FF),
  onPrimary: Color(0xFF0B1022),
  primaryContainer: Color(0xFF1C2340),
  onPrimaryContainer: Color(0xFFC3CEFF),
  secondary: Color(0xFFA3A9B6),
  onSecondary: Color(0xFF0B0D10),
  secondaryContainer: Color(0xFF1E222A),
  onSecondaryContainer: Color(0xFFE4E7EC),
  error: Color(0xFFFF9A9F),
  onError: Color(0xFF0B0D10),
  surface: Color(0xFF14171C),
  onSurface: Color(0xFFECEEF2),
  onSurfaceVariant: Color(0xFFA3A9B6),
  surfaceContainerLowest: Color(0xFF0B0D10),
  surfaceContainerLow: Color(0xFF111418),
  surfaceContainer: Color(0xFF181B21),
  surfaceContainerHigh: Color(0xFF1E222A),
  surfaceContainerHighest: Color(0xFF262B33),
  outline: Color(0xFF5C6578),
  outlineVariant: Color(0xFF262B33),
);

/// Builds a theme. In the Hindi interface every line gets the Devanagari line height and no
/// letter spacing, like the web app's `html[lang=hi]`; content in another language sets its own
/// height (text_utils.dart).
ThemeData buildTheme({required bool dark, required bool hindiUi}) {
  final scheme = dark ? darkScheme : lightScheme;
  final colors = dark ? AppColors.dark : AppColors.light;
  final textTheme = _textTheme(scheme, hindiUi: hindiUi);
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    fontFamily: 'NotoSans',
    fontFamilyFallback: const ['NotoSansDevanagari'],
    scaffoldBackgroundColor: dark ? const Color(0xFF0B0D10) : const Color(0xFFFAFAFA),
    extensions: [colors],
    textTheme: textTheme,
    materialTapTargetSize: MaterialTapTargetSize.padded,
  );
  final label = textTheme.labelLarge;
  const pillShape = StadiumBorder();
  OutlineInputBorder outline(Color c, [double w = 1]) => OutlineInputBorder(
    borderRadius: Radii.mdAll,
    borderSide: BorderSide(color: c, width: w),
  );
  return base.copyWith(
    pageTransitionsTheme: const PageTransitionsTheme(
      builders: {TargetPlatform.android: ReducedMotionTransitions(FadeForwardsPageTransitionsBuilder())},
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: scheme.surface,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: Radii.lgAll,
        side: BorderSide(color: colors.border),
      ),
    ),
    appBarTheme: AppBarTheme(
      backgroundColor: base.scaffoldBackgroundColor,
      surfaceTintColor: Colors.transparent,
      scrolledUnderElevation: 0,
      centerTitle: false,
      titleTextStyle: textTheme.titleLarge,
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: scheme.surface,
      contentPadding: const EdgeInsets.all(Space.lg),
      border: outline(scheme.outline),
      enabledBorder: outline(scheme.outline),
      focusedBorder: outline(scheme.primary, 2),
      hintStyle: textTheme.bodyLarge?.copyWith(color: colors.mutedForeground),
      helperStyle: textTheme.bodySmall?.copyWith(color: colors.mutedForeground),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(Space.minTouch, 52),
        padding: const EdgeInsets.symmetric(horizontal: Space.xl, vertical: Space.md),
        shape: pillShape,
        textStyle: label,
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        minimumSize: const Size(Space.minTouch, 52),
        padding: const EdgeInsets.symmetric(horizontal: Space.xl, vertical: Space.md),
        shape: pillShape,
        side: BorderSide(color: scheme.outline),
        textStyle: label,
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(Space.minTouch, Space.minTouch),
        padding: const EdgeInsets.symmetric(horizontal: Space.md),
        shape: pillShape,
        textStyle: label,
      ),
    ),
    segmentedButtonTheme: SegmentedButtonThemeData(
      style: SegmentedButton.styleFrom(
        minimumSize: const Size(Space.minTouch, Space.minTouch),
        textStyle: label,
        side: BorderSide(color: scheme.outline),
        selectedBackgroundColor: scheme.primaryContainer,
        selectedForegroundColor: scheme.onPrimaryContainer,
      ),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: const RoundedRectangleBorder(borderRadius: Radii.mdAll),
      insetPadding: const EdgeInsets.fromLTRB(Space.gutter, 0, Space.gutter, Space.lg),
      backgroundColor: scheme.onSurface,
      contentTextStyle: textTheme.bodyMedium?.copyWith(color: scheme.surface),
    ),
    bottomSheetTheme: BottomSheetThemeData(
      backgroundColor: scheme.surface,
      surfaceTintColor: Colors.transparent,
      showDragHandle: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(Radii.xl))),
    ),
    listTileTheme: ListTileThemeData(
      minVerticalPadding: Space.md,
      contentPadding: const EdgeInsets.symmetric(horizontal: Space.lg),
      shape: const RoundedRectangleBorder(borderRadius: Radii.lgAll),
      titleTextStyle: textTheme.bodyLarge?.copyWith(fontWeight: FontWeight.w600),
      subtitleTextStyle: textTheme.bodySmall?.copyWith(color: colors.mutedForeground),
    ),
    dividerTheme: DividerThemeData(color: colors.border, thickness: 1, space: 1),
    progressIndicatorTheme: ProgressIndicatorThemeData(color: scheme.primary, linearTrackColor: colors.border),
  );
}

/// One type scale for the whole app (tokens.dart). Latin: 1.25-1.4 for headings, 1.5 for body.
/// Hindi interface: 1.75 everywhere. Letter spacing is 0 everywhere: it splits Devanagari
/// conjuncts, and both languages should look like one app.
TextTheme _textTheme(ColorScheme scheme, {required bool hindiUi}) {
  TextStyle style(double size, FontWeight weight, double latinHeight) => TextStyle(
    fontFamily: 'NotoSans',
    fontFamilyFallback: const ['NotoSansDevanagari'],
    fontSize: size,
    fontWeight: weight,
    height: hindiUi ? devanagariLineHeight : latinHeight,
    letterSpacing: 0,
    color: scheme.onSurface,
  );
  return TextTheme(
    displayLarge: style(TypeScale.display + 6, FontWeight.w700, 1.25),
    displayMedium: style(TypeScale.display, FontWeight.w700, 1.25),
    displaySmall: style(TypeScale.display - 2, FontWeight.w700, 1.25),
    headlineLarge: style(TypeScale.headline + 4, FontWeight.w700, 1.3),
    headlineMedium: style(TypeScale.headline, FontWeight.w700, 1.3),
    headlineSmall: style(TypeScale.headline - 2, FontWeight.w700, 1.3),
    titleLarge: style(TypeScale.title + 2, FontWeight.w600, 1.4),
    titleMedium: style(TypeScale.title, FontWeight.w600, 1.4),
    titleSmall: style(TypeScale.body, FontWeight.w600, 1.4),
    bodyLarge: style(TypeScale.body, FontWeight.w400, latinLineHeight),
    bodyMedium: style(TypeScale.label + 1, FontWeight.w400, latinLineHeight),
    bodySmall: style(TypeScale.caption, FontWeight.w400, latinLineHeight),
    labelLarge: style(TypeScale.label + 1, FontWeight.w600, 1.4),
    labelMedium: style(TypeScale.caption, FontWeight.w600, 1.4),
    labelSmall: style(TypeScale.caption - 1, FontWeight.w600, 1.4),
  );
}

/// Page transitions that disappear when the phone's "Remove animations" setting is on.
class ReducedMotionTransitions extends PageTransitionsBuilder {
  const ReducedMotionTransitions(this.inner);

  final PageTransitionsBuilder inner;

  @override
  Duration get transitionDuration => inner.transitionDuration;

  @override
  Duration get reverseTransitionDuration => inner.reverseTransitionDuration;

  @override
  Widget buildTransitions<T>(
    PageRoute<T> route,
    BuildContext context,
    Animation<double> animation,
    Animation<double> secondaryAnimation,
    Widget child,
  ) {
    if (MediaQuery.disableAnimationsOf(context)) return child;
    return inner.buildTransitions(route, context, animation, secondaryAnimation, child);
  }
}
