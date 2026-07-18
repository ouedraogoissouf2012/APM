import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

/// Transcription de la voix de l'utilisateur — DESIGN_SPEC §5.3.
///
/// Fraunces italique light 19, entre guillemets français « », avec un
/// curseur clignotant (barre 2×15 clay, blink 1 s en steps) tant que
/// l'écoute est active. Curseur statique si les animations sont
/// désactivées (accessibilité).
class TranscriptText extends StatefulWidget {
  const TranscriptText(this.text, {super.key, required this.listening});

  final String text;

  /// Vrai pendant que le micro écoute : affiche le curseur clignotant.
  final bool listening;

  @override
  State<TranscriptText> createState() => _TranscriptTextState();
}

class _TranscriptTextState extends State<TranscriptText>
    with SingleTickerProviderStateMixin {
  // Géométrie du curseur (DESIGN_SPEC §5.3).
  static const _cursorWidth = 2.0;
  static const _cursorHeight = 15.0;

  late final AnimationController _blink;

  @override
  void initState() {
    super.initState();
    _blink = AnimationController(
      vsync: this,
      duration: AppMotion.cursorBlink,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _syncBlink();
  }

  @override
  void didUpdateWidget(TranscriptText oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.listening != widget.listening) _syncBlink();
  }

  void _syncBlink() {
    final animate =
        widget.listening && !MediaQuery.disableAnimationsOf(context);
    if (animate && !_blink.isAnimating) {
      _blink.repeat();
    } else if (!animate) {
      _blink.stop();
      _blink.value = 0; // curseur visible en statique
    }
  }

  @override
  void dispose() {
    _blink.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Flexible(
          child: Text(
            '« ${widget.text} »',
            key: const Key('transcript_text'),
            style: AppType.transcript(colors.textPrimary),
          ),
        ),
        if (widget.listening) ...[
          const SizedBox(width: AppSpacing.xs),
          AnimatedBuilder(
            key: const Key('transcript_cursor'),
            animation: _blink,
            builder: (_, _) => Opacity(
              key: const Key('transcript_cursor_opacity'),
              // Blink en steps (pas de fondu) : visible la 1re moitié.
              opacity: _blink.value < 0.5 ? 1.0 : 0.0,
              child: SizedBox(
                width: _cursorWidth,
                height: _cursorHeight,
                child: ColoredBox(color: colors.accent),
              ),
            ),
          ),
        ],
      ],
    );
  }
}
