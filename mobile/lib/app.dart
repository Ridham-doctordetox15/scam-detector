/// The app shell: themes, languages, services, and routing of content shared from other apps.
library;

import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';

import 'api/api_client.dart';
import 'i18n/strings.dart';
import 'platform/screenshot_picker.dart';
import 'platform/share_receiver.dart';
import 'screens/home_screen.dart';
import 'screens/results_screen.dart';
import 'state/app_scope.dart';
import 'state/controllers.dart';
import 'theme/app_theme.dart';

const List<Locale> supportedLocales = [Locale('en'), Locale('hi')];

/// Registers the bundled fonts' OFL licences on Flutter's licence page.
void registerFontLicences() {
  LicenseRegistry.addLicense(() async* {
    for (final (family, file) in const [
      ('Noto Sans', 'assets/fonts/OFL-NotoSans.txt'),
      ('Noto Sans Devanagari', 'assets/fonts/OFL-NotoSansDevanagari.txt'),
    ]) {
      yield LicenseEntryWithLineBreaks([family], await rootBundle.loadString(file));
    }
  });
}

class ScamCheckerApp extends StatefulWidget {
  const ScamCheckerApp({
    super.key,
    required this.api,
    required this.picker,
    required this.shareReceiver,
    this.settings,
  });

  final ApiClient api;
  final ScreenshotPicker picker;
  final ShareReceiver shareReceiver;

  /// Injected by tests to start in a given language or theme.
  final AppSettings? settings;

  @override
  State<ScamCheckerApp> createState() => _ScamCheckerAppState();
}

class _ScamCheckerAppState extends State<ScamCheckerApp> {
  final GlobalKey<NavigatorState> _navigator = GlobalKey<NavigatorState>();
  late final AppSettings _settings = widget.settings ?? AppSettings();
  late final BackendStatus _backend = BackendStatus(widget.api);
  StreamSubscription<SharedItem>? _shareSub;

  @override
  void initState() {
    super.initState();
    _backend.check();
    _shareSub = widget.shareReceiver.shares.listen(_onShare);
    widget.shareReceiver.initialShare().then((item) {
      if (item != null && mounted) _onShare(item);
    });
  }

  @override
  void dispose() {
    _shareSub?.cancel();
    widget.shareReceiver.dispose();
    _backend.dispose();
    if (widget.settings == null) _settings.dispose();
    super.dispose();
  }

  /// Opens the results screen for a share and starts the check straight away. Any screen that
  /// was open (an older result, About) is closed first, so Back always returns to Home.
  void _onShare(SharedItem item) {
    final input = switch (item) {
      SharedText(:final text) => TextAnalysis(text, fromShare: true),
      SharedImage(:final bytes) => ImageAnalysis(bytes, fromShare: true),
      SharedError(:final code) => InvalidAnalysis(code, fromShare: true),
    };
    void open() {
      final nav = _navigator.currentState;
      if (nav == null) return;
      nav.popUntil((route) => route.isFirst);
      nav.push(ResultsScreen.route(input));
    }

    // The navigator exists after the first frame; a share at launch may arrive before that.
    if (_navigator.currentState == null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => open());
    } else {
      open();
    }
  }

  @override
  Widget build(BuildContext context) {
    return AppScope(
      api: widget.api,
      picker: widget.picker,
      settings: _settings,
      backend: _backend,
      child: ListenableBuilder(
        listenable: _settings,
        builder: (context, _) => MaterialApp(
          navigatorKey: _navigator,
          debugShowCheckedModeBanner: false,
          onGenerateTitle: (context) => Strings.of(context).t('meta.title'),
          locale: _settings.locale,
          supportedLocales: supportedLocales,
          localizationsDelegates: GlobalMaterialLocalizations.delegates,
          // Device language Hindi -> Hindi interface; anything else -> English.
          localeResolutionCallback: (locale, supported) =>
              locale?.languageCode == 'hi' ? const Locale('hi') : const Locale('en'),
          themeMode: _settings.themeMode,
          theme: buildTheme(dark: false, hindiUi: false),
          darkTheme: buildTheme(dark: true, hindiUi: false),
          // The theme's line height must follow the *resolved* locale (device language too).
          builder: (context, child) {
            final hindi = Strings.of(context).isHindi;
            final dark = Theme.of(context).brightness == Brightness.dark;
            return Theme(
              data: buildTheme(dark: dark, hindiUi: hindi),
              child: child!,
            );
          },
          home: const HomeScreen(),
        ),
      ),
    );
  }
}
