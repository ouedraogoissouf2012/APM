import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/audio/providers.dart';
import '../../../core/observability/ref_report_error.dart';
import '../../../core/router/routes.dart';
import '../../../core/ui/app_back_leading.dart';
import '../../../data/models/proof.dart';
import '../../review/error_type_label.dart';
import '../view_model/proof_view_model.dart';

/// « Ma preuve » (#126): shows the FACTUAL progress on a skill between the
/// learner's first and latest session — the CEFR estimate then vs now and the
/// error types they resolved (honestly surfacing any regressions too). No
/// invented score; when there isn't enough history yet, it says so.
class ProofScreen extends ConsumerWidget {
  const ProofScreen({super.key, required this.skill});

  final String skill;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(proofProvider(skill));
    return Scaffold(
      appBar: AppBar(
        leading: const AppBackLeading(),
        title: const Text('Ma preuve'),
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Text(
            'Impossible de charger ta preuve.',
            key: Key('proof_error'),
          ),
        ),
        data: (proof) => proof == null
            ? _NotEnoughYet(skill: skill)
            : _ProofBody(proof: proof, skill: skill),
      ),
    );
  }
}

/// Compiles a surprise-transfer challenge for [skill] and launches it as a
/// mission conversation. Stateful for its own in-flight/disabled state.
class _TransferButton extends ConsumerStatefulWidget {
  const _TransferButton({required this.skill});

  final String skill;

  @override
  ConsumerState<_TransferButton> createState() => _TransferButtonState();
}

class _TransferButtonState extends ConsumerState<_TransferButton> {
  bool _loading = false;

  Future<void> _start() async {
    setState(() => _loading = true);
    try {
      final mission = await ref
          .read(proofRepositoryProvider)
          .transferChallenge(widget.skill);
      if (!mounted) return;
      context.go(Routes.conversationMission(mission.id));
    } catch (e, s) {
      if (!mounted) return;
      // (#351) An unexpected failure here would otherwise vanish silently —
      // report it so a recurring cause is visible instead of just a
      // "réessaie" snackbar with no trail.
      ref.reportError(
        e,
        s,
        context: '_TransferButtonState._start',
        data: {'skill': widget.skill},
      );
      setState(() => _loading = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Impossible de créer le défi — réessaie')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: double.infinity,
      child: FilledButton.icon(
        key: const Key('transfer_button'),
        icon: const Icon(Icons.bolt),
        label: Text(_loading ? 'Je prépare un défi…' : 'Tenter le transfert'),
        onPressed: _loading ? null : _start,
      ),
    );
  }
}

class _NotEnoughYet extends StatelessWidget {
  const _NotEnoughYet({required this.skill});

  final String skill;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.timeline, size: 48),
            const SizedBox(height: 12),
            const Text(
              'Ta preuve se construit',
              key: Key('proof_empty'),
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 4),
            Text(
              'Refais cette situation au moins une deuxième fois : je te montrerai '
              'ce que tu as concrètement amélioré, entre avant et maintenant.',
              style: Theme.of(context).textTheme.bodySmall,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 20),
            _TransferButton(skill: skill),
          ],
        ),
      ),
    );
  }
}

class _ProofBody extends StatelessWidget {
  const _ProofBody({required this.proof, required this.skill});

