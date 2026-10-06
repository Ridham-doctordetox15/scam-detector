/// "Was this correct?" Yes / No. Mirrors web/src/components/FeedbackBox.tsx: one answer per
/// result, retry only for transient errors, and the outcome shown inline plus a short snackbar.
///
/// The chosen answer stays visibly selected (filled, with a tick) after it is sent, the status
/// line grows in smoothly instead of leaving an empty gap, and a light haptic confirms the save.
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

class FeedbackBox extends StatefulWidget {
  const FeedbackBox({super.key, required this.predictionId});

  final String predictionId;

  @override
  State<FeedbackBox> createState() => _FeedbackBoxState();
}

class _FeedbackBoxState extends State<FeedbackBox> {
  FeedbackController? _controller;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _controller ??= FeedbackController(AppScope.of(context).api, widget.predictionId);
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  Future<void> _answer(UserVerdict verdict) async {
    final s = Strings.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final controller = _controller!;
    await controller.answer(verdict);
    final state = controller.state;
    if (state is FeedbackSaved) unawaited(HapticFeedback.lightImpact());
    messenger
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(switch (state) {
            FeedbackSaved() => s.t('feedback.toastSaved'),
            FeedbackFailed(:final error) =>
              '${s.t('feedback.toastFailed')}: ${s.errorMessage(error.code, retryAfterS: error.retryAfterS)}',
            _ => '',
          }),
        ),
      );
  }

  @override
  Widget build(BuildContext context) {
    final controller = _controller!;
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) {
        final s = Strings.of(context);
        final colors = AppColors.of(context);
        final scheme = Theme.of(context).colorScheme;
        final text = Theme.of(context).textTheme;
        final state = controller.state;
        final chosen = switch (state) {
          FeedbackSending(:final verdict) || FeedbackSaved(:final verdict) => verdict,
          _ => null,
        };
        final String status = switch (state) {
          FeedbackIdle() => '',
          FeedbackSending() => s.t('feedback.sending'),
          FeedbackSaved() => s.t('feedback.thanks'),
          FeedbackFailed(:final error, :final isFinal) =>
            s.errorMessage(error.code, retryAfterS: error.retryAfterS) + (isFinal ? '' : ' ${s.t('feedback.retry')}'),
        };

        Widget button(UserVerdict verdict, IconData icon, String label) {
          final onPressed = controller.buttonsEnabled ? () => _answer(verdict) : null;
          final selected = chosen == verdict;
          // Inside the button, so "selected" merges into the button's own TalkBack node.
          final child = Semantics(selected: selected, child: Text(label));
          // The chosen answer keeps its selected colours even while the buttons are locked.
          return selected
              ? FilledButton.icon(
                  onPressed: onPressed,
                  style: FilledButton.styleFrom(
                    backgroundColor: scheme.primaryContainer,
                    foregroundColor: scheme.onPrimaryContainer,
                    disabledBackgroundColor: scheme.primaryContainer,
                    disabledForegroundColor: scheme.onPrimaryContainer,
                  ),
                  icon: const Icon(Icons.check_rounded),
                  label: child,
                )
              : OutlinedButton.icon(onPressed: onPressed, icon: Icon(icon), label: child);
        }

        return Card(
          key: const Key('feedback-box'),
          child: Padding(
            padding: const EdgeInsets.all(Space.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Semantics(header: true, child: Text(s.t('feedback.question'), style: text.titleMedium)),
                Semantics(
                  liveRegion: true,
                  child: SmoothSize(
                    alignment: Alignment.topLeft,
                    child: status.isEmpty
                        ? const SizedBox(width: double.infinity)
                        : Padding(
                            padding: const EdgeInsets.only(top: Space.xs),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (state is FeedbackSaved) ...[
                                  ExcludeSemantics(
                                    child: Padding(
                                      padding: const EdgeInsets.only(top: 2),
                                      child: Icon(Icons.check_circle_rounded, size: 18, color: colors.low.fg),
                                    ),
                                  ),
                                  const SizedBox(width: Space.sm),
                                ],
                                Expanded(
                                  child: Text(status, style: text.bodyMedium?.copyWith(color: colors.mutedForeground)),
                                ),
                              ],
                            ),
                          ),
                  ),
                ),
                const SizedBox(height: Space.md),
                Wrap(
                  spacing: Space.sm,
                  runSpacing: Space.sm,
                  children: [
                    button(UserVerdict.correct, Icons.thumb_up_outlined, s.t('feedback.yes')),
                    button(UserVerdict.incorrect, Icons.thumb_down_outlined, s.t('feedback.no')),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
