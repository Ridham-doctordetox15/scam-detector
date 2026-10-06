/// About: how it works, what the numbers mean, privacy, limitations and sharing tips.
/// The text is the web app's About page wording (web/src/i18n), except the few app-only notes.
library;

import 'package:flutter/material.dart';

import '../i18n/strings.dart';
import '../theme/app_theme.dart';
import '../theme/tokens.dart';
import '../widgets/display_options.dart';
import '../widgets/ui.dart';

/// Keys of the web "What the numbers mean" findings, in display order.
const List<String> _findingKeys = [
  'about.findings.transformer',
  'about.findings.unseen',
  'about.findings.promotions',
  'about.findings.rag',
  'about.findings.ocr',
  'about.findings.realScreenshots',
  'about.findings.noIndianSet',
];

class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final text = Theme.of(context).textTheme;
    final muted = AppColors.of(context).mutedForeground;

    // The web's last limitation is about the website's demo mode, which the app doesn't have.
    final limits = s.list('about.limits').take(3).toList();
    // The web's last privacy point is about "this website"; the app has its own versions.
    final privacy = [...s.list('about.privacy').take(4), ...s.list('mobile.privacyApp')];

    Widget section(IconData icon, String title, Widget child) => Padding(
      padding: const EdgeInsets.only(top: Space.cardGap),
      child: SectionCard(icon: icon, title: title, child: child),
    );

    return Scaffold(
      appBar: AppBar(title: Text(s.t('about.title')), actions: const [DisplayOptionsButton()]),
      body: SafeArea(
        child: ListView(
          key: const Key('about-list'),
          padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xs, Space.gutter, Space.xxl),
          children: [
            Text(s.t('about.intro'), style: text.bodyLarge),
            section(
              Icons.account_tree_outlined,
              s.t('about.howHeading'),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(s.t('about.diagramDesc'), style: text.bodyMedium?.copyWith(color: muted)),
                  const SizedBox(height: Space.md),
                  _Numbered(items: s.list('about.steps')),
                ],
              ),
            ),
            section(Icons.ios_share_rounded, s.t('mobile.shareHeading'), _Bullets(items: s.list('mobile.shareTips'))),
            section(
              Icons.insights_outlined,
              s.t('about.findingsHeading'),
              _Bullets(items: [for (final k in _findingKeys) s.t(k)]),
            ),
            section(Icons.lock_outline_rounded, s.t('about.privacyHeading'), _Bullets(items: privacy)),
            section(Icons.info_outline_rounded, s.t('about.limitsHeading'), _Bullets(items: limits)),
            section(
              Icons.code_rounded,
              s.t('about.sourceHeading'),
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(s.t('about.sourceText'), style: text.bodyMedium),
                  const SizedBox(height: Space.lg),
                  OutlinedButton.icon(
                    key: const Key('licences'),
                    icon: const Icon(Icons.description_outlined),
                    label: Text(s.t('mobile.licences')),
                    onPressed: () => showLicensePage(context: context, applicationName: s.t('meta.title')),
                  ),
                ],
              ),
            ),
            const SizedBox(height: Space.xl),
            Text(s.t('footer.disclaimer'), style: text.bodySmall?.copyWith(color: muted)),
          ],
        ),
      ),
    );
  }
}

class _Bullets extends StatelessWidget {
  const _Bullets({required this.items});

  final List<String> items;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.bodyMedium;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final (i, item) in items.indexed) ...[
          if (i > 0) const SizedBox(height: Space.sm),
          MarkedRow(
            markerTop: 0,
            gap: Space.sm + 2,
            marker: ExcludeSemantics(child: Text('•', style: style)),
            child: Text(item, style: style),
          ),
        ],
      ],
    );
  }
}

class _Numbered extends StatelessWidget {
  const _Numbered({required this.items});

  final List<String> items;

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.bodyMedium;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final (i, item) in items.indexed) ...[
          if (i > 0) const SizedBox(height: Space.md),
          MarkedRow(
            marker: StepNumber(i + 1),
            child: Text(item, style: style),
          ),
        ],
      ],
    );
  }
}