  final Proof proof;
  final String skill;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          key: const Key('proof_cefr'),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                  children: [
                    _Level(label: 'Avant', level: proof.baselineCefr),
                    const Icon(Icons.arrow_forward),
                    _Level(label: 'Maintenant', level: proof.latestCefr),
                  ],
                ),
                const SizedBox(height: 8),
                // Turn counts (#333): so a shorter session isn't read as progress —
                // the comparison above is per-turn, and this shows its basis.
                Text(
                  "D'après ${_turnsPhrase(proof.baselineTurns)} avant, "
                  '${_turnsPhrase(proof.latestTurns)} maintenant',
                  key: const Key('proof_turns'),
                  style: theme.textTheme.bodySmall,
                ),
                if (proof.baselineTurns > 0 &&
                    proof.latestTurns > 0 &&
                    proof.latestTurns < proof.baselineTurns) ...[
                  const SizedBox(height: 4),
                  Text(
                    'Séance plus courte : comparaison ramenée au même rythme '
                    '(par échange), pas au volume brut.',
                    key: const Key('proof_shorter_session_note'),
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.tertiary,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        // Audible before/after (#199): when two spoken takes exist for this skill,
        // let the learner HEAR the progress, not just read the CEFR delta.
        _AudibleProof(skill: skill),
        if (proof.resolved.isNotEmpty) ...[
          Text('Tu as corrigé', style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          for (final t in proof.resolved)
            _ErrorTile(
              errorType: t,
              keyPrefix: 'resolved',
              icon: Icons.check_circle,
              color: theme.colorScheme.primary,
            ),
        ] else
          Text(
            'Pas encore de faute résolue sur cette compétence — continue !',
            style: theme.textTheme.bodyMedium,
          ),
        if (proof.improved.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('En progrès', style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          for (final t in proof.improved)
            _ErrorTile(
              errorType: t,
              keyPrefix: 'improved',
              icon: Icons.trending_up,
              color: theme.colorScheme.primary,
              subtitle: 'Encore présente, mais moins souvent qu\'avant',
            ),
        ],
        if (proof.newOrWorse.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('À surveiller', style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          for (final t in proof.newOrWorse)
            _ErrorTile(
              errorType: t,
              keyPrefix: 'worse',
              icon: Icons.warning_amber,
              color: theme.colorScheme.tertiary,
            ),
        ],
        const Divider(height: 32),
        Text(
          'Vraie maîtrise : réussir la même compétence dans une situation '
          'inédite, sans préparation.',
          style: theme.textTheme.bodySmall,
        ),
        const SizedBox(height: 8),
        _TransferButton(skill: skill),
      ],
    );
  }
}

/// The audible before/after (#199): plays the learner's own first vs latest take
/// on this skill, back to back. Hidden until there are two takes to compare, so it
/// never shows an empty player. Takes live on-device only (#128).
class _AudibleProof extends ConsumerWidget {
  const _AudibleProof({required this.skill});

  final String skill;

  /// (#353) playBytes() was previously fire-and-forget: a decode/playback
  /// failure vanished as an unhandled Future rejection, and the button just
  /// looked dead. Lower priority than the network-backed cases elsewhere in
  /// this ticket (these bytes are already on-device, so failures should be
  /// rarer — decode errors, not network drops) but the same swallow-and-say-
  /// nothing pattern, so still worth surfacing.
  Future<void> _play(
    BuildContext context,
    WidgetRef ref,
    Uint8List bytes,
  ) async {
    try {
      await ref.read(audioPlaybackProvider).playBytes(bytes, 'audio/wav');
    } catch (e, s) {
      ref.reportError(
        e,
        s,
        context: '_AudibleProof._play',
        data: {'skill': skill},
      );
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Impossible de lire cet enregistrement'),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final takes = ref.watch(voiceTakesProvider(skill)).value;
    if (takes == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Card(
      key: const Key('audible_proof'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Écoute ton avant/après', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                OutlinedButton.icon(
                  key: const Key('play_baseline'),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Ta voix — avant'),
                  onPressed: () => _play(context, ref, takes.baseline),
                ),
                OutlinedButton.icon(
                  key: const Key('play_latest'),
                  icon: const Icon(Icons.play_arrow),
                  label: const Text('Ta voix — maintenant'),
                  onPressed: () => _play(context, ref, takes.latest),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// A learner-turn count for display. 0 means the count is unknown (no
/// transcript row, e.g. a session predating turn tracking) rather than a
/// genuinely empty session — the backend falls back to raw error counts in
/// that case (proof/service.py `_rate`), so mobile must not read it as a
/// literal zero either.
String _turnsPhrase(int turns) => turns > 0
    ? '$turns échange${turns > 1 ? 's' : ''}'
    : "un nombre d'échanges non disponible";

/// One error-type row, shared by the resolved/improved/regressed sections
/// (#333) so their identical ListTile shape lives in one place.
class _ErrorTile extends StatelessWidget {
  const _ErrorTile({
    required this.errorType,
    required this.keyPrefix,
    required this.icon,
    required this.color,
    this.subtitle,
  });

  final String errorType;
  final String keyPrefix;
  final IconData icon;
  final Color color;
  final String? subtitle;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      key: Key('${keyPrefix}_$errorType'),
      contentPadding: EdgeInsets.zero,
      leading: Icon(icon, color: color),
      title: Text(errorTypeLabel(errorType)),
      subtitle: subtitle == null ? null : Text(subtitle!),
    );
  }
}

class _Level extends StatelessWidget {
  const _Level({required this.label, required this.level});

  final String label;
  final String level;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      children: [
        Text(label, style: theme.textTheme.labelSmall),
        Text(level, style: theme.textTheme.headlineMedium),
      ],
    );
  }
}
