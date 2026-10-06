/// Shows an analysis result: the same information as web/src/components/ResultCard.tsx.
///
/// Layout (Phase 11b): a risk-tinted hero with the gauge, the verdict and the single most
/// important step ("Do this first"), then cards in order: warning signs, the remaining steps, why,
/// and "More details" (pattern, links, screenshot text), then feedback. Cards appear one after
/// another unless the phone's "Remove animations" setting is on.
///
/// Deliberately never shows a probability or score (the API has none), timings, or any link as a
/// tappable link: links stay defanged plain text, including links inside text read from a
/// screenshot (the web app shows that text as-is; the app defangs it).
/// Interface labels follow the UI language; the API's content (red flags, explanation, advice)
/// gets typography for its own language from the response's `language` field.
library;

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';

import '../api/models.dart';
import '../generated/web_data.g.dart';
import '../i18n/strings.dart';
import '../theme/app_theme.dart';
import '../theme/motion.dart';
import '../theme/tokens.dart';
import '../util/text_utils.dart';
import 'feedback_box.dart';
import 'risk_widgets.dart';
import 'ui.dart';

/// Display name and category of a knowledge-base pattern. Unknown ids are prettified instead of
/// hidden, so a newer backend still shows something sensible (same rule as web/src/lib/patterns.ts).
({String name, bool? scam}) patternInfo(String id) {
  final known = patternNames[id];
  if (known != null) return (name: known.name, scam: known.scam);
  final words = id.replaceAll(RegExp(r'[_-]+'), ' ').trim();
  return (name: words.isEmpty ? id : words[0].toUpperCase() + words.substring(1), scam: null);
}

class ResultView extends StatelessWidget {
  const ResultView({super.key, required this.result});

  final AnalyzeResponse result;

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final colors = AppColors.of(context);
    final risk = colors.risk(result.riskLevel);
    final text = Theme.of(context).textTheme;
    final body = contentStyle(text.bodyLarge, result.language);
    final pattern = result.matchedPattern == null ? null : patternInfo(result.matchedPattern!);
    final laterSteps = result.whatToDo.skip(1).toList();

    final details = <Widget>[
      if (pattern != null)
        SectionCard(
          icon: Icons.fingerprint_rounded,
          title: s.t('result.matchedPattern'),
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: pattern.name,
                  style: const TextStyle(fontWeight: FontWeight.w600, height: latinLineHeight),
                ),
                if (pattern.scam != null)
                  TextSpan(
                    text: ' (${pattern.scam! ? s.t('result.patternScam') : s.t('result.patternLegit')})',
                    style: TextStyle(color: colors.mutedForeground),
                  ),
              ],
            ),
            style: text.bodyLarge,
          ),
        ),
      if (result.urlFindings.isNotEmpty)
        SectionCard(
          icon: Icons.link_off_rounded,
          title: s.t('result.links'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(s.t('result.linkNote'), style: text.bodyMedium?.copyWith(color: colors.mutedForeground)),
              for (final finding in result.urlFindings) ...[
                const SizedBox(height: Space.md),
                _LinkPanel(finding: finding),
              ],
            ],
          ),
        ),
      if (result.ocr != null) _OcrSection(ocr: result.ocr!),
    ];

    final cards = <Widget>[
      // 1. Warning signs (or a calm "none found").
      result.redFlags.isEmpty
          ? SectionCard(
              icon: Icons.check_circle_outline_rounded,
              iconColor: colors.low.fg,
              title: s.t('mobile.noWarningSignsTitle'),
              child: Text(s.t('result.noRedFlags'), style: text.bodyLarge?.copyWith(color: colors.mutedForeground)),
            )
          : SectionCard(
              icon: Icons.warning_amber_rounded,
              iconColor: risk.fg,
              title: s.t('result.redFlags'),
              child: Column(
                key: const Key('red-flags'),
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final (i, flag) in result.redFlags.indexed) ...[
                    if (i > 0) const SizedBox(height: Space.sm + 2),
                    MarkedRow(
                      markerTop: 3,
                      marker: ExcludeSemantics(child: Icon(Icons.error_outline_rounded, size: 20, color: risk.fg)),
                      child: Text(flag, style: body),
                    ),
                  ],
                ],
              ),
            ),
      // 2. The remaining steps (the first one is in the hero).
      if (laterSteps.isNotEmpty)
        SectionCard(
          icon: Icons.checklist_rounded,
          title: s.t('result.whatToDo'),
          child: Column(
            key: const Key('what-to-do'),
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              for (final (i, step) in laterSteps.indexed) ...[
                if (i > 0) const SizedBox(height: Space.md),
                // Numbered from 2: step 1 is "Do this first" above. Numbers are list markers.
                MarkedRow(
                  marker: StepNumber(i + 2),
                  child: Text(step, style: body),
                ),
              ],
            ],
          ),
        ),
      // 3. Why.
      SectionCard(
        icon: Icons.lightbulb_outline_rounded,
        title: s.t('result.explanation'),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(result.explanation, key: const Key('explanation'), style: body),
            const SizedBox(height: Space.md),
            _ExplainedBy(path: result.explainerPath),
          ],
        ),
      ),
      // 4. More details.
      if (details.isNotEmpty) ...[
        Padding(
          padding: const EdgeInsets.only(top: Space.sm, left: Space.xs),
          child: Semantics(header: true, child: Text(s.t('mobile.detailsHeading'), style: text.titleLarge)),
        ),
        ...details,
      ],
      Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.xs),
        child: Text(s.t('result.verdictNote'), style: text.bodySmall?.copyWith(color: colors.mutedForeground)),
      ),
      FeedbackBox(key: ValueKey(result.predictionId), predictionId: result.predictionId),
    ];

    return Column(
      key: const Key('result-card'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Entrance(child: ResultHero(result: result)),
        for (final (i, card) in cards.indexed) ...[
          const SizedBox(height: Space.cardGap),
          Entrance(index: i + 1, child: card),
        ],
      ],
    );
  }
}

