import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
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
      appBar: AppBar(title: const Text('Ma preuve')),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Text('Impossible de charger ta preuve.', key: Key('proof_error')),
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
    } catch (_) {
      if (!mounted) return;
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
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: [
                _Level(label: 'Avant', level: proof.baselineCefr),
                const Icon(Icons.arrow_forward),
                _Level(label: 'Maintenant', level: proof.latestCefr),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        if (proof.resolved.isNotEmpty) ...[
          Text('Tu as corrigé', style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          for (final t in proof.resolved)
            ListTile(
              key: Key('resolved_$t'),
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.check_circle, color: theme.colorScheme.primary),
              title: Text(errorTypeLabel(t)),
            ),
        ] else
          Text(
            'Pas encore de faute résolue sur cette compétence — continue !',
            style: theme.textTheme.bodyMedium,
          ),
        if (proof.newOrWorse.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('À surveiller', style: theme.textTheme.titleMedium),
          const SizedBox(height: 6),
          for (final t in proof.newOrWorse)
            ListTile(
              key: Key('worse_$t'),
              contentPadding: EdgeInsets.zero,
              leading: Icon(Icons.warning_amber, color: theme.colorScheme.tertiary),
              title: Text(errorTypeLabel(t)),
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
