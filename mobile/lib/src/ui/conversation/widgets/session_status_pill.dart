import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';

/// Pill de statut de session — DESIGN_SPEC §6.1.
///
/// Dot vert « en direct » + sujet de la conversation + chrono écoulé.
/// Le chrono démarre quand [active] devient vrai et s'arrête proprement
/// (timer annulé au dispose — jamais de timer orphelin).
class SessionStatusPill extends StatefulWidget {
  const SessionStatusPill({
    super.key,
    required this.topic,
    required this.active,
  });

  /// Sujet affiché (titre du scénario ou « Conversation libre »).
  final String topic;

  /// Vrai quand une session est en cours (le chrono tourne).
  final bool active;

  @override
  State<SessionStatusPill> createState() => _SessionStatusPillState();
}

class _SessionStatusPillState extends State<SessionStatusPill> {
  static const _dotSize = 8.0;

  final _stopwatch = Stopwatch();
  Timer? _ticker;

  @override
  void initState() {
    super.initState();
    _syncTicker();
  }

  @override
  void didUpdateWidget(SessionStatusPill oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.active != widget.active) _syncTicker();
  }

  void _syncTicker() {
    if (widget.active) {
      _stopwatch.start();
      _ticker ??= Timer.periodic(
        const Duration(seconds: 1),
        (_) => setState(() {}),
      );
    } else {
      _stopwatch.stop();
      _ticker?.cancel();
      _ticker = null;
    }
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  String get _elapsed {
    final total = _stopwatch.elapsed.inSeconds;
    final minutes = total ~/ 60;
    final seconds = (total % 60).toString().padLeft(2, '0');
    return '$minutes:$seconds';
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: colors.surface,
        borderRadius: BorderRadius.circular(AppRadius.pill),
        border: Border.all(color: colors.border, width: AppStroke.hairline),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: _dotSize,
              height: _dotSize,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: widget.active ? colors.positive : colors.textFaint,
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Text(widget.topic, style: AppType.label(colors.textPrimary)),
            const SizedBox(width: AppSpacing.sm),
            Text(_elapsed, style: AppType.label(colors.textMuted)),
          ],
        ),
      ),
    );
  }
}
