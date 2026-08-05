import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/progress_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  test('load fetches sessions + aggregated progress (no per-session N+1)', () async {
    final api = _MockApiClient();
    when(() => api.getList('/sessions')).thenAnswer(
      (_) async => [
        {
          'id': 2,
          'mode': 'scenario',
          'scenario_id': 'job_interview',
          'started_at': '2026-07-02T20:00:00Z',
          'duration_minutes': 6,
          'cefr_estimate': 'A2',
        },
        {
          'id': 1,
          'mode': 'free',
          'scenario_id': null,
          'started_at': '2026-07-01T20:00:00Z',
          'duration_minutes': 4,
          'cefr_estimate': 'A1',
        },
      ],
    );
    when(() => api.getJson('/me/progress')).thenAnswer(
      (_) async => {
        'cefr_trend': [
          {'session_id': 1, 'started_at': '2026-07-01T20:00:00Z', 'level': 'A1'},
          {'session_id': 2, 'started_at': '2026-07-02T20:00:00Z', 'level': 'A2'},
        ],
        'recurring_errors': [
          {'error_type': 'grammar', 'count': 2, 'latest_correction': 'He goes'},
          {'error_type': 'pronunciation', 'count': 1, 'latest_correction': 'sheep'},
        ],
      },
    );

    final snapshot = await ProgressRepository(api).load();

    expect(snapshot.sessions, hasLength(2));
    expect(snapshot.cefrTrend.map((p) => p.level), ['A1', 'A2']);
    expect(snapshot.recurringErrors.first.errorType, 'grammar');
    expect(snapshot.recurringErrors.first.count, 2);
    expect(snapshot.recurringErrors.first.latestCorrection, 'He goes');

    // The old per-session debrief fetch loop is gone: /me/progress is the source.
    verify(() => api.getJson('/me/progress')).called(1);
  });

  test('an empty backend snapshot yields empty trend and errors', () async {
    final api = _MockApiClient();
    when(() => api.getList('/sessions')).thenAnswer((_) async => []);
    when(() => api.getJson('/me/progress')).thenAnswer(
      (_) async => {'cefr_trend': <dynamic>[], 'recurring_errors': <dynamic>[]},
    );

    final snapshot = await ProgressRepository(api).load();

    expect(snapshot.isEmpty, isTrue);
    expect(snapshot.cefrTrend, isEmpty);
    expect(snapshot.recurringErrors, isEmpty);
  });
}
