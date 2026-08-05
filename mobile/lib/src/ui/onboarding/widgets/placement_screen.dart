import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../view_model/placement_view_model.dart';

/// The ~60 s spoken placement shown right after registration. The learner speaks
/// a few short answers (level estimated server-side) and gives their interests
/// and goal (pre-fills the profile). Entirely skippable — a tap on "Passer" goes
/// straight to home and the account keeps its default level.
class PlacementScreen extends ConsumerStatefulWidget {
  const PlacementScreen({super.key});

  @override
  ConsumerState<PlacementScreen> createState() => _PlacementScreenState();
}

class _PlacementScreenState extends ConsumerState<PlacementScreen> {
  final _interests = TextEditingController();
  final _goal = TextEditingController();
  bool _answeredAll = false;

  @override
  void dispose() {
    _interests.dispose();
    _goal.dispose();
    super.dispose();
  }

  void _skip() => context.go(Routes.home);

  Future<void> _onMicTap(PlacementState state) async {
    final vm = ref.read(placementViewModelProvider.notifier);
    if (state.status == PlacementStatus.idle) {
      await vm.startRecording();
    } else if (state.status == PlacementStatus.recording) {
      final wasLast = state.isLastQuestion;
      await vm.stopAndTranscribe();
      if (wasLast && mounted) setState(() => _answeredAll = true);
    }
  }

  Future<void> _submit() async {
    final vm = ref.read(placementViewModelProvider.notifier);
    final ok = await vm.submit(
      interests: _interests.text
          .split(',')
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toList(),
      goal: _goal.text.trim(),
    );
    if (!mounted) return;
    if (ok) {
      context.go(Routes.home);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Impossible d’enregistrer — tu peux réessayer ou passer'),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(placementViewModelProvider);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Petit échauffement'),
        actions: [
          TextButton(
            key: const Key('placement_skip'),
            onPressed: _skip,
            child: const Text('Passer'),
          ),
        ],
      ),
      body: Padding(
        padding: const EdgeInsets.all(24),
        child: _answeredAll ? _finalStep(state) : _questionStep(state),
      ),
    );
  }

  Widget _questionStep(PlacementState state) {
    final recording = state.status == PlacementStatus.recording;
    final busy = state.status == PlacementStatus.transcribing;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          'Parle-moi un peu en anglais pour que j’ajuste ton niveau. '
          'Réponds à voix haute — pas de bonne ou mauvaise réponse.',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 8),
        Text(
          'Question ${state.questionIndex + 1} / ${kPlacementQuestions.length}',
          style: Theme.of(context).textTheme.labelMedium,
        ),
        const SizedBox(height: 24),
        Text(
          state.currentQuestion,
          key: const Key('placement_question'),
          style: Theme.of(context).textTheme.headlineSmall,
        ),
        const Spacer(),
        Center(
          child: FilledButton.icon(
            key: const Key('placement_mic'),
            onPressed: busy ? null : () => _onMicTap(state),
            icon: Icon(recording ? Icons.stop : Icons.mic),
            label: Text(
              busy
                  ? 'Je t’écoute…'
                  : recording
                  ? 'Terminer ma réponse'
                  : 'Parler',
            ),
          ),
        ),
        const SizedBox(height: 24),
      ],
    );
  }

  Widget _finalStep(PlacementState state) {
    final submitting = state.status == PlacementStatus.submitting;
    return ListView(
      children: [
        Text(
          'Deux dernières choses pour personnaliser tes conversations :',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 16),
        TextField(
          key: const Key('placement_interests'),
          controller: _interests,
          decoration: const InputDecoration(
            labelText: 'Tes centres d’intérêt (séparés par des virgules)',
            helperText: 'ex. football, cuisine, voyages',
          ),
        ),
        const SizedBox(height: 12),
        TextField(
          key: const Key('placement_goal'),
          controller: _goal,
          decoration: const InputDecoration(
            labelText: 'Ton objectif',
            helperText: 'ex. réussir un entretien d’embauche',
          ),
        ),
        const SizedBox(height: 24),
        FilledButton(
          key: const Key('placement_submit'),
          onPressed: submitting ? null : _submit,
          child: Text(submitting ? 'Un instant…' : 'C’est parti'),
        ),
      ],
    );
  }
}
