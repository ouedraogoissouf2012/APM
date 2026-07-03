import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../scenarios.dart';

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
            key: const Key('free_conversation'),
            child: ListTile(
              leading: const Text('🗣️', style: TextStyle(fontSize: 28)),
              title: const Text('Free conversation'),
              subtitle: const Text('Talk about anything you like.'),
              onTap: () => context.go('/conversation?mode=free'),
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
                onTap: () => context.go(
                  '/conversation?mode=scenario&scenario=${scenario.id}',
                ),
              ),
            ),
        ],
      ),
    );
  }
}
