/// Home: paste a message or pick a screenshot, plus the sample messages.
///
/// One obvious action: the form comes straight after a short title, with the check button
/// visible without scrolling. Problems with the input are shown right under the field and clear
/// as soon as the user types or switches mode.
library;

import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../config/limits.dart';
import '../generated/web_data.g.dart';
import '../i18n/strings.dart';
import '../state/app_scope.dart';
import '../state/controllers.dart';
import '../theme/app_theme.dart';
import '../theme/motion.dart';
import '../theme/tokens.dart';
import '../util/image_check.dart';
import '../util/text_utils.dart';
import '../widgets/display_options.dart';
import '../widgets/status_widgets.dart';
import '../widgets/ui.dart';
import 'about_screen.dart';
import 'results_screen.dart';

enum _Mode { text, image }

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final TextEditingController _text = TextEditingController();
  _Mode _mode = _Mode.text;
  Uint8List? _image;

  /// A problem with the input, shown under the field (empty text, unsupported image...).
  ErrorInfo? _inputError;

  @override
  void initState() {
    super.initState();
    _text.addListener(_onTextChanged);
  }

  /// The text when the listener last ran (the controller also notifies on selection and focus).
  String _lastText = '';

  /// Typing clears a stale "please paste a message first" (found on the phone). Only a real
  /// edit does: losing focus when the Check button is tapped must not hide the new error.
  void _onTextChanged() => setState(() {
    if (_text.text == _lastText) return;
    _lastText = _text.text;
    if (_inputError != null && _mode == _Mode.text) _inputError = null;
  });

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  void _open(AnalysisInput input) {
    final problem = validateInput(input);
    if (problem != null) {
      setState(() => _inputError = ErrorInfo(problem));
      return;
    }
    setState(() => _inputError = null);
    Navigator.of(context).push(ResultsScreen.route(input));
  }

  Future<void> _pickImage() async {
    final bytes = await AppScope.of(context).picker.pick();
    if (!mounted || bytes == null) return;
    final problem = validateImageBytes(bytes);
    setState(() {
      _inputError = problem == null ? null : ErrorInfo(problem);
      if (problem == null) _image = bytes;
    });
  }

  void _pickSample(TextSample sample) {
    setState(() {
      _mode = _Mode.text;
      _text.text = sample.text;
    });
    _open(TextAnalysis(sample.text));
  }

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final scope = AppScope.of(context);
    final colors = AppColors.of(context);
    final text = Theme.of(context).textTheme;
    final motion = Motion.of(context);
    final chars = charCount(_text.text);

    return Scaffold(
      appBar: AppBar(
        // Scales down instead of being cut off ("Scam Message Chec...") on 360 dp phones.
        title: FittedBox(fit: BoxFit.scaleDown, alignment: Alignment.centerLeft, child: Text(s.t('meta.title'))),
        actions: [
          IconButton(
            key: const Key('open-about'),
            tooltip: s.t('nav.about'),
            icon: const Icon(Icons.info_outline_rounded),
            onPressed: () => Navigator.of(context).push(AppPageRoute<void>(builder: (_) => const AboutScreen())),
          ),
          const DisplayOptionsButton(),
        ],
      ),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(Space.gutter, Space.xs, Space.gutter, Space.xxl),
          children: [
            Semantics(header: true, child: Text(s.t('hero.title'), style: text.headlineMedium)),
            const SizedBox(height: Space.xs),
            Text(s.t('hero.subtitle'), style: text.bodyLarge?.copyWith(color: colors.mutedForeground)),
            const SizedBox(height: Space.lg),
            ServerStatusBanner(status: scope.backend),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(Space.lg),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Semantics(header: true, child: Text(s.t('form.heading'), style: text.titleMedium)),
                    const SizedBox(height: Space.md),
                    SegmentedButton<_Mode>(
                      key: const Key('input-mode'),
                      showSelectedIcon: false,
                      segments: [
                        ButtonSegment(
                          value: _Mode.text,
                          icon: const Icon(Icons.notes_rounded),
                          label: Text(s.t('form.tabText')),
                        ),
                        ButtonSegment(
                          value: _Mode.image,
                          icon: const Icon(Icons.image_outlined),
                          label: Text(s.t('form.tabImage')),
                        ),
                      ],
                      selected: {_mode},
                      onSelectionChanged: (v) => setState(() {
                        _mode = v.first;
                        _inputError = null;
                      }),
                    ),
                    const SizedBox(height: Space.lg),
                    // Cross-fades only when the mode changes; while typing, the field grows
                    // directly (an animated size would briefly clip the button below it).
                    AnimatedSwitcher(
                      duration: motion.medium,
                      switchInCurve: motion.curve,
                      layoutBuilder: (current, previous) =>
                          Stack(alignment: Alignment.topCenter, children: [...previous, ?current]),
                      child: Column(
                        key: ValueKey(_mode),
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: _mode == _Mode.text ? _textInput(s, chars) : _imageInput(s),
                      ),
                    ),
                    const SizedBox(height: Space.md),
                    Text(s.t('form.privacyHint'), style: text.bodySmall?.copyWith(color: colors.mutedForeground)),
                  ],
                ),
              ),
            ),
            const SizedBox(height: Space.lg),
            // The three promises, compact.
            Wrap(
              spacing: Space.sm,
              runSpacing: Space.sm,
              children: [for (final point in s.list('hero.points')) _TrustChip(point)],
            ),
            const SizedBox(height: Space.xxl),
            Semantics(header: true, child: Text(s.t('samples.heading'), style: text.titleLarge)),
            const SizedBox(height: Space.xs),
            Text(s.t('mobile.samplesIntro'), style: text.bodyMedium?.copyWith(color: colors.mutedForeground)),
            const SizedBox(height: Space.md),
            Card(
              clipBehavior: Clip.antiAlias,
              child: Column(
                children: [
                  for (final (i, sample) in textSamples.indexed) ...[
                    if (i > 0) const Divider(indent: Space.lg, endIndent: Space.lg),
                    _SampleTile(sample: sample, onTap: () => _pickSample(sample)),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// The input error, right under the control it is about.
  List<Widget> _inlineError(Strings s) => [
    if (_inputError != null) ...[
      const SizedBox(height: Space.md),
      InlineNotice(
        key: ValueKey('input-error-${_inputError!.code}'),
        icon: errorIcon(_inputError!.code),
        message: s.errorMessage(_inputError!.code, retryAfterS: _inputError!.retryAfterS),
      ),
    ],
  ];

  List<Widget> _textInput(Strings s, int chars) {
    final tooLong = chars > maxTextChars;
    final colors = AppColors.of(context);
    return [
      TextField(
        key: const Key('message-input'),
        controller: _text,
        minLines: 5,
        maxLines: 10,
        keyboardType: TextInputType.multiline,
        decoration: InputDecoration(
          labelText: s.t('form.textLabel'),
          hintText: s.t('form.textPlaceholder'),
          alignLabelWithHint: true,
          helperText: s.t('form.charCount', {'n': chars, 'max': maxTextChars}),
          helperStyle: tooLong ? Theme.of(context).textTheme.bodySmall?.copyWith(color: colors.high.fg) : null,
        ),
      ),
      ..._inlineError(s),
      const SizedBox(height: Space.md),
      FilledButton.icon(
        key: const Key('submit-text'),
        onPressed: () => _open(TextAnalysis(_text.text)),
        icon: const Icon(Icons.manage_search_rounded),
        label: Text(s.t('form.submit')),
      ),
    ];
  }

  List<Widget> _imageInput(Strings s) {
    final image = _image;
    final colors = AppColors.of(context);
    final text = Theme.of(context).textTheme;
    if (image == null) {
      // Designed empty state: a dashed-feeling drop area that is itself the picker button.
      return [
        // Its own TalkBack node (container), not merged into the form card's text.
        Semantics(
          container: true,
          button: true,
          label: s.t('form.chooseFile'),
          excludeSemantics: true,
          child: Material(
            key: const Key('pick-image'),
            color: colors.subtle,
            shape: RoundedRectangleBorder(
              borderRadius: Radii.lgAll,
              side: BorderSide(color: colors.border, width: 1.5),
            ),
            child: InkWell(
              customBorder: const RoundedRectangleBorder(borderRadius: Radii.lgAll),
              onTap: _pickImage,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: Space.lg, vertical: Space.xl),
                child: Column(
                  children: [
                    IconBadge(
                      icon: Icons.add_photo_alternate_outlined,
                      background: Theme.of(context).colorScheme.primaryContainer,
                      foreground: Theme.of(context).colorScheme.onPrimaryContainer,
                      size: 52,
                    ),
                    const SizedBox(height: Space.md),
                    Text(
                      s.t('form.chooseFile'),
                      textAlign: TextAlign.center,
                      style: text.titleSmall?.copyWith(color: Theme.of(context).colorScheme.primary),
                    ),
                    const SizedBox(height: Space.xs),
                    Text(
                      s.t('mobile.pickHint'),
                      textAlign: TextAlign.center,
                      style: text.bodySmall?.copyWith(color: colors.mutedForeground),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
        ..._inlineError(s),
      ];
    }
    return [
      ClipRRect(
        borderRadius: Radii.mdAll,
        child: Container(
          color: colors.subtle,
          constraints: const BoxConstraints(maxHeight: 320),
          child: Image.memory(
            image,
            fit: BoxFit.contain,
            semanticLabel: s.t('form.previewAlt'),
            errorBuilder: (_, _, _) => const SizedBox(height: 80, child: Icon(Icons.broken_image_outlined)),
          ),
        ),
      ),
      const SizedBox(height: Space.sm),
      // A Wrap, so the two long labels go onto two lines on narrow phones instead of overflowing.
      Wrap(
        spacing: Space.sm,
        children: [
          TextButton.icon(
            onPressed: _pickImage,
            icon: const Icon(Icons.photo_library_outlined),
            label: Text(s.t('mobile.changeImage')),
          ),
          TextButton.icon(
            key: const Key('remove-image'),
            onPressed: () => setState(() => _image = null),
            icon: const Icon(Icons.close_rounded),
            label: Text(s.t('form.removeImage')),
          ),
        ],
      ),
      ..._inlineError(s),
      const SizedBox(height: Space.sm),
      FilledButton.icon(
        key: const Key('submit-image'),
        onPressed: () => _open(ImageAnalysis(image)),
        icon: const Icon(Icons.manage_search_rounded),
        label: Text(s.t('form.submitImage')),
      ),
    ];
  }
}

/// One of the three promises ("No message text is stored") as a small chip.
class _TrustChip extends StatelessWidget {
  const _TrustChip(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    final colors = AppColors.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: Space.md, vertical: Space.xs + 2),
      decoration: BoxDecoration(
        color: colors.low.bg,
        borderRadius: Radii.mdAll,
        border: Border.all(color: colors.low.border),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          ExcludeSemantics(
            child: Padding(
              padding: const EdgeInsets.only(top: 2),
              child: Icon(Icons.check_circle_outline_rounded, size: 16, color: colors.low.fg),
            ),
          ),
          const SizedBox(width: Space.xs + 2),
          Flexible(
            child: Text(label, style: Theme.of(context).textTheme.bodySmall?.copyWith(color: colors.low.fg)),
          ),
        ],
      ),
    );
  }
}

/// A sample message row: its title, and whether it was written as a scam or as safe.
class _SampleTile extends StatelessWidget {
  const _SampleTile({required this.sample, required this.onTap});

  final TextSample sample;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final s = Strings.of(context);
    final colors = AppColors.of(context);
    final tag = sample.expectedScam ? colors.high : colors.low;
    return ListTile(
      key: ValueKey('sample-${sample.id}'),
      shape: const RoundedRectangleBorder(),
      title: Text(s.t(sample.titleKey)),
      subtitle: Padding(
        padding: const EdgeInsets.only(top: Space.xs),
        child: Row(
          children: [
            ExcludeSemantics(
              child: Icon(
                sample.expectedScam ? Icons.report_outlined : Icons.verified_user_outlined,
                size: 16,
                color: tag.fg,
              ),
            ),
            const SizedBox(width: Space.xs + 2),
            Flexible(
              child: Text(
                s.t(sample.expectedScam ? 'samples.expectedScam' : 'samples.expectedSafe'),
                style: Theme.of(context).textTheme.bodySmall?.copyWith(color: tag.fg),
              ),
            ),
          ],
        ),
      ),
      trailing: ExcludeSemantics(child: Icon(Icons.chevron_right_rounded, color: colors.mutedForeground)),
      onTap: onTap,
    );
  }
}
