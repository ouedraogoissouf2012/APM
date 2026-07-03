import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../data/models/progress_snapshot.dart';
import '../../../data/models/session_summary.dart';
import '../view_model/progress_view_model.dart';

class SessionHistoryScreen extends ConsumerWidget {
  const SessionHistoryScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final async = ref.watch(progressProvider);
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
        data: (snapshot) {
          if (snapshot.isEmpty) {
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Text(
                  'No progress yet. Complete a conversation to see your CEFR trend, recent sessions, and recurring errors.',
                  key: Key('progress_empty'),
                  textAlign: TextAlign.center,
                ),
              ),
            );
          }
          return RefreshIndicator(
            onRefresh: () => ref.refresh(progressProvider.future),
            child: ListView.separated(
              padding: const EdgeInsets.all(12),
              itemCount: snapshot.sessions.length + 2,
              separatorBuilder: (_, _) => const SizedBox(height: 8),
              itemBuilder: (_, index) {
                if (index == 0) return _CefrTrendCard(snapshot: snapshot);
                if (index == 1) return _RecurringErrorsCard(snapshot: snapshot);
                return _SessionTile(session: snapshot.sessions[index - 2]);
              },
            ),
          );
        },
      ),
    );
  }
}

class _CefrTrendCard extends StatelessWidget {
  const _CefrTrendCard({required this.snapshot});

  final ProgressSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    final trend = snapshot.cefrTrend;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'CEFR progress',
              key: const Key('cefr_progress_title'),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 12),
            if (trend.isEmpty)
              const Text('Finish a debrief to start your CEFR trend.')
            else
              _CefrTrendLine(points: trend),
          ],
        ),
      ),
    );
  }
}

class _CefrTrendLine extends StatelessWidget {
  const _CefrTrendLine({required this.points});

  final List<CefrPoint> points;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    return SizedBox(
      height: 92,
      child: CustomPaint(
        painter: _CefrTrendPainter(
          points: points,
          color: theme.colorScheme.primary,
        ),
        child: Row(
          mainAxisAlignment: points.length == 1
              ? MainAxisAlignment.center
              : MainAxisAlignment.spaceBetween,
          children: [
            for (final point in points)
              Semantics(
                label: 'CEFR ${point.level}',
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    Container(
                      key: Key('cefr_point_${point.sessionId}'),
                      width: 36,
                      height: 36,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        color: theme.colorScheme.primaryContainer,
                        shape: BoxShape.circle,
                      ),
                      child: Text(
                        point.level,
                        style: theme.textTheme.labelMedium?.copyWith(
                          color: theme.colorScheme.onPrimaryContainer,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _CefrTrendPainter extends CustomPainter {
  const _CefrTrendPainter({required this.points, required this.color});

  final List<CefrPoint> points;
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    if (points.length < 2) return;

    final paint = Paint()
      ..color = color.withValues(alpha: 0.36)
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;
    final step = size.width / (points.length - 1);
    final path = Path();

    for (var index = 0; index < points.length; index++) {
      final offset = Offset(index * step, _levelY(points[index].level, size));
      if (index == 0) {
        path.moveTo(offset.dx, offset.dy);
      } else {
        path.lineTo(offset.dx, offset.dy);
      }
    }

    canvas.drawPath(path, paint);
  }

  double _levelY(String level, Size size) {
    const order = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'];
    final index = order.indexOf(level.toUpperCase());
    final normalized = index < 0 ? 0.0 : index / (order.length - 1);
    return 24 + (1 - normalized) * (size.height - 48);
  }

  @override
  bool shouldRepaint(covariant _CefrTrendPainter oldDelegate) =>
      oldDelegate.points != points || oldDelegate.color != color;
}

class _RecurringErrorsCard extends StatelessWidget {
  const _RecurringErrorsCard({required this.snapshot});

  final ProgressSnapshot snapshot;

  @override
  Widget build(BuildContext context) {
    final errors = snapshot.recurringErrors;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Recurring errors',
              key: const Key('recurring_errors_title'),
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 8),
            if (errors.isEmpty)
              const Text('No recurring errors found in recent debriefs.')
            else
              for (final error in errors)
                ListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  leading: const Icon(Icons.warning_amber_outlined),
                  title: Text('${error.errorType} (${error.count})'),
                  subtitle: Text(error.latestCorrection),
                ),
          ],
        ),
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
