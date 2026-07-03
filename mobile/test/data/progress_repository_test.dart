import 'package:apm/src/core/network/api_exception.dart';
import 'package:apm/src/core/network/authenticated_api_client.dart';
import 'package:apm/src/data/repositories/progress_repository.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

class _MockApiClient extends Mock implements AuthenticatedApiClient {}

void main() {
  test(
    'load builds CEFR trend and recurring errors from recent debriefs',
    () async {
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
      when(() => api.getJson('/sessions/2/debrief')).thenAnswer(
        (_) async => {
          'cefr_estimate': 'A2',
          'summary': 'better',
          'errors': [
            {
              'original': 'I go yesterday',
              'correction': 'I went yesterday',
              'rule': 'Use past simple',
              'error_type': 'grammar',
            },
            {
              'original': 'ship',
              'correction': 'sheep',
              'rule': 'Long vowel',
              'error_type': 'pronunciation',
            },
          ],
        },
      );
      when(() => api.getJson('/sessions/1/debrief')).thenAnswer(
        (_) async => {
          'cefr_estimate': 'A1',
          'summary': 'start',
          'errors': [
            {
              'original': 'He go',
              'correction': 'He goes',
              'rule': 'Third person singular',
              'error_type': 'grammar',
            },
          ],
        },
      );

      final snapshot = await ProgressRepository(api).load();

      expect(snapshot.sessions, hasLength(2));
      expect(snapshot.cefrTrend.map((point) => point.level), ['A1', 'A2']);
      expect(snapshot.recurringErrors.first.errorType, 'grammar');
      expect(snapshot.recurringErrors.first.count, 2);
      expect(snapshot.recurringErrors.first.latestCorrection, 'He goes');
    },
  );

  test('load ignores sessions whose debrief is not generated yet', () async {
    final api = _MockApiClient();
    when(() => api.getList('/sessions')).thenAnswer(
      (_) async => [
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
    when(() => api.getJson('/sessions/1/debrief')).thenThrow(
      const ApiException(
        statusCode: 404,
        code: 'NotFoundError',
        message: 'missing',
      ),
    );

    final snapshot = await ProgressRepository(api).load();

    expect(snapshot.cefrTrend.single.level, 'A1');
    expect(snapshot.recurringErrors, isEmpty);
  });
}
