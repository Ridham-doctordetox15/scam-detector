/// Error panel, retry button, server status banner and the loading skeleton.
///
/// Problems with the app or the server use neutral colours: the scam red is kept for "this
/// message is risky", so the two can never be confused.
library;

import 'dart:async';

import 'package:flutter/material.dart';

import '../i18n/strings.dart';
import '../state/controllers.dart';
import '../theme/app_theme.dart';
import '../theme/motion.dart';
import '../theme/tokens.dart';
import 'ui.dart';

/// An icon that hints at the kind of problem. Mirrors web/src/components/ErrorNotice.tsx.
IconData errorIcon(String code) {
  if (const {'network_error', 'client_timeout', 'not_configured'}.contains(code)) return Icons.wifi_off_rounded;
  if (const {'rate_limited', 'busy', 'timeout'}.contains(code)) return Icons.schedule_rounded;
  if (const {
    'unsupported_type',
    'corrupt',
    'empty',
    'too_small',
    'too_many_pixels',
    'no_text_found',
    'mobile.shareUnsupported',
    'mobile.shareReadFailed',
  }.contains(code)) {
    return Icons.hide_image_outlined;
  }
  if (const {'too_large', 'body_too_large', 'length_required'}.contains(code)) return Icons.file_present_outlined;
  if (const {'empty_text', 'text_too_long', 'invalid_request'}.contains(code)) return Icons.edit_note_rounded;
  if (code.endsWith('_unavailable') || code == 'internal_error') return Icons.dns_outlined;
  return Icons.error_outline_rounded;
}

/// A friendly message for any error code, plus the request ID for support, and optional actions.
class ErrorCard extends StatelessWidget {
  const ErrorCard({super.key, required this.error, this.actions = const []});

  final ErrorInfo error;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    return StatusPanel(
      key: ValueKey('error-${error.code}'),
      icon: errorIcon(error.code),
      title: s.t('errors.heading'),
      body: s.errorMessage(error.code, retryAfterS: error.retryAfterS),
      footnote: error.requestId == null ? null : '${s.t('errors.requestId', {'id': ''})}${error.requestId}',
      actions: actions,
    );
  }
}

/// "Try again". When the server said how long to wait, it counts down ("Try again in 20 s");
/// it stays usable throughout, exactly as before.
class RetryButton extends StatefulWidget {
  const RetryButton({super.key, required this.onPressed, this.waitSeconds});

  final VoidCallback onPressed;
  final int? waitSeconds;

  @override
  State<RetryButton> createState() => _RetryButtonState();
}

class _RetryButtonState extends State<RetryButton> {
  Timer? _timer;
  late int _left = widget.waitSeconds ?? 0;

  @override
  void initState() {
    super.initState();
    if (_left > 0) {
      _timer = Timer.periodic(const Duration(seconds: 1), (t) {
        setState(() => _left--);
        if (_left <= 0) t.cancel();
      });
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    return FilledButton.icon(
      onPressed: widget.onPressed,
      icon: const Icon(Icons.refresh_rounded),
      label: Text(_left > 0 ? s.t('mobile.retryIn', {'s': _left}) : s.t('mobile.tryAgain')),
    );
  }
}

/// Shows the server's state above the input form: checking, unreachable (with retry) or not
/// configured. Nothing is shown once the server is live.
class ServerStatusBanner extends StatelessWidget {
  const ServerStatusBanner({super.key, required this.status});

  final BackendStatus status;

  Future<void> _retry(BuildContext context) async {
    final s = Strings.of(context);
    final messenger = ScaffoldMessenger.of(context);
    final next = await status.check();
    messenger.showSnackBar(
      SnackBar(content: Text(next == BackendState.live ? s.t('mode.nowLive') : s.t('mode.stillUnreachable'))),
    );
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: status,
      builder: (context, _) {
        final s = Strings.of(context);
        final colors = AppColors.of(context);
        final scheme = Theme.of(context).colorScheme;
        final text = Theme.of(context).textTheme;
        final checking = status.state == BackendState.checking;

        Widget row(Widget leading, String title) => Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(padding: const EdgeInsets.only(top: 2), child: leading),
            const SizedBox(width: Space.md),
            Expanded(child: Text(title, style: text.titleSmall)),
          ],
        );

