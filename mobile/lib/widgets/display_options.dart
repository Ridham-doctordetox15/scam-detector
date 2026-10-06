/// Interface language (EN | हिंदी) and colour theme (System / Light / Dark). Choices last until
/// the app closes; nothing is saved.
library;

import 'package:flutter/material.dart';

import '../i18n/strings.dart';
import '../state/app_scope.dart';
import '../theme/tokens.dart';

/// App-bar button that opens the display options sheet.
class DisplayOptionsButton extends StatelessWidget {
  const DisplayOptionsButton({super.key});

  @override
  Widget build(BuildContext context) {
    return IconButton(
      key: const Key('display-options'),
      tooltip: Strings.of(context).t('mobile.displayOptions'),
      icon: const Icon(Icons.tune_rounded),
      onPressed: () => showModalBottomSheet<void>(context: context, builder: (_) => const DisplayOptionsSheet()),
    );
  }
}

class DisplayOptionsSheet extends StatelessWidget {
  const DisplayOptionsSheet({super.key});

  @override
  Widget build(BuildContext context) {
    final settings = AppScope.of(context).settings;
    return ListenableBuilder(
      listenable: settings,
      builder: (context, _) {
        final s = Strings.of(context);
        final text = Theme.of(context).textTheme;
        final current = Strings.languageFor(Localizations.localeOf(context));
        // Each language name in its own script and font, with the same line height, so
        // "EN" and "हिंदी" sit on one baseline in either interface language.
        Text langLabel(String key, {required bool devanagari}) =>
            Text(s.t(key), style: TextStyle(fontFamily: devanagari ? 'NotoSansDevanagari' : 'NotoSans', height: 1.3));
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(Space.xl, 0, Space.xl, Space.xl),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Semantics(header: true, child: Text(s.t('mobile.displayOptions'), style: text.titleLarge)),
                const SizedBox(height: Space.xl),
                Text(s.t('langSwitch.label'), style: text.titleSmall),
                const SizedBox(height: Space.sm),
                SegmentedButton<UiLanguage>(
                  key: const Key('language-switch'),
                  segments: [
                    ButtonSegment(value: UiLanguage.en, label: langLabel('langSwitch.en', devanagari: false)),
                    ButtonSegment(value: UiLanguage.hi, label: langLabel('langSwitch.hi', devanagari: true)),
                  ],
                  selected: {current},
                  onSelectionChanged: (v) => settings.locale = Locale(v.first.name),
                ),
                const SizedBox(height: Space.xl),
                Text(s.t('theme.label'), style: text.titleSmall),
                const SizedBox(height: Space.sm),
                SegmentedButton<ThemeMode>(
                  key: const Key('theme-switch'),
                  segments: [
                    ButtonSegment(
                      value: ThemeMode.system,
                      icon: const Icon(Icons.brightness_auto_outlined),
                      label: Text(s.t('theme.system')),
                    ),
                    ButtonSegment(
                      value: ThemeMode.light,
                      icon: const Icon(Icons.light_mode_outlined),
                      label: Text(s.t('theme.light')),
                    ),
                    ButtonSegment(
                      value: ThemeMode.dark,
                      icon: const Icon(Icons.dark_mode_outlined),
                      label: Text(s.t('theme.dark')),
                    ),
                  ],
                  showSelectedIcon: false,
                  selected: {settings.themeMode},
                  onSelectionChanged: (v) => settings.themeMode = v.first,
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