/// The answer, first: gauge, verdict and risk level, and the single most important step.
/// Screen readers hear the verdict first, then the step, then the gauge (one image).
class ResultHero extends StatelessWidget {
  const ResultHero({super.key, required this.result});

  final AnalyzeResponse result;

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final risk = AppColors.of(context).risk(result.riskLevel);
    final scheme = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    final firstStep = result.whatToDo.isEmpty ? null : result.whatToDo.first;

    return Semantics(
      container: true,
      explicitChildNodes: true,
      child: Container(
        key: const Key('result-hero'),
        padding: const EdgeInsets.fromLTRB(Space.lg, Space.xl, Space.lg, Space.lg),
        decoration: BoxDecoration(
          color: risk.bg,
          borderRadius: Radii.xlAll,
          border: Border.all(color: risk.border),
        ),
        child: Column(
          children: [
            Semantics(
              sortKey: const OrdinalSortKey(2),
              child: RiskGauge(risk: result.riskLevel),
            ),
            const SizedBox(height: Space.lg),
            Semantics(
              sortKey: const OrdinalSortKey(0),
              child: RiskBand(verdict: result.verdict, risk: result.riskLevel),
            ),
            if (firstStep != null) ...[
              const SizedBox(height: Space.lg),
              Semantics(
                sortKey: const OrdinalSortKey(1),
                child: MergeSemantics(
                  child: Container(
                    key: const Key('first-step'),
                    width: double.infinity,
                    padding: const EdgeInsets.all(Space.lg),
                    decoration: BoxDecoration(color: scheme.surface, borderRadius: Radii.lgAll),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            ExcludeSemantics(child: Icon(Icons.arrow_circle_right_rounded, size: 20, color: risk.fg)),
                            const SizedBox(width: Space.sm),
                            Expanded(
                              child: Text(s.t('mobile.firstStep'), style: text.labelLarge?.copyWith(color: risk.fg)),
                            ),
                          ],
                        ),
                        const SizedBox(height: Space.xs),
                        Text(firstStep, style: contentStyle(text.titleMedium, result.language)),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// "Explanation written by an AI model (Groq)." Tap for the longer note.
class _ExplainedBy extends StatelessWidget {
  const _ExplainedBy({required this.path});

  final ExplainerPath path;

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final colors = AppColors.of(context);
    return Tooltip(
      message: s.t('result.aiTooltip'),
      triggerMode: TooltipTriggerMode.tap,
      // Not a Chip: a Chip cuts its label off on narrow phones; this pill wraps.
      child: Container(
        key: const Key('explained-by'),
        padding: const EdgeInsets.symmetric(horizontal: Space.md, vertical: Space.sm),
        decoration: BoxDecoration(
          color: colors.subtle,
          border: Border.all(color: colors.border),
          borderRadius: Radii.mdAll,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ExcludeSemantics(
              child: Icon(Icons.auto_awesome_outlined, size: 16, color: Theme.of(context).colorScheme.primary),
            ),
            const SizedBox(width: Space.sm),
            Flexible(
              child: Text(
                s.t('result.explainedBy', {'who': s.t('result.explainer.${path.name}')}),
                style: Theme.of(context).textTheme.bodySmall?.copyWith(color: colors.mutedForeground),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A tinted inner panel. A Material (not a coloured box), so ink effects of the expandable rows
/// inside stay visible.
class _Panel extends StatelessWidget {
  const _Panel({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return SizedBox(
      width: double.infinity,
      child: Material(
        color: colors.subtle,
        shape: RoundedRectangleBorder(
          borderRadius: Radii.mdAll,
          side: BorderSide(color: colors.border),
        ),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(Space.md + 2, Space.md, Space.md + 2, Space.xs),
          child: child,
        ),
      ),
    );
  }
}

/// An expandable row (link checks, screenshot text) with a 48 dp touch target and a chevron
/// that turns. Collapsed content is not built.
class _Expandable extends StatefulWidget {
  const _Expandable({super.key, required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  State<_Expandable> createState() => _ExpandableState();
}

class _ExpandableState extends State<_Expandable> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    final motion = Motion.of(context);
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          button: true,
          expanded: _open,
          child: InkWell(
            borderRadius: Radii.smAll,
            onTap: () => setState(() => _open = !_open),
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: Space.minTouch),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      widget.title,
                      style: Theme.of(context).textTheme.labelLarge?.copyWith(color: scheme.primary),
                    ),
                  ),
                  AnimatedRotation(
                    turns: _open ? 0.5 : 0,
                    duration: motion.medium,
                    curve: motion.curve,
                    child: ExcludeSemantics(child: Icon(Icons.expand_more_rounded, color: scheme.primary)),
                  ),
                ],
              ),
            ),
          ),
        ),
        SmoothSize(
          alignment: Alignment.topCenter,
          child: _open
              ? Padding(
                  padding: const EdgeInsets.only(bottom: Space.sm),
                  child: widget.child,
                )
              : const SizedBox(width: double.infinity),
        ),
      ],
    );
  }
}

class _LinkPanel extends StatelessWidget {
  const _LinkPanel({required this.finding});

  final UrlFinding finding;

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final colors = AppColors.of(context);
    final text = Theme.of(context).textTheme;
    final small = text.labelMedium?.copyWith(color: colors.mutedForeground, fontWeight: FontWeight.w500);
    return _Panel(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // A Wrap: with Hindi labels or large text the two labels go onto two lines.
          Wrap(
            spacing: Space.lg,
            runSpacing: Space.xs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ExcludeSemantics(
                    child: Icon(Icons.document_scanner_outlined, size: 16, color: colors.mutedForeground),
                  ),
                  const SizedBox(width: Space.xs + 2),
                  Flexible(child: Text(s.t('result.inspectedLink'), style: small)),
                ],
              ),
              Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ExcludeSemantics(child: Icon(Icons.lock_outline_rounded, size: 14, color: colors.mutedForeground)),
                  const SizedBox(width: Space.xs),
                  Flexible(child: Text(s.t('result.notClickable'), style: small)),
                ],
              ),
            ],
          ),
          const SizedBox(height: Space.sm),
          // Plain selectable text: never a link, never tappable. At least 48 dp tall, because it
          // can be long-pressed to copy (MergeSemantics gives TalkBack the 48 dp box, too).
          MergeSemantics(
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: Space.minTouch, minWidth: double.infinity),
              child: Align(
                alignment: Alignment.centerLeft,
                child: SelectableText(
                  finding.urlDefanged,
                  key: const Key('defanged-url'),
                  style: text.bodyMedium?.copyWith(fontFamily: 'monospace', height: latinLineHeight),
                ),
              ),
            ),
          ),
          RiskChip(
            risk: finding.riskBand,
            label: s.t('result.linkRisk', {'risk': s.t('result.risk.${finding.riskBand.name}')}),
          ),
          const SizedBox(height: Space.xs),
          if (finding.reasons.isNotEmpty)
            _Expandable(
              title: s.t('result.linkChecks', {'n': finding.reasons.length}),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final reason in finding.reasons)
                    Padding(
                      padding: const EdgeInsets.only(bottom: Space.xs),
                      child: MarkedRow(
                        gap: Space.sm,
                        markerTop: 0,
                        marker: ExcludeSemantics(child: Text('•', style: text.bodyMedium)),
                        child: Text(
                          reason,
                          style: text.bodyMedium?.copyWith(color: colors.mutedForeground, height: latinLineHeight),
                        ),
                      ),
                    ),
                ],
              ),
            )
          else
            const SizedBox(height: Space.sm),
        ],
      ),
    );
  }
}

