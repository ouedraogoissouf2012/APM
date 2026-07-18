import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';

/// Éléments internes du [VoiceOrb] — ne pas utiliser hors du design system.

/// Waveform du cœur de l'orbe — DESIGN_SPEC §5.1.
///
/// 5 barres (couleur `waveformBar`), largeur 4, radius 3, hauteurs de
/// référence [20, 34, 26, 38, 18], scaleY 0.35→1.0 en boucle easeInOut
/// alternée, décalage de 150 ms par barre. Si [amplitude] est fournie
/// (voix TTS), elle module la hauteur des barres.
class OrbWaveform extends StatelessWidget {
  const OrbWaveform({
    super.key,
    required this.animation,
    required this.scale,
    this.amplitude,
  });

  /// Contrôleur partagé de l'orbe (période = un aller-retour complet).
  final Animation<double> animation;

  /// Facteur d'échelle global (size / 170).
  final double scale;

  /// Amplitude TTS normalisée 0..1 ; null = boucle autonome.
  final double? amplitude;

  // Design de référence (base 170).
  static const _heights = [20.0, 34.0, 26.0, 38.0, 18.0];
  static const _barWidth = 4.0;
  static const _barRadius = 3.0;
  static const _barGap = 4.0;
  static const _minScaleY = 0.35;
  static const _staggerFraction = 150 / 2200; // 150 ms sur un cycle complet

  double _scaleYFor(int index) {
    final phase = (animation.value + index * _staggerFraction) % 1.0;
    // Triangle : montée sur la 1re moitié du cycle, descente sur la 2de.
    final triangle = phase < 0.5 ? phase * 2 : 2 - phase * 2;
    final eased = AppMotion.curveLoop.transform(triangle);
    final level = amplitude?.clamp(0.2, 1.0) ?? 1.0;
    return (_minScaleY + (1 - _minScaleY) * eased) * level;
  }

  @override
  Widget build(BuildContext context) {
    final color = context.colors.waveformBar;
    return AnimatedBuilder(
      animation: animation,
      builder: (_, _) => Row(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          for (var i = 0; i < _heights.length; i++) ...[
            if (i > 0) SizedBox(width: _barGap * scale),
            Container(
              key: Key('orb_bar_$i'),
              width: _barWidth * scale,
              height: _heights[i] * scale * _scaleYFor(i),
              decoration: BoxDecoration(
                color: color,
                borderRadius: BorderRadius.circular(_barRadius * scale),
              ),
            ),
          ],
        ],
      ),
    );
  }
}

/// Trois points pulsants — état « réflexion » de l'orbe (DESIGN_SPEC §5.1).
class OrbThinkingDots extends StatelessWidget {
  const OrbThinkingDots({
    super.key,
    required this.animation,
    required this.scale,
  });

  final Animation<double> animation;
  final double scale;

  static const _dotCount = 3;
  static const _dotSize = 6.0;
  static const _dotGap = 5.0;
  static const _minOpacity = 0.3;
  static const _staggerFraction = 0.15;

  double _opacityFor(int index) {
    final phase = (animation.value + index * _staggerFraction) % 1.0;
    final triangle = phase < 0.5 ? phase * 2 : 2 - phase * 2;
    final eased = AppMotion.curveLoop.transform(triangle);
    return _minOpacity + (1 - _minOpacity) * eased;
  }

  @override
  Widget build(BuildContext context) {
    final color = context.colors.waveformBar;
    return AnimatedBuilder(
      animation: animation,
      builder: (_, _) => Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < _dotCount; i++) ...[
            if (i > 0) SizedBox(width: _dotGap * scale),
            Opacity(
              opacity: _opacityFor(i),
              child: Container(
                key: Key('orb_dot_$i'),
                width: _dotSize * scale,
                height: _dotSize * scale,
                decoration:
                    BoxDecoration(shape: BoxShape.circle, color: color),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
