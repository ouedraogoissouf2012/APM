import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

/// Chip de correction doré — DESIGN_SPEC §5.2.
///
/// « L'erreur n'est jamais rouge. Elle est dorée — précieuse. »
/// Affiche : ✦ faute barrée → forme correcte, sur fond [correctionBg].
///
/// Principe de non-interruption : le chip apparaît (fade + slide-up
/// 250 ms) seulement [delay] après la fin de la phrase — jamais pendant
/// que l'utilisateur parle. Si `MediaQuery.disableAnimations` est actif,
/// l'apparition est immédiate (accessibilité).
class CorrectionChip extends StatefulWidget {
  const CorrectionChip({
    super.key,
    required this.original,
    required this.corrected,
    this.delay = AppMotion.chipDelay,
  });

  /// La formulation fautive de l'apprenant (sera barrée).
  final String original;

  /// La forme correcte.
  final String corrected;

  /// Délai avant apparition (400 ms par défaut — DESIGN_SPEC).
  final Duration delay;

  @override
  State<CorrectionChip> createState() => _CorrectionChipState();
}

class _CorrectionChipState extends State<CorrectionChip>
    with SingleTickerProviderStateMixin {
  // Géométrie propre au composant (DESIGN_SPEC §5.2).
  static const _padding = EdgeInsets.symmetric(vertical: 5, horizontal: 11);
  static const _iconSize = 14.0;
  static const _fontSize = 12.0;
  static const _slideFrom = Offset(0, 0.25);

  late final AnimationController _entrance;
  bool _scheduled = false;

  @override
  void initState() {
    super.initState();
    _entrance = AnimationController(
      vsync: this,
      duration: AppMotion.chipEntrance,
    );
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (_scheduled) return;
    _scheduled = true;
    if (MediaQuery.disableAnimationsOf(context)) {
      _entrance.value = 1;
    } else {
      Future<void>.delayed(widget.delay).then((_) {
        if (mounted) _entrance.forward();
      });
    }
  }

  @override
  void dispose() {
    _entrance.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final gold = colors.correction;

    return FadeTransition(
      key: const Key('correction_chip_fade'),
      opacity: _entrance.drive(CurveTween(curve: AppMotion.curveDefault)),
      child: SlideTransition(
        position: _entrance.drive(
          Tween(begin: _slideFrom, end: Offset.zero)
              .chain(CurveTween(curve: AppMotion.curveDefault)),
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: colors.correctionBg,
            borderRadius: BorderRadius.circular(AppRadius.chip),
            border: Border.all(
              color: colors.correctionBorder,
              width: AppStroke.hairline,
            ),
          ),
          child: Padding(
            padding: _padding,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.auto_awesome, size: _iconSize, color: gold),
                const SizedBox(width: AppSpacing.sm),
                Flexible(
                  child: Text.rich(
                    key: const Key('correction_chip_text'),
                    TextSpan(
                      style: AppType.label(gold)
                          .copyWith(fontSize: _fontSize),
                      children: [
                        TextSpan(
                          text: widget.original,
                          style: TextStyle(
                            color: gold.withValues(alpha: 0.6),
                            decoration: TextDecoration.lineThrough,
                            decorationColor: gold.withValues(alpha: 0.6),
                          ),
                        ),
                        const TextSpan(text: ' → '),
                        TextSpan(
                          text: widget.corrected,
                          style: TextStyle(color: gold),
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