class _OcrSection extends StatelessWidget {
  const _OcrSection({required this.ocr});

  final OcrInfo ocr;

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final colors = AppColors.of(context);
    final text = Theme.of(context).textTheme;
    // Links inside the screenshot's text are defanged too (a difference from the web app).
    final shown = defangLinksInText(ocr.extractedText);
    return SectionCard(
      icon: Icons.document_scanner_outlined,
      title: s.t('result.extractedText'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text.rich(
            TextSpan(
              children: [
                TextSpan(
                  text: '${s.t('result.ocrQuality')}: ',
                  style: const TextStyle(fontWeight: FontWeight.w600),
                ),
                TextSpan(text: s.t('result.ocrQualityValue.${ocr.quality.name}')),
              ],
            ),
            style: text.bodyLarge,
          ),
          if (ocr.darkMode)
            Padding(
              padding: const EdgeInsets.only(top: Space.xs),
              child: Row(
                children: [
                  ExcludeSemantics(child: Icon(Icons.dark_mode_outlined, size: 16, color: colors.mutedForeground)),
                  const SizedBox(width: Space.xs + 2),
                  Flexible(
                    child: Text(
                      s.t('result.darkMode'),
                      style: text.bodyMedium?.copyWith(color: colors.mutedForeground),
                    ),
                  ),
                ],
              ),
            ),
          const SizedBox(height: Space.xs),
          _Expandable(
            key: const Key('extracted-text-toggle'),
            title: s.t('mobile.showText'),
            child: _Panel(
              child: Padding(
                padding: const EdgeInsets.only(bottom: Space.sm),
                child: SelectableText(
                  shown,
                  key: const Key('extracted-text'),
                  style: guessedStyle(text.bodyMedium, shown),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
