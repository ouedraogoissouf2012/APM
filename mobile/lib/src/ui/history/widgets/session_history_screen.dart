import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../data/models/session_summary.dart';
import '../view_model/session_history_view_model.dart';

class SessionHistoryScreen extends ConsumerWidget {
  const SessionHistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(sessionHistoryProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('History')),
      body: async.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, _) => const Center(
          child: Text(
            'Could not load your history.',
            key: Key('history_error'),
          ),
        ),
        data: (sessions) {
          if (sessions.isEmpty) {
            return const Center(child: Text('No sessions yet.'));
          }
          return RefreshIndicator(
            onRefresh: () => ref.refresh(sessionHistoryProvider.future),
            child: ListView.separated(
              padding: const EdgeInsets.all(12),
              itemCount: sessions.length,
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (_, index) => _SessionTile(session: sessions[index]),
            ),
          );
        },
      ),
    );
  }
}

class _SessionTile extends StatelessWidget {
  const _SessionTile({required this.session});

  final SessionSummary session;

  @override
  Widget build(BuildContext context) {
    final title = session.scenarioId == null
        ? 'Free conversation'
        : _scenarioTitle(session.scenarioId!);
    final duration = session.durationMinutes == null
        ? 'In progress'
        : '${session.durationMinutes!.toStringAsFixed(1)} min';

    return Card(
      child: ListTile(
        key: Key('session_${session.id}'),
        leading: const Icon(Icons.history),
        title: Text(title),
        subtitle: Text('${_formatDate(session.startedAt)} · $duration'),
        trailing: session.cefrEstimate == null
            ? null
            : Text(
                session.cefrEstimate!,
                style: Theme.of(context).textTheme.titleMedium,
              ),
        onTap: session.cefrEstimate == null
            ? null
            : () => context.go('/debrief/${session.id}'),
      ),
    );
  }
}

String _scenarioTitle(String id) => id
    .split('_')
    .map(
      (part) =>
          part.isEmpty ? part : '${part[0].toUpperCase()}${part.substring(1)}',
    )
    .join(' ');

String _formatDate(DateTime value) {
  final local = value.toLocal();
  final month = local.month.toString().padLeft(2, '0');
  final day = local.day.toString().padLeft(2, '0');
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  return '$day/$month ${hour}h$minute';
}
