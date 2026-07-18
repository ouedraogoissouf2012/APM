import 'package:flutter/material.dart';

import '../../core/theme/app_theme.dart';
import 'voice_orb_parts.dart';

/// États de l'orbe vocal — DESIGN_SPEC §5.1.
enum VoiceOrbState {
  /// Anneaux arrêtés, cœur statique avec icône micro.
  idle,

  /// Tout animé : anneaux de propagation + waveform.
  listening,

  /// Waveform remplacée par 3 points pulsants.
  thinking,

  /// Waveform pilotée par l'amplitude TTS si disponible.
  speaking,
}

/// L'orbe vocal — LE composant signature de l'app (DESIGN_SPEC §5.1).
///
/// Du fond vers l'avant : 2 anneaux de propagation (bordure 1 px accent,
/// scale 0.92→1.18 + fade, 2400 ms, le 2ᵉ décalé de 1200 ms), disque
/// externe `surfaceAlt`, disque médian `surfaceHi`, cœur accent (~84/170)
/// contenant la waveform / l'icône micro / les points de réflexion.
///
/// Toute la géométrie est proportionnelle à [size] (référence 170).
/// Respecte `MediaQuery.disableAnimations` : rendu statique, aucune boucle.
class VoiceOrb extends StatefulWidget {
  const VoiceOrb({
    super.key,
    required this.state,
    this.size = 170,
    this.amplitude,
  });

  final VoiceOrbState state;

  /// Diamètre du disque externe (design de référence : 170).
  final double size;

  /// Amplitude TTS normalisée 0..1 (état [VoiceOrbState.speaking]).
  final double? amplitude;

  @override
  State<VoiceOrb> createState() => _VoiceOrbState();
}

class _VoiceOrbState extends State<VoiceOrb> with TickerProviderStateMixin {
  // Proportions du design de référence (base 170 — DESIGN_SPEC §5.1).
  static const _referenceSize = 170.0;
  static const _midFraction = 130 / _referenceSize;
  static const _coreFraction = 84 / _referenceSize;
  static const _ringMinScale = 0.92;
  static const _ringMaxScale = 1.18;
  static const _ringMaxOpacity = 0.9;
  static const _ringCount = 2;

  late final AnimationController _rings;
  late final AnimationController _wave;

  @override
  void initState() {
    super.initState();
    _rings = AnimationController(vsync: this, duration: AppMotion.orbRing);
    // Un aller-retour complet de barre = 2 × 1100 ms (montée + descente).
    _wave = AnimationController(vsync: this, duration: AppMotion.waveform * 2);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _syncAnimations();
  }

  @override
  void didUpdateWidget(VoiceOrb oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.state != widget.state) _syncAnimations();
  }

  void _syncAnimations() {
    final active = widget.state != VoiceOrbState.idle &&
        !MediaQuery.disableAnimationsOf(context);
    if (active) {
      if (!_rings.isAnimating) _rings.repeat();
      if (!_wave.isAnimating) _wave.repeat();
    } else {
      _rings.stop();
      _rings.value = 0;
      _wave.stop();
      _wave.value = 0;
    }
  }

  @override
  void dispose() {
    _rings.dispose();
    _wave.dispose();
    super.dispose();
  }

  bool get _showRings => widget.state != VoiceOrbState.idle;

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    final size = widget.size;

    return SizedBox(
      width: size,
      height: size,
      child: Stack(
        alignment: Alignment.center,
        clipBehavior: Clip.none,
        children: [
          if (_showRings)
            for (var i = 0; i < _ringCount; i++) _buildRing(i, colors),
          _disc(size, colors.surfaceAlt),
          _disc(size * _midFraction, colors.surfaceHi),
          _disc(size * _coreFraction, colors.accent, child: _coreContent()),
        ],
      ),
    );
  }

  /// Anneau de propagation [index] : phase décalée d'un demi-cycle par
  /// anneau (1200 ms sur 2400 ms), scale 0.92→1.18, fade 0.9→0, easeOut.
  Widget _buildRing(int index, AppSemanticColors colors) {
    return AnimatedBuilder(
      animation: _rings,
      builder: (_, _) {
        final t = (_rings.value + index / _ringCount) % 1.0;
        final eased = AppMotion.curveDefault.transform(t);
        final scale =
            _ringMinScale + (_ringMaxScale - _ringMinScale) * eased;
        return Transform.scale(
          scale: scale,
          child: Opacity(
            opacity: _ringMaxOpacity * (1 - eased),
            child: Container(
              key: Key('orb_ring_$index'),
              width: widget.size,
              height: widget.size,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                border: Border.all(
                  color: colors.accent,
                  width: AppStroke.hairline,
                ),
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _disc(double diameter, Color color, {Widget? child}) {
    return Container(
      width: diameter,
      height: diameter,
      decoration: BoxDecoration(shape: BoxShape.circle, color: color),
      child: child == null ? null : Center(child: child),
    );
  }

  Widget _coreContent() {
    final scale = widget.size / _referenceSize;
    return switch (widget.state) {
      VoiceOrbState.idle => Icon(
          Icons.mic,
          size: 28 * scale,
          color: context.colors.waveformBar,
        ),
      VoiceOrbState.listening ||
      VoiceOrbState.speaking =>
        OrbWaveform(
          animation: _wave,
          scale: scale,
          amplitude: widget.amplitude,
        ),
      VoiceOrbState.thinking => OrbThinkingDots(
          animation: _wave,
          scale: scale,
        ),
    };
  }
}
