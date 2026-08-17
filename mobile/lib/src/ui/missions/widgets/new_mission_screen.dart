import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/routes.dart';
import '../../../core/ui/app_back_leading.dart';
import '../../../data/models/mission.dart';
import '../view_model/mission_view_model.dart';

/// « Nouvelle mission » — the learner pastes a real document (job offer, CV,
/// pitch, topic) or describes the upcoming call, and APM compiles a tailored
/// simulation. The brief is shown BEFORE launching so the learner sees exactly
/// what they will rehearse (issue #125).
class NewMissionScreen extends ConsumerStatefulWidget {
  const NewMissionScreen({super.key});

  @override
  ConsumerState<NewMissionScreen> createState() => _NewMissionScreenState();
}

class _NewMissionScreenState extends ConsumerState<NewMissionScreen> {
  final _content = TextEditingController();

  @override
  void dispose() {
    _content.dispose();
    super.dispose();
  }

  Future<void> _compile() async {
    final ok = await ref
        .read(missionViewModelProvider.notifier)
        .compile(_content.text);
    if (!mounted || ok) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Impossible de compiler — réessaie')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(missionViewModelProvider);
    final vm = ref.read(missionViewModelProvider.notifier);
    final compiling = state.status == MissionStatus.compiling;

    return Scaffold(
      appBar: AppBar(
        leading: const AppBackLeading(),
        title: const Text('Nouvelle mission'),
      ),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            'Colle ton offre d’emploi, ton CV, ton pitch, ou décris l’appel à '
            'venir. Je prépare une simulation sur mesure.',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          const SizedBox(height: 16),
          _SourceTypePicker(
            selected: state.sourceType,
            onSelected: vm.selectSourceType,
          ),
          const SizedBox(height: 12),
          TextField(
            key: const Key('mission_content'),
            controller: _content,
            maxLines: 8,
            minLines: 4,
            decoration: const InputDecoration(
              labelText: 'Ton texte',
              alignLabelWithHint: true,
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 16),
          FilledButton(
            key: const Key('compile_mission_button'),
            onPressed: compiling ? null : _compile,
            child: Text(compiling ? 'Je prépare…' : 'Préparer la simulation'),
          ),
          if (state.mission != null) ...[
            const SizedBox(height: 24),
            _MissionBrief(mission: state.mission!),
          ],
        ],
      ),
    );
  }
}

class _SourceTypePicker extends StatelessWidget {
  const _SourceTypePicker({required this.selected, required this.onSelected});

  final MissionSourceType selected;
  final ValueChanged<MissionSourceType> onSelected;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      children: [
        for (final type in MissionSourceType.values)
          ChoiceChip(
            key: Key('source_${type.wire}'),
            label: Text(type.label),
            selected: type == selected,
            onSelected: (_) => onSelected(type),
          ),
      ],
    );
  }
}

class _MissionBrief extends StatelessWidget {
  const _MissionBrief({required this.mission});

  final Mission mission;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      key: const Key('mission_brief'),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Ta simulation', style: theme.textTheme.titleMedium),
            const SizedBox(height: 8),
            _Field(label: 'Interlocuteur', value: mission.persona),
            const SizedBox(height: 6),
            _Field(label: 'Objectif', value: mission.goal),
            if (mission.likelyQuestions.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text('Questions probables', style: theme.textTheme.labelLarge),
              const SizedBox(height: 4),
              for (final q in mission.likelyQuestions)
                Padding(
                  padding: const EdgeInsets.only(bottom: 2),
                  child: Text('· $q', style: theme.textTheme.bodyMedium),
                ),
            ],
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                key: const Key('launch_mission_button'),
                icon: const Icon(Icons.mic),
                label: const Text('Commencer la simulation'),
                onPressed: () =>
                    context.go(Routes.conversationMission(mission.id)),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Field extends StatelessWidget {
  const _Field({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: theme.textTheme.labelSmall),
        Text(value, style: theme.textTheme.bodyLarge),
      ],
    );
  }
}