        final Widget? content = switch (status.state) {
          BackendState.live => null,
          BackendState.checking => row(
            const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2.5)),
            s.t('mode.checking'),
          ),
          BackendState.unreachable => Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              row(
                ExcludeSemantics(child: Icon(Icons.cloud_off_rounded, size: 20, color: colors.medium.fg)),
                s.t('mobile.unreachableTitle'),
              ),
              Padding(
                padding: const EdgeInsets.only(left: 20 + Space.md, top: Space.xs),
                child: Text(s.t('mobile.unreachableBody'), style: text.bodyMedium),
              ),
              Padding(
                padding: const EdgeInsets.only(left: 20 + Space.md - Space.md, top: Space.xs),
                child: TextButton.icon(
                  onPressed: status.retrying ? null : () => _retry(context),
                  icon: status.retrying
                      ? const SizedBox.square(dimension: 16, child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.refresh_rounded),
                  label: Text(status.retrying ? s.t('mode.retrying') : s.t('mode.retry')),
                ),
              ),
            ],
          ),
          BackendState.notConfigured || BackendState.insecure => row(
            ExcludeSemantics(child: Icon(Icons.cloud_off_rounded, size: 20, color: colors.medium.fg)),
            s.t(status.state == BackendState.insecure ? 'mobile.insecureTitle' : 'mobile.notConfiguredTitle'),
          ),
        };
        return SmoothSize(
          alignment: Alignment.topCenter,
          child: content == null
              ? const SizedBox(width: double.infinity)
              : Padding(
                  padding: const EdgeInsets.only(bottom: Space.lg),
                  child: Semantics(
                    liveRegion: true,
                    container: true,
                    child: Container(
                      key: ValueKey('server-${status.state.name}'),
                      width: double.infinity,
                      padding: const EdgeInsets.fromLTRB(Space.lg, Space.md, Space.lg, Space.md),
                      decoration: BoxDecoration(
                        color: checking ? scheme.surface : colors.medium.bg,
                        border: Border.all(color: checking ? colors.border : colors.medium.border),
                        borderRadius: Radii.lgAll,
                      ),
                      child: content,
                    ),
                  ),
                ),
        );
      },
    );
  }
}

/// Placeholder shaped like the real result (hero, then cards) while a check runs, with a gentle
/// shimmer (static when animations are off) and the loading message for screen readers.
/// For screenshots, a second reassuring line appears after a few seconds.
class ResultSkeleton extends StatefulWidget {
  const ResultSkeleton({super.key, required this.message, this.slow = false});

  final String message;

  /// True for screenshots, which can take much longer than text.
  final bool slow;

  @override
  State<ResultSkeleton> createState() => _ResultSkeletonState();
}

class _ResultSkeletonState extends State<ResultSkeleton> with SingleTickerProviderStateMixin {
  late final AnimationController _shimmer = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 1400),
  );
  Timer? _slowTimer;
  bool _showSlow = false;

  @override
  void initState() {
    super.initState();
    if (widget.slow) {
      _slowTimer = Timer(const Duration(seconds: 8), () {
        if (mounted) setState(() => _showSlow = true);
      });
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (Motion.of(context).enabled) {
      if (!_shimmer.isAnimating) _shimmer.repeat();
    } else {
      _shimmer.stop();
    }
  }

  @override
  void dispose() {
    _slowTimer?.cancel();
    _shimmer.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    final text = Theme.of(context).textTheme;
    final motion = Motion.of(context);
    Widget bar(double? width, double height, {double radius = Radii.sm}) => Container(
      width: width,
      height: height,
      decoration: BoxDecoration(color: colors.border, borderRadius: BorderRadius.circular(radius)),
    );
    Widget card(List<double?> lines) => Container(
      padding: const EdgeInsets.all(Space.lg),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: Radii.lgAll,
        border: Border.all(color: colors.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          bar(140, 18),
          for (final w in lines) ...[const SizedBox(height: Space.md), bar(w, 12)],
        ],
      ),
    );

    final placeholder = Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Container(
          height: 300,
          padding: const EdgeInsets.all(Space.xl),
          decoration: BoxDecoration(
            color: colors.subtle,
            borderRadius: Radii.xlAll,
            border: Border.all(color: colors.border),
          ),
          child: Column(
            children: [
              bar(180, 96, radius: 96),
              const SizedBox(height: Space.xl),
              bar(170, 28),
              const SizedBox(height: Space.sm),
              bar(100, 16),
              const Spacer(),
              bar(double.infinity, 56, radius: Radii.lg),
            ],
          ),
        ),
        const SizedBox(height: Space.cardGap),
        card([double.infinity, double.infinity, 200]),
        const SizedBox(height: Space.cardGap),
        card([double.infinity, 240]),
      ],
    );

    return Column(
      key: const Key('result-skeleton'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Semantics(
          liveRegion: true,
          container: true,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(widget.message, style: text.bodyLarge),
              SmoothSize(
                alignment: Alignment.topLeft,
                child: _showSlow
                    ? Padding(
                        padding: const EdgeInsets.only(top: Space.xs),
                        child: Text(
                          Strings.of(context).t('mobile.stillWorking'),
                          style: text.bodyMedium?.copyWith(color: colors.mutedForeground),
                        ),
                      )
                    : const SizedBox(width: double.infinity),
              ),
              // With "Remove animations" on, the moving bar is left out (the message says it all).
              if (motion.enabled) ...[
                const SizedBox(height: Space.md),
                const ClipRRect(borderRadius: Radii.pill, child: LinearProgressIndicator(minHeight: 6)),
              ],
            ],
          ),
        ),
        const SizedBox(height: Space.xl),
        ExcludeSemantics(
          child: AnimatedBuilder(
            animation: _shimmer,
            builder: (context, child) => ShaderMask(
              blendMode: BlendMode.srcATop,
              shaderCallback: (rect) {
                final t = _shimmer.value;
                final band = colors.subtle.withValues(alpha: motion.enabled ? 0.55 : 0);
                return LinearGradient(
                  begin: Alignment(-1.5 + 3 * t, -0.3),
                  end: Alignment(-0.5 + 3 * t, 0.3),
                  colors: [Colors.transparent, band, Colors.transparent],
                ).createShader(rect);
              },
              child: child,
            ),
            child: placeholder,
          ),
        ),
      ],
    );
  }
}
