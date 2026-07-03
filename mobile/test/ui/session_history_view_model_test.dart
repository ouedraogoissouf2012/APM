import 'package:apm/src/data/models/session_summary.dart';
import 'package:apm/src/data/repositories/session_history_repository.dart';
import 'package:apm/src/ui/history/view_model/session_history_view_model.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockSessionHistoryRepository extends Mock
    implements SessionHistoryRepository {}

void main() {
  test('sessionHistoryProvider loads recent sessions', () async {
    final repo = _MockSessionHistoryRepository();
    when(repo.listRecent).thenAnswer(
      (_) async => [
        SessionSummary(
          id: 1,
          mode: 'free',
          startedAt: DateTime.utc(2026, 7, 1, 20),
          scenarioId: null,
          durationMinutes: 3,
          cefrEstimate: null,
        ),
      ],
    );
    final c = ProviderContainer(
      overrides: [sessionHistoryRepositoryProvider.overrideWithValue(repo)],
    );
    addTearDown(c.dispose);

    final sessions = await c.read(sessionHistoryProvider.future);

    expect(sessions.single.id, 1);
    verify(repo.listRecent).called(1);
  });
}
