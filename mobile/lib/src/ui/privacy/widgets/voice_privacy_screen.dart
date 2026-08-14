import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/audio/providers.dart';
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

class _Body extends ConsumerStatefulWidget {
  const _Body({required this.consent});

  final VoiceConsent consent;

  @override
  ConsumerState<_Body> createState() => _BodyState();
}

class _BodyState extends ConsumerState<_Body> {
  bool _togglePending = false;
  bool _exportPending = false;
  bool _erasePending = false;

  Future<void> _toggle(
    BuildContext context,
    String field,
    bool value,
  ) async {
    if (_togglePending) return;
    _togglePending = true;
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
    } finally {
      _togglePending = false;
    }
  }

  Future<void> _export(BuildContext context) async {
    if (_exportPending) return;
    _exportPending = true;
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
            'Aucun enregistrement audio n\'est conservé.\n\n'
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
    } finally {
      _exportPending = false;
    }
  }

  Future<void> _erase(BuildContext context) async {
    if (_erasePending) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Effacer mes données voix ?'),
        content: const Text(
          'Tes phrases dites, tes bilans, ton vocabulaire, tes révisions et tes '
          'enregistrements vocaux sur cet appareil seront supprimés. Ton compte '
          'est conservé. Irréversible.',
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
    _erasePending = true;
    try {
      // Erase BOTH sides: the on-device raw takes (they live ONLY here by design
      // #128, #219) AND the server-derived data. Local first — it is the most
      // private (raw audio). Success is claimed only if both succeed, so the
      // "erased" message is never a lie.
      await ref.read(voiceTakeStoreProvider).eraseAll();
      await ref.read(voicePrivacyRepositoryProvider).eraseData();
      // #382: eraseAll() wipes the on-device store, but voiceTakesProvider is
      // a plain (non-autoDispose) cache of the DECRYPTED bytes it already
      // read — without this, "Ma preuve" for a skill viewed before the erase
      // keeps replaying the supposedly-erased audio from that cache until an
      // app restart, making the success message below a lie. A .family
      // invalidate drops every cached skill, not just one.
      ref.invalidate(voiceTakesProvider);
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
    } finally {
      _erasePending = false;
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Text(
          'Ta voix t\'appartient. L\'audio est traité puis supprimé — jamais '
          'conservé. Tu contrôles le reste ci-dessous.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 12),
        SwitchListTile(
          key: const Key('consent_transcription'),
          title: const Text('Transcription serveur'),
          subtitle: const Text(
            'Meilleure reconnaissance de ton accent. Sinon, reconnaissance sur '
            'l\'appareil.',
          ),
          value: widget.consent.transcription,
          onChanged: _togglePending
              ? null
              : (v) => _toggle(context, 'transcription', v),
        ),
        SwitchListTile(
          key: const Key('consent_scoring'),
          title: const Text('Analyse de prononciation'),
          subtitle: const Text('Scores de prononciation (désactivé par défaut).'),
          value: widget.consent.scoring,
          onChanged: _togglePending
              ? null
              : (v) => _toggle(context, 'scoring', v),
        ),
        SwitchListTile(
          key: const Key('consent_b2b_share'),
          title: const Text('Partage avec mon école / employeur'),
          subtitle: const Text('Jamais sans ton choix explicite.'),
          value: widget.consent.b2bShare,
          onChanged: _togglePending
              ? null
              : (v) => _toggle(context, 'b2b_share', v),
        ),
        SwitchListTile(
          key: const Key('consent_model_training'),
          title: const Text('Amélioration des modèles'),
          subtitle: const Text('Utiliser mes données pour entraîner les modèles.'),
          value: widget.consent.modelTraining,
          onChanged: _togglePending
              ? null
              : (v) => _toggle(context, 'model_training', v),
        ),
        const Divider(height: 32),
        OutlinedButton.icon(
          key: const Key('export_voice_data'),
          icon: const Icon(Icons.download_outlined),
          label: const Text('Exporter mes données'),
          onPressed: _exportPending ? null : () => _export(context),
        ),
        const SizedBox(height: 8),
        TextButton.icon(
          key: const Key('erase_voice_data'),
          icon: const Icon(Icons.delete_outline),
          label: const Text('Effacer mes données voix'),
          style: TextButton.styleFrom(foregroundColor: Colors.red),
          onPressed: _erasePending ? null : () => _erase(context),
        ),
      ],
    );
  }
}
