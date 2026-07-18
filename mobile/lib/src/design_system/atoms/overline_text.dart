import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

/// Overline — « JE T'ÉCOUTE », « MÉMOIRE », « TON COMBAT »…
///
/// Règle DESIGN_SPEC §3 appliquée par construction : les overlines sont
/// TOUJOURS en majuscules avec letter-spacing — le widget force
/// [String.toUpperCase], impossible de dévier depuis un écran.
class OverlineText extends StatelessWidget {
  const OverlineText(this.text, {super.key, this.color});

  final String text;

  /// Couleur du rôle : `textMuted` par défaut ; `correction` (gold) pour
  /// « TON COMBAT », `positive` pour « TA VICTOIRE », etc.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Text(
      text.toUpperCase(),
      style: AppType.overline(color ?? context.colors.textMuted),
    );
  }
}
