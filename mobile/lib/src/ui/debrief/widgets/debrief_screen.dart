import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../data/models/debrief.dart';
import '../view_model/debrief_view_model.dart';

class DebriefScreen extends ConsumerWidget {
  const DebriefScreen({super.key, required this.sessionId});

  final int sessionId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(debriefProvider(sessionId));
    return Scaffold(
      appBar: AppBar(
        title: const Text('Your debrief'),
        actions: [
          IconButton(
            key: const Key('debrief_home_button'),
            icon: const Icon(Icons.home),
            onPressed: () => context.go('/home'),
          ),
        ],
      ),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Padding(
            padding: EdgeInsets.all(24),
            child: Text(
              'Could not load your debrief.',
              key: Key('debrief_error'),
            ),
          ),
        ),
        data: (debrief) => _DebriefBody(debrief: debrief),
      ),
    );
  }
}

class _DebriefBody extends StatelessWidget {
  const _DebriefBody({required this.debrief});

  final Debrief debrief;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Card(
          child: ListTile(
            leading: const Icon(Icons.school),
            title: const Text('Estimated level'),
            trailing: Text(
              debrief.cefrEstimate,
              key: const Key('cefr_estimate'),
              style: Theme.of(context).textTheme.titleLarge,
            ),
          ),
        ),
        if (debrief.summary.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 12),
            child: Text(debrief.summary),
          ),
        const SizedBox(height: 8),
        Text(
          'Corrections (${debrief.errors.length})',
          style: Theme.of(context).textTheme.titleMedium,
        ),
        const SizedBox(height: 8),
        if (debrief.errors.isEmpty)
          const Text('No mistakes spotted — great job!')
        else
          ...debrief.errors.map(
            (e) => Card(
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      e.original,
                      style: const TextStyle(
                        decoration: TextDecoration.lineThrough,
                      ),
                    ),
                    Text(
                      e.correction,
                      style: TextStyle(
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(e.rule, style: Theme.of(context).textTheme.bodySmall),
                  ],
                ),
              ),
            ),
          ),
      ],
    );
  }
}
