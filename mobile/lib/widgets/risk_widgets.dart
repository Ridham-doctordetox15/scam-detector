/// Risk display: a band-only gauge, the verdict in words, and small risk chips.
///
/// The API returns no score, and none is shown: the gauge has three equal bands and the needle
/// settles on the middle of the active band, so it shows the band and nothing finer. It is exposed
/// to screen readers as one labelled image ("Risk level: High"), not as a slider or meter.
/// The band names sit under the arc (Low, Medium, High from left to right) with the active one
/// emphasised; nothing is printed above the arc, where it could be read as the answer.
library;

import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../api/models.dart';
import '../i18n/strings.dart';
import '../theme/app_theme.dart';
import '../theme/motion.dart';
import '../theme/tokens.dart';

/// A different icon shape per level, so colour is never the only signal.
IconData riskIcon(RiskLevel level) => switch (level) {
  RiskLevel.low => Icons.verified_user_outlined,
  RiskLevel.medium => Icons.warning_amber_rounded,
  RiskLevel.high => Icons.report_outlined,
};

class RiskGauge extends StatefulWidget {
  const RiskGauge({super.key, required this.risk, this.width = 200});

  final RiskLevel risk;
  final double width;

  /// Needle angle in degrees (180 = pointing left) for the middle of each band.
  static const Map<RiskLevel, double> needleDeg = {RiskLevel.low: 150, RiskLevel.medium: 90, RiskLevel.high: 30};

  @override
  State<RiskGauge> createState() => _RiskGaugeState();
}

class _RiskGaugeState extends State<RiskGauge> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this);
  bool _started = false;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    final motion = Motion.of(context);
    if (!motion.enabled) {
      _controller.value = 1; // "Remove animations": drawn in place
    } else {
      _controller.duration = motion.gauge;
      _controller.forward();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final colors = AppColors.of(context);
    final scheme = Theme.of(context).colorScheme;
    final label = s.t('result.gaugeLabel', {'risk': s.t('result.gaugeBand.${widget.risk.name}')});
    final base = Theme.of(context).textTheme.labelMedium?.copyWith(height: 1.2);
    final width = widget.width;

    Widget bandLabel(RiskLevel level, TextAlign align) {
      final active = level == widget.risk;
      return Expanded(
        child: Text(
          s.t('result.gaugeBand.${level.name}'),
          textAlign: align,
          style: base?.copyWith(
            color: active ? colors.risk(level).fg : colors.mutedForeground,
            fontWeight: active ? FontWeight.w700 : FontWeight.w500,
          ),
        ),
      );
    }

    return Semantics(
      key: const Key('risk-gauge'),
      label: label,
      image: true,
      excludeSemantics: true,
      child: SizedBox(
        width: width,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SizedBox(
              width: width,
              height: width * 0.56,
              child: AnimatedBuilder(
                animation: _controller,
                builder: (context, _) => CustomPaint(
                  painter: _GaugePainter(
                    risk: widget.risk,
                    colors: colors,
                    needle: scheme.onSurface,
                    hub: scheme.surface,
                    // Overshoots slightly and settles, like the web gauge's spring; the overshoot
                    // stays inside the active band.
                    progress: Curves.easeOutBack.transform(_controller.value),
                    highlight: Curves.easeOut.transform(_controller.value),
                  ),
                ),
              ),
            ),
            const SizedBox(height: Space.xs),
            Row(
              children: [
                bandLabel(RiskLevel.low, TextAlign.left),
                bandLabel(RiskLevel.medium, TextAlign.center),
                bandLabel(RiskLevel.high, TextAlign.right),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _GaugePainter extends CustomPainter {
  _GaugePainter({
    required this.risk,
    required this.colors,
    required this.needle,
    required this.hub,
    required this.progress,
    required this.highlight,
  });

  final RiskLevel risk;
  final AppColors colors;
  final Color needle;
  final Color hub;

  /// 0 = needle resting at the left end, 1 = in the middle of the active band.
  final double progress;

  /// 0 = all bands dimmed, 1 = active band at full colour.
  final double highlight;

  @override
  void paint(Canvas canvas, Size size) {
    const stroke = 16.0;
    final radius = math.min(size.width / 2, size.height) - stroke / 2 - 2;
    final center = Offset(size.width / 2, size.height - 6);
    const gap = 4 * math.pi / 180;
    final rect = Rect.fromCircle(center: center, radius: radius);
    for (final (i, level) in RiskLevel.values.indexed) {
      final active = level == risk;
      final alpha = active ? 0.28 + 0.72 * highlight : 0.28;
      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeCap = StrokeCap.round
        ..strokeWidth = active ? stroke : stroke - 5
        ..color = colors.risk(level).solid.withValues(alpha: alpha);
      // Canvas angles go clockwise from 3 o'clock; the gauge runs from 9 o'clock over the top.
      final start = math.pi + i * math.pi / 3 + (i == 0 ? 0 : gap / 2);
      final sweep = math.pi / 3 - (i == 0 || i == 2 ? gap / 2 : gap);
      canvas.drawArc(rect, start, sweep, false, paint);
    }
    final target = RiskGauge.needleDeg[risk]!;
    final deg = 180 + (target - 180) * progress;
    final angle = deg * math.pi / 180;
    final tip = center + Offset(math.cos(angle), -math.sin(angle)) * (radius - stroke - 6);
    canvas.drawLine(
      center,
      tip,
      Paint()
        ..color = needle
        ..strokeWidth = 4
        ..strokeCap = StrokeCap.round,
    );
    canvas.drawCircle(center, 8, Paint()..color = needle);
    canvas.drawCircle(center, 3.5, Paint()..color = hub);
  }

  @override
  bool shouldRepaint(_GaugePainter old) =>
      old.risk != risk ||
      old.colors != colors ||
      old.needle != needle ||
      old.progress != progress ||
      old.highlight != highlight;
}

/// Verdict and risk as words, with an icon whose shape differs per level. A live region, so
/// screen readers announce the verdict when the result appears.
class RiskBand extends StatelessWidget {
  const RiskBand({super.key, required this.verdict, required this.risk});

  final Verdict verdict;
  final RiskLevel risk;

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final c = AppColors.of(context).risk(risk);
    final text = Theme.of(context).textTheme;
    return Semantics(
      liveRegion: true,
      child: MergeSemantics(
        child: Row(
          key: const Key('risk-band'),
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(riskIcon(risk), color: c.fg, size: 34),
            const SizedBox(width: Space.md),
            Flexible(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(s.t('result.verdict.${verdict.name}'), style: text.displayMedium?.copyWith(color: c.fg)),
                  Text(s.t('result.risk.${risk.name}'), style: text.titleMedium?.copyWith(color: c.fg)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// Small pill with a risk word (used for links).
class RiskChip extends StatelessWidget {
  const RiskChip({super.key, required this.risk, required this.label});

  final RiskLevel risk;
  final String label;

  @override
  Widget build(BuildContext context) {
    final c = AppColors.of(context).risk(risk);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: c.bg,
        border: Border.all(color: c.border),
        borderRadius: Radii.pill,
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: Space.md - 2, vertical: Space.xs),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            ExcludeSemantics(child: Icon(riskIcon(risk), size: 16, color: c.fg)),
            const SizedBox(width: Space.xs + 2),
            Flexible(
              child: Text(label, style: Theme.of(context).textTheme.labelMedium?.copyWith(color: c.fg)),
            ),
          ],
        ),
      ),
    );
  }
}
