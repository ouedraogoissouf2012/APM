import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';
import '../design_system/atoms/app_button.dart';
import '../design_system/atoms/overline_text.dart';
import '../design_system/molecules/correction_chip.dart';
import '../design_system/molecules/transcript_text.dart';
import '../design_system/organisms/voice_orb.dart';

/// Galerie de développement — vitrine de chaque composant du design
/// system dans les deux thèmes. Accessible uniquement en debug via
/// `/dev/gallery`. Aucune logique métier ici : démonstration pure.
class GalleryPage extends StatelessWidget {
  const GalleryPage({super.key});

  @override
  Widget build(BuildContext context) {
    final colors = context.colors;
    return Scaffold(
      appBar: AppBar(title: const Text('Design system')),
      body: ListView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        children: [
          const _Section('Typographie'),
          Text('Good evening, Seven.',
              style: AppType.displayLg(colors.textPrimary)),
          const SizedBox(height: AppSpacing.sm),
          Text('82', style: AppType.displayXl(colors.textPrimary)),
          const SizedBox(height: AppSpacing.sm),
          Text('Un titre de carte', style: AppType.displayMd(colors.textPrimary)),
          const SizedBox(height: AppSpacing.sm),
          Text('Corps de texte fonctionnel en Inter, lisible et discret.',
              style: AppType.body(colors.textSecondary)),
          const SizedBox(height: AppSpacing.sm),
          const OverlineText('je t\'écoute'),
          const _Section('Orbe vocal'),
          const Wrap(
            spacing: AppSpacing.xl,
            runSpacing: AppSpacing.xl,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              _LabeledOrb('idle', VoiceOrbState.idle),
              _LabeledOrb('listening', VoiceOrbState.listening),
              _LabeledOrb('thinking', VoiceOrbState.thinking),
              _LabeledOrb('speaking', VoiceOrbState.speaking),
            ],
          ),
          const _Section('Transcription'),
          const TranscriptText('I have been working on my English…',
              listening: true),
          const _Section('Correction (l\'erreur est dorée)'),
          const Align(
            alignment: Alignment.centerLeft,
            child: CorrectionChip(
              original: 'I have 25 years',
              corrected: 'I am 25',
            ),
          ),
          const _Section('Boutons'),
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.md,
            children: [
              AppButton.primary(
                  label: 'Parler', icon: Icons.mic, onPressed: () {}),
              AppButton.outlined(label: 'Encore', onPressed: () {}),
              AppButton.ghost(label: 'Passer', onPressed: () {}),
              const AppButton.primary(label: 'Désactivé'),
            ],
          ),
          const _Section('Overlines de catégories'),
          Wrap(
            spacing: AppSpacing.lg,
            children: [
              const OverlineText('ton monde'),
              OverlineText('ton combat', color: colors.correction),
              OverlineText('ta victoire', color: colors.positive),
            ],
          ),
          const _Section('Inversion cream (mode bilan)'),
          _CreamPreview(),
          const SizedBox(height: AppSpacing.xxl),
        ],
      ),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section(this.title);

  final String title;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(
          top: AppSpacing.xxl, bottom: AppSpacing.md),
      child: OverlineText(title),
    );
  }
}

class _LabeledOrb extends StatelessWidget {
  const _LabeledOrb(this.label, this.state);

  final String label;
  final VoiceOrbState state;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        VoiceOrb(state: state, size: 110),
        const SizedBox(height: AppSpacing.sm),
        OverlineText(label),
      ],
    );
  }
}

/// Aperçu du thème clair : l'inversion narrative appliquée localement —
/// le mécanisme exact qu'utilisera l'écran bilan.
class _CreamPreview extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final light = AppTheme.light();
    return Theme(
      data: light,
      child: Builder(
        builder: (context) {
          final colors = context.colors;
          return Container(
            padding: const EdgeInsets.all(AppSpacing.xl),
            decoration: BoxDecoration(
              color: colors.background,
              borderRadius: BorderRadius.circular(AppRadius.hero),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                OverlineText('bilan de session',
                    color: colors.textMuted),
                const SizedBox(height: AppSpacing.md),
                Text('82', style: AppType.displayXl(colors.textPrimary)),
                const SizedBox(height: AppSpacing.xs),
                Text('+6 pts depuis mardi',
                    style: AppType.label(colors.accent)),
                const SizedBox(height: AppSpacing.lg),
                AppButton.primary(
                    label: 'Ajouter au carnet', onPressed: () {}),
              ],
            ),
          );
        },
      ),
    );
  }
}
