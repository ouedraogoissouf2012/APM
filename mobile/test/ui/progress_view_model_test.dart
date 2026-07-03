import 'package:apm/src/data/models/progress_snapshot.dart';
import 'package:apm/src/data/models/session_summary.dart';
import 'package:apm/src/data/repositories/progress_repository.dart';
import 'package:apm/src/ui/history/view_model/progress_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockProgressRepository extends Mock implements ProgressRepository {}

void main() {
  test('progressProvider loads the progress snapshot', () async {
    final repo = _MockProgressRepository();
    final snapshot = ProgressSnapshot(
      sessions: [
        SessionSummary(
          id: 1,
          mode: 'free',
          startedAt: DateTime.utc(2026, 7, 1, 20),
          scenarioId: null,
          durationMinutes: 3,
          cefrEstimate: 'A1',
        ),
      ],
      cefrTrend: [
        CefrPoint(
          sessionId: 1,
          startedAt: DateTime.utc(2026, 7, 1, 20),
          level: 'A1',
        ),
      ],
      recurringErrors: const [],
    );
    when(repo.load).thenAnswer((_) async => snapshot);
    final c = ProviderContainer(
      overrides: [progressRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(c.dispose);

    final result = await c.read(progressProvider.future);

    expect(result.sessions.single.id, 1);
    expect(result.cefrTrend.single.level, 'A1');
    verify(repo.load).called(1);
  });
}
