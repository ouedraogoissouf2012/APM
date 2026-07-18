import 'package:flutter/animation.dart';

/// Motion — contrat DESIGN_SPEC §7.
///
/// Micro-interactions 150–250 ms · transitions d'écran 300 ms ·
/// ambiance (orbe, anneaux) 1100–2400 ms en boucle.
/// `easeOut` par défaut, `easeInOut` pour les boucles.
/// Toujours respecter `MediaQuery.disableAnimations` (accessibilité).
abstract final class AppMotion {
  // Micro-interactions
  static const micro = Duration(milliseconds: 200);
  static const chipEntrance = Duration(milliseconds: 250);

  /// Délai avant l'apparition d'une correction : 400 ms APRÈS la fin de la
  /// phrase — jamais pendant que l'utilisateur parle (non-interruption).
  static const chipDelay = Duration(milliseconds: 400);

  // Transitions d'écran
  static const screen = Duration(milliseconds: 300);

  /// Conversation → Bilan : fade `ink` → `cream` (l'inversion doit se SENTIR).
  static const inversion = Duration(milliseconds: 450);

  // Ambiance (boucles)
  static const orbRing = Duration(milliseconds: 2400);
  static const orbRingOffset = Duration(milliseconds: 1200);
  static const waveform = Duration(milliseconds: 1100);
  static const waveformStagger = Duration(milliseconds: 150);
  static const cursorBlink = Duration(milliseconds: 1000);

  // Courbes
  static const curveDefault = Curves.easeOut;
  static const curveLoop = Curves.easeInOut;
}
