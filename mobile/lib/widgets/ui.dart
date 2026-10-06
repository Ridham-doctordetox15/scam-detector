/// Small building blocks shared by every screen, so cards, panels and notices look the same
/// everywhere. All sizes come from theme/tokens.dart.
library;

import 'package:flutter/material.dart';

import '../theme/app_theme.dart';
import '../theme/tokens.dart';

/// A titled card: an optional decorative icon, a heading (announced as a heading), then content.
class SectionCard extends StatelessWidget {
  const SectionCard({super.key, required this.title, required this.child, this.icon, this.iconColor});

  final String title;
  final Widget child;
  final IconData? icon;
  final Color? iconColor;

  @override
  Widget build(BuildContext context) {
    final text = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Space.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              header: true,
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (icon != null) ...[
                    ExcludeSemantics(
                      child: Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Icon(icon, size: 20, color: iconColor ?? AppColors.of(context).mutedForeground),
                      ),
                    ),
                    const SizedBox(width: Space.sm),
                  ],
                  Expanded(child: Text(title, style: text.titleMedium)),
                ],
              ),
            ),
            const SizedBox(height: Space.md),
            child,
          ],
        ),
      ),
    );
  }
}

/// An icon in a soft circle. Decorative: hidden from screen readers.
class IconBadge extends StatelessWidget {
  const IconBadge({super.key, required this.icon, required this.background, required this.foreground, this.size = 44});

  final IconData icon;
  final Color background;
  final Color foreground;
  final double size;

  @override
  Widget build(BuildContext context) => ExcludeSemantics(
    child: Container(
      width: size,
      height: size,
      decoration: BoxDecoration(color: background, shape: BoxShape.circle),
      child: Icon(icon, color: foreground, size: size * 0.5),
    ),
  );
}

/// Tone of a [StatusPanel]: neutral for app problems (never the scam red), warning for "the
/// server is away" states.
enum StatusTone { neutral, warning }

/// A designed empty / error / status state: icon badge, title, message and actions.
class StatusPanel extends StatelessWidget {
  const StatusPanel({
    super.key,
    required this.icon,
    required this.title,
    this.body,
    this.footnote,
    this.actions = const [],
    this.tone = StatusTone.neutral,
  });

  final IconData icon;
  final String title;
  final String? body;

  /// Small selectable line under the message (e.g. a request ID for support).
  final String? footnote;
  final List<Widget> actions;
  final StatusTone tone;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final colors = AppColors.of(context);
    final text = Theme.of(context).textTheme;
    final (badgeBg, badgeFg, border) = switch (tone) {
      StatusTone.neutral => (scheme.primaryContainer, scheme.onPrimaryContainer, colors.border),
      StatusTone.warning => (colors.medium.bg, colors.medium.fg, colors.medium.border),
    };
    return Card(
      shape: RoundedRectangleBorder(
        borderRadius: Radii.lgAll,
        side: BorderSide(color: border),
      ),
      child: Padding(
        padding: const EdgeInsets.all(Space.xl),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            IconBadge(icon: icon, background: badgeBg, foreground: badgeFg),
            const SizedBox(height: Space.lg),
            Semantics(header: true, child: Text(title, style: text.titleMedium)),
            if (body != null) ...[const SizedBox(height: Space.xs), Text(body!, style: text.bodyLarge)],
            if (footnote != null) ...[
              const SizedBox(height: Space.sm),
              SelectableText(footnote!, style: text.bodySmall?.copyWith(color: colors.mutedForeground)),
            ],
            if (actions.isNotEmpty) ...[
              const SizedBox(height: Space.xl),
              Wrap(spacing: Space.md, runSpacing: Space.sm, children: actions),
            ],
          ],
        ),
      ),
    );
  }
}

/// A short message right under the control it is about (e.g. "Please paste a message first").
/// Announced when it appears; uses the primary colour, not the scam red.
class InlineNotice extends StatelessWidget {
  const InlineNotice({super.key, required this.message, this.icon = Icons.info_outline_rounded});

  final String message;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Semantics(
      liveRegion: true,
      container: true,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: Space.md, vertical: Space.sm + 2),
        decoration: BoxDecoration(color: scheme.primaryContainer, borderRadius: Radii.mdAll),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ExcludeSemantics(
              child: Padding(
                padding: const EdgeInsets.only(top: 2),
                child: Icon(icon, size: 20, color: scheme.onPrimaryContainer),
              ),
            ),
            const SizedBox(width: Space.sm),
            Expanded(
              child: Text(
                message,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: scheme.onPrimaryContainer),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A numbered list marker. Decorative: the list order already gives the number to TalkBack.
class StepNumber extends StatelessWidget {
  const StepNumber(this.number, {super.key});

  final int number;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    // Grows with the text size (up to 1.6x), so the number stays readable at large font sizes.
    final scaler = MediaQuery.textScalerOf(context).clamp(maxScaleFactor: 1.6);
    final size = scaler.scale(26);
    return ExcludeSemantics(
      child: Container(
        width: size,
        height: size,
        alignment: Alignment.center,
        decoration: BoxDecoration(color: scheme.primaryContainer, shape: BoxShape.circle),
        child: Text(
          '$number',
          textScaler: scaler,
          style: Theme.of(context).textTheme.labelMedium?.copyWith(color: scheme.onPrimaryContainer, height: 1.2),
        ),
      ),
    );
  }
}

/// A bulleted or icon-marked row: [marker] at the first line, [child] wrapping beside it.
class MarkedRow extends StatelessWidget {
  const MarkedRow({super.key, required this.marker, required this.child, this.gap = Space.md, this.markerTop = 2});

  final Widget marker;
  final Widget child;
  final double gap;
  final double markerTop;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Padding(
        padding: EdgeInsets.only(top: markerTop),
        child: marker,
      ),
      SizedBox(width: gap),
      Expanded(child: child),
    ],
  );
}
