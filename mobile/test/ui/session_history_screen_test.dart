import 'package:apm/src/data/models/session_summary.dart';
import 'package:apm/src/ui/history/view_model/session_history_view_model.dart';
import 'package:apm/src/ui/history/widgets/session_history_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('shows recent sessions', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          sessionHistoryProvider.overrideWith(
            (ref) async => [
              SessionSummary(
                id: 1,
                mode: 'scenario',
                startedAt: DateTime.utc(2026, 7, 1, 20),
                scenarioId: 'job_interview',
                durationMinutes: 4.5,
                cefrEstimate: 'A2',
              ),
            ],
          ),
        ],
        child: const MaterialApp(home: SessionHistoryScreen()),
      ),
    );

    await tester.pump();

    expect(find.byKey(const Key('session_1')), findsOneWidget);
    expect(find.text('Job Interview'), findsOneWidget);
    expect(find.text('A2'), findsOneWidget);
  });
}
