/// Results: loading, then the result or an error. Used for typed text, picked screenshots and
/// content shared from other apps (which starts the check straight away).
///
/// The three states cross-fade, a haptic marks the moment the result arrives (stronger for
/// higher risk), and "Check another message" stays reachable in a bar at the bottom.
library;

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../api/models.dart';
import '../i18n/strings.dart';
import '../state/app_scope.dart';
import '../state/controllers.dart';
import '../theme/app_theme.dart';
import '../theme/motion.dart';
import '../theme/tokens.dart';
import '../widgets/display_options.dart';
import '../widgets/result_view.dart';
import '../widgets/status_widgets.dart';

class ResultsScreen extends StatefulWidget {
  const ResultsScreen({super.key, required this.input});

  final AnalysisInput input;

  /// Route name, so a new share can replace an open results screen.
  static const String routeName = '/results';

  static Route<void> route(AnalysisInput input) => AppPageRoute<void>(
    settings: const RouteSettings(name: routeName),
    builder: (_) => ResultsScreen(input: input),
  );

  @override
  State<ResultsScreen> createState() => _ResultsScreenState();
}

class _ResultsScreenState extends State<ResultsScreen> {
  AnalysisController? _controller;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_controller == null) {
      _controller = AnalysisController(AppScope.of(context).api, widget.input)..addListener(_onState);
      _controller!.run();
    }
  }

  /// A short haptic when a result arrives: heavier for higher risk.
  void _onState() {
    final state = _controller?.state;
    if (state is! AnalysisDone) return;
    unawaited(switch (state.result.riskLevel) {
      RiskLevel.high => HapticFeedback.heavyImpact(),
      RiskLevel.medium => HapticFeedback.mediumImpact(),
      RiskLevel.low => HapticFeedback.lightImpact(),
    });
  }

  @override
  void dispose() {
    _controller?.removeListener(_onState);
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final controller = _controller!;
    final input = widget.input;
    final text = Theme.of(context).textTheme;
    final muted = AppColors.of(context).mutedForeground;
    final motion = Motion.of(context);

    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final state = controller.state;
        final Widget content = switch (state) {
          AnalysisLoading() => ResultSkeleton(
            key: const ValueKey('loading'),
            message: s.t(input is ImageAnalysis ? 'form.analyzingImage' : 'form.analyzingText'),
            slow: input is ImageAnalysis,
          ),
          AnalysisDone(:final result) => ResultView(key: ValueKey(result.predictionId), result: result),
          AnalysisFailed(:final error) => ErrorCard(
            error: error,
            actions: [
              if (isRetryable(error.code))
                RetryButton(key: const Key('retry'), onPressed: controller.run, waitSeconds: error.retryAfterS),
            ],
          ),
        };
        return Scaffold(
          appBar: AppBar(title: Text(s.t('result.heading')), actions: const [DisplayOptionsButton()]),
          bottomNavigationBar: state is AnalysisLoading
              ? null
              : SafeArea(
                  child: Container(
                    padding: const EdgeInsets.fromLTRB(Space.gutter, Space.sm, Space.gutter, Space.md),
                    decoration: BoxDecoration(
                      color: Theme.of(context).scaffoldBackgroundColor,
                      border: Border(top: BorderSide(color: AppColors.of(context).border)),
                    ),
                    child: OutlinedButton.icon(
                      key: const Key('check-another'),
                      onPressed: () => Navigator.of(context).popUntil((r) => r.isFirst),
                      icon: const Icon(Icons.arrow_back_rounded),
                      label: Text(s.t('mobile.checkAnother')),
                    ),
                  ),
                ),
          body: SafeArea(
            child: ListView(
              padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xs, Space.gutter, Space.xl),
              children: [
                if (input.fromShare && input is! InvalidAnalysis)
                  Padding(
                    padding: const EdgeInsets.only(bottom: Space.md),
                    child: Row(
                      children: [
                        ExcludeSemantics(child: Icon(Icons.share_outlined, size: 18, color: muted)),
                        const SizedBox(width: Space.sm),
                        Expanded(
                          child: Text(
                            s.t(input is ImageAnalysis ? 'mobile.sharedImage' : 'mobile.sharedText'),
                            style: text.bodyMedium?.copyWith(color: muted),
                          ),
                        ),
                      ],
                    ),
                  ),
                AnimatedSwitcher(
                  duration: motion.medium,
                  switchInCurve: motion.curve,
                  switchOutCurve: Curves.easeIn,
                  layoutBuilder: (current, previous) =>
                      Stack(alignment: Alignment.topCenter, children: [...previous, ?current]),
                  child: content,
                ),
                const SizedBox(height: Space.lg),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: Space.xs),
                  child: Text(s.t('footer.disclaimer'), style: text.bodySmall?.copyWith(color: muted)),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
