import 'package:apm/src/data/models/progress_snapshot.dart';
import 'package:apm/src/data/models/session_summary.dart';
import 'package:apm/src/ui/history/view_model/progress_view_model.dart';
import 'package:apm/src/ui/history/widgets/session_history_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows CEFR progress, recurring errors, and recent sessions', (
    tester,
  ) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          progressProvider.overrideWith(
            (ref) async => ProgressSnapshot(
              sessions: [
                SessionSummary(
                  id: 1,
                  mode: 'scenario',
                  startedAt: DateTime.utc(2026, 7, 1, 20),
                  scenarioId: 'job_interview',
                  durationMinutes: 4.5,
                  cefrEstimate: 'A2',
                ),
              ],
              cefrTrend: [
                CefrPoint(
                  sessionId: 1,
                  startedAt: DateTime.utc(2026, 7, 1, 20),
                  level: 'A2',
                ),
              ],
              recurringErrors: const [
                RecurringError(
                  errorType: 'grammar',
                  count: 2,
                  latestCorrection: 'Use past simple',
                ),
              ],
            ),
          ),
        ],
        child: const MaterialApp(home: SessionHistoryScreen()),
      ),
    );

    await tester.pump();

    expect(find.byKey(const Key('cefr_progress_title')), findsOneWidget);
    expect(find.byKey(const Key('recurring_errors_title')), findsOneWidget);
    expect(find.byKey(const Key('cefr_point_1')), findsOneWidget);
    expect(find.text('grammar (2)'), findsOneWidget);
    expect(find.byKey(const Key('session_1')), findsOneWidget);
    expect(find.text('Job Interview'), findsOneWidget);
    expect(find.text('A2'), findsWidgets);
  });

  testWidgets('shows an empty progress state', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          progressProvider.overrideWith(
            (ref) async => const ProgressSnapshot(
              sessions: [],
              cefrTrend: [],
              recurringErrors: [],
            ),
          ),
        ],
        child: const MaterialApp(home: SessionHistoryScreen()),
      ),
    );

    await tester.pump();

    expect(find.byKey(const Key('progress_empty')), findsOneWidget);
  });
}
