import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/session_history_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  test('listRecent fetches sessions and parses summaries', () async {
    final api = _MockApiClient();
    when(() => api.getList('/sessions')).thenAnswer(
      (_) async => [
        {
          'id': 1,
          'mode': 'scenario',
          'scenario_id': 'restaurant',
          'started_at': '2026-07-01T20:00:00Z',
          'duration_minutes': 4.5,
          'cefr_estimate': 'A2',
        },
      ],
    );
    final repo = SessionHistoryRepository(api);

    final sessions = await repo.listRecent();

    expect(sessions.single.id, 1);
    expect(sessions.single.scenarioId, 'restaurant');
    expect(sessions.single.durationMinutes, 4.5);
    expect(sessions.single.cefrEstimate, 'A2');
  });
}
