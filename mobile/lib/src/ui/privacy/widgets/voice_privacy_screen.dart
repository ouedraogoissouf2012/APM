import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../data/models/voice_consent.dart';
import '../view_model/voice_privacy_view_model.dart';

/// « Ma voix & confidentialité » (#128): the learner sees and controls what
/// happens to their voice — grant/revoke each consent, export their data, or
/// erase it. Honest by design: raw audio is never stored, and the screen says so.
class VoicePrivacyScreen extends ConsumerWidget {
  const VoicePrivacyScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(voiceConsentProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Ma voix & confidentialité')),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Text('Impossible de charger tes réglages.', key: Key('privacy_error')),
        ),
        data: (consent) => _Body(consent: consent),
      ),
    );
  }
}

class _Body extends ConsumerWidget {
  const _Body({required this.consent});

  final VoiceConsent consent;

  Future<void> _toggle(
    BuildContext context,
    WidgetRef ref,
    String field,
    bool value,
  ) async {
    try {
      await ref
          .read(voicePrivacyRepositoryProvider)
          .setConsent(field, value);
      ref.invalidate(voiceConsentProvider);
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Échec — réessaie')),
        );
      }
    }
  }

  Future<void> _export(BuildContext context, WidgetRef ref) async {
    try {
      final data = await ref.read(voicePrivacyRepositoryProvider).exportData();
      final utterances = (data['utterances'] as List?)?.length ?? 0;
      final vocabulary = (data['vocabulary'] as List?)?.length ?? 0;
      if (!context.mounted) return;
      showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Export de tes données voix'),
          content: Text(
            'Aucun enregistrement audio n’est conservé.\n\n'
            '$utterances phrase(s) dite(s) et $vocabulary mot(s) de vocabulaire '
            'sont associés à ton compte.',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text('OK'),
            ),
          ],
        ),
      );
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Export impossible — réessaie')),
        );
      }
    }
  }

  Future<void> _erase(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Effacer mes données voix ?'),
        content: const Text(
          'Tes phrases dites, tes bilans, ton vocabulaire et tes révisions '
          'seront supprimés. Ton compte est conservé. Irréversible.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Annuler'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Effacer'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await ref.read(voicePrivacyRepositoryProvider).eraseData();
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Tes données voix ont été effacées')),
        );
      }
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Effacement impossible — réessaie')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Ta voix t’appartient. L’audio est traité puis supprimé — jamais '
          'conservé. Tu contrôles le reste ci-dessous.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 12),
        SwitchListTile(
          key: const Key('consent_transcription'),
          title: const Text('Transcription serveur'),
          subtitle: const Text(
            'Meilleure reconnaissance de ton accent. Sinon, reconnaissance sur '
            'l’appareil.',
          ),
          value: consent.transcription,
          onChanged: (v) => _toggle(context, ref, 'transcription', v),
        ),
        SwitchListTile(
          key: const Key('consent_scoring'),
          title: const Text('Analyse de prononciation'),
          subtitle: const Text('Scores de prononciation (désactivé par défaut).'),
          value: consent.scoring,
          onChanged: (v) => _toggle(context, ref, 'scoring', v),
        ),
        SwitchListTile(
          key: const Key('consent_b2b_share'),
          title: const Text('Partage avec mon école / employeur'),
          subtitle: const Text('Jamais sans ton choix explicite.'),
          value: consent.b2bShare,
          onChanged: (v) => _toggle(context, ref, 'b2b_share', v),
        ),
        SwitchListTile(
          key: const Key('consent_model_training'),
          title: const Text('Amélioration des modèles'),
          subtitle: const Text('Utiliser mes données pour entraîner les modèles.'),
          value: consent.modelTraining,
          onChanged: (v) => _toggle(context, ref, 'model_training', v),
        ),
        const Divider(height: 32),
        OutlinedButton.icon(
          key: const Key('export_voice_data'),
          icon: const Icon(Icons.download_outlined),
          label: const Text('Exporter mes données'),
          onPressed: () => _export(context, ref),
        ),
        const SizedBox(height: 8),
        TextButton.icon(
          key: const Key('erase_voice_data'),
          icon: const Icon(Icons.delete_outline),
          label: const Text('Effacer mes données voix'),
          style: TextButton.styleFrom(foregroundColor: Colors.red),
          onPressed: () => _erase(context, ref),
        ),
      ],
    );
  }
}
