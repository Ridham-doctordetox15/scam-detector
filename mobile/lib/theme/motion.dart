/// Motion that respects the phone's "Remove animations" setting.
///
/// Android reports that setting as `MediaQuery.disableAnimations`. Every animation in the app
/// takes its duration from [Motion], so one switch turns all of them off: widgets then jump
/// straight to their final state.
library;

import 'package:flutter/material.dart';

import 'tokens.dart';

@immutable
class Motion {
  const Motion({required this.enabled});

  /// Motion for this part of the tree.
  static Motion of(BuildContext context) => Motion(enabled: !MediaQuery.disableAnimationsOf(context));

  final bool enabled;

  Duration get short => enabled ? MotionTokens.short : Duration.zero;
  Duration get medium => enabled ? MotionTokens.medium : Duration.zero;
  Duration get long => enabled ? MotionTokens.long : Duration.zero;
  Duration get gauge => enabled ? MotionTokens.gauge : Duration.zero;

  /// Delay before the item at [index] of a staggered list starts to appear.
  Duration stagger(int index) => enabled ? MotionTokens.stagger * index : Duration.zero;

  Curve get curve => MotionTokens.emphasized;
}

/// Fades and lifts [child] in once, after [delay]. With animations off it is shown at once.
///
/// Used for the result cards appearing in order. It animates only on first build, so scrolling
/// or rebuilding never replays it.
class Entrance extends StatefulWidget {
  const Entrance({super.key, required this.child, this.index = 0});

  final Widget child;

  /// Position in a staggered list (0 = first).
  final int index;

  @override
  State<Entrance> createState() => _EntranceState();
}

class _EntranceState extends State<Entrance> with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(vsync: this);
  bool _started = false;
  late Animation<double> _curve = _controller;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_started) return;
    _started = true;
    final motion = Motion.of(context);
    if (!motion.enabled) {
      _controller.value = 1;
      return;
    }
    // One controller covers the stagger delay and the entrance (no timers), so it is driven
    // purely by frames and settles cleanly in tests.
    final delay = motion.stagger(widget.index);
    final total = delay + motion.long;
    _controller.duration = total;
    _curve = CurvedAnimation(
      parent: _controller,
      curve: Interval(delay.inMicroseconds / total.inMicroseconds, 1, curve: MotionTokens.emphasized),
    );
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final curved = _curve;
    return FadeTransition(
      opacity: curved,
      child: SlideTransition(
        position: Tween<Offset>(begin: const Offset(0, 0.04), end: Offset.zero).animate(curved),
        child: widget.child,
      ),
    );
  }
}

/// A Material page route that is instant when "Remove animations" is on. The transition itself
/// is already skipped then (app_theme.dart), and this also drops its timing, so the new screen
/// is fully there in the first frame.
class AppPageRoute<T> extends MaterialPageRoute<T> {
  AppPageRoute({required super.builder, super.settings});

  bool get _reduced {
    final context = navigator?.context;
    return context != null && (MediaQuery.maybeDisableAnimationsOf(context) ?? false);
  }

  @override
  Duration get transitionDuration => _reduced ? Duration.zero : super.transitionDuration;

  @override
  Duration get reverseTransitionDuration => _reduced ? Duration.zero : super.reverseTransitionDuration;
}

/// AnimatedSize that is a plain pass-through when animations are off (an AnimatedSize with a
/// zero duration trips a layout assertion in Flutter).
class SmoothSize extends StatelessWidget {
  const SmoothSize({super.key, required this.child, this.alignment = Alignment.topCenter});

  final Widget child;
  final AlignmentGeometry alignment;

  @override
  Widget build(BuildContext context) {
    final motion = Motion.of(context);
    if (!motion.enabled) return child;
    return AnimatedSize(duration: motion.medium, curve: motion.curve, alignment: alignment, child: child);
  }
}
