import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../../core/router/debounced_push.dart';
import '../../../core/router/routes.dart';
import '../../../data/models/scenarios.dart';
import '../../../data/models/session_modes.dart';

class ScenariosScreen extends StatelessWidget {
  const ScenariosScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Choose a scenario')),
      body: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          Card(
            key: const Key('new_mission'),
            child: ListTile(
              leading: const Text('🎯', style: TextStyle(fontSize: 28)),
              title: const Text('Mission sur mesure'),
              subtitle: const Text(
                'Répète ton vrai entretien, ta présentation, ton appel.',
              ),
              onTap: () => context.go(Routes.newMission),
            ),
          ),
          Card(
            key: const Key('free_conversation'),
            child: ListTile(
              leading: const Text('🗣️', style: TextStyle(fontSize: 28)),
              title: const Text('Free conversation'),
              subtitle: const Text('Talk about anything you like.'),
              onTap: () => context.go(Routes.conversationFree),
            ),
          ),
          const Divider(),
          for (final scenario in kScenarios)
            Card(
              key: Key('scenario_${scenario.id}'),
              child: ListTile(
                leading: Text(
                  scenario.emoji,
                  style: const TextStyle(fontSize: 28),
                ),
                title: Text(scenario.title),
                subtitle: Text(scenario.description),
                trailing: IconButton(
                  key: Key('proof_${scenario.id}'),
                  icon: const Icon(Icons.timeline),
                  tooltip: 'Ma preuve',
                  onPressed: () => context.debouncedPush(Routes.proof(scenario.id)),
                ),
                onTap: () => context.go(
                  Routes.conversationWith(
                    mode: kSessionModeScenario,
                    scenarioId: scenario.id,
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
